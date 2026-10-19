"""Sensor-agnostic events emitted by every radar source.

Sources translate their wire format into these, so the state, server and UI never
need to know which radar is attached.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    """A tracked person, in meters relative to the sensor."""

    x: float  # sideways; + is to the sensor's right (before any axis flips)
    y: float  # depth; distance straight out from the sensor face
    speed_cm_s: float = 0.0
    track_id: int = 0


@dataclass(frozen=True)
class HeartRate:
    bpm: float


@dataclass(frozen=True)
class BreathRate:
    per_minute: float


@dataclass(frozen=True)
class Distance:
    """Distance to the person whose vitals are being measured; None when no lock."""

    meters: float | None


@dataclass(frozen=True)
class Phases:
    """Raw chest-motion phase samples; heart is used for the live waveform."""

    total: float
    breath: float
    heart: float


@dataclass(frozen=True)
class Targets:
    targets: tuple[Target, ...]


@dataclass(frozen=True)
class Presence:
    present: bool


@dataclass(frozen=True)
class Firmware:
    version: str


Event = HeartRate | BreathRate | Distance | Phases | Targets | Presence | Firmware
