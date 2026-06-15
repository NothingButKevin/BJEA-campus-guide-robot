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
# 树莓派实现（通过 lgpio 直接输出 50Hz PWM，兼容 Pi 5 的 RP1 芯片）
# ------------------------------------------------------------------

class RPiMotorController(MotorController):
    """PWM 控制的车用底盘，使用 lgpio 直接输出 50Hz 舵机信号。

    硬件接线（差分混控驱动板）：:

        - **油门引脚**（drive_pin，GPIO27）：>7.5% 占空比 = 双轮前进，
          7.5% = 停止，<7.5% = 双轮后退。
        - **转向引脚**（steer_pin，GPIO17）：>7.5% = 右转（左前右后），
          7.5% = 直行，<7.5% = 左转（左后右前）。

    驱动板内置混控，最终输出为::

        左轮 = 油门 + 转向
        右轮 = 油门 - 转向

    lgpio 直接输出 50Hz 方波，占空比 5%（后退/左转）… 10%（前进/右转），
    7.5% 为中立点。实车验证 Pi 5 RP1 芯片下稳定工作。

    .. 注意::

        需要 root 权限访问 /dev/gpiochip0。
    """

    _NEUTRAL = 7.5   # 中立（停止 / 直行）
    _MAX_FWD = 10.0  # 全速前进 / 右满舵
    _MAX_REV = 5.0   # 全速后退 / 左满舵

    def __init__(self, config: dict):
        import lgpio as _lgpio
        self._lgpio = _lgpio

        self._chip = _lgpio.gpiochip_open(0)
        self._drive_pin = config["drive_pin"]
        self._steer_pin = config["steer_pin"]

        _lgpio.gpio_claim_output(self._chip, self._drive_pin)
        _lgpio.gpio_claim_output(self._chip, self._steer_pin)

        # 初始化为中位信号（7.5% 占空比）
        self._lgpio.tx_pwm(self._chip, self._drive_pin, 50, self._NEUTRAL)
        self._lgpio.tx_pwm(self._chip, self._steer_pin, 50, self._NEUTRAL)

        logger.info(
            "RPi 电机控制器就绪（油门=GPIO%d 转向=GPIO%d）",
            config["drive_pin"],
            config["steer_pin"],
        )

    def forward(self, speed: float = 0.3):
        """前进，*speed* 0.0–1.0。"""
        duty = self._NEUTRAL + speed * (self._MAX_FWD - self._NEUTRAL)
        self._lgpio.tx_pwm(self._chip, self._drive_pin, 50, duty)

    def backward(self, speed: float = 0.3):
        """后退，*speed* 0.0–1.0。"""
        duty = self._NEUTRAL - speed * (self._NEUTRAL - self._MAX_REV)
        self._lgpio.tx_pwm(self._chip, self._drive_pin, 50, duty)

    def stop(self):
        """油门回中（7.5% = 停止）。"""
        self._lgpio.tx_pwm(self._chip, self._drive_pin, 50, self._NEUTRAL)

    def steer(self, value: float):
        """转向：-1.0（左转） … 1.0（右转）。"""
        duty = self._NEUTRAL + value * (self._MAX_FWD - self._NEUTRAL)
        self._lgpio.tx_pwm(self._chip, self._steer_pin, 50, duty)

    def center_steering(self):
        """转向回中。"""
        self._lgpio.tx_pwm(self._chip, self._steer_pin, 50, self._NEUTRAL)

    def cleanup(self):
        """释放 GPIO 资源。"""
        import lgpio

        self._lgpio.tx_pwm(self._chip, self._drive_pin, 0, 0)
        self._lgpio.tx_pwm(self._chip, self._steer_pin, 0, 0)
        self._lgpio.gpio_free(self._chip, self._drive_pin)
        self._lgpio.gpio_free(self._chip, self._steer_pin)
        self._lgpio.gpiochip_close(self._chip)


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
        import lgpio  # noqa: F401

        return RPiMotorController(config)
    except ImportError:
        logger.info("lgpio 不可用 —— 使用 Mock 电机控制器")
        return MockMotorController()
