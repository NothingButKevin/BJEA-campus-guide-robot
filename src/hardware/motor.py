"""Motor controller abstraction with RPi GPIO and mock implementations."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Abstract interface
# ------------------------------------------------------------------

class MotorController(ABC):
    """Hardware-agnostic motor / steering interface."""

    @abstractmethod
    def forward(self, speed: float = 0.3):
        """Drive forward.  *speed* is 0.0 – 1.0."""

    @abstractmethod
    def backward(self, speed: float = 0.3):
        """Drive backward."""

    @abstractmethod
    def stop(self):
        """Stop all drive + steering."""

    @abstractmethod
    def steer(self, value: float):
        """Steer: -1.0 = full left, 1.0 = full right, 0.0 = centre."""

    @abstractmethod
    def center_steering(self):
        """Return steering to neutral."""

    @abstractmethod
    def cleanup(self):
        """Release hardware resources."""


# ------------------------------------------------------------------
# Raspberry Pi implementation (PWM via RPi.GPIO)
# ------------------------------------------------------------------

class RPiMotorController(MotorController):
    """PWM-controlled car chassis using RPi.GPIO.

    .. note::
        Only works on a Raspberry Pi with ``RPi.GPIO`` installed.
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

        # neutral
        self._pwm_drive.start(7.5)
        self._pwm_steer.start(7.5)

        logger.info(
            "RPiMotorController ready (drive=GPIO%d steer=GPIO%d)",
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
        """value: -1.0 (left) … 1.0 (right). Neutral = 7.5 %."""
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
# Mock implementation (desktop development & tests)
# ------------------------------------------------------------------

class MockMotorController(MotorController):
    """Logs every motor command — no physical hardware needed."""

    def forward(self, speed: float = 0.3):
        logger.info("[MockMotor] forward  (speed=%.2f)", speed)

    def backward(self, speed: float = 0.3):
        logger.info("[MockMotor] backward (speed=%.2f)", speed)

    def stop(self):
        logger.info("[MockMotor] stop")

    def steer(self, value: float):
        direction = "centre" if abs(value) < 0.01 else ("right" if value > 0 else "left")
        logger.info("[MockMotor] steer %s (%.2f)", direction, value)

    def center_steering(self):
        logger.info("[MockMotor] centre steering")

    def cleanup(self):
        logger.info("[MockMotor] cleanup")


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_motor(config: dict) -> MotorController:
    """Return the appropriate motor controller for the current platform."""
    try:
        import RPi.GPIO  # noqa: F401

        return RPiMotorController(config)
    except ImportError:
        logger.info("RPi.GPIO not available – using MockMotorController")
        return MockMotorController()
