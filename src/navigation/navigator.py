"""Sensor-based navigation primitives.

Replaces the old time-based dead-reckoning ("go forward N seconds") with
closed-loop primitives that use encoder odometry and MPU6050 heading.

On desktop / mock hardware the sensor readings are zero, so the navigator
falls back to timed open-loop operation automatically.
"""

import logging
import time
from typing import Any

import yaml

from hardware.motor import MotorController
from hardware.sensors import Sensors

logger = logging.getLogger(__name__)

# Fallback speed for open-loop mode (m/s estimate — tune on hardware).
_FALLBACK_SPEED_MPS = 0.3

# Minimum step duration for closed-loop correction (seconds).
_CORRECTION_INTERVAL = 0.05


class Navigator:
    """Executes route steps using sensor feedback when available."""

    def __init__(self, motor: MotorController, sensors: Sensors, config: dict):
        self._motor = motor
        self._sensors = sensors
        self._routes = self._load_routes(config.get("routes_file", "resources/routes.yaml"))

    # ------------------------------------------------------------------
    @staticmethod
    def _load_routes(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("Routes file not found: %s", path)
        except yaml.YAMLError:
            logger.warning("Failed to parse routes file: %s", path)
        return {}

    # ------------------------------------------------------------------
    # Motion primitives
    # ------------------------------------------------------------------

    def go_straight(self, distance_meters: float):
        """Drive forward *distance_meters*, keeping heading straight."""
        logger.info("Navigator: go_straight %.1f m", distance_meters)

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
                # keep heading straight
                heading_err = self._sensors.get_heading()
                correction = max(-1.0, min(1.0, -heading_err * 0.5))
                self._motor.steer(correction)
            else:
                # open-loop fallback: estimate from elapsed time
                est = elapsed * _FALLBACK_SPEED_MPS
                if est >= distance_meters:
                    break

            self._motor.forward(0.3)
            time.sleep(_CORRECTION_INTERVAL)

        self._motor.stop()

    def turn(self, degrees: float):
        """Turn *degrees* in place. Positive = right, negative = left."""
        direction = 1 if degrees >= 0 else -1
        target = abs(degrees)
        logger.info("Navigator: turn %+.0f deg", degrees)

        self._sensors.reset_heading()

        use_closed_loop = self._sensors._mpu is not None
        start_time = time.time()

        while True:
            if use_closed_loop:
                current = abs(self._sensors.get_heading())
                if current >= target:
                    break
            else:
                # rough open-loop estimate: ~45 deg/s at steering duty ~0.5
                elapsed = time.time() - start_time
                if elapsed * 45 >= target:
                    break

            self._motor.steer(direction)
            self._motor.forward(0.2)
            time.sleep(_CORRECTION_INTERVAL)

        self._motor.center_steering()
        self._motor.stop()

    # ------------------------------------------------------------------
    # Route execution
    # ------------------------------------------------------------------

    def follow_route(self, route_name: str):
        """Execute all steps of a named route from routes.yaml.

        Returns True if the route completed, False if the route is missing.
        """
        steps: list[dict[str, Any]] = self._routes.get(route_name, [])

        if not steps:
            logger.error("Unknown route: %s", route_name)
            return False

        logger.info("Navigator: starting route '%s' (%d steps)", route_name, len(steps))

        for i, step in enumerate(steps):
            action = step.get("action", "")
            logger.debug("  step %d/%d: %s %s", i + 1, len(steps), action, step)

            if action == "go":
                self.go_straight(float(step.get("distance", 0)))
            elif action == "turn":
                self.turn(float(step.get("angle", 0)))
            elif action == "stop":
                break
            else:
                logger.warning("Unknown action '%s' – skipping", action)

        self._motor.stop()
        logger.info("Navigator: route '%s' complete", route_name)
        return True

    @property
    def routes(self) -> list[str]:
        """List known route names."""
        return list(self._routes.keys())
