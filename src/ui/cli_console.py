"""CLI 控制台 —— 在守护线程中监听 stdin，将命令注入 robot。

命令集：
    y / yes     确认（CONFIRMING 状态时有效）
    n / no      取消
    s / status  打印当前状态
    d / debug   打印各模块调试信息
    l / log     切换日志级别
    h / help    显示帮助
    q / quit    安全关机
"""

import io
import logging
import sys
import threading

logger = logging.getLogger(__name__)

_BANNER = """\
═══════════════════════════════════════════
  BJEA 校园导览机器人 v0.1.0
  控制台已就绪。输入 h 查看帮助。
═══════════════════════════════════════════"""


class CLIConsole:
    """CLI 控制台，运行在守护线程中。"""

    def __init__(self, robot, color_output: bool = True):
        """
        参数:
            robot: Robot 实例
            color_output: 是否启用彩色终端输出
        """
        self._robot = robot
        self._color = color_output and sys.stdout.isatty()
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    def start(self):
        """在守护线程中启动 CLI 输入循环。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._input_loop, daemon=True, name="cli-console")
        self._thread.start()
        logger.debug("CLI 控制台线程已启动")

    def stop(self):
        """设置退出标志并等待线程结束。"""
        self._running = False
        # 向 stdin 注入换行使 input() 解除阻塞（hack）
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.debug("CLI 控制台线程已停止")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _print(self, text: str, color: str = ""):
        """打印到 stdout。*color* 为 ANSI 颜色名或空字符串。"""
        if self._color and color:
            codes = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "red": "\033[31m",
                "bold": "\033[1m",
            }
            prefix = codes.get(color, "")
            suffix = "\033[0m" if prefix else ""
            print(f"{prefix}{text}{suffix}")
        else:
            print(text)

    def _input_loop(self):
        """主输入循环（在守护线程中运行）。

        使用 sys.stdin.readline() 而非 input()，因为 macOS 上 tkinter
        会劫持 PyOS_InputHook，导致非主线程中 input() → Tcl_WaitForEvent → abort。
        """
        self._print(_BANNER, "cyan")

        while self._running:
            # 打印提示符（用 sys.stdout.write 避免 print 的线程安全问题）
            sys.stdout.write("> ")
            sys.stdout.flush()

            try:
                user_input = sys.stdin.readline()
            except Exception:
                self._print("CLI 输入中断。", "yellow")
                self._running = False
                break

            # readline 在 EOF 时返回空字符串
            if not user_input:
                self._print("stdin 已关闭，CLI 输入暂停。", "yellow")
                self._running = False
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            handled = self._robot.process_cli_command(user_input)

            if not handled:
                self._print(f"未知命令: {user_input}。输入 h 查看帮助。", "yellow")

        self._running = False
