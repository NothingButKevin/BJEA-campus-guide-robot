"""机器人核心状态机。

编排完整的校园导览工作流：听 → 匹配 → （确认 | 闲聊） → 导航 → 到站。
管理模型生命周期 —— 导航期间卸载 LLM 和 TTS 模型以释放内存给传感器。
"""

import logging
import queue
from enum import Enum, auto

import yaml

from hardware.audio_player import AudioPlayer
from hardware.face_detector import FaceDetector
from hardware.motor import MotorController, create_motor
from hardware.sensors import Sensors
from llm.fallback import LLMFallback
from matching.keyword_matcher import KeywordMatcher
from navigation.navigator import Navigator
from speech.recognizer import SpeechRecognizer
from speech.synthesizer import SpeechSynthesizer

logger = logging.getLogger(__name__)


class State(Enum):
    STANDBY = auto()       # 待机中，等待人脸唤醒
    IDLE = auto()          # 空闲，准备问候
    LISTENING = auto()     # 正在听用户说话
    MATCHING = auto()      # 匹配用户输入
    CONFIRMING = auto()    # 确认目的地
    CHATTING = auto()      # 关键字匹配失败 → LLM 闲聊兜底
    NAVIGATING = auto()    # 导航中；语音/LLM 模型已卸载
    ARRIVED = auto()       # 到达目的地
    SHUTDOWN = auto()      # 关机


# ------------------------------------------------------------------
# 闲聊意图预设回复（TTS 合成）
# ------------------------------------------------------------------

_CHAT_RESPONSES: dict[str, str] = {
    "chat_greeting":   "你好！我是 BJEA 校园导览机器人，请问要去哪里？",
    "chat_identity":   "我是 BJEA 校园导览机器人，没有名字。你可以叫我机器人。",
    "chat_capability": "我可以带你去校园里不同的教学楼，比如八号楼、九号楼、十号楼、十一号楼。只要告诉我去哪里就行。",
    "chat_nav_status": "我们正在前往目的地的路上，请稍等。",
    "chat_farewell":   "再见！有需要随时叫我。",
}


