"""Sensor abstraction: MPU6050 IMU + wheel encoders.

Provides heading angle and distance-travelled readings used by the
navigator for closed-loop motion primitives.
"""

import logging
import time

logger = logging.getLogger(__name__)


class Sensors:
    """Read MPU6050 heading and encoder-based odometry.

    On a desktop (mock mode), heading and distance are always zero so the
    navigator falls back to open-loop timing.
    """

    def __init__(self, config: dict):
        self._ticks_per_meter = config.get("encoder_ticks_per_meter", 20)
        self._mpu_address = config.get("mpu6050_address", 0x68)

        self._mpu = self._init_mpu()

        # heading state
        self._heading_bias: float = 0.0
        self._last_gyro_time: float = 0.0
        self._heading: float = 0.0

        # odometry state
        self._encoder_count: int = 0
        self._distance_bias: float = 0.0

        logger.info("Sensors initialised (mock=%s)", self._mpu is None)

    # ------------------------------------------------------------------
    def _init_mpu(self):
        try:
            from mpu6050 import MPU6050

            return MPU6050(self._mpu_address)
        except Exception:
            logger.warning("MPU6050 unavailable – heading will be mock (0.0)")
            return None

    # ------------------------------------------------------------------
    # Heading (gyro integration)
    # ------------------------------------------------------------------

    def get_heading(self) -> float:
        """Current absolute heading in degrees (positive = right turn from reset)."""
        if self._mpu is None:
            return 0.0

        now = time.time()
        dt = now - self._last_gyro_time if self._last_gyro_time > 0 else 0.0
        self._last_gyro_time = now

        try:
            gyro_z = self._mpu.get_gyro_data()["z"]  # deg / s
            self._heading += gyro_z * dt
        except Exception:
            pass

        return self._heading - self._heading_bias

    def reset_heading(self):
        """Zero the heading reference."""
        self._heading_bias = self._heading
        self._last_gyro_time = time.time()

    # ------------------------------------------------------------------
    # Odometry (encoder)
    # ------------------------------------------------------------------

    def get_distance_traveled(self) -> float:
        """Distance in metres since last ``reset_distance()``."""
        if self._ticks_per_meter <= 0:
            return 0.0
        raw = self._encoder_count
        dist = raw / self._ticks_per_meter
        return dist - self._distance_bias

    def reset_distance(self):
        """Zero the odometer reference."""
        self._distance_bias = self._encoder_count / max(self._ticks_per_meter, 1)

    # ------------------------------------------------------------------
    # Encoder tick feed (call from GPIO interrupt or polling loop)
    # ------------------------------------------------------------------

    def increment_encoder(self, ticks: int = 1):
        self._encoder_count += ticks
