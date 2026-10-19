"""Thread-safe latest-known sensor state, turned into JSON snapshots for the UI."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from .events import (
    BreathRate,
    Distance,
    Event,
    Firmware,
    HeartRate,
    Phases,
    Presence,
    Target,
    Targets,
)

# Readings outside these ranges are the radar saying "no lock", not real vitals.
HEART_RATE_RANGE = (30.0, 220.0)
BREATH_RATE_RANGE = (3.0, 60.0)


@dataclass
class ViewConfig:
    max_range_m: float = 6.0
    fov_deg: float = 120.0
    swap_xy: bool = False
    flip_x: bool = False
    flip_y: bool = False

    def transform(self, target: Target) -> tuple[float, float]:
        x, y = target.x, target.y
        if self.swap_xy:
            x, y = y, x
        if self.flip_x:
            x = -x
        if self.flip_y:
            y = -y
        return x, y


class SensorState:
    def __init__(
        self,
        view: ViewConfig | None = None,
        source: str = "unknown",
        stale_after_s: float = 3.0,
        clock=time.monotonic,
    ) -> None:
        self.view = view or ViewConfig()
        self.source = source
        self._stale_after = stale_after_s
        self._clock = clock
        self._lock = threading.Lock()
        self._values: dict[str, tuple[object, float]] = {}
        self._phases: deque[tuple[float, float]] = deque(maxlen=600)
        self._last_event_at: float | None = None
        self._status_ok = False
        self._status_message = "Starting…"
        self._firmware: str | None = None

    def set_status(self, ok: bool, message: str) -> None:
        with self._lock:
            self._status_ok = ok
            self._status_message = message

    def apply(self, event: Event) -> None:
        now = self._clock()
        with self._lock:
            self._last_event_at = now
            match event:
                case HeartRate(bpm=bpm):
                    self._values["heart_rate"] = (_in_range(bpm, HEART_RATE_RANGE), now)
                case BreathRate(per_minute=rate):
                    self._values["breath_rate"] = (_in_range(rate, BREATH_RATE_RANGE), now)
                case Distance(meters=meters):
                    self._values["distance"] = (meters, now)
                case Presence(present=present):
                    self._values["presence"] = (present, now)
                case Targets(targets=targets):
                    self._values["targets"] = (targets, now)
                case Phases(heart=heart, breath=breath):
                    self._phases.append((round(heart, 4), round(breath, 4)))
                case Firmware(version=version):
                    self._firmware = version

    def drain_phases(self) -> list[tuple[float, float]]:
        with self._lock:
            samples = list(self._phases)
            self._phases.clear()
        return samples

    def _fresh(self, key: str, now: float):
        value, at = self._values.get(key, (None, 0.0))
        return value if now - at <= self._stale_after else None

    def snapshot(self) -> dict:
        now = self._clock()
        with self._lock:
            heart_rate = self._fresh("heart_rate", now)
            breath_rate = self._fresh("breath_rate", now)
            distance = self._fresh("distance", now)
            presence = self._fresh("presence", now)
            targets: tuple[Target, ...] = self._fresh("targets", now) or ()
            receiving = self._last_event_at is not None and now - self._last_event_at <= self._stale_after
            status_ok, status_message = self._status_ok, self._status_message
            firmware = self._firmware

        vitals_index = _vitals_target(targets, distance)
        people = []
        for i, target in enumerate(targets):
            x, y = self.view.transform(target)
            people.append(
                {
                    "id": target.track_id,
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "speed_cm_s": round(target.speed_cm_s, 1),
                    "vitals": i == vitals_index,
                }
            )

        return {
            "type": "state",
            "source": self.source,
            "status": {
                "ok": status_ok and receiving,
                "receiving": receiving,
                "message": status_message,
                "firmware": firmware,
            },
            "heart_rate": _round(heart_rate),
            "breath_rate": _round(breath_rate),
            "distance_m": _round(distance, 2),
            "presence": presence if presence is not None else bool(people),
            "people": people,
            "view": {"max_range_m": self.view.max_range_m, "fov_deg": self.view.fov_deg},
        }

def _in_range(value: float, bounds: tuple[float, float]) -> float | None:
    if math.isnan(value) or not bounds[0] <= value <= bounds[1]:
        return None
    return value


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _vitals_target(targets: tuple[Target, ...], distance: float | None) -> int | None:
    """Guess which tracked person the heart rate belongs to.

    The radar reports one set of vitals plus the range it measured them at, so pick
    the target whose range best matches; without a range, the nearest person.
    """
    if not targets:
        return None
    ranges = [math.hypot(t.x, t.y) for t in targets]
    reference = distance if distance is not None else 0.0
    return min(range(len(targets)), key=lambda i: abs(ranges[i] - reference))
