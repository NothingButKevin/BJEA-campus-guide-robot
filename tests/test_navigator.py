"""Tests for Navigator motion primitives (mock sensors)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from unittest.mock import patch

import pytest

from hardware.motor import MockMotorController
from hardware.sensors import Sensors
from navigation.navigator import Navigator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def navigator():
    motor = MockMotorController()
    sensors = Sensors({"encoder_ticks_per_meter": 20, "mpu6050_address": 0x68})
    # Use a non-existent routes file so the navigator starts empty.
    return Navigator(motor, sensors, {"routes_file": "tests/_nonexistent_routes.yaml"})


# ------------------------------------------------------------------
# Route loading
# ------------------------------------------------------------------

class TestRouteLoading:
    def test_empty_routes_property(self, navigator):
        assert navigator.routes == []

    def test_missing_route_follow_returns_false(self, navigator):
        assert navigator.follow_route("nonexistent") is False


# ------------------------------------------------------------------
# Motion primitives (open-loop fallback — fast)
# ------------------------------------------------------------------

class TestGoStraight:
    def test_completes_without_error(self, navigator):
        # 0.1 m — should complete in ~0.3 s
        navigator.go_straight(0.1)

    def test_short_distance(self, navigator):
        navigator.go_straight(0.05)


class TestTurn:
    def test_completes_without_error(self, navigator):
        navigator.turn(30)

    def test_negative_turn(self, navigator):
        navigator.turn(-45)
