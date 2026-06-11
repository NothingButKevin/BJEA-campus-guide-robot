"""机器人脸部 GUI —— tkinter 全屏显示。

- 上部：大号 emoji（PNG 图片或 Unicode 回退）
- 下部：动态内容区（波形图 / 字幕 / 导航状态 / 提示文字）
- 每 ~33ms 轮询 robot 状态并更新 UI
"""

import logging
import os
import random
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

logger = logging.getLogger(__name__)

# 回退 emoji Unicode 字符（当 PNG 缺失时使用）
_FALLBACK_EMOJI = {
    "IDLE": "😊",
    "LISTENING": "🎧",
    "MATCHING": "🤔",
    "CONFIRMING": "❓",
    "CHATTING": "💬",
    "NAVIGATING": "🚗",
    "ARRIVED": "🎉",
    "SHUTDOWN": "😴",
    "STANDBY": "😴",
}


class WaveformCanvas(tk.Canvas):
    """64 条竖纹的音频频谱可视化 Canvas。"""

    def __init__(self, parent, config: dict, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        self._config = config
        self._bar_count = config.get("bars", 64)
        self._base_color = config.get("color", "#4a9eff")
        self._peak_color = config.get("peak_color", "#00ff88")
        self._bars: list[int] = []  # Canvas 矩形 ID 列表
        self._history: list[float] = [0.0] * self._bar_count  # 频谱历史（衰减用）
        self._built = False

    def _build_bars(self):
        """根据当前 Canvas 尺寸创建居中的竖条矩形。"""
        self.delete("all")
        self._bars.clear()

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        n = self._bar_count
        bar_w = max(4, (w * 0.6) / n)
        gap = max(2, bar_w * 0.25)
        total_width = n * (bar_w + gap) - gap
        offset_x = (w - total_width) / 2
        mid_y = h / 2  # 中轴线

        for i in range(n):
            x1 = offset_x + i * (bar_w + gap)
            x2 = x1 + bar_w
            # 初始状态：一条细线在中轴
            bar_id = self.create_rectangle(x1, mid_y, x2, mid_y + 1, fill=self._base_color, outline="")
            self._bars.append(bar_id)

        self._built = True

    def update_waveform(self, volume: float):
        """根据当前音量 level 更新竖条高度，以中线为轴上下波动。"""
        w = self.winfo_width()
        h = self.winfo_height()

        if w < 10 or h < 10:
            return

        if not self._built or len(self._bars) != self._bar_count:
            self._build_bars()

        n = self._bar_count
        bar_w = max(4, (w * 0.6) / n)
        gap = max(2, bar_w * 0.25)
        offset_x = (w - (n * (bar_w + gap) - gap)) / 2
        mid_y = h / 2

        # 衰减历史值
        for i in range(n):
            self._history[i] *= 0.85

        # 将 volume 映射到 0.0–1.0 范围
        level = min(1.0, volume / 800.0)

        # 全部条响应音量，中间高两边低
        for i in range(n):
            # 距离中轴越远幅度越小（抛物线分布）
            dist_factor = 1.0 - abs(i - n / 2) / (n / 2) * 0.6
            jitter = random.uniform(0.7, 1.0)
            val = level * dist_factor * jitter
            if val > self._history[i]:
                self._history[i] = val

        # 更新竖条：从中轴上下对称展开
        max_half_h = h * 0.42  # 最大半高
        min_half_h = 1
        for i in range(n):
            half_h = max(min_half_h, int(self._history[i] * max_half_h))
            x1 = offset_x + i * (bar_w + gap)
            x2 = x1 + bar_w
            y1 = mid_y - half_h
            y2 = mid_y + half_h

            color = self._peak_color if self._history[i] > 0.7 else self._base_color

            self.coords(self._bars[i], x1, y1, x2, y2)
            self.itemconfig(self._bars[i], fill=color)

    def reset(self):
        """重置频谱历史（退出 LISTENING 时调用）。"""
        self._history = [0.0] * self._bar_count


class RobotFace(tk.Tk):
    """机器人脸部 GUI 主窗口。"""

    def __init__(self, config: dict):
        super().__init__()
        self._cfg = config.get("ui", {}).get("gui", {})
        self._robot = None

        # --- 窗口设置 ---
        self.title("BJEA Campus Guide Robot")
        self.configure(bg=self._cfg.get("bg_color", "#0d1b2a"))

        fullscreen = self._cfg.get("fullscreen", True)
        if fullscreen and os.environ.get("DISPLAY") is not None:
            try:
                self.attributes("-fullscreen", True)
            except tk.TclError:
                logger.warning("全屏模式不可用，使用窗口模式")
                self.geometry(
                    f"{self._cfg.get('width', 1024)}x{self._cfg.get('height', 600)}"
                )
        else:
            self.geometry(
                f"{self._cfg.get('width', 1024)}x{self._cfg.get('height', 600)}"
            )

        # 全屏时隐藏光标，窗口模式保留光标（方便桌面开发调试）
        if fullscreen and not self._cfg.get("cursor_visible", False):
            self.config(cursor="none")

        # 绑定 Esc 退出全屏 / 关闭
        self.bind("<Escape>", lambda e: self._on_escape())

        # --- 字体 ---
        self._subtitle_font = self._load_font(
            self._cfg.get("subtitle_font_size", 42)
        )
        self._info_font = self._load_font(24)
        self._small_font = self._load_font(16)

        # --- Emoji 预加载 ---
        self._emoji_cache: dict[str, tk.PhotoImage] = {}
        self._load_emoji_images()

        # --- 布局 ---
        self._build_ui()

        # --- 状态追踪 ---
        self._last_state_name: str = ""
        self._last_speech = ""
        self._content_mode: str = ""  # 当前下部显示的布局模式，避免每帧重布局
        self._smooth_progress: float = 0.0  # 插值后的进度条值

    # ------------------------------------------------------------------
    # 字体加载
    # ------------------------------------------------------------------

    @staticmethod
    def _load_font(size: int, bold: bool = False) -> tuple:
        """尝试加载系统中文字体，回退到 tkinter 默认。"""
        candidates = [
            "Noto Sans CJK SC",
            "PingFang SC",
            "Heiti SC",
            "STHeiti",
            "Microsoft YaHei",
            "SimHei",
            "TkDefaultFont",
        ]
        for name in candidates:
            try:
                families = tkfont.families()
                if name in families:
                    weight = "bold" if bold else "normal"
                    return (name, size, weight)
            except Exception:
                pass
        return ("TkDefaultFont", size)

    # ------------------------------------------------------------------
    # Emoji 管理
    # ------------------------------------------------------------------

    def _load_emoji_images(self):
        """预加载所有状态对应的 emoji PNG 到缓存。PNG 缺失时使用 Unicode 回退。"""
        emoji_dir = Path(self._cfg.get("emoji_dir", "resources/ui/emoji"))
        states = [
            "idle", "listening", "matching", "confirming",
            "chatting", "navigating", "arrived", "shutdown",
        ]

        for state_name in states:
            png_path = emoji_dir / f"{state_name}.png"
            if png_path.exists():
                try:
                    from PIL import Image, ImageTk

                    img = Image.open(png_path)
                    self._emoji_cache[state_name] = ImageTk.PhotoImage(img)
                    logger.debug("Emoji PNG 已加载: %s", png_path)
                    continue
                except Exception:
                    logger.warning("Emoji PNG 加载失败: %s，回退 Unicode", png_path)

            # 回退：创建包含 Unicode 字符的 PhotoImage
            self._emoji_cache[state_name] = None
            logger.debug("Emoji '%s' 使用 Unicode 回退", state_name)

    def _get_emoji_for_state(self, state_name: str):
        """返回给定状态使用的 emoji 键名。"""
        mapping = {
            "IDLE": "idle",
            "LISTENING": "listening",
            "MATCHING": "matching",
            "CONFIRMING": "confirming",
            "CHATTING": "chatting",
            "NAVIGATING": "navigating",
            "ARRIVED": "arrived",
            "SHUTDOWN": "shutdown",
            "STANDBY": "shutdown",  # 复用睡眠脸
        }
        return mapping.get(state_name, "idle")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """构建 GUI 组件树。"""
        bg = self._cfg.get("bg_color", "#0d1b2a")

        # 让根窗口的网格行按比例伸缩
        self.grid_rowconfigure(0, weight=55)  # 上部 emoji 区 55%
        self.grid_rowconfigure(1, weight=45)  # 下部内容区 45%
        self.grid_columnconfigure(0, weight=1)

        # --- 上部：Emoji 显示 ---
        self._emoji_frame = tk.Frame(self, bg=bg)
        self._emoji_frame.grid(row=0, column=0, sticky="nsew")
        self._emoji_frame.grid_rowconfigure(0, weight=1)
        self._emoji_frame.grid_columnconfigure(0, weight=1)

        # Emoji Label
        self._emoji_label = tk.Label(
            self._emoji_frame,
            bg=bg,
            font=("Noto Color Emoji", 180),
            text="",
            fg="white",
        )
        self._emoji_label.grid(row=0, column=0)

        # --- 下部：动态内容区 ---
        self._content_frame = tk.Frame(self, bg=bg)
        self._content_frame.grid(row=1, column=0, sticky="nsew")
        self._content_frame.grid_rowconfigure(0, weight=1)
        self._content_frame.grid_columnconfigure(0, weight=1)

        # 波形图 Canvas（LISTENING 时显示）
        wf_cfg = self._cfg.get("waveform", {})
        self._waveform = WaveformCanvas(
            self._content_frame,
            config=wf_cfg,
            bg=bg,
        )

        # 字幕 Label（SPEAKING / 其他状态时显示文字）
        text_color = self._cfg.get("subtitle_color", "#ffffff")
        self._subtitle_label = tk.Label(
            self._content_frame,
            bg=bg,
            fg=text_color,
            font=self._subtitle_font,
            wraplength=self.winfo_screenwidth() * 0.85,
            text="",
            justify="center",
        )

        # 信息 Label（较小文字，NAVIGATING 时显示进度等）
        info_color = self._cfg.get("text_color", "#c0c0c0")
        self._info_label = tk.Label(
            self._content_frame,
            bg=bg,
            fg=info_color,
            font=self._info_font,
            wraplength=self.winfo_screenwidth() * 0.85,
            text="",
            justify="center",
        )

        # 进度条 Canvas（STANDBY 时显示）
        self._progress_canvas = tk.Canvas(
            self._content_frame,
            bg=bg,
            highlightthickness=0,
            height=20,
        )

        # 默认显示 idle 状态
        self._subtitle_label.place(relx=0.5, rely=0.5, anchor="center")
        self._subtitle_label.config(text="你好！请问要去哪里？")
        self._content_mode = "single"

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def attach(self, robot):
        """绑定 robot 实例并启动轮询。所有 tkinter 操作在主线程 _tick() 中完成。"""
        self._robot = robot
        self._last_state_name = robot.state.name
        self._update_emoji(robot.state.name)
        self._tick()

    # ------------------------------------------------------------------
    # 轮询
    # ------------------------------------------------------------------

    def _tick(self):
        """每 ~33ms（30fps）轮询 robot 状态并刷新 UI（纯主线程，不跨线程调 tk）。"""
        if self._robot is None:
            return

        fps = self._cfg.get("fps", 30)
        interval = int(1000 / fps)

        state_name = self._robot.state.name

        # ── Emoji：状态变化时更新（在主线程检测，不依赖跨线程回调）──
        if state_name != self._last_state_name:
            self._last_state_name = state_name
            self._update_emoji(state_name)

        # ── 布局切换：仅在状态类型变化时执行 ──
        new_mode = self._mode_for_state(state_name)
        if new_mode != self._content_mode:
            self._switch_layout(new_mode)
            self._content_mode = new_mode

        # ── 内容更新：每帧只更新数据，不动布局 ──
        self._update_content(state_name)

        self.after(interval, self._tick)

    # ------------------------------------------------------------------
    # 布局模式映射
    # ------------------------------------------------------------------

    @staticmethod
    def _mode_for_state(state_name: str) -> str:
        """将状态名映射到布局模式。"""
        if state_name in ("LISTENING",):
            return "waveform"
        elif state_name in ("STANDBY",):
            return "standby"
        elif state_name == "NAVIGATING":
            return "dual"      # 双行：标题 + 进度
        elif state_name == "CONFIRMING":
            return "dual"
        else:
            return "single"    # 单行文字

    # ------------------------------------------------------------------
    # 布局切换（仅在 mode 变化时调用一次）
    # ------------------------------------------------------------------

    def _switch_layout(self, mode: str):
        """切换下部内容区的 widget 布局（仅在 mode 变化时调用）。"""
        # 离开波形图模式时重置频谱历史
        if self._content_mode == "waveform" and mode != "waveform":
            self._waveform.reset()
        # 进入待机模式时重置进度条
        if mode == "standby" and self._content_mode != "standby":
            self._smooth_progress = 0.0

        self._hide_all_content()

        if mode == "waveform":
            self._waveform.place(relx=0.5, rely=0.5, relwidth=0.95, relheight=0.8, anchor="center")
        elif mode == "standby":
            self._subtitle_label.place(relx=0.5, rely=0.35, anchor="center")
            self._progress_canvas.place(relx=0.5, rely=0.6, relwidth=0.5, height=20, anchor="center")
        elif mode == "dual":
            self._subtitle_label.place(relx=0.5, rely=0.35, anchor="center")
            self._info_label.place(relx=0.5, rely=0.6, anchor="center")
        else:  # single
            self._subtitle_label.place(relx=0.5, rely=0.5, anchor="center")

    # ------------------------------------------------------------------
    # 内容更新（每帧调用，只改 widget 内容，不碰布局）
    # ------------------------------------------------------------------

    def _update_content(self, state_name: str):
        """根据当前状态更新 widget 内容（文字、波形等），不改变布局。"""
        if state_name == "LISTENING":
            volume = self._robot.recognizer.current_volume if self._robot else 0.0
            self._waveform.update_waveform(volume)

        elif state_name == "NAVIGATING":
            self._update_navigating_text()

        elif state_name == "MATCHING":
            self._subtitle_label.config(text="正在理解...")

        elif state_name == "CONFIRMING":
            self._update_confirming_text()

        elif state_name == "CHATTING":
            self._subtitle_label.config(text="正在思考...")

        elif state_name == "ARRIVED":
            self._update_arrived_text()

        elif state_name in ("IDLE",):
            self._subtitle_label.config(text="你好！请问要去哪里？")

        elif state_name == "STANDBY":
            target = self._robot._face_progress if self._robot else 0.0
            if target == 0.0:
                self._smooth_progress = 0.0
            else:
                self._smooth_progress += (target - self._smooth_progress) * 0.15
            self._subtitle_label.config(text="待机中，请正对屏幕激活我")
            self._draw_progress_bar(self._smooth_progress)
            if self._robot and self._robot.face_detector._debug:
                self._robot.face_detector.show_debug_window()
        elif state_name == "SHUTDOWN":
            self._subtitle_label.config(text="再见！")

        # 字幕流式更新：TTS 播报文字（非空时才覆盖，避免空白闪烁）
        speech = self._robot._current_speech if self._robot else ""
        if speech and speech != self._last_speech:
            self._last_speech = speech
            self._subtitle_label.config(text=speech)
        elif not speech:
            self._last_speech = ""

    # ── 文本辅助 ──

    _LOCATION_NAMES = {
        "8th_building": "八号楼",
        "9th_building": "九号楼",
        "10th_building": "十号楼",
        "11th_building": "十一号楼",
    }

    def _loc_display(self, key: str) -> str:
        return self._LOCATION_NAMES.get(key, key)

    def _update_navigating_text(self):
        if not self._robot or not self._robot._pending_location:
            return
        loc = self._loc_display(self._robot._pending_location)
        self._subtitle_label.config(text=f"正在前往 {loc}")

        progress = self._robot.navigator.get_progress()
        step, total = progress["step"], progress["total"]
        action = {"go": "直行", "turn": "转向", "stop": "到达"}.get(progress["current_action"], progress["current_action"])
        self._info_label.config(text=f"第 {step}/{total} 步：{action}" if total else "")

    def _update_confirming_text(self):
        if not self._robot or not self._robot._pending_location:
            return
        loc = self._loc_display(self._robot._pending_location)
        self._subtitle_label.config(text=f"前往 {loc}？")
        self._info_label.config(text="请说「确认」或按 CLI 输入 y")

    def _update_arrived_text(self):
        if self._robot and self._robot._pending_location:
            loc = self._loc_display(self._robot._pending_location)
            self._subtitle_label.config(text=f"已到达 {loc}！")
        else:
            self._subtitle_label.config(text="已到达！")

    # ------------------------------------------------------------------
    # 状态 → 内容切换
    # ------------------------------------------------------------------

    def _draw_progress_bar(self, progress: float):
        """绘制水平进度条。"""
        c = self._progress_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return
        # 背景轨道
        c.create_rectangle(0, 0, w, h, fill="#1a2a3e", outline="")
        # 填充
        fill_w = int(w * progress)
        if fill_w > 0:
            accent = self._cfg.get("accent_color", "#4a9eff")
            c.create_rectangle(0, 0, fill_w, h, fill=accent, outline="")
            c.create_rectangle(0, 0, fill_w, h // 3, fill="#6ab4ff", outline="")

    def _hide_all_content(self):
        """隐藏下部所有内容组件。"""
        self._waveform.place_forget()
        self._subtitle_label.place_forget()
        self._info_label.place_forget()
        self._progress_canvas.place_forget()

    # ------------------------------------------------------------------
    # Emoji 更新
    # ------------------------------------------------------------------

    def _update_emoji(self, state_name: str):
        """切换 emoji 显示。"""
        emoji_key = self._get_emoji_for_state(state_name)

        if emoji_key in self._emoji_cache and self._emoji_cache[emoji_key] is not None:
            self._emoji_label.config(image=self._emoji_cache[emoji_key], text="")
            return

        fallback_char = _FALLBACK_EMOJI.get(state_name, "🤖")
        self._emoji_label.config(image="", text=fallback_char)

    # ------------------------------------------------------------------
    # 窗口控制
    # ------------------------------------------------------------------

    def _on_escape(self):
        """Esc 键：先退出全屏，再按则关闭。"""
        try:
            is_fullscreen = self.attributes("-fullscreen")
        except tk.TclError:
            is_fullscreen = False

        if is_fullscreen:
            self.attributes("-fullscreen", False)
        else:
            self._shutdown()

    def _shutdown(self):
        """安全关闭 GUI。"""
        logger.info("GUI 正在关闭...")
        if self._robot:
            self._robot.cmd_queue.put("shutdown")
        self.destroy()

# ------------------------------------------------------------------
# 独立测试入口
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("启动 GUI 测试窗口（按 Esc 退出）...")

    import time
    from enum import Enum, auto

    class FakeState(Enum):
        IDLE = auto(); LISTENING = auto(); MATCHING = auto()
        CONFIRMING = auto(); CHATTING = auto(); NAVIGATING = auto(); ARRIVED = auto()

    class FakeRobot:
        state = FakeState.IDLE
        _current_speech = ""
        _last_recognized_text = ""
        _pending_location = "8th_building"
        class FakeRecognizer: current_volume = 0.0
        class FakeNavigator:
            def get_progress(self):
                return {"destination": "8th_building", "step": 2, "total": 4, "current_action": "go"}
        recognizer = FakeRecognizer(); navigator = FakeNavigator()

    fake = FakeRobot()
    cfg = {
        "ui": {"gui": {
            "fullscreen": False, "width": 1024, "height": 600, "fps": 30,
            "bg_color": "#0d1b2a", "accent_color": "#4a9eff",
            "text_color": "#c0c0c0", "subtitle_color": "#ffffff",
            "emoji_dir": "resources/ui/emoji", "cursor_visible": True,
            "waveform": {"bars": 64, "color": "#4a9eff", "peak_color": "#00ff88"},
            "subtitle_font_size": 42,
        }}
    }

    app = RobotFace(cfg)
    app._robot = fake
    states = list(FakeState)
    start = time.time()

    def demo_tick():
        idx = int((time.time() - start) / 3) % len(states)
        fake.state = states[idx]
        if fake.state == FakeState.LISTENING:
            fake.recognizer.current_volume = 200 + random.randint(-100, 600)
        else:
            fake.recognizer.current_volume = 0
        app._tick()
        app.after(33, demo_tick)

    app.after(100, demo_tick)
    app.mainloop()
