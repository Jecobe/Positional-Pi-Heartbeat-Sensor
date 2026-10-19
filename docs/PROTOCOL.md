# MR60BHA2 serial protocol notes

These notes come from Seeed's MIT-licensed
[Seeed-mmWave-library](https://github.com/Love4yzp/Seeed-mmWave-library)
(`src/SeeedmmWave.cpp`, `src/SEEED_MR60BHA2.cpp`). The decoder is in
`heartbeat_radar/sources/mr60bha2.py`.

UART: 115200 baud, 8N1.

## Frame

| Field | Bytes | Notes |
|---|---|---|
| SOF | 1 | always `0x01` |
| ID | 2 | big-endian frame counter |
| LEN | 2 | big-endian payload length |
| TYPE | 2 | big-endian frame type |
| HEAD_CKSUM | 1 | `~(XOR of the 7 bytes before it)` |
| DATA | LEN | little-endian values |
| DATA_CKSUM | 1 | `~(XOR of DATA)` |

## Frame types

| Type | Name | Payload |
|---|---|---|
| `0x0A04` | Target info | `u32 count`, then `count` × (`f32 x`, `f32 y`, `i32 dop_index`, `i32 cluster_index`); x and y in meters; speed in cm/s = `dop_index × 17.28` |
| `0x0A08` | Point cloud | same layout as target info (not used by the UI) |
| `0x0A13` | Heart/breath phase | `f32 total`, `f32 breath`, `f32 heart` |
| `0x0A14` | Breath rate | `f32` breaths per minute |
| `0x0A15` | Heart rate | `f32` beats per minute |
| `0x0A16` | Distance | `u32 valid flag`, `f32 meters` |
| `0x0F09` | Human detected | `u8` 0 or 1 |
| `0xFFFF` | Firmware | 4 bytes: project, major, sub, modified |

Run `heartbeat-radar dump --raw` to see every frame as hex. It's useful for
checking these notes against a real sensor or adding new frame types.
