"""Command line entry point: ``heartbeat-radar serve`` or ``heartbeat-radar dump``."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging")

    parser = argparse.ArgumentParser(
        prog="heartbeat-radar", description="Positional Pi Heartbeat Sensor: mmWave radar web UI."
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", parents=[common], help="run the web UI (default)")
    serve.add_argument("--source", choices=["mr60bha2", "sim"], default="mr60bha2")
    serve.add_argument("--port", default="auto", help="serial port, e.g. /dev/ttyACM0 (default: auto-detect)")
    serve.add_argument("--host", default="0.0.0.0", help="address to listen on (default: all interfaces)")
    serve.add_argument("--http-port", type=int, default=8000)
    serve.add_argument("--sim-people", type=int, default=2, help="people to simulate, 1-3 (sim source only)")
    serve.add_argument("--max-range", type=float, default=6.0, help="meters shown on the map")
    serve.add_argument("--fov", type=float, default=120.0, help="sensor field of view drawn on the map, degrees")
    serve.add_argument("--swap-xy", action="store_true", help="swap the radar's x and y axes")
    serve.add_argument("--flip-x", action="store_true", help="mirror left/right")
    serve.add_argument("--flip-y", action="store_true", help="mirror toward/away")

    dump = sub.add_parser("dump", parents=[common], help="print decoded radar frames (hardware bring-up)")
    dump.add_argument("--port", default="auto")
    dump.add_argument("--raw", action="store_true", help="also print every frame as hex")

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"serve", "dump", "-h", "--help", "--version"}:
        argv.insert(0, "serve")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "dump":
        return _dump(args)
    return _serve(args)


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app
    from .state import SensorState, ViewConfig

    if args.source == "sim":
        from .sources.simulator import SimulatedSource

        source = SimulatedSource(people=args.sim_people)
    else:
        from .sources.serial_source import MR60BHA2SerialSource

        source = MR60BHA2SerialSource(port=args.port)

    view = ViewConfig(
        max_range_m=args.max_range,
        fov_deg=args.fov,
        swap_xy=args.swap_xy,
        flip_x=args.flip_x,
        flip_y=args.flip_y,
    )
    app = create_app(source, SensorState(view=view, source=source.name))
    uvicorn.run(app, host=args.host, port=args.http_port, log_level="info")
    return 0


def _dump(args: argparse.Namespace) -> int:
    import serial

    from .sources.mr60bha2 import BAUD, TYPE_NAMES, FrameParser, decode_frame
    from .sources.serial_source import find_radar_port

    port = find_radar_port() if args.port == "auto" else args.port
    if port is None:
        print("No radar serial port found. Pass --port /dev/ttyACM0 (or similar).", file=sys.stderr)
        return 1
    print(f"Reading {port} at {BAUD} baud. Ctrl+C to stop.")
    parser = FrameParser()
    start = time.monotonic()
    try:
        with serial.Serial(port, BAUD, timeout=0.2) as conn:
            while True:
                for frame in parser.feed(conn.read(conn.in_waiting or 1)):
                    name = TYPE_NAMES.get(frame.type, "unknown")
                    line = f"{time.monotonic() - start:8.2f}s 0x{frame.type:04X} {name:<15} {decode_frame(frame)}"
                    if args.raw or name == "unknown":
                        line += f"  data={frame.data.hex(' ')}"
                    print(line, flush=True)
    except KeyboardInterrupt:
        print(f"\nBad/corrupt frames skipped: {parser.bad_frames}")
    except serial.SerialException as exc:
        print(f"Serial error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
