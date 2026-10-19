"""A fake MR60BHA2 so the UI can be developed and demoed without hardware.

It emits real encoded MR60BHA2 frames and runs them through the same parser as the
serial source, so the whole pipeline is exercised.
"""

from __future__ import annotations

import math
import random
import struct
import threading
import time

from ..events import Target
from ..state import SensorState
from .mr60bha2 import (
    TYPE_BREATH_RATE,
    TYPE_DISTANCE,
    TYPE_FIRMWARE,
    TYPE_HEART_BREATH_PHASE,
    TYPE_HEART_RATE,
    TYPE_HUMAN_DETECTION,
    FrameParser,
    decode_frame,
    encode_frame,
    encode_target_info,
)

TICK_S = 0.05


class _Person:
    def __init__(self, rng: random.Random, track_id: int, restless: bool) -> None:
        self.rng = rng
        self.track_id = track_id
        self.restless = restless
        self.x, self.y = self._spot()
        self.goal = self._spot()
        self.pause = rng.uniform(2, 8)
        self.resting_hr = rng.uniform(60, 75)
        self.heart_rate = self.resting_hr
        self.breath_rate = rng.uniform(12, 16)
        self.heart_phase = 0.0
        self.breath_phase = 0.0
        self.speed = 0.0

    def _spot(self) -> tuple[float, float]:
        depth = self.rng.uniform(0.6, 4.5 if self.restless else 1.4)
        angle = math.radians(self.rng.uniform(-45, 45))
        return depth * math.sin(angle), depth * math.cos(angle)

    def step(self, dt: float) -> None:
        dx, dy = self.goal[0] - self.x, self.goal[1] - self.y
        dist = math.hypot(dx, dy)
        if self.pause > 0:
            self.pause -= dt
            self.speed = 0.0
        elif dist < 0.05:
            self.goal = self._spot()
            self.pause = self.rng.uniform(4, 15) if not self.restless else self.rng.uniform(1, 4)
        else:
            walk = min(dist, (0.9 if self.restless else 0.35) * dt)
            self.x += dx / dist * walk
            self.y += dy / dist * walk
            self.speed = walk / dt * 100

        # Mean-reverting wander, a bit higher while walking.
        resting_hr = self.resting_hr + (15 if self.speed else 0)
        self.heart_rate += (resting_hr - self.heart_rate) * 0.08 * dt + self.rng.gauss(0, 0.6) * math.sqrt(dt)
        self.breath_rate += (14 - self.breath_rate) * 0.05 * dt + self.rng.gauss(0, 0.3) * math.sqrt(dt)
        self.heart_phase = (self.heart_phase + dt * self.heart_rate / 60) % 1
        self.breath_phase = (self.breath_phase + dt * self.breath_rate / 60) % 1

    def target(self) -> Target:
        jitter = self.rng.gauss
        return Target(self.x + jitter(0, 0.02), self.y + jitter(0, 0.02), self.speed, self.track_id)

    def heart_wave(self) -> float:
        p = self.heart_phase
        lub = math.exp(-((p - 0.10) ** 2) / 0.0012)
        dub = 0.55 * math.exp(-((p - 0.28) ** 2) / 0.0018)
        return lub + dub + self.rng.gauss(0, 0.03)

    def breath_wave(self) -> float:
        return math.sin(2 * math.pi * self.breath_phase)


class SimulatedSource:
    name = "simulator"

    def __init__(self, people: int = 1, seed: int | None = None) -> None:
        self.people = max(1, min(people, 3))
        self.seed = seed

    def run(self, state: SensorState, stop: threading.Event) -> None:
        rng = random.Random(self.seed)
        people = [_Person(rng, i, restless=i > 0) for i in range(self.people)]
        parser = FrameParser()
        state.set_status(True, "Simulated radar (no hardware)")
        last = time.monotonic()
        tick = 0
        wire = encode_frame(TYPE_FIRMWARE, bytes([2, 1, 0, 7]))
        while not stop.is_set():
            now = time.monotonic()
            dt, last = now - last, now
            for person in people:
                person.step(dt)
            subject = people[0]

            wire += encode_frame(
                TYPE_HEART_BREATH_PHASE,
                struct.pack("<fff", subject.heart_wave() + subject.breath_wave(), subject.breath_wave(), subject.heart_wave()),
            )
            if tick % 4 == 0:
                wire += encode_target_info([p.target() for p in people])
            if tick % 20 == 0:
                wire += encode_frame(TYPE_HEART_RATE, struct.pack("<f", subject.heart_rate))
                wire += encode_frame(TYPE_BREATH_RATE, struct.pack("<f", subject.breath_rate))
                wire += encode_frame(TYPE_DISTANCE, struct.pack("<If", 1, math.hypot(subject.x, subject.y)))
                wire += encode_frame(TYPE_HUMAN_DETECTION, b"\x01")

            for frame in parser.feed(wire):
                event = decode_frame(frame)
                if event is not None:
                    state.apply(event)
            wire = b""
            tick += 1
            stop.wait(TICK_S)
