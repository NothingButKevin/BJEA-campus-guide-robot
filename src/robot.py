"""Core robot state machine.

Orchestrates the full campus-guide workflow: listen → match → (confirm |
chat) → navigate → arrive.  Manages model lifecycle so that the LLM and
TTS models are unloaded during navigation to free memory for sensors.
"""

import logging
from enum import Enum, auto

import yaml

from hardware.audio_player import AudioPlayer
from hardware.motor import MotorController, create_motor
from hardware.sensors import Sensors
from llm.fallback import LLMFallback
from matching.keyword_matcher import KeywordMatcher
from navigation.navigator import Navigator
from speech.recognizer import SpeechRecognizer
from speech.synthesizer import SpeechSynthesizer

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    MATCHING = auto()
    CONFIRMING = auto()
    CHATTING = auto()       # keyword match failed → LLM fallback
    NAVIGATING = auto()     # driving; speech/LLM models unloaded
    ARRIVED = auto()
    SHUTDOWN = auto()


# ------------------------------------------------------------------
# Chat intent responses (pre-recorded or TTS)
# ------------------------------------------------------------------

_CHAT_RESPONSES: dict[str, str] = {
    "chat_greeting":   "你好！我是 BJEA 校园导览机器人，请问要去哪里？",
    "chat_identity":   "我是 BJEA 校园导览机器人，没有名字。你可以叫我机器人。",
    "chat_capability": "我可以带你去校园里不同的教学楼，比如八号楼、九号楼、十号楼、十一号楼。只要告诉我去哪里就行。",
    "chat_nav_status": "我们正在前往目的地的路上，请稍等。",
    "chat_farewell":   "再见！有需要随时叫我。",
}


class Robot:
    """Top-level campus-guide robot application."""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

        # --- modules --------------------------------------------------
        self._cfg_res = self._cfg.get("resources", {})
        self._cfg_chat = self._cfg.get("chat", {})

        self.recognizer = SpeechRecognizer(self._cfg.get("asr", {}))
        self.synthesizer = SpeechSynthesizer(self._cfg.get("tts", {}))
        self.audio = AudioPlayer(self._cfg_res.get("audio_dir", "resources/audio"))
        self.matcher = KeywordMatcher.from_config(self._cfg_res)
        self.motor = create_motor(self._cfg.get("motor", {}))
        self.sensors = Sensors(self._cfg.get("sensors", {}))
        self.navigator = Navigator(self.motor, self.sensors, self._cfg.get("navigation", {}))

        # LLM is loaded lazily on first fallback or can be pre-loaded.
        self._llm: LLMFallback | None = None

        # --- state ----------------------------------------------------
        self.state = State.IDLE
        self._pending_location: str | None = None
        self._last_user_input: str = ""

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _ensure_llm(self) -> LLMFallback:
        if self._llm is None:
            self._llm = LLMFallback(self._cfg.get("llm", {}))
        return self._llm

    def _enter_navigation(self, location: str):
        """Unload speech / LLM models, begin driving."""
        logger.info("Entering NAVIGATION → %s", location)

        # free memory
        if self._llm is not None:
            self._llm.release()
        self.synthesizer.release()

        self.state = State.NAVIGATING
        self.motor.center_steering()

        # drive
        ok = self.navigator.follow_route(location)
        if not ok:
            self.synthesizer = SpeechSynthesizer(self._cfg.get("tts", {}))
            self.synthesizer.speak("抱歉，我不认识这条路。")
            self.state = State.IDLE
            return

        # arrived – bring speech models back
        self._exit_navigation(location)

    def _exit_navigation(self, location: str):
        """Reload TTS model and play arrival audio."""
        logger.info("Exiting NAVIGATION — reloading models")
        self.synthesizer = SpeechSynthesizer(self._cfg.get("tts", {}))
        self.audio.final_playing(location)
        self.state = State.ARRIVED

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _run_idle(self):
        self.audio.simple_playing("greeting")
        self.state = State.LISTENING

    def _run_listening(self):
        self._last_user_input = self.recognizer.recognize()
        self.state = State.MATCHING

    def _run_matching(self):
        threshold = self._cfg_chat.get("match_threshold", 80)
        gap = self._cfg_chat.get("score_gap", 10)

        key, confidence = self.matcher.match_with_confidence(
            self._last_user_input, score_threshold=threshold, score_gap=gap
        )

        logger.info("Match: key=%s confidence=%.1f", key, confidence)

        if key == "none":
            self.state = State.CHATTING
        elif key.startswith("chat_"):
            self._handle_chat_intent(key)
        elif key == "confirm":
            if self._pending_location:
                self._enter_navigation(self._pending_location)
            else:
                self.synthesizer.speak("请先告诉我要去哪里。")
                self.state = State.LISTENING
        else:
            # navigation or action target
            self._pending_location = key
            self.state = State.CONFIRMING

    def _handle_chat_intent(self, key: str):
        response = _CHAT_RESPONSES.get(key)
        if response:
            self.synthesizer.speak(response)
        self.state = State.LISTENING

    def _run_confirming(self):
        self.audio.confirm_playing(self._pending_location)
        self.state = State.LISTENING  # next round will match confirm / retry

    def _run_chatting(self):
        llm = self._ensure_llm()
        if llm.available:
            reply = llm.respond(self._last_user_input)
        else:
            reply = "抱歉，我不太明白您的意思。"

        if reply:
            self.synthesizer.speak(reply)
        else:
            self.synthesizer.speak("抱歉，我不太明白您的意思。")

        self.state = State.LISTENING

    def _run_arrived(self):
        self.state = State.IDLE
        self._pending_location = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Blocking main loop — runs until SHUTDOWN."""
        logger.info("Robot starting. State = %s", self.state.name)

        try:
            while self.state != State.SHUTDOWN:
                handler = {
                    State.IDLE:       self._run_idle,
                    State.LISTENING:  self._run_listening,
                    State.MATCHING:   self._run_matching,
                    State.CONFIRMING: self._run_confirming,
                    State.CHATTING:   self._run_chatting,
                    State.ARRIVED:    self._run_arrived,
                }.get(self.state)

                if handler is None:
                    logger.error("No handler for state %s", self.state)
                    break

                handler()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — shutting down.")
        finally:
            self.motor.cleanup()
            logger.info("Robot stopped.")
