"""测试遥控模式 HTTP 服务器。

使用 MockMotorController + 随机端口，不与实际硬件交互。
"""

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from hardware.motor import MockMotorController
from remote.server import RemoteControlHandler, create_server


@pytest.fixture
def motor():
    return MockMotorController()


@pytest.fixture
def server(motor):
    """在随机端口启动 HTTP 服务器。"""
    srv = create_server("127.0.0.1", 0, motor)  # port=0 → OS 分配
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    RemoteControlHandler.cleanup()


@pytest.fixture
def port(server):
    return server.server_address[1]


def _get(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    return conn.getresponse()


class TestRemoteServer:
    """HTTP 服务器功能测试。"""

    def test_serves_html(self, port):
        resp = _get(port, "/")
        assert resp.status == 200
        content_type = resp.getheader("Content-Type")
        assert "text/html" in content_type
        body = resp.read().decode("utf-8")
        assert "BJEA" in body

    def test_api_move_forward(self, port):
        resp = _get(port, "/api/move?action=forward")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"

    def test_api_move_stop(self, port):
        resp = _get(port, "/api/move?action=stop")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"

    def test_api_unknown_action(self, port):
        resp = _get(port, "/api/move?action=fly")
        assert resp.status == 400

    def test_api_post(self, port):
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"action": "forward"}).encode("utf-8")
        conn.request(
            "POST", "/api/move", body=body,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["action"] == "forward"

    def test_404(self, port):
        resp = _get(port, "/nonexistent")
        assert resp.status == 404
