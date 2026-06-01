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
# 树莓派实现（通过 RPi.GPIO 输出 PWM）
# ------------------------------------------------------------------

class RPiMotorController(MotorController):
    """PWM 控制的车用底盘，使用 RPi.GPIO。

    注意:
        仅树莓派平台可用，依赖 ``RPi.GPIO`` 库。
    """

    def __init__(self, config: dict):
        import RPi.GPIO as GPIO

        self._drive_pin = config["drive_pin"]
        self._steer_pin = config["steer_pin"]
        freq = config.get("pwm_freq", 50)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._drive_pin, GPIO.OUT)
        GPIO.setup(self._steer_pin, GPIO.OUT)

        self._pwm_drive = GPIO.PWM(self._drive_pin, freq)
        self._pwm_steer = GPIO.PWM(self._steer_pin, freq)

        # 初始化为中位信号
        self._pwm_drive.start(7.5)
        self._pwm_steer.start(7.5)

        logger.info(
            "RPi 电机控制器就绪（驱动=GPIO%d 转向=GPIO%d）",
            self._drive_pin,
            self._steer_pin,
        )

    def forward(self, speed: float = 0.3):
        duty = 7.5 + speed * 0.5
        self._pwm_drive.ChangeDutyCycle(duty)

    def backward(self, speed: float = 0.3):
        duty = 7.5 - speed * 0.5
        self._pwm_drive.ChangeDutyCycle(duty)

    def stop(self):
        self._pwm_drive.ChangeDutyCycle(7.5)

    def steer(self, value: float):
        """value: -1.0（左） … 1.0（右）。中位 = 7.5% 占空比。"""
        duty = 7.5 + value * 0.5
        self._pwm_steer.ChangeDutyCycle(duty)

    def center_steering(self):
        self._pwm_steer.ChangeDutyCycle(7.5)

    def cleanup(self):
        import RPi.GPIO as GPIO

        self._pwm_drive.stop()
        self._pwm_steer.stop()
        GPIO.cleanup()


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
        import RPi.GPIO  # noqa: F401

        return RPiMotorController(config)
    except ImportError:
        logger.info("RPi.GPIO 不可用 —— 使用 Mock 电机控制器")
        return MockMotorController()
