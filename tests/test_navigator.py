"""测试 Navigator 运动原语（Mock 传感器）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from unittest.mock import patch

import pytest

from hardware.motor import MockMotorController
from hardware.sensors import Sensors
from navigation.navigator import Navigator


# ------------------------------------------------------------------
# 测试夹具
# ------------------------------------------------------------------

@pytest.fixture
def navigator():
    motor = MockMotorController()
    sensors = Sensors({"encoder_ticks_per_meter": 20, "mpu6050_address": 0x68})
    # Mock 传感器下航向和距离均返回 0.0 → 自动走开环兜底
    return Navigator(motor, sensors, {"routes_file": "tests/_nonexistent_routes.yaml"})


# ------------------------------------------------------------------
# 路径加载
# ------------------------------------------------------------------

class TestRouteLoading:
    def test_empty_routes_property(self, navigator):
        """空路径文件时 routes 属性返回空列表"""
        assert navigator.routes == []

    def test_missing_route_follow_returns_false(self, navigator):
        """不存在的路径名返回 False"""
        assert navigator.follow_route("nonexistent") is False


# ------------------------------------------------------------------
# 运动原语（开环兜底 —— 快速执行）
# ------------------------------------------------------------------

class TestGoStraight:
    def test_completes_without_error(self, navigator):
        """0.1 米直行应正常完成"""
        navigator.go_straight(0.1)

    def test_short_distance(self, navigator):
        """极短距离测试"""
        navigator.go_straight(0.05)


class TestTurn:
    def test_completes_without_error(self, navigator):
        """右转 30 度应正常完成"""
        navigator.turn(30)

    def test_negative_turn(self, navigator):
        """负角度左转应正常完成"""
        navigator.turn(-45)
