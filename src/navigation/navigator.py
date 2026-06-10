"""传感器闭环导航执行器。

用编码器里程计和 MPU6050 航向角替换原来的时间打表（"前进 N 秒"），
实现定距走、定角转的闭环运动原语。

桌面端 / Mock 硬件下传感器读数为零，自动降级为开环时间估算。
"""

import logging
import time
from typing import Any

import yaml

from hardware.motor import MotorController
from hardware.sensors import Sensors

logger = logging.getLogger(__name__)

# 开环模式下估算的前进速度（米/秒 —— 需在真车上标定）
_FALLBACK_SPEED_MPS = 0.3

# 闭环修正的最小间隔（秒）
_CORRECTION_INTERVAL = 0.05


class Navigator:
    """利用传感器反馈执行路径步骤。"""

    def __init__(self, motor: MotorController, sensors: Sensors, config: dict):
        self._motor = motor
        self._sensors = sensors
        self._routes = self._load_routes(config.get("routes_file", "resources/routes.yaml"))

        # 导航进度（供 GUI 读取）
        self._current_destination: str = ""
        self._current_step: int = 0
        self._total_steps: int = 0
        self._current_action: str = ""

    # ------------------------------------------------------------------
    @staticmethod
    def _load_routes(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("路径文件未找到: %s", path)
        except yaml.YAMLError:
            logger.warning("路径文件解析失败: %s", path)
        return {}

    # ------------------------------------------------------------------
    # 运动原语
    # ------------------------------------------------------------------

    def go_straight(self, distance_meters: float):
        """按编码器里程计前进 *distance_meters* 米，MPU6050 保持航向不偏。"""
        logger.info("导航器: 直行 %.1f 米", distance_meters)

        self._sensors.reset_distance()
        self._sensors.reset_heading()

        start_time = time.time()
        use_closed_loop = self._sensors._mpu is not None

        while True:
            elapsed = time.time() - start_time

            if use_closed_loop:
                dist = self._sensors.get_distance_traveled()
                if dist >= distance_meters:
                    break
                # 保持直线不偏 —— P 控制器修正航向
                heading_err = self._sensors.get_heading()
                correction = max(-1.0, min(1.0, -heading_err * 0.5))
                self._motor.steer(correction)
            else:
                # 开环兜底：根据时间估算
                est = elapsed * _FALLBACK_SPEED_MPS
                if est >= distance_meters:
                    break

            self._motor.forward(0.3)
            time.sleep(_CORRECTION_INTERVAL)

        self._motor.stop()

    def turn(self, degrees: float):
        """原地转向 *degrees* 度。正值 = 右转，负值 = 左转。"""
        direction = 1 if degrees >= 0 else -1
        target = abs(degrees)
        logger.info("导航器: 转向 %+.0f 度", degrees)

        self._sensors.reset_heading()

        use_closed_loop = self._sensors._mpu is not None
        start_time = time.time()

        while True:
            if use_closed_loop:
                current = abs(self._sensors.get_heading())
                if current >= target:
                    break
            else:
                # 开环粗略估算：约 45 度/秒（舵机占空比 ~0.5）
                elapsed = time.time() - start_time
                if elapsed * 45 >= target:
                    break

            self._motor.steer(direction)
            self._motor.forward(0.2)
            time.sleep(_CORRECTION_INTERVAL)

        self._motor.center_steering()
        self._motor.stop()

    # ------------------------------------------------------------------
    # 路径执行
    # ------------------------------------------------------------------

    def follow_route(self, route_name: str):
        """执行 routes.yaml 中指定路径的所有步骤。

        返回 True 表示路径执行完毕，False 表示路径不存在。
        """
        steps: list[dict[str, Any]] = self._routes.get(route_name, [])

        if not steps:
            logger.error("未知路径: %s", route_name)
            return False

        logger.info("导航器: 开始执行路径 '%s'（共 %d 步）", route_name, len(steps))

        self._current_destination = route_name
        self._current_step = 0
        self._total_steps = len(steps)

        for i, step in enumerate(steps):
            action = step.get("action", "")
            self._current_step = i + 1
            self._current_action = action
            logger.debug("  第 %d/%d 步: %s %s", i + 1, len(steps), action, step)

            if action == "go":
                self.go_straight(float(step.get("distance", 0)))
            elif action == "turn":
                self.turn(float(step.get("angle", 0)))
            elif action == "stop":
                break
            else:
                logger.warning("未知动作 '%s' —— 跳过", action)

        self._motor.stop()
        logger.info("导航器: 路径 '%s' 执行完毕", route_name)
        return True

    @property
    def routes(self) -> list[str]:
        """列出所有已知路径名称。"""
        return list(self._routes.keys())

    def get_progress(self) -> dict:
        """返回当前导航进度（供 GUI 和 CLI 读取）。"""
        return {
            "destination": self._current_destination,
            "step": self._current_step,
            "total": self._total_steps,
            "current_action": self._current_action,
        }
