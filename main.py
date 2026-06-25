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
    print(f"   {C['green']}[4] 地图录入模式{C['reset']}")
    ans = _ask(f"  选择 {C['yellow']}[1]{C['reset']}: ", "1", {"1", "2", "3", "4"})
    debug = ans == "2"
    remote_mode = ans == "3"
    map_record_mode = ans == "4"

    enable_gui = not remote_mode and not map_record_mode
    enable_cli = not remote_mode and not map_record_mode

    # ── 摘要 ──
    _mode_label = "地图录入" if map_record_mode else ("遥控" if remote_mode else ("调试" if debug else "正常"))
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
        "map_record_mode": map_record_mode,
    }


# ------------------------------------------------------------------
def run_navigation(config_path: str, enable_gui: bool = True, enable_cli: bool = True,
                   fullscreen: bool = True, show_cursor: bool = False,
                   debug: bool = False, selected_map=None):
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
    robot.loaded_map = selected_map
    if selected_map is not None:
        robot._cfg.setdefault("mapping", {})["active_map"] = selected_map.name
        logger.info("已载入地图: %s (%s 点, %s waypoint)", selected_map.name, len(selected_map.points), len(selected_map.waypoints))
    else:
        logger.info("未载入地图")
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


def _select_mapping_map(storage):
    """交互式选择或创建地图。"""
    maps = storage.list_maps()
    print()
    print("BJEA 地图录入模式 — 地图选择")
    print("-" * 40)
    if maps:
        for i, name in enumerate(maps, start=1):
            print(f"  [{i}] {name}")
        print()
        print("输入数字选择已有地图；输入新名称创建地图。")
    else:
        print("当前没有已有地图。输入地图名称创建新地图。")

    while True:
        raw = input("地图: ").strip()
        if not raw:
            print("地图名称不能为空。")
            continue
        if raw.isdigit() and maps:
            idx = int(raw)
            if 1 <= idx <= len(maps):
                return storage.load(maps[idx - 1]), False
            print("地图编号不存在。")
            continue
        if storage.exists(raw):
            return storage.load(raw), False
        return storage.create(raw), True


def _select_navigation_map(config_path: str):
    """正常运行前选择已有地图；无地图或取消时退出程序。"""
    import yaml

    from mapping.storage import MapStorage

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    storage = MapStorage(cfg.get("mapping", {}).get("maps_dir", "maps"))
    maps = storage.list_maps()
    print()
    print("请选择要载入的地图")
    print("-" * 40)
    if not maps:
        print("当前没有已有地图。请先进入地图录入模式创建地图。")
        raise SystemExit(1)

    for i, name in enumerate(maps, start=1):
        print(f"  [{i}] {name}")
    print()
    print("输入数字选择地图；直接按 Enter 退出。")

    while True:
        raw = input("地图: ").strip()
        if not raw:
            print("未选择地图，退出。")
            raise SystemExit(1)
        if not raw.isdigit():
            print("请输入地图编号，或直接按 Enter 退出。")
            continue
        idx = int(raw)
        if 1 <= idx <= len(maps):
            return storage.load(maps[idx - 1])
        print("地图编号不存在。")


