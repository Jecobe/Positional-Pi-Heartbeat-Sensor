"""Radar data sources. Each runs in a background thread and feeds a SensorState."""

from __future__ import annotations

import threading
from typing import Protocol

from ..state import SensorState


class Source(Protocol):
    name: str

    def run(self, state: SensorState, stop: threading.Event) -> None:
        """Block, feeding events into ``state`` until ``stop`` is set."""
