"""LLM fallback for open-ended chat when keyword matching is not confident.

Uses llama-cpp-python to run a quantised Qwen2.5-0.5B model locally.
The model is loaded only when needed and can be released during navigation
to free memory for vision / sensor processing.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMFallback:
    """Thin wrapper around llama-cpp-python for short chat responses.

    The model on disk is ~350 MB (Q4_K_M quantisation).  Inference takes
    1-2 seconds on a Raspberry Pi 5.
    """

    def __init__(self, config: dict):
        self._model_path = config.get("model_path", "")
        self._max_tokens = int(config.get("max_tokens", 64))
        self._temperature = float(config.get("temperature", 0.7))
        self._n_ctx = int(config.get("n_ctx", 512))
        self._llm: Optional[object] = None

        if not self._model_path:
            logger.warning("No LLM model path configured – fallback disabled.")
            return

        self._load()

    # ------------------------------------------------------------------
    def _load(self):
        """Load the GGUF model into memory."""
        try:
            from llama_cpp import Llama
        except ImportError:
            logger.warning("llama-cpp-python not installed – LLM fallback disabled.")
            self._loaded = False
            return

        logger.info("Loading LLM %s ...", self._model_path)
        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            verbose=False,
        )
        self._loaded = True

    def _unload(self):
        self._llm = None
        self._loaded = False

    # -- public API ----------------------------------------------------

    @property
    def available(self) -> bool:
        return self._loaded and self._llm is not None

    def respond(self, user_input: str) -> str:
        """Generate a one-sentence Chinese reply.  Returns empty string when unavailable."""
        if not self.available:
            return ""

        prompt = (
            "你是一个北京中学国际部的校园导航机器人。"
            "用简短的中文回复用户，不超过一句话。\n\n"
            f"用户: {user_input}\n"
            "助手:"
        )

        try:
            output = self._llm(
                prompt,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                stop=["用户:", "\n"],
            )
            reply = output["choices"][0]["text"].strip()
            logger.debug("LLM reply: %s", reply)
            return reply
        except Exception:
            logger.exception("LLM inference failed")
            return ""

    def release(self):
        """Unload the model from memory (call before navigation)."""
        if self._loaded:
            logger.info("Releasing LLM model ...")
            self._unload()

    def reload(self):
        """Reload the model (call after navigation completes)."""
        if self._model_path and not self._loaded:
            self._load()
