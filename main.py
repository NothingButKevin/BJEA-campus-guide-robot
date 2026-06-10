"""校园导览机器人 —— 统一入口。

用法::

    python main.py                      # 交互式配置 → 启动
    python main.py --quick              # 跳过问答，默认配置启动
    python main.py --demo               # 语音控制行进 demo
    python main.py --config path/to/config.yaml
"""

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path

# 确保 src/ 在 Python 路径中，使内部 import 在任意调用目录下都能正常工作
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

logger = logging.getLogger("robot")


# ------------------------------------------------------------------
# 交互式配置
# ------------------------------------------------------------------

def _ask(prompt: str, default: str = "", valid: set = None) -> str:
    """带提示的 input()。空输入返回 default；非法输入重试。"""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        if valid is None or raw.lower() in valid:
            return raw.lower()
        print(f"  非法输入「{raw}」，请重试。")


def _can_show_gui() -> bool:
    """检测是否有图形显示器可用（不创建 Tk 实例，避免干扰后续 GUI）。"""
    # macOS/Linux 有 DISPLAY 环境变量或是在原生桌面环境
    if sys.platform == "darwin":
        return True  # Mac 始终有显示器
    if os.environ.get("DISPLAY"):
        return True
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    # Pi 上检查 /dev/fb0
    if os.path.exists("/dev/fb0"):
        return True
    return False


def interactive_setup() -> dict:
    """交互式问答，返回运行配置 dict。"""

    # ── 颜色 ──
    C = {"cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
         "bold": "\033[1m", "reset": "\033[0m"}
    if not sys.stdout.isatty():
        C = {k: "" for k in C}  # 非终端则禁用颜色

    print()
    print(f"{C['bold']}BJEA 校园导览机器人 — 启动配置{C['reset']}")
    print("-" * 40)

    # Q1: 环境
    print(f"\n{C['cyan']}1. 运行环境？{C['reset']}")
    print("   [1] Mac 开发")
    print("   [2] 树莓派（有屏幕）")
    print("   [3] 树莓派（SSH 远程）")
    env = _ask(f"  选择 {C['yellow']}[1]{C['reset']}: ", "1", {"1", "2", "3"})

    if env == "3":
        # SSH — 无 GUI，仅 CLI
        enable_gui = False
        enable_cli = True
        fullscreen = False
        show_cursor = True
    elif env == "2":
        enable_gui = True
        enable_cli = False
        fullscreen = True
        show_cursor = False
    else:  # "1" or default
        enable_gui = _can_show_gui()
        enable_cli = True
        fullscreen = False
        show_cursor = True

    # Q2: 模式
    print(f"\n{C['cyan']}2. 运行模式？{C['reset']}")
    print("   [1] 正常运行")
    print("   [2] 调试运行（详细日志 + 模块诊断）")
    mode = _ask(f"  选择 {C['yellow']}[1]{C['reset']}: ", "1", {"1", "2"})
    debug = mode == "2"

    # Q3: GUI（仅在非 SSH 且有 display 时问）
    if env != "3" and _can_show_gui():
        default_gui = "y" if enable_gui else "n"
        ans = _ask(
            f"\n{C['cyan']}3. 启动 GUI 脸部？{C['reset']} ({C['yellow']}y{C['reset']}/n) [{default_gui}]: ",
            default_gui,
            {"y", "n", "yes", "no"},
        )
        enable_gui = ans.startswith("y")

    # CLI 始终启动（刚性要求）
    enable_cli = True

    # ── 摘要 ──
    print(f"\n{C['bold']}══════════════════{C['reset']}")
    print(f"  环境       : {['Mac 开发', '树莓派', 'SSH 远程'][int(env)-1]}")
    print(f"  模式       : {'调试' if debug else '正常'}")
    print(f"  GUI 脸部   : {'开启' if enable_gui else '关闭'}")
    print(f"  CLI 控制台 : 开启（始终）")
    print(f"{C['bold']}══════════════════{C['reset']}")
    _ask(f"\n{C['yellow']}按 Enter 启动...{C['reset']}", "")

    return {
        "enable_gui": enable_gui,
        "enable_cli": enable_cli,
        "debug": debug,
        "fullscreen": fullscreen,
        "show_cursor": show_cursor,
    }


