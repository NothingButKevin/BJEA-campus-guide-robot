"""遥控模式 —— 轻量 HTTP 服务器 + 电机控制端点。

使用 Python 标准库 http.server + socketserver.ThreadingMixIn，零第三方 Web 框架依赖。
每个 HTTP 请求对电机执行一次操作（无状态），通过 200ms 间隔的重复请求实现持续运动。
"""

import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Callable, Optional

from hardware.motor import MotorController

logger = logging.getLogger(__name__)

# ── 常量 ──
_MOVE_SPEED = 0.3       # 直行速度
_STEER_LEFT  = 0.2      # 左转舵量
_STEER_RIGHT = 0.2      # 右转舵量（可独立调校不对称电机）
_CMD_TIMEOUT = 2.0      # 看门狗超时（秒），超时自动停止

# ── HTML 模板路径 ──
_HTML_DIR = Path(__file__).resolve().parent / "html"


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，daemon_threads 确保主线程退出时自动清理。"""
    daemon_threads = True


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 —— 提供遥控网页 + 电机控制 API。"""

    # 类级变量：由 create_server() 注入，所有 handler 实例共享
    motor: Optional[MotorController] = None
    map_snapshot_provider: Optional[Callable[[], dict]] = None
    snapshot_handler: Optional[Callable[[dict], dict]] = None
    waypoint_handler: Optional[Callable[[dict], dict]] = None
    save_handler: Optional[Callable[[dict], dict]] = None
    pose_handler: Optional[Callable[[dict], dict]] = None
    accept_candidate_handler: Optional[Callable[[dict], dict]] = None
    discard_snapshot_handler: Optional[Callable[[dict], dict]] = None
    motion_observer: Optional[Callable[[str], None]] = None
    _last_cmd_time: float = 0.0
    _watchdog: Optional[threading.Timer] = None
    _watchdog_lock = threading.Lock()

    # ── 日志重定向到 logging ──
    def log_message(self, format, *args):
        logger.debug("HTTP: %s", format % args)

    # ── 路由 ──
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/map" or self.path == "/map.html":
            self._serve_map_html()
        elif self.path.startswith("/api/"):
            self._handle_api()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._handle_api()
        else:
            self.send_error(404)

    # ── HTML 服务 ──
    def _serve_html(self):
        html_path = _HTML_DIR / ("map.html" if RemoteControlHandler.map_snapshot_provider else "controller.html")
        if not html_path.exists():
            self.send_error(500, "Template not found")
            return
        html = html_path.read_text("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_map_html(self):
        if RemoteControlHandler.map_snapshot_provider is None:
            self.send_error(404, "Map provider not enabled")
            return
        html_path = _HTML_DIR / "map.html"
        if not html_path.exists():
            self.send_error(500, "Template not found")
            return
        html = html_path.read_text("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    # ── API 处理 ──
    def _handle_api(self):
        if self.path.startswith("/api/map"):
            self._handle_map_api()
            return
        if self.path.startswith("/api/snapshot"):
            self._handle_callback_api(RemoteControlHandler.snapshot_handler, "快照服务未启用")
            return
        if self.path.startswith("/api/waypoint"):
            self._handle_callback_api(RemoteControlHandler.waypoint_handler, "路径点服务未启用")
            return
        if self.path.startswith("/api/save"):
            self._handle_callback_api(RemoteControlHandler.save_handler, "保存服务未启用")
            return
        if self.path.startswith("/api/pose"):
            self._handle_callback_api(RemoteControlHandler.pose_handler, "位姿服务未启用")
            return
        if self.path.startswith("/api/accept-candidate"):
            self._handle_callback_api(RemoteControlHandler.accept_candidate_handler, "候选确认服务未启用")
            return
        if self.path.startswith("/api/discard-snapshot"):
            self._handle_callback_api(RemoteControlHandler.discard_snapshot_handler, "快照丢弃服务未启用")
            return

        # 解析参数：GET 用 query string，POST 用 JSON body
        if self.command == "POST":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                params = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._json_response(400, {"error": "无效的 JSON"})
                return
        else:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            params = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

        action = params.get("action", "")
        logger.info("遥控命令: %s", action)

        motor = RemoteControlHandler.motor
        if motor is None:
            self._json_response(500, {"error": "电机未初始化"})
            return

        # ── 动作分发 ──
        # 驱动板混控：左轮 = 油门 + 转向，右轮 = 油门 - 转向。
        # 油门和转向不可同时非零，否则混控非线性叠加导致异常。
        # 匹配 demo.py 已验证模式：直行只给油门，转弯只给转向。
        if action == "forward":
            motor.center_steering()
            motor.forward(_MOVE_SPEED)
        elif action == "backward":
            motor.center_steering()
            motor.backward(_MOVE_SPEED)
        elif action == "left":
            motor.stop()            # 油门回中
            motor.steer(-_STEER_LEFT)
        elif action == "right":
            motor.stop()            # 油门回中
            motor.steer(_STEER_RIGHT)
        elif action == "stop":
            motor.stop()
            motor.center_steering()
        elif action == "ping":
            pass  # 保活探测
        else:
            self._json_response(400, {"error": f"未知动作: {action}"})
            return

        if RemoteControlHandler.motion_observer is not None:
            RemoteControlHandler.motion_observer(action)

        # 重置看门狗
        if action != "ping":
            RemoteControlHandler._reset_watchdog()

        self._json_response(200, {"status": "ok", "action": action})

    def _handle_map_api(self):
        provider = RemoteControlHandler.map_snapshot_provider
        if provider is None:
            self._json_response(404, {"error": "地图服务未启用"})
            return
        try:
            self._json_response(200, provider())
        except Exception as exc:
            logger.exception("地图快照生成失败: %s", exc)
            self._json_response(500, {"error": str(exc)})

    def _request_params(self) -> dict:
        if self.command == "POST":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            if not body:
                return {}
            return json.loads(body)
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

    def _handle_callback_api(self, callback: Optional[Callable[[dict], dict]], disabled_error: str):
        if callback is None:
            self._json_response(404, {"error": disabled_error})
            return
        try:
            self._json_response(200, callback(self._request_params()))
        except json.JSONDecodeError:
            self._json_response(400, {"error": "无效的 JSON"})
        except Exception as exc:
            logger.exception("API 处理失败: %s", exc)
            self._json_response(500, {"error": str(exc)})

    # ── JSON 响应 ──
    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    # ── 看门狗 ──
    @classmethod
    def _reset_watchdog(cls):
        """每次收到遥控指令时重置看门狗定时器。"""
        with cls._watchdog_lock:
            if cls._watchdog is not None:
                cls._watchdog.cancel()
            cls._last_cmd_time = time.time()
            cls._watchdog = threading.Timer(_CMD_TIMEOUT, cls._timeout_stop)
            cls._watchdog.daemon = True
            cls._watchdog.start()

    @classmethod
    def _timeout_stop(cls):
        """看门狗触发：超时未收到指令，自动停止电机。"""
        elapsed = time.time() - cls._last_cmd_time
        logger.warning("遥控命令超时（%.1f秒未收到指令），自动停止电机", elapsed)
        if cls.motor:
            cls.motor.stop()
            cls.motor.center_steering()

    @classmethod
    def cleanup(cls):
        """取消看门狗定时器（服务器关闭时调用）。"""
        with cls._watchdog_lock:
            if cls._watchdog is not None:
                cls._watchdog.cancel()
                cls._watchdog = None
        cls.map_snapshot_provider = None
        cls.snapshot_handler = None
        cls.waypoint_handler = None
        cls.save_handler = None
        cls.pose_handler = None
        cls.accept_candidate_handler = None
        cls.discard_snapshot_handler = None
        cls.motion_observer = None


# ── 工厂函数 ──
def create_server(
    host: str,
    port: int,
    motor: MotorController,
    map_snapshot_provider: Optional[Callable[[], dict]] = None,
    snapshot_handler: Optional[Callable[[dict], dict]] = None,
    waypoint_handler: Optional[Callable[[dict], dict]] = None,
    save_handler: Optional[Callable[[dict], dict]] = None,
    pose_handler: Optional[Callable[[dict], dict]] = None,
    accept_candidate_handler: Optional[Callable[[dict], dict]] = None,
    discard_snapshot_handler: Optional[Callable[[dict], dict]] = None,
    motion_observer: Optional[Callable[[str], None]] = None,
) -> _ThreadingHTTPServer:
    """创建并配置 HTTP 服务器。"""
    RemoteControlHandler.motor = motor
    RemoteControlHandler.map_snapshot_provider = map_snapshot_provider
    RemoteControlHandler.snapshot_handler = snapshot_handler
    RemoteControlHandler.waypoint_handler = waypoint_handler
    RemoteControlHandler.save_handler = save_handler
    RemoteControlHandler.pose_handler = pose_handler
    RemoteControlHandler.accept_candidate_handler = accept_candidate_handler
    RemoteControlHandler.discard_snapshot_handler = discard_snapshot_handler
    RemoteControlHandler.motion_observer = motion_observer
    server = _ThreadingHTTPServer((host, port), RemoteControlHandler)
    server.timeout = 0.5  # 允许 serve_forever 在 shutdown 时快速退出
    return server
