import struct

import pytest

from heartbeat_radar.events import BreathRate, Distance, Firmware, HeartRate, Phases, Presence, Target, Targets
from heartbeat_radar.sources.mr60bha2 import (
    TYPE_BREATH_RATE,
    TYPE_DISTANCE,
    TYPE_FIRMWARE,
    TYPE_HEART_BREATH_PHASE,
    TYPE_HEART_RATE,
    TYPE_HUMAN_DETECTION,
    TYPE_TARGET_INFO,
    Frame,
    FrameParser,
    checksum,
    decode_frame,
    encode_frame,
    encode_target_info,
)


def test_checksum_is_inverted_xor():
    assert checksum(b"") == 0xFF
    assert checksum(bytes([0x01, 0x02])) == (~0x03) & 0xFF


def test_known_heart_rate_frame_bytes():
    # Built by hand from the documented layout, independent of encode_frame.
    header = bytes([0x01, 0x00, 0x05, 0x00, 0x04, 0x0A, 0x15])
    data = struct.pack("<f", 72.0)
    raw = header + bytes([checksum(header)]) + data + bytes([checksum(data)])
    assert encode_frame(TYPE_HEART_RATE, data, frame_id=5) == raw

    (frame,) = FrameParser().feed(raw)
    assert frame == Frame(5, TYPE_HEART_RATE, data)
    assert decode_frame(frame) == HeartRate(72.0)


@pytest.mark.parametrize(
    ("frame_type", "payload", "expected"),
    [
        (TYPE_BREATH_RATE, struct.pack("<f", 15.0), BreathRate(15.0)),
        (TYPE_DISTANCE, struct.pack("<If", 1, 1.25), Distance(1.25)),
        (TYPE_DISTANCE, struct.pack("<If", 0, 1.25), Distance(None)),
        (TYPE_HEART_BREATH_PHASE, struct.pack("<fff", 1.0, 0.5, 0.25), Phases(1.0, 0.5, 0.25)),
        (TYPE_HUMAN_DETECTION, b"\x01", Presence(True)),
        (TYPE_HUMAN_DETECTION, b"\x00", Presence(False)),
        (TYPE_FIRMWARE, bytes([2, 1, 0, 7]), Firmware("2.1.0.7")),
    ],
)
def test_decode_payloads(frame_type, payload, expected):
    (frame,) = FrameParser().feed(encode_frame(frame_type, payload))
    assert decode_frame(frame) == expected


def test_target_info_round_trip():
    targets = [Target(0.5, 1.5, 17.28 * 2, 3), Target(-1.0, 2.0, 0.0, 4)]
    (frame,) = FrameParser().feed(encode_target_info(targets))
    assert frame.type == TYPE_TARGET_INFO
    assert decode_frame(frame) == Targets(tuple(targets))


def test_target_count_larger_than_payload_is_clamped():
    payload = struct.pack("<I", 5) + struct.pack("<ffii", 1.0, 2.0, 0, 1)
    (frame,) = FrameParser().feed(encode_frame(TYPE_TARGET_INFO, payload))
    assert decode_frame(frame) == Targets((Target(1.0, 2.0, 0.0, 1),))


def test_truncated_payload_decodes_to_none():
    (frame,) = FrameParser().feed(encode_frame(TYPE_HEART_RATE, b"\x00\x01"))
    assert decode_frame(frame) is None


def test_unknown_type_decodes_to_none():
    (frame,) = FrameParser().feed(encode_frame(0x1234, b"\x00"))
    assert decode_frame(frame) is None


def test_parser_handles_byte_at_a_time_and_noise():
    stream = (
        b"\xaa\x01\x55garbage"
        + encode_frame(TYPE_HEART_RATE, struct.pack("<f", 60.0))
        + b"\x01\x02"
        + encode_frame(TYPE_BREATH_RATE, struct.pack("<f", 12.0))
    )
    parser = FrameParser()
    frames = []
    for byte in stream:
        frames += parser.feed(bytes([byte]))
    assert [decode_frame(f) for f in frames] == [HeartRate(60.0), BreathRate(12.0)]


def test_corrupt_data_checksum_is_skipped_and_parser_recovers():
    bad = bytearray(encode_frame(TYPE_HEART_RATE, struct.pack("<f", 60.0)))
    bad[-1] ^= 0xFF
    good = encode_frame(TYPE_HEART_RATE, struct.pack("<f", 61.0))
    parser = FrameParser()
    frames = parser.feed(bytes(bad) + good)
    assert [decode_frame(f) for f in frames] == [HeartRate(61.0)]
    assert parser.bad_frames >= 1
