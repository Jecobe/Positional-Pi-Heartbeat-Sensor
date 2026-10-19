import threading

from heartbeat_radar.events import Distance, HeartRate, Phases, Target, Targets
from heartbeat_radar.sources.simulator import SimulatedSource
from heartbeat_radar.state import SensorState, ViewConfig


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_vitals_attach_to_target_matching_distance():
    state = SensorState(clock=FakeClock())
    state.apply(Targets((Target(0.0, 0.8), Target(0.0, 3.0))))
    state.apply(Distance(2.9))
    people = state.snapshot()["people"]
    assert [p["vitals"] for p in people] == [False, True]


def test_vitals_default_to_nearest_without_distance():
    state = SensorState(clock=FakeClock())
    state.apply(Targets((Target(0.0, 3.0), Target(0.0, 0.8))))
    assert [p["vitals"] for p in state.snapshot()["people"]] == [False, True]


def test_out_of_range_heart_rate_is_hidden():
    state = SensorState(clock=FakeClock())
    state.apply(HeartRate(0.0))
    assert state.snapshot()["heart_rate"] is None
    state.apply(HeartRate(71.4))
    assert state.snapshot()["heart_rate"] == 71.4


def test_stale_values_expire():
    clock = FakeClock()
    state = SensorState(clock=clock, stale_after_s=3.0)
    state.apply(HeartRate(70.0))
    state.apply(Targets((Target(0.0, 1.0),)))
    clock.now += 5
    snap = state.snapshot()
    assert snap["heart_rate"] is None
    assert snap["people"] == []
    assert snap["status"]["receiving"] is False


def test_axis_transforms():
    state = SensorState(view=ViewConfig(swap_xy=True, flip_x=True), clock=FakeClock())
    state.apply(Targets((Target(1.0, 2.0),)))
    (person,) = state.snapshot()["people"]
    assert (person["x"], person["y"]) == (-2.0, 1.0)


def test_phases_are_drained_once():
    state = SensorState(clock=FakeClock())
    state.apply(Phases(0.0, 0.1, 0.2))
    assert state.drain_phases() == [(0.2, 0.1)]
    assert state.drain_phases() == []


def test_simulator_feeds_state_through_parser():
    state = SensorState(source="simulator")
    stop = threading.Event()
    thread = threading.Thread(target=SimulatedSource(people=2, seed=1).run, args=(state, stop))
    thread.start()
    try:
        stop.wait(1.3)
    finally:
        stop.set()
        thread.join()
    snap = state.snapshot()
    assert snap["status"]["ok"]
    assert snap["status"]["firmware"] == "2.1.0.7"
    assert len(snap["people"]) == 2
    assert 40 < snap["heart_rate"] < 120
    assert state.drain_phases()
