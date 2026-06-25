import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hardware.motor import MockMotorController
from remote.server import RemoteControlHandler, create_server


def _get(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    return conn.getresponse()


def _post(port, path, data):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        path,
        body=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return conn.getresponse()


def test_map_html_and_api_enabled():
    provider = lambda: {"name": "map", "pose": {"x": 0, "y": 0, "yaw": 0}, "points": [], "waypoints": []}
    srv = create_server("127.0.0.1", 0, MockMotorController(), map_snapshot_provider=provider)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]
    try:
        resp = _get(port, "/map")
        assert resp.status == 200
        assert "text/html" in resp.getheader("Content-Type")
        assert "BJEA" in resp.read().decode("utf-8")

        resp = _get(port, "/api/map")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["name"] == "map"
    finally:
        srv.shutdown()
        RemoteControlHandler.cleanup()


def test_mapping_post_apis_enabled():
    provider = lambda: {"name": "map", "pose": {"x": 0, "y": 0, "yaw": 0}, "points": [], "waypoints": []}
    srv = create_server(
        "127.0.0.1",
        0,
        MockMotorController(),
        map_snapshot_provider=provider,
        snapshot_handler=lambda params: {"status": "ok", "name": params.get("name")},
        waypoint_handler=lambda params: {"status": "ok", "name": params.get("name")},
        save_handler=lambda params: {"status": "ok"},
        pose_handler=lambda params: {"status": "ok", "pose": params},
        accept_candidate_handler=lambda params: {"status": "ok", "rank": params.get("rank")},
        discard_snapshot_handler=lambda params: {"status": "ok", "discarded": True},
    )
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]
    try:
        assert json.loads(_post(port, "/api/snapshot", {"name": "A"}).read())["name"] == "A"
        assert json.loads(_post(port, "/api/waypoint", {"name": "W"}).read())["name"] == "W"
        assert json.loads(_post(port, "/api/save", {}).read())["status"] == "ok"
        assert json.loads(_post(port, "/api/pose", {"x": 1}).read())["pose"]["x"] == 1
        assert json.loads(_post(port, "/api/accept-candidate", {"rank": 2}).read())["rank"] == 2
        assert json.loads(_post(port, "/api/discard-snapshot", {}).read())["discarded"]
    finally:
        srv.shutdown()
        RemoteControlHandler.cleanup()
