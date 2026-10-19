"""Reads an MR60BHA2 over USB serial (via the XIAO ESP32C6 bridge firmware)."""

from __future__ import annotations

import logging
import threading

import serial
from serial.tools import list_ports

from ..state import SensorState
from .mr60bha2 import BAUD, FrameParser, decode_frame

log = logging.getLogger(__name__)

ESPRESSIF_USB_VID = 0x303A
RETRY_DELAY_S = 2.0


def find_radar_port() -> str | None:
    """Pick the XIAO ESP32C6 (Espressif USB VID), falling back to any USB serial port."""
    ports = list(list_ports.comports())
    for port in ports:
        if port.vid == ESPRESSIF_USB_VID:
            return port.device
    for port in ports:
        if port.device.startswith(("/dev/ttyACM", "/dev/ttyUSB")):
            return port.device
    return None


class MR60BHA2SerialSource:
    name = "mr60bha2"

    def __init__(self, port: str = "auto") -> None:
        self.port = port

    def run(self, state: SensorState, stop: threading.Event) -> None:
        while not stop.is_set():
            port = find_radar_port() if self.port == "auto" else self.port
            if port is None:
                state.set_status(False, "No radar found. Is the XIAO plugged in over USB?")
                stop.wait(RETRY_DELAY_S)
                continue
            try:
                self._read_port(port, state, stop)
            except serial.SerialException as exc:
                log.warning("Serial error on %s: %s", port, exc)
                state.set_status(False, f"{port}: {exc}")
                stop.wait(RETRY_DELAY_S)

    def _read_port(self, port: str, state: SensorState, stop: threading.Event) -> None:
        parser = FrameParser()
        with serial.Serial(port, BAUD, timeout=0.2) as conn:
            log.info("Reading MR60BHA2 on %s", port)
            state.set_status(True, f"Connected on {port}")
            while not stop.is_set():
                chunk = conn.read(conn.in_waiting or 1)
                for frame in parser.feed(chunk):
                    event = decode_frame(frame)
                    if event is not None:
                        state.apply(event)