# ------------------------------------------------------------------
def run_navigation(config_path: str, enable_gui: bool = True, enable_cli: bool = True,
                   fullscreen: bool = True, show_cursor: bool = False,
                   debug: bool = False):
    """启动完整的校园导览状态机。"""
    import yaml

    from robot import Robot
    from ui.cli_console import CLIConsole
    from ui.gui_display import RobotFace

    # 加载配置并注入运行时覆盖
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    ui_cfg = cfg.setdefault("ui", {}).setdefault("gui", {})
    ui_cfg["fullscreen"] = fullscreen
    ui_cfg["cursor_visible"] = show_cursor

    robot = Robot(config_path)

    gui: RobotFace | None = None
    cli: CLIConsole | None = None

    shutdown_event = threading.Event()

    # --- 信号处理 ---
    def _signal_handler(signum, frame):
        logger.info("收到信号 %s，正在关机...", signum)
        shutdown_event.set()
        robot.cmd_queue.put("shutdown")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # --- 调试诊断 ---
    if debug:
        import time
        print(f"\n{'='*40}")
        print(f"  Robot      : state={robot.state.name}")
        print(f"  Recognizer : loaded")
        print(f"  Synthesizer: loaded")
        print(f"  LLM        : {'loaded' if robot._llm else 'lazy'}")
        print(f"  Motor      : {type(robot.motor).__name__}")
        print(f"  Sensors    : Mock={getattr(robot.sensors, '_mpu', None) is None}")
        print(f"  Navigator  : {len(robot.navigator.routes)} routes")
        print(f"{'='*40}\n")
        time.sleep(0.5)

    # --- 启动 CLI ---
    if enable_cli:
        cli_cfg = cfg.get("ui", {}).get("cli", {})
        cli = CLIConsole(robot, color_output=cli_cfg.get("color_output", True))
        cli.start()
        logger.info("CLI 控制台已启动")

    # --- 检查 GUI 可用性 ---
    if enable_gui:
        if not _can_show_gui():
            logger.warning("无可用显示器，GUI 已禁用")
            enable_gui = False
        else:
            gui = RobotFace(cfg)

    # --- 启动 Robot ---
    robot_thread = threading.Thread(
        target=robot.run,
        name="robot-main",
        daemon=False,
    )
    robot_thread.start()

    # --- 启动 GUI ---
    if gui:
        gui.attach(robot)

        def _on_gui_close():
            robot.cmd_queue.put("shutdown")

        gui.protocol("WM_DELETE_WINDOW", _on_gui_close)

        def _check_shutdown():
            if shutdown_event.is_set() or robot.state.name == "SHUTDOWN":
                gui.destroy()
                return
            gui.after(500, _check_shutdown)

        gui.after(500, _check_shutdown)
        gui.mainloop()

    # 等待 robot 线程退出
    robot_thread.join(timeout=15)

    # --- 清理 ---
    if cli:
        cli.stop()
    logger.info("应用已退出。")
    sys.exit(0)


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
    parser.add_argument(
        "--quick",
        action="store_true",
        help="跳过交互式配置，使用默认设置启动。",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="（配合 --quick）禁用 GUI。",
    )
    parser.add_argument(
        "--no-cli",
        action="store_true",
        help="（配合 --quick）禁用 CLI。",
    )

    args = parser.parse_args()

    # Demo 模式：不经过交互配置
    if args.demo:
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        run_demo(args.config)
        return

    # 普通模式：交互式配置
    if args.quick:
        setup = {
            "enable_gui": not args.no_gui,
            "enable_cli": not args.no_cli,
            "debug": args.log_level == "DEBUG",
            "fullscreen": True,
            "show_cursor": False,
        }
    else:
        setup = interactive_setup()

    log_level = "DEBUG" if setup["debug"] else args.log_level
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_navigation(
        args.config,
        enable_gui=setup["enable_gui"],
        enable_cli=setup["enable_cli"],
        fullscreen=setup["fullscreen"],
        show_cursor=setup["show_cursor"],
        debug=setup["debug"],
    )


if __name__ == "__main__":
    main()