def run_mapping(config_path: str):
    """启动地图录入模式：HTTP 遥控 + LD06 建图 + CLI waypoint。"""
    import yaml

    from hardware.lidar_ld06 import create_lidar
    from hardware.motor import create_motor
    from mapping.map_model import Pose
    from mapping.mapper import MapperConfig, PointCloudMapper
    from mapping.storage import MapStorage
    from remote.qrcode_util import display_qr, get_local_ip
    from remote.server import RemoteControlHandler, create_server

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    storage = MapStorage(cfg.get("mapping", {}).get("maps_dir", "maps"))
    point_map, created = _select_mapping_map(storage)
    point_map.metadata.setdefault("lidar", cfg.get("lidar", {}))
    point_map.metadata.setdefault("mapping", cfg.get("mapping", {}))
    logger.info("地图录入模式 —— %s地图: %s", "新建" if created else "加载", point_map.name)

    motor = create_motor(cfg.get("motor", {}))
    motor.stop()
    motor.center_steering()

    lidar = create_lidar(cfg.get("lidar", {}))

    mapper = PointCloudMapper(
        point_map,
        storage,
        MapperConfig.from_dict(cfg.get("mapping", {})),
        lidar=lidar,
    )
    port = cfg.get("remote", {}).get("port", 8080)
    host = "0.0.0.0"
    local_ip = get_local_ip()
    base_url = f"http://{local_ip}:{port}"
    map_url = f"{base_url}/map"

    display_qr(
        base_url,
        title="地图录入模式",
        exit_hint="同一页面遥控、采快照、查看地图；终端输入 h 查看备用命令",
    )
    print(f"    地图录入页面: {base_url}")
    print()

    def _snapshot_api(params: dict) -> dict:
        pose_data = params.get("initial_pose")
        initial_pose = None
        if isinstance(pose_data, dict):
            initial_pose = Pose.from_dict(pose_data)
        result = mapper.capture_and_integrate(str(params.get("name", "")), initial_pose)
        return {"status": "ok", "match": result.as_dict(), "map": mapper.snapshot()}

    def _waypoint_api(params: dict) -> dict:
        wp = mapper.add_waypoint(str(params.get("name", "")).strip())
        return {"status": "ok", "waypoint": wp.as_dict(), "map": mapper.snapshot()}

    def _save_api(params: dict) -> dict:
        path = storage.save(point_map)
        return {"status": "ok", "path": str(path)}

    def _pose_api(params: dict) -> dict:
        pose = Pose(
            float(params.get("x", 0.0)),
            float(params.get("y", 0.0)),
            float(params.get("yaw", 0.0)),
        )
        mapper.set_pose(pose)
        return {"status": "ok", "pose": pose.as_dict(), "map": mapper.snapshot()}

    def _accept_candidate_api(params: dict) -> dict:
        result = mapper.accept_candidate(
            int(params.get("rank", 1)),
            str(params.get("name", "")),
        )
        return {"status": "ok", "match": result.as_dict(), "map": mapper.snapshot()}

    def _discard_snapshot_api(params: dict) -> dict:
        return {"status": "ok", "map": mapper.discard_pending_snapshot()}

    server = create_server(
        host,
        port,
        motor,
        map_snapshot_provider=mapper.snapshot,
        snapshot_handler=_snapshot_api,
        waypoint_handler=_waypoint_api,
        save_handler=_save_api,
        pose_handler=_pose_api,
        accept_candidate_handler=_accept_candidate_api,
        discard_snapshot_handler=_discard_snapshot_api,
    )
    server_thread = threading.Thread(target=server.serve_forever, name="mapping-http-server", daemon=True)
    server_thread.start()
    logger.info("地图录入 HTTP 服务已启动: %s", base_url)

    shutdown_flag = threading.Event()

    def _signal_handler(signum, frame):
        logger.info("收到信号 %s，正在关闭地图录入模式...", signum)
        shutdown_flag.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    def _print_help():
        print("  snap xxx     停稳后采集快照并拼接")
        print("  new xxx      在当前位置新建/覆盖 waypoint")
        print("  del xxx      删除 waypoint")
        print("  pose x y yaw 手动设置当前位置")
        print("  list         列出 waypoint")
        print("  save         保存地图")
        print("  h/help       显示帮助")
        print("  q/quit/exit  保存并退出")

    print("地图录入命令：")
    _print_help()

    try:
        while not shutdown_flag.is_set():
            try:
                cmd = input("map> ").strip()
            except EOFError:
                shutdown_flag.wait()
                break
            if not cmd:
                continue
            lower = cmd.lower()
            if lower in {"q", "quit", "exit"}:
                break
            if lower in {"h", "help"}:
                _print_help()
                continue
            if lower == "save":
                path = storage.save(point_map)
                print(f"已保存: {path}")
                continue
            if lower.startswith("pose "):
                parts = cmd.split()
                if len(parts) != 4:
                    print("用法: pose x y yaw")
                    continue
                pose = mapper.set_pose(Pose(float(parts[1]), float(parts[2]), float(parts[3])))
                print(f"当前位姿: x={pose.x:.2f}, y={pose.y:.2f}, yaw={pose.yaw:.1f}")
                continue
            if lower == "list":
                snapshot = point_map.snapshot()
                waypoints = snapshot["waypoints"]
                if not waypoints:
                    print("当前地图没有 waypoint。")
                for wp in waypoints:
                    print(f"  {wp['name']}: x={wp['x']:.2f}, y={wp['y']:.2f}, yaw={wp['yaw']:.1f}")
                continue
            if cmd.startswith("snap "):
                name = cmd[5:].strip()
                result = mapper.capture_and_integrate(name)
                storage.save(point_map)
                print(
                    f"快照 {name or '-'}: {'成功' if result.accepted else '失败'} "
                    f"overlap={result.overlap_ratio:.2f} error={result.mean_error_m:.3f} "
                    f"pose=({result.pose.x:.2f},{result.pose.y:.2f},{result.pose.yaw:.1f})"
                )
                continue
            if cmd.startswith("new "):
                name = cmd[4:].strip()
                try:
                    wp = mapper.add_waypoint(name)
                    print(f"已创建 waypoint {wp.name}: x={wp.x:.2f}, y={wp.y:.2f}, yaw={wp.yaw:.1f}")
                except ValueError as exc:
                    print(str(exc))
                continue
            if cmd.startswith("del "):
                name = cmd[4:].strip()
                if point_map.delete_waypoint(name):
                    storage.save(point_map)
                    print(f"已删除 waypoint: {name}")
                else:
                    print(f"未找到 waypoint: {name}")
                continue
            print(f"未知命令: {cmd}")
            _print_help()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    finally:
        logger.info("正在停止地图录入模式...")
        try:
            storage.save(point_map)
        except Exception as exc:
            logger.error("保存地图失败: %s", exc)
        server.shutdown()
        RemoteControlHandler.cleanup()
        try:
            lidar.close()
        except Exception:
            pass
        motor.stop()
        motor.center_steering()
        motor.cleanup()
        logger.info("地图录入模式已退出。")
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
    parser.add_argument(
        "--map-record",
        action="store_true",
        help="（配合 --quick）直接进入地图录入模式。",
    )
    parser.add_argument(
        "--map-name",
        default="",
        help="正常运行时直接载入指定地图；未指定时交互式启动会提示选择。",
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
            "enable_gui": not args.no_gui and not args.remote and not args.map_record,
            "enable_cli": not args.no_cli and not args.remote and not args.map_record,
            "debug": args.log_level == "DEBUG",
            "fullscreen": True,
            "show_cursor": False,
            "remote_mode": args.remote,
            "map_record_mode": args.map_record,
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

    if setup.get("map_record_mode"):
        run_mapping(args.config)
        return

    if args.map_name:
        from mapping.storage import MapStorage
        import yaml

        with open(args.config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        selected_map = MapStorage(cfg.get("mapping", {}).get("maps_dir", "maps")).load(args.map_name)
    elif args.quick:
        print("正常运行模式必须载入地图。请使用 --map-name 指定地图，或不要使用 --quick 以交互选择。")
        raise SystemExit(1)
    else:
        selected_map = _select_navigation_map(args.config)

    run_navigation(
        args.config,
        enable_gui=setup["enable_gui"],
        enable_cli=setup["enable_cli"],
        fullscreen=setup["fullscreen"],
        show_cursor=setup["show_cursor"],
        debug=setup["debug"],
        selected_map=selected_map,
    )


if __name__ == "__main__":
    main()
