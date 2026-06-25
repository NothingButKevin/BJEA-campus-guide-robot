import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from hardware.lidar_ld06 import LD06Config, LD06Lidar, LD06_PACKET_SIZE, ld06_crc, parse_ld06_packet


def _packet(start_angle=9000, end_angle=10100):
    data = bytearray(LD06_PACKET_SIZE)
    data[0] = 0x54
    data[1] = 0x2C
    data[2] = 0x00
    data[3] = 0x00
    data[4] = start_angle & 0xFF
    data[5] = start_angle >> 8
    offset = 6
    for i in range(12):
        distance = 1000 + i * 10
        data[offset] = distance & 0xFF
        data[offset + 1] = distance >> 8
        data[offset + 2] = 180
        offset += 3
    data[42] = end_angle & 0xFF
    data[43] = end_angle >> 8
    data[44] = 0
    data[45] = 0
    data[46] = ld06_crc(bytes(data[:-1]))
    return bytes(data)


def test_parse_valid_packet():
    points = parse_ld06_packet(_packet(), inverted=False)
    assert len(points) == 12
    assert points[0] == (90.0, 1.0, 180)
    assert points[-1][0] == 101.0
    assert points[-1][1] == pytest.approx(1.11)


def test_inverted_angle_reverses_direction():
    points = parse_ld06_packet(_packet(start_angle=9000, end_angle=9000), inverted=True)
    assert points[0][0] == 270.0


def test_invalid_crc_is_rejected():
    packet = bytearray(_packet())
    packet[-1] ^= 0xFF
    with pytest.raises(ValueError):
        parse_ld06_packet(bytes(packet), inverted=False)


class _FakeSerial:
    def __init__(self, packets):
        self.buffer = b"".join(packets)
        self.reset_count = 0

    def read(self, size):
        if not self.buffer:
            return b""
        data = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return data

    def reset_input_buffer(self):
        self.reset_count += 1


def test_lidar_read_scan_waits_for_angle_coverage():
    packets = [_packet(start_angle=0, end_angle=1100) for _ in range(40)]
    lidar = LD06Lidar(LD06Config())
    lidar._serial = _FakeSerial(packets)

    points = lidar.read_scan(timeout=0.2)

    assert len(points) > 360


def test_lidar_flush_input_resets_serial_buffer():
    lidar = LD06Lidar(LD06Config())
    serial = _FakeSerial([])
    lidar._serial = serial

    lidar.flush_input()

    assert serial.reset_count == 1
