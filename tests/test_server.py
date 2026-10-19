from fastapi.testclient import TestClient

from heartbeat_radar.server import create_app
from heartbeat_radar.sources.simulator import SimulatedSource
from heartbeat_radar.state import SensorState


def test_serves_ui_and_streams_state():
    app = create_app(SimulatedSource(seed=2), SensorState(source="simulator"))
    with TestClient(app) as client:
        assert "Heartbeat Radar" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/api/state").json()["type"] == "state"
        with client.websocket_connect("/ws") as ws:
            first = ws.receive_json()
            assert first["source"] == "simulator"
            streamed = ws.receive_json()
            assert "heart_wave" in streamed
