"""最简电机初始化测试 —— 仅创建电机并保持中立。

用法：在树莓派上运行  python tests/manual_motor_test.py
期望：电机完全静止。如左后右停则问题在 motor.py 初始化层。
"""
import sys
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

import yaml
from hardware.motor import create_motor

with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

motor = create_motor(cfg.get("motor", {}))
print(f"电机类型: {type(motor).__name__}")
motor.stop()
motor.center_steering()
print("已设 throttle=0 steer=0 → 均为 7.5% 占空比")
print("预期：电机静止。Ctrl+C 退出。")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    motor.cleanup()
    print("结束。")
