"""校园导览机器人 —— 统一入口。

用法::

    python main.py                      # 交互式配置 → 启动
    python main.py --quick              # 跳过问答，默认配置启动
    python main.py --demo               # 语音控制行进 demo
    python main.py --config path/to/config.yaml
"""

import argparse
import logging
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

    # Q1: 显示模式（树莓派默认全屏，其他平台默认窗口）
    _pi_model = Path("/proc/device-tree/model")
    _is_pi = _pi_model.exists() and "raspberry pi" in _pi_model.read_text().lower()
    _default_display = "2" if _is_pi else "1"
    print(f"\n{C['cyan']}1. 显示模式？{C['reset']}")
    print("   [1] 窗口模式")
    print("   [2] 全屏模式")
    ans = _ask(f"  选择 {C['yellow']}[{_default_display}]{C['reset']}: ", _default_display, {"1", "2"})
    fullscreen = ans == "2"
    show_cursor = not fullscreen

    # Q2: 运行模式
    print(f"\n{C['cyan']}2. 运行模式？{C['reset']}")
    print("   [1] 正常运行")
    print("   [2] 调试运行（详细日志 + 模块诊断）")
    print(f"   {C['green']}[3] 遥控模式{C['reset']}")
    ans = _ask(f"  选择 {C['yellow']}[1]{C['reset']}: ", "1", {"1", "2", "3"})
    debug = ans == "2"
    remote_mode = ans == "3"

    enable_gui = not remote_mode
    enable_cli = not remote_mode

    # ── 摘要 ──
    _mode_label = "遥控" if remote_mode else ("调试" if debug else "正常")
    print(f"\n{C['bold']}══════════════════{C['reset']}")
    print(f"  显示模式   : {'全屏' if fullscreen else '窗口'}")
    print(f"  运行模式   : {_mode_label}")
    print(f"{C['bold']}══════════════════{C['reset']}")
    _ask(f"\n{C['yellow']}按 Enter 启动...{C['reset']}", "")

    return {
        "enable_gui": enable_gui,
        "enable_cli": enable_cli,
        "debug": debug,
        "fullscreen": fullscreen,
        "show_cursor": show_cursor,
        "remote_mode": remote_mode,
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
    robot.face_detector._debug = debug  # 调试模式：启用摄像头预览窗口

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

    # --- 启动 GUI ---
    if enable_gui:
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


def run_remote(config_path: str):
    """启动遥控模式：HTTP 服务器 + 电机控制，无 GUI/语音/LLM。"""
    import socket
    import yaml

    from hardware.motor import create_motor
    from remote.qrcode_util import display_qr, get_local_ip
    from remote.server import create_server

    # 只加载电机配置段（不需要 ASR/TTS/LLM 等）
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    motor = create_motor(cfg.get("motor", {}))
    logger.info("遥控模式 —— 电机控制器: %s", type(motor).__name__)

    # 显式确保电机处于停止 / 直行状态
    motor.stop()
    motor.center_steering()
    logger.info("电机已初始化为中立位")

    # 端口配置
    port = cfg.get("remote", {}).get("port", 8080)
    host = "0.0.0.0"

    # 获取局域网 IP
    local_ip = get_local_ip()
    url = f"http://{local_ip}:{port}"

    # 显示二维码
    display_qr(url)

    # 启动 HTTP 服务器
    server = create_server(host, port, motor)
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="http-server",
        daemon=True,
    )
    server_thread.start()
    logger.info("HTTP 服务器已启动: %s", url)

    # ── 信号处理 ──
    shutdown_flag = threading.Event()

    def _signal_handler(signum, frame):
        logger.info("收到信号 %s，正在关闭...", signum)
        shutdown_flag.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── 主循环：等待 'q' 或信号 ──
    try:
        while not shutdown_flag.is_set():
            try:
                cmd = input()
            except EOFError:
                # stdin 关闭（如被重定向），等待信号
                shutdown_flag.wait()
                break
            if cmd.strip().lower() == "q":
                logger.info("收到 'q' 命令，正在关闭...")
                break
            elif cmd.strip().lower() == "h":
                print("  q — 退出遥控模式")
                print("  h — 显示帮助")
    except KeyboardInterrupt:
        logger.info("收到中断信号")

    # ── 清理 ──
    logger.info("正在停止遥控模式...")
    server.shutdown()
    from remote.server import RemoteControlHandler
    RemoteControlHandler.cleanup()
    motor.cleanup()
    logger.info("遥控模式已退出。")
    sys.exit(0)


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
    parser.add_argument(
        "--remote",
        action="store_true",
        help="（配合 --quick）直接进入遥控模式。",
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
            "enable_gui": not args.no_gui and not args.remote,
            "enable_cli": not args.no_cli and not args.remote,
            "debug": args.log_level == "DEBUG",
            "fullscreen": True,
            "show_cursor": False,
            "remote_mode": args.remote,
        }
    else:
        setup = interactive_setup()

    log_level = "DEBUG" if setup["debug"] else args.log_level
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 遥控模式分支
    if setup.get("remote_mode"):
        run_remote(args.config)
        return

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