class Robot:
    """校园导览机器人顶层应用。"""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

        # --- 模块组装 --------------------------------------------------
        self._cfg_res = self._cfg.get("resources", {})
        self._cfg_chat = self._cfg.get("chat", {})

        self.recognizer = SpeechRecognizer(self._cfg.get("asr", {}))
        self.synthesizer = SpeechSynthesizer(self._cfg.get("tts", {}))
        self.audio = AudioPlayer(self.synthesizer)
        self.matcher = KeywordMatcher.from_config(self._cfg_res)
        self.motor = create_motor(self._cfg.get("motor", {}))
        self.sensors = Sensors(self._cfg.get("sensors", {}))
        self.navigator = Navigator(self.motor, self.sensors, self._cfg.get("navigation", {}))
        self.face_detector = FaceDetector(self._cfg.get("face_detector", {}))

        # LLM 在第一次兜底时懒加载，也可预加载
        self._llm: LLMFallback | None = None

        # --- 线程安全通道 ----------------------------------------------
        self.cmd_queue: queue.Queue[str] = queue.Queue()  # CLI → robot 命令队列
        self._state_listeners: list = []                   # 状态变更回调

        # --- GUI 共享数据（原子读取）-----------------------------------
        self._current_speech: str = ""       # 当前 TTS 播报文字（GUI 字幕）
        self._last_recognized_text: str = ""  # 最近一次语音识别结果
        self._face_progress: float = 0.0     # 人脸检测进度 0.0–1.0（GUI 进度条）

        # --- 状态 ------------------------------------------------------
        self.state = State.STANDBY
        self._pending_location: str | None = None
        self._last_user_input: str = ""

    # ------------------------------------------------------------------
    # 状态管理（线程安全的状态迁移 + CLI 命令处理）
    # ------------------------------------------------------------------

    def add_state_listener(self, callback):
        """注册状态变更回调。callback(old_state, new_state)。"""
        self._state_listeners.append(callback)

    def _notify_state_change(self, old_state, new_state):
        for cb in self._state_listeners:
            try:
                cb(old_state, new_state)
            except Exception:
                logger.exception("状态回调异常")

    def set_state(self, new_state):
        """统一的状态设置入口，自动通知监听器。"""
        old = self.state
        self.state = new_state
        if old != new_state:
            logger.info("状态: %s → %s", old.name, new_state.name)
            self._notify_state_change(old, new_state)

    def process_cli_command(self, cmd: str) -> bool:
        """处理来自 CLI 的命令。返回 True 表示已处理。"""
        cmd = cmd.strip().lower()

        if cmd in ("y", "yes"):
            self.cmd_queue.put("confirm")
            return True
        elif cmd in ("n", "no"):
            self.cmd_queue.put("cancel")
            return True
        elif cmd in ("q", "quit", "exit"):
            self.cmd_queue.put("shutdown")
            return True
        elif cmd in ("s", "status"):
            print(f"当前状态: {self.state.name}")
            print(f"  目的地: {self._pending_location or '(无)'}")
            print(f"  最近识别: {self._last_recognized_text or '(无)'}")
            return True
        elif cmd in ("w", "wake"):
            if self.state == State.STANDBY:
                self.cmd_queue.put("wake")
            else:
                print("仅在待机状态下可手动唤醒")
            return True
        elif cmd in ("h", "help"):
            print("命令: y(确认) n(取消) s(状态) d(调试) l(日志) w(唤醒) q(退出) h(帮助)")
            return True
        elif cmd in ("l", "log"):
            root = logging.getLogger()
            new_level = logging.INFO if root.level >= logging.INFO else logging.DEBUG
            root.setLevel(new_level)
            print(f"日志级别 → {logging.getLevelName(new_level)}")
            return True
        elif cmd in ("d", "debug"):
            print(f"Robot      : state={self.state.name}")
            print(f"Recognizer : loaded={self.recognizer._is_running if hasattr(self.recognizer, '_is_running') else '?'}")
            print(f"Synthesizer: loaded={getattr(self.synthesizer, '_loaded', '?')}")
            print(f"LLM        : loaded={self._llm is not None}")
            print(f"Motor      : type={type(self.motor).__name__}")
            print(f"FaceDetect : {'available' if self.face_detector.available else 'disabled'}")
            return True

        return False  # 未识别的命令

    # ------------------------------------------------------------------
    # 模型生命周期管理
    # ------------------------------------------------------------------

    def _ensure_llm(self) -> LLMFallback:
        if self._llm is None:
            self._llm = LLMFallback(self._cfg.get("llm", {}))
        return self._llm

    def _enter_navigation(self, location: str):
        """卸载语音/LLM 模型，开始导航。"""
        logger.info("进入导航状态 → %s", location)

        # 释放内存
        if self._llm is not None:
            self._llm.release()
        self.synthesizer.release()

        self.set_state(State.NAVIGATING)
        self.motor.center_steering()

        # 执行路径
        ok = self.navigator.follow_route(location)
        if not ok:
            self.synthesizer = SpeechSynthesizer(self._cfg.get("tts", {}))
            self._current_speech = "抱歉，我不认识这条路。"
            self.audio.error_path_not_found()
            self._current_speech = ""
            self.set_state(State.IDLE)
            return

        # 到站 —— 恢复语音模型
        self._exit_navigation(location)

    def _exit_navigation(self, location: str):
        """重新加载 TTS 模型并播报到站音频。"""
        logger.info("退出导航状态 —— 重新加载模型")
        self.synthesizer = SpeechSynthesizer(self._cfg.get("tts", {}))
        self.audio.arrived(location)
        self.set_state(State.ARRIVED)

    # ------------------------------------------------------------------
    # 状态处理函数
    # ------------------------------------------------------------------

    def _run_standby(self):
        """待机：等待人脸检测或 CLI 'w' 唤醒。"""
        # 检查 CLI 手动唤醒
        try:
            cmd = self.cmd_queue.get_nowait()
            if cmd == "wake":
                logger.info("CLI 手动唤醒")
                self._face_progress = 0.0
                self.set_state(State.IDLE)
                return
            elif cmd == "shutdown":
                self.set_state(State.SHUTDOWN)
                return
        except queue.Empty:
            pass

        wake_secs = self._cfg.get("face_detector", {}).get("wake_seconds", 5)
        self._face_progress = 0.0

        def _should_stop():
            """检查是否有 shutdown 或 wake 命令。"""
            try:
                cmd = self.cmd_queue.get_nowait()
                if cmd == "shutdown":
                    return True
                elif cmd == "wake":
                    return True
                else:
                    self.cmd_queue.put(cmd)  # 放回去
                    return False
            except queue.Empty:
                return False

        if self.face_detector.available:
            woke = self.face_detector.wait_for_face(
                min_seconds=wake_secs,
                progress_callback=lambda p: setattr(self, '_face_progress', p),
                stop_check=_should_stop,
            )
        else:
            import time
            time.sleep(0.5)
            woke = True

        self._face_progress = 0.0
        if woke:
            self.set_state(State.IDLE)

    def _run_idle(self):
        self.audio.greeting()
        self.set_state(State.LISTENING)

    def _run_listening(self):
        self._last_user_input = self.recognizer.recognize()
        self._last_recognized_text = self._last_user_input
        self.set_state(State.MATCHING)

    def _run_matching(self):
        threshold = self._cfg_chat.get("match_threshold", 80)
        gap = self._cfg_chat.get("score_gap", 10)

        key, confidence = self.matcher.match_with_confidence(
            self._last_user_input, score_threshold=threshold, score_gap=gap
        )

        logger.info("匹配结果: key=%s 置信度=%.1f", key, confidence)

        if key == "none":
            self.set_state(State.CHATTING)
        elif key.startswith("chat_"):
            self._handle_chat_intent(key)
        elif key == "confirm":
            if self._pending_location:
                self._enter_navigation(self._pending_location)
            else:
                self._current_speech = "请先告诉我要去哪里。"
                self.synthesizer.speak("请先告诉我要去哪里。")
                self._current_speech = ""
                self.set_state(State.LISTENING)
        else:
            # 导航目标或动作指令
            self._pending_location = key
            self.set_state(State.CONFIRMING)

    def _handle_chat_intent(self, key: str):
        response = _CHAT_RESPONSES.get(key)
        if response:
            self._current_speech = response
            self.synthesizer.speak(response)
            self._current_speech = ""
        self.set_state(State.LISTENING)

    def _run_confirming(self):
        # 先检查 CLI 是否有待处理的确认命令
        try:
            cli_cmd = self.cmd_queue.get_nowait()
            if cli_cmd == "confirm":
                if self._pending_location:
                    logger.info("CLI 确认导航 → %s", self._pending_location)
                    self._enter_navigation(self._pending_location)
                    return
            elif cli_cmd == "cancel":
                logger.info("CLI 取消导航")
                self._pending_location = None
                self._current_speech = "已取消。请问要去哪里？"
                self.synthesizer.speak("已取消。请问要去哪里？")
                self._current_speech = ""
                self.set_state(State.LISTENING)
                return
            elif cli_cmd == "shutdown":
                self.set_state(State.SHUTDOWN)
                return
        except queue.Empty:
            pass

        self.audio.confirm(self._pending_location)
        self.set_state(State.LISTENING)  # 下一轮会匹配到 confirm 或重试

    def _run_chatting(self):
        llm = self._ensure_llm()
        if llm.available:
            reply = llm.respond(self._last_user_input)
        else:
            reply = "抱歉，我不太明白您的意思。"

        if reply:
            self._current_speech = reply
            self.synthesizer.speak(reply)
            self._current_speech = ""
        else:
            self.synthesizer.speak("抱歉，我不太明白您的意思。")

        self.set_state(State.LISTENING)

    def _run_arrived(self):
        self.set_state(State.STANDBY)
        self._pending_location = None

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self):
        """阻塞式主循环 —— 运行直到 SHUTDOWN 状态。"""
        logger.info("机器人启动。当前状态 = %s", self.state.name)

        try:
            while self.state != State.SHUTDOWN:
                # 轮询 CLI 命令（非阻塞）
                try:
                    cmd = self.cmd_queue.get_nowait()
                    if cmd == "shutdown":
                        self.set_state(State.SHUTDOWN)
                        break
                except queue.Empty:
                    pass

                handler = {
                    State.STANDBY:    self._run_standby,
                    State.IDLE:       self._run_idle,
                    State.LISTENING:  self._run_listening,
                    State.MATCHING:   self._run_matching,
                    State.CONFIRMING: self._run_confirming,
                    State.CHATTING:   self._run_chatting,
                    State.NAVIGATING: None,  # 导航在 _enter_navigation 中同步阻塞
                    State.ARRIVED:    self._run_arrived,
                }.get(self.state)

                if handler is None:
                    if self.state == State.NAVIGATING:
                        break  # 导航在 _enter_navigation 中处理完毕
                    logger.error("状态 %s 无处理函数", self.state)
                    break

                handler()

        except KeyboardInterrupt:
            logger.info("收到键盘中断 —— 正在关机。")
        except Exception:
            logger.exception("主循环异常 —— 正在关机。")
        finally:
            self.set_state(State.SHUTDOWN)
            self.motor.cleanup()
            logger.info("机器人已停止。")
