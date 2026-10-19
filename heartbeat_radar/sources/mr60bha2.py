"""Seeed Studio MR60BHA2 60 GHz breathing/heartbeat radar protocol.

Frame layout (from Seeed's MIT-licensed Seeed-mmWave-library):

    SOF(0x01) | ID(2) | LEN(2) | TYPE(2) | HEAD_CKSUM(1) | DATA(LEN) | DATA_CKSUM(1)

Header fields are big-endian. Payload numbers are little-endian float32/uint32.
Each checksum is the bitwise NOT of the XOR of the bytes it covers.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..events import (
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

SOF = 0x01
HEADER_LEN = 8
MAX_DATA_LEN = 512
BAUD = 115200

TYPE_TARGET_INFO = 0x0A04
TYPE_POINT_CLOUD = 0x0A08
TYPE_HEART_BREATH_PHASE = 0x0A13
TYPE_BREATH_RATE = 0x0A14
TYPE_HEART_RATE = 0x0A15
TYPE_DISTANCE = 0x0A16
TYPE_HUMAN_DETECTION = 0x0F09
TYPE_FIRMWARE = 0xFFFF

TYPE_NAMES = {
    TYPE_TARGET_INFO: "target_info",
    TYPE_POINT_CLOUD: "point_cloud",
    TYPE_HEART_BREATH_PHASE: "phases",
    TYPE_BREATH_RATE: "breath_rate",
    TYPE_HEART_RATE: "heart_rate",
    TYPE_DISTANCE: "distance",
    TYPE_HUMAN_DETECTION: "human_detection",
    TYPE_FIRMWARE: "firmware",
}

# Doppler bin size; dop_index * RANGE_STEP gives speed in cm/s.
RANGE_STEP_CM_S = 17.28

_TARGET_STRUCT = struct.Struct("<ffii")


def checksum(data: bytes | bytearray | memoryview) -> int:
    value = 0
    for byte in data:
        value ^= byte
    return ~value & 0xFF


@dataclass(frozen=True)
class Frame:
    frame_id: int
    type: int
    data: bytes


def encode_frame(frame_type: int, data: bytes = b"", frame_id: int = 0) -> bytes:
    header = struct.pack(">BHHH", SOF, frame_id & 0xFFFF, len(data), frame_type)
    return header + bytes([checksum(header)]) + data + bytes([checksum(data)])


class FrameParser:
    """Incremental parser that resyncs on noise, truncation and bad checksums."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.bad_frames = 0

    def feed(self, chunk: bytes) -> list[Frame]:
        self._buf += chunk
        frames: list[Frame] = []
        buf = self._buf
        while True:
            start = buf.find(SOF)
            if start < 0:
                buf.clear()
                break
            if start:
                del buf[:start]
            if len(buf) < HEADER_LEN:
                break
            frame_id, length, frame_type = struct.unpack_from(">HHH", buf, 1)
            if checksum(buf[: HEADER_LEN - 1]) != buf[HEADER_LEN - 1] or length > MAX_DATA_LEN:
                self.bad_frames += 1
                del buf[0]
                continue
            total = HEADER_LEN + length + 1
            if len(buf) < total:
                break
            data = bytes(buf[HEADER_LEN : HEADER_LEN + length])
            if checksum(data) != buf[total - 1]:
                self.bad_frames += 1
                del buf[0]
                continue
            frames.append(Frame(frame_id, frame_type, data))
            del buf[:total]
        return frames


def _decode_targets(data: bytes) -> tuple[Target, ...]:
    (count,) = struct.unpack_from("<I", data)
    count = min(count, (len(data) - 4) // _TARGET_STRUCT.size)
    targets = []
    for i in range(count):
        x, y, dop_index, cluster_index = _TARGET_STRUCT.unpack_from(data, 4 + i * _TARGET_STRUCT.size)
        targets.append(Target(x=x, y=y, speed_cm_s=dop_index * RANGE_STEP_CM_S, track_id=cluster_index))
    return tuple(targets)


def _decode_distance(data: bytes) -> Distance:
    flag, meters = struct.unpack_from("<If", data)
    return Distance(meters if flag else None)


_DECODERS = {
    TYPE_HEART_RATE: lambda d: HeartRate(struct.unpack_from("<f", d)[0]),
    TYPE_BREATH_RATE: lambda d: BreathRate(struct.unpack_from("<f", d)[0]),
    TYPE_DISTANCE: _decode_distance,
    TYPE_HEART_BREATH_PHASE: lambda d: Phases(*struct.unpack_from("<fff", d)),
    TYPE_TARGET_INFO: lambda d: Targets(_decode_targets(d)),
    TYPE_HUMAN_DETECTION: lambda d: Presence(bool(d[0])),
    TYPE_FIRMWARE: lambda d: Firmware(".".join(str(b) for b in d[:4])),
}


def decode_frame(frame: Frame) -> Event | None:
    """Translate a frame into an event; None for unknown or malformed payloads."""
    decoder = _DECODERS.get(frame.type)
    if decoder is None:
        return None
    try:
        return decoder(frame.data)
    except (struct.error, IndexError):
        return None


def encode_target_info(targets: list[Target]) -> bytes:
    payload = struct.pack("<I", len(targets))
    for t in targets:
        payload += _TARGET_STRUCT.pack(t.x, t.y, round(t.speed_cm_s / RANGE_STEP_CM_S), t.track_id)
    return encode_frame(TYPE_TARGET_INFO, payload)
