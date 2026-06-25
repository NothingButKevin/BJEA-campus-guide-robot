#!/usr/bin/env python3
"""捕获 LD06 雷达两整圈原始数据，存 JSON。在树莓派上运行。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hardware.lidar_ld06 import LD06Lidar, LD06Config, LD06_POINTS_PER_PACKET


def main():
    config = LD06Config()
    lidar = LD06Lidar(config)
    lidar.open()

    print("开始采集两整圈 (≥720 个原始点)...")
    all_points: list[dict] = []
    seen_first_angle = False
    first_angle = None
    crossed_zero_count = 0  # 统计经过 0° 的次数来判断圈数

    deadline = time.time() + 8.0  # 最长 8 秒，防止死循环
    last_angle = None
    last_flush = time.time()

    while time.time() < deadline:
        packet = lidar._read_packet(time.time() + 0.5)
        if packet is None:
            continue

        try:
            # 直接解析原始极坐标，不做角度修正
            from hardware.lidar_ld06 import (
                LD06_HEADER, LD06_VER_LEN, LD06_POINTS_PER_PACKET,
                _u16,
            )

            start_angle_raw = _u16(packet, 4) / 100.0
            end_angle_raw = _u16(packet, 42) / 100.0
            span = (end_angle_raw - start_angle_raw) % 360.0
            step = span / (LD06_POINTS_PER_PACKET - 1)

            offset = 6
            for i in range(LD06_POINTS_PER_PACKET):
                distance_mm = _u16(packet, offset)
                confidence = packet[offset + 2]
                raw_angle = (start_angle_raw + step * i) % 360.0

                if not seen_first_angle:
                    first_angle = raw_angle
                    seen_first_angle = True

                # 检测角度穿越 0°/360° 边界
                if last_angle is not None and last_angle > 300 and raw_angle < 60:
                    crossed_zero_count += 1
                    print(f"  → 第 {crossed_zero_count} 次过零，当前点数: {len(all_points)}")

                last_angle = raw_angle

                if distance_mm > 0:
                    all_points.append({
                        "angle_deg": round(raw_angle, 2),
                        "distance_m": round(distance_mm / 1000.0, 4),
                        "confidence": confidence,
                    })
                offset += 3

            # 过了 3 次零 = 已经集满两整圈
            if crossed_zero_count >= 3:
                print(f"已采集两整圈，共 {len(all_points)} 个有效点")
                break

            # 每秒刷新一次进度
            if time.time() - last_flush > 1.0:
                print(f"  当前已采集 {len(all_points)} 个点...")
                last_flush = time.time()

        except Exception as exc:
            print(f"包解析异常: {exc}")
            continue

    lidar.close()

    if len(all_points) < 100:
        print(f"⚠️ 点数过少 ({len(all_points)})，雷达可能未正常运转")
        sys.exit(1)

    out_path = Path.home() / "lidar_two_turns.json"
    out_path.write_text(json.dumps(all_points, ensure_ascii=False), encoding="utf-8")
    print(f"✅ 已保存 {len(all_points)} 个原始点到 {out_path}")
    print(f"   首点角度: {all_points[0]['angle_deg']}°, 末点角度: {all_points[-1]['angle_deg']}°")
    print(f"   距离范围: {min(p['distance_m'] for p in all_points):.3f}m ~ {max(p['distance_m'] for p in all_points):.3f}m")


if __name__ == "__main__":
    main()
