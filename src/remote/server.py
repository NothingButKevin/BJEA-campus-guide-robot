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
from typing import Optional

from hardware.motor import MotorController

logger = logging.getLogger(__name__)

# ── 常量 ──
_MOVE_SPEED = 0.3       # 直行速度
_STEER_ANGLE = 0.5      # 转弯舵量
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
        html_path = _HTML_DIR / "controller.html"
        if not html_path.exists():
            self.send_error(500, "Template not found")
            return
        html = html_path.read_text("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    # ── API 处理 ──
    def _handle_api(self):
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
            motor.steer(-_STEER_ANGLE)
        elif action == "right":
            motor.stop()            # 油门回中
            motor.steer(_STEER_ANGLE)
        elif action == "stop":
            motor.stop()
            motor.center_steering()
        elif action == "ping":
            pass  # 保活探测
        else:
            self._json_response(400, {"error": f"未知动作: {action}"})
            return

        # 重置看门狗
        RemoteControlHandler._reset_watchdog()

        self._json_response(200, {"status": "ok", "action": action})

    # ── JSON 响应 ──
    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
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


# ── 工厂函数 ──
def create_server(host: str, port: int, motor: MotorController) -> _ThreadingHTTPServer:
    """创建并配置 HTTP 服务器。"""
    RemoteControlHandler.motor = motor
    server = _ThreadingHTTPServer((host, port), RemoteControlHandler)
    server.timeout = 0.5  # 允许 serve_forever 在 shutdown 时快速退出
    return server
