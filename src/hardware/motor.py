"""电机控制器 —— 抽象接口 + Raspberry Pi PWM 实现 + Mock 测试实现。"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 抽象接口
# ------------------------------------------------------------------

class MotorController(ABC):
    """与硬件无关的电机 / 转向接口。"""

    @abstractmethod
    def forward(self, speed: float = 0.3):
        """前进，*speed* 取值范围 0.0 – 1.0。"""

    @abstractmethod
    def backward(self, speed: float = 0.3):
        """后退。"""

    @abstractmethod
    def stop(self):
        """停止所有驱动和转向。"""

    @abstractmethod
    def steer(self, value: float):
        """转向：-1.0 = 左满舵，1.0 = 右满舵，0.0 = 回中。"""

    @abstractmethod
    def center_steering(self):
        """转向回中。"""

    @abstractmethod
    def cleanup(self):
        """释放硬件资源。"""


# ------------------------------------------------------------------
# 树莓派实现（通过 gpiozero 输出 PWM，兼容 Pi 5 的 RP1 芯片）
# ------------------------------------------------------------------

class RPiMotorController(MotorController):
    """PWM 控制的车用底盘，使用 gpiozero。

    兼容树莓派 3/4/5，gpiozero 自动选择底层 GPIO 驱动（Pi 5 用 lgpio，旧版用 RPi.GPIO）。
    """

    def __init__(self, config: dict):
        from gpiozero import Servo

        self._drive = Servo(config["drive_pin"])
        self._steer = Servo(config["steer_pin"])

        # 初始化为中位信号（value=0 对应 1.5ms 脉冲）
        self._drive.value = 0
        self._steer.value = 0

        logger.info(
            "RPi 电机控制器就绪（驱动=GPIO%d 转向=GPIO%d）",
            config["drive_pin"],
            config["steer_pin"],
        )

    def forward(self, speed: float = 0.3):
        """前进，speed 0.0–1.0，映射为 1.5–1.6ms 脉冲。"""
        self._drive.value = speed * 0.2

    def backward(self, speed: float = 0.3):
        """后退，speed 0.0–1.0，映射为 1.5–1.4ms 脉冲。"""
        self._drive.value = -speed * 0.2

    def stop(self):
        """驱动电机回中（1.5ms 脉冲 = 停止）。"""
        self._drive.value = 0

    def steer(self, value: float):
        """转向：-1.0（左） … 1.0（右）。中位 = 1.5ms 脉冲。"""
        self._steer.value = value * 0.2

    def center_steering(self):
        """转向回中。"""
        self._steer.value = 0

    def cleanup(self):
        """释放 PWM 资源。"""
        self._drive.close()
        self._steer.close()


# ------------------------------------------------------------------
# Mock 实现（桌面开发与测试用）
# ------------------------------------------------------------------

class MockMotorController(MotorController):
    """将所有电机指令记录到日志 —— 无需实际硬件。"""

    def forward(self, speed: float = 0.3):
        logger.info("[Mock电机] 前进  (速度=%.2f)", speed)

    def backward(self, speed: float = 0.3):
        logger.info("[Mock电机] 后退 (速度=%.2f)", speed)

    def stop(self):
        logger.info("[Mock电机] 停止")

    def steer(self, value: float):
        direction = "回中" if abs(value) < 0.01 else ("右转" if value > 0 else "左转")
        logger.info("[Mock电机] 转向 %s (%.2f)", direction, value)

    def center_steering(self):
        logger.info("[Mock电机] 转向回中")

    def cleanup(self):
        logger.info("[Mock电机] 清理资源")


# ------------------------------------------------------------------
# 工厂函数
# ------------------------------------------------------------------

def create_motor(config: dict) -> MotorController:
    """根据当前平台自动选择电机控制器实现。"""
    try:
        from gpiozero import Servo  # noqa: F401

        return RPiMotorController(config)
    except ImportError:
        logger.info("gpiozero 不可用 —— 使用 Mock 电机控制器")
        return MockMotorController()
