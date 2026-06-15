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
# 树莓派实现（通过 gpiozero + lgpio 输出 PWM，兼容 Pi 5 的 RP1 芯片）
# ------------------------------------------------------------------

class RPiMotorController(MotorController):
    """PWM 控制的车用底盘，使用 gpiozero Servo + lgpio 后端。

    硬件接线（差分混控驱动板）：:

        - **油门引脚**（drive_pin，GPIO27）：>7.5% 占空比 = 双轮前进，
          7.5% = 停止，<7.5% = 双轮后退。
        - **转向引脚**（steer_pin，GPIO17）：>7.5% = 右转（左前右后），
          7.5% = 直行，<7.5% = 左转（左后右前）。

    驱动板内置混控，最终输出为::

        左轮 = 油门 + 转向
        右轮 = 油门 - 转向

    使用 gpiozero ``Servo`` 类（value=-1…1 映射 1–2ms 脉冲，0 对应 1.5ms 中立），
    经实车验证 Pi 5 + lgpio 下输出正确。

    .. 注意::

        Pi 5 必须设置 ``GPIOZERO_PIN_FACTORY=lgpio``（构造函数自动处理），
        否则 gpiozero 回退到 RPi.GPIO 软件 PWM，在 RP1 芯片上不工作。
    """

    def __init__(self, config: dict):
        import os

        # Pi 5（RP1 芯片）需要 lgpio 后端，否则 PWM 无输出
        if "GPIOZERO_PIN_FACTORY" not in os.environ:
            os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

        from gpiozero import Servo

        self._throttle = Servo(config["drive_pin"])   # GPIO27 → 油门
        self._steering = Servo(config["steer_pin"])   # GPIO17 → 转向

        # 初始化为中位信号（value=0 对应 1.5ms / 7.5% 脉冲）
        self._throttle.value = 0
        self._steering.value = 0

        logger.info(
            "RPi 电机控制器就绪（油门=GPIO%d 转向=GPIO%d）",
            config["drive_pin"],
            config["steer_pin"],
        )

    def forward(self, speed: float = 0.3):
        """前进，*speed* 0.0–1.0。"""
        self._throttle.value = speed * 0.2

    def backward(self, speed: float = 0.3):
        """后退，*speed* 0.0–1.0。"""
        self._throttle.value = -speed * 0.2

    def stop(self):
        """油门回中（1.5ms 脉冲 = 停止）。"""
        self._throttle.value = 0

    def steer(self, value: float):
        """转向：-1.0（左转） … 1.0（右转）。"""
        self._steering.value = value * 0.2

    def center_steering(self):
        """转向回中。"""
        self._steering.value = 0

    def cleanup(self):
        """释放 PWM 资源。"""
        self._throttle.close()
        self._steering.close()


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
    """根据当前平台自动选择电机控制器实现。

    Pi 5 必须使用 lgpio 后端——环境变量必须在 gpiozero 首次导入前设置。
    """
    import os
    os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")

    try:
        from gpiozero import Servo  # noqa: F401

        return RPiMotorController(config)
    except ImportError:
        logger.info("gpiozero 不可用 —— 使用 Mock 电机控制器")
        return MockMotorController()
