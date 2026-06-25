"""LD06 激光雷达读取与数据包解析。"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class LidarReadError(RuntimeError):
    """雷达串口临时读取失败。"""


LD06_HEADER = 0x54
LD06_VER_LEN = 0x2C
LD06_PACKET_SIZE = 47
LD06_POINTS_PER_PACKET = 12

PolarPoint = tuple[float, float, int]


_CRC_TABLE = [
    0x00, 0x4D, 0x9A, 0xD7, 0x79, 0x34, 0xE3, 0xAE, 0xF2, 0xBF, 0x68, 0x25, 0x8B, 0xC6, 0x11, 0x5C,
    0xA9, 0xE4, 0x33, 0x7E, 0xD0, 0x9D, 0x4A, 0x07, 0x5B, 0x16, 0xC1, 0x8C, 0x22, 0x6F, 0xB8, 0xF5,
    0x1F, 0x52, 0x85, 0xC8, 0x66, 0x2B, 0xFC, 0xB1, 0xED, 0xA0, 0x77, 0x3A, 0x94, 0xD9, 0x0E, 0x43,
    0xB6, 0xFB, 0x2C, 0x61, 0xCF, 0x82, 0x55, 0x18, 0x44, 0x09, 0xDE, 0x93, 0x3D, 0x70, 0xA7, 0xEA,
    0x3E, 0x73, 0xA4, 0xE9, 0x47, 0x0A, 0xDD, 0x90, 0xCC, 0x81, 0x56, 0x1B, 0xB5, 0xF8, 0x2F, 0x62,
    0x97, 0xDA, 0x0D, 0x40, 0xEE, 0xA3, 0x74, 0x39, 0x65, 0x28, 0xFF, 0xB2, 0x1C, 0x51, 0x86, 0xCB,
    0x21, 0x6C, 0xBB, 0xF6, 0x58, 0x15, 0xC2, 0x8F, 0xD3, 0x9E, 0x49, 0x04, 0xAA, 0xE7, 0x30, 0x7D,
    0x88, 0xC5, 0x12, 0x5F, 0xF1, 0xBC, 0x6B, 0x26, 0x7A, 0x37, 0xE0, 0xAD, 0x03, 0x4E, 0x99, 0xD4,
    0x7C, 0x31, 0xE6, 0xAB, 0x05, 0x48, 0x9F, 0xD2, 0x8E, 0xC3, 0x14, 0x59, 0xF7, 0xBA, 0x6D, 0x20,
    0xD5, 0x98, 0x4F, 0x02, 0xAC, 0xE1, 0x36, 0x7B, 0x27, 0x6A, 0xBD, 0xF0, 0x5E, 0x13, 0xC4, 0x89,
    0x63, 0x2E, 0xF9, 0xB4, 0x1A, 0x57, 0x80, 0xCD, 0x91, 0xDC, 0x0B, 0x46, 0xE8, 0xA5, 0x72, 0x3F,
    0xCA, 0x87, 0x50, 0x1D, 0xB3, 0xFE, 0x29, 0x64, 0x38, 0x75, 0xA2, 0xEF, 0x41, 0x0C, 0xDB, 0x96,
    0x42, 0x0F, 0xD8, 0x95, 0x3B, 0x76, 0xA1, 0xEC, 0xB0, 0xFD, 0x2A, 0x67, 0xC9, 0x84, 0x53, 0x1E,
    0xEB, 0xA6, 0x71, 0x3C, 0x92, 0xDF, 0x08, 0x45, 0x19, 0x54, 0x83, 0xCE, 0x60, 0x2D, 0xFA, 0xB7,
    0x5D, 0x10, 0xC7, 0x8A, 0x24, 0x69, 0xBE, 0xF3, 0xAF, 0xE2, 0x35, 0x78, 0xD6, 0x9B, 0x4C, 0x01,
    0xF4, 0xB9, 0x6E, 0x23, 0x8D, 0xC0, 0x17, 0x5A, 0x06, 0x4B, 0x9C, 0xD1, 0x7F, 0x32, 0xE5, 0xA8,
]


def ld06_crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc = _CRC_TABLE[(crc ^ byte) & 0xFF]
    return crc


def _u16(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)


def normalize_angle(angle: float) -> float:
    return angle % 360.0


def correct_angle(angle: float, inverted: bool = False, offset_deg: float = 0.0) -> float:
    corrected = -angle if inverted else angle
    return normalize_angle(corrected + offset_deg)


def parse_ld06_packet(packet: bytes, inverted: bool = False, angle_offset_deg: float = 0.0) -> list[PolarPoint]:
    """解析一个 47 字节 LD06 包，返回 `(angle_deg, distance_m, confidence)`。"""
    if len(packet) != LD06_PACKET_SIZE:
        raise ValueError("LD06 数据包长度错误")
    if packet[0] != LD06_HEADER or packet[1] != LD06_VER_LEN:
        raise ValueError("LD06 数据包头错误")
    if ld06_crc(packet[:-1]) != packet[-1]:
        raise ValueError("LD06 CRC 校验失败")

    start_angle = _u16(packet, 4) / 100.0
    end_angle = _u16(packet, 42) / 100.0
    span = (end_angle - start_angle) % 360.0
    step = span / (LD06_POINTS_PER_PACKET - 1)

    points: list[PolarPoint] = []
    offset = 6
    for i in range(LD06_POINTS_PER_PACKET):
        distance_mm = _u16(packet, offset)
        confidence = packet[offset + 2]
        raw_angle = normalize_angle(start_angle + step * i)
        angle = correct_angle(raw_angle, inverted=inverted, offset_deg=angle_offset_deg)
        if distance_mm > 0 and math.isfinite(angle):
            points.append((angle, distance_mm / 1000.0, confidence))
        offset += 3
    return points


@dataclass
class LD06Config:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 230400
    inverted: bool = False
    angle_offset_deg: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "LD06Config":
        return cls(
            port=str(data.get("port", "/dev/ttyUSB0")),
            baudrate=int(data.get("baudrate", 230400)),
            inverted=bool(data.get("inverted", False)),
            angle_offset_deg=float(data.get("angle_offset_deg", 0.0)),
        )


class LD06Lidar:
    """串口读取 LD06 数据。"""

    def __init__(self, config: LD06Config):
        self.config = config
        self._serial = None

    def open(self):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("缺少 pyserial，请先安装 requirements.txt") from exc

        self._serial = serial.Serial(
            self.config.port,
            self.config.baudrate,
            timeout=0.2,
        )
        logger.info("LD06 雷达已打开: %s @ %s", self.config.port, self.config.baudrate)

    def read_scan(self, timeout: float = 1.0) -> list[PolarPoint]:
        if self._serial is None:
            self.open()

        deadline = time.time() + timeout
        scan: list[PolarPoint] = []
        covered_angles: set[int] = set()
        while time.time() < deadline:
            packet = self._read_packet(deadline)
            if packet is None:
                continue
            try:
                points = parse_ld06_packet(
                    packet,
                    inverted=self.config.inverted,
                    angle_offset_deg=self.config.angle_offset_deg,
                )
            except ValueError as exc:
                logger.debug("丢弃 LD06 包: %s", exc)
                continue
            scan.extend(points)
            covered_angles.update(int(round(angle)) % 360 for angle, _, _ in points)
            if len(covered_angles) >= 330:
                break
        return scan

    def flush_input(self):
        if self._serial is None:
            self.open()
        assert self._serial is not None
        try:
            self._serial.reset_input_buffer()
        except AttributeError:
            self._serial.flushInput()

    def close(self):
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _read_packet(self, deadline: float) -> Optional[bytes]:
        assert self._serial is not None
        while time.time() < deadline:
            try:
                b = self._serial.read(1)
            except Exception as exc:
                raise LidarReadError(str(exc)) from exc
            if not b:
                continue
            if b[0] != LD06_HEADER:
                continue
            rest = self._serial.read(LD06_PACKET_SIZE - 1)
            if len(rest) != LD06_PACKET_SIZE - 1:
                return None
            packet = b + rest
            if packet[1] != LD06_VER_LEN:
                continue
            return packet
        return None


class MockLD06Lidar:
    """桌面端测试用雷达，返回一个稳定的前方矩形轮廓。"""

    def __init__(self, config: LD06Config | None = None):
        self.config = config or LD06Config()
        self._tick = 0

    def open(self):
        logger.info("使用 Mock LD06 雷达")

    def read_scan(self, timeout: float = 1.0) -> list[PolarPoint]:
        time.sleep(min(timeout, 0.05))
        self._tick += 1
        points: list[PolarPoint] = []
        for angle in range(180, 361, 2):
            rad = math.radians(270 - angle)
            # 前方墙 + 左右边界，制造足够的可匹配结构。
            distance = 3.0
            if abs(math.sin(rad)) > 0.65:
                distance = min(distance, 1.8 / abs(math.sin(rad)))
            points.append((float(angle), distance, 180))
        return points

    def flush_input(self):
        pass

    def close(self):
        pass


def create_lidar(config: dict):
    lidar_cfg = LD06Config.from_dict(config)
    try:
        lidar = LD06Lidar(lidar_cfg)
        lidar.open()
        return lidar
    except Exception as exc:
        logger.warning("LD06 不可用 —— 使用 Mock 雷达: %s", exc)
        mock = MockLD06Lidar(lidar_cfg)
        mock.open()
        return mock
