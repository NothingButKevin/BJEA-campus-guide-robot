"""校园导览机器人 —— 统一入口。

用法::

    python main.py                  # 完整导航工作流
    python main.py --demo           # 语音控制行进 demo
    python main.py --config path/to/config.yaml
"""

import argparse
import logging
import sys
from pathlib import Path

# 确保 src/ 在 Python 路径中，使内部 import 在任意调用目录下都能正常工作
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

logger = logging.getLogger("robot")


def run_navigation(config_path: str):
    """启动完整的校园导览状态机。"""
    from robot import Robot

    robot = Robot(config_path)
    robot.run()


def run_demo(config_path: str):
    """启动语音控制行进 demo。"""
    from demo import run as demo_run

    demo_run(config_path)


# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="BJEA 校园导览机器人")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="运行语音控制行进 demo（而非完整导航）。",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="日志输出级别。",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.demo:
        run_demo(args.config)
    else:
        run_navigation(args.config)


if __name__ == "__main__":
    main()
