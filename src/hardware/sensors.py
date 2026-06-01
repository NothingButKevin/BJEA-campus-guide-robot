"""传感器抽象层 —— MPU6050 陀螺仪 + 轮式编码器。

提供航向角和行进距离读数，供导航器实现闭环运动原语。
"""

import logging
import time

logger = logging.getLogger(__name__)


class Sensors:
    """读取 MPU6050 航向和编码器里程计数据。

    在桌面端（Mock 模式）下航向和距离均返回零，导航器自动降级为
    开环时间估算。
    """

    def __init__(self, config: dict):
        self._ticks_per_meter = config.get("encoder_ticks_per_meter", 20)
        self._mpu_address = config.get("mpu6050_address", 0x68)

        self._mpu = self._init_mpu()

        # 航向状态
        self._heading_bias: float = 0.0
        self._last_gyro_time: float = 0.0
        self._heading: float = 0.0

        # 里程计状态
        self._encoder_count: int = 0
        self._distance_bias: float = 0.0

        logger.info("传感器初始化完毕（Mock=%s）", self._mpu is None)

    # ------------------------------------------------------------------
    def _init_mpu(self):
        try:
            from mpu6050 import MPU6050

            return MPU6050(self._mpu_address)
        except Exception:
            logger.warning("MPU6050 不可用 —— 航向将使用 Mock 值 (0.0)")
            return None

    # ------------------------------------------------------------------
    # 航向（陀螺仪积分）
    # ------------------------------------------------------------------

    def get_heading(self) -> float:
        """当前绝对航向角（度），正值表示自归零后右转。"""
        if self._mpu is None:
            return 0.0

        now = time.time()
        dt = now - self._last_gyro_time if self._last_gyro_time > 0 else 0.0
        self._last_gyro_time = now

        try:
            gyro_z = self._mpu.get_gyro_data()["z"]  # 度/秒
            self._heading += gyro_z * dt
        except Exception:
            pass

        return self._heading - self._heading_bias

    def reset_heading(self):
        """将当前航向归零作为基准。"""
        self._heading_bias = self._heading
        self._last_gyro_time = time.time()

    # ------------------------------------------------------------------
    # 里程计（编码器）
    # ------------------------------------------------------------------

    def get_distance_traveled(self) -> float:
        """自上次 ``reset_distance()`` 以来的行进距离（米）。"""
        if self._ticks_per_meter <= 0:
            return 0.0
        raw = self._encoder_count
        dist = raw / self._ticks_per_meter
        return dist - self._distance_bias

    def reset_distance(self):
        """归零里程计基准。"""
        self._distance_bias = self._encoder_count / max(self._ticks_per_meter, 1)

    # ------------------------------------------------------------------
    # 编码器脉冲输入（由 GPIO 中断或轮询循环调用）
    # ------------------------------------------------------------------

    def increment_encoder(self, ticks: int = 1):
        self._encoder_count += ticks
