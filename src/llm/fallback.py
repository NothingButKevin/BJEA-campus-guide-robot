"""LLM 兜底模块 —— 关键字匹配失败时处理开放式闲聊。

使用 llama-cpp-python 在本地运行量化的 Qwen2.5-0.5B 模型。
模型仅在需要时加载，导航期间可释放以腾出内存给传感器处理。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMFallback:
    """对 llama-cpp-python 的轻量封装，用于简短中文闲聊回复。

    模型文件约 350 MB（Q4_K_M 量化），在树莓派 5 上推理约 1-2 秒。
    """

    def __init__(self, config: dict):
        self._model_path = config.get("model_path", "")
        self._max_tokens = int(config.get("max_tokens", 64))
        self._temperature = float(config.get("temperature", 0.7))
        self._n_ctx = int(config.get("n_ctx", 512))
        self._llm: Optional[object] = None
        self._loaded = False

        if not self._model_path:
            logger.warning("未配置 LLM 模型路径 —— 兜底功能已禁用。")
            return

        self._load()

    # ------------------------------------------------------------------
    def _load(self):
        """将 GGUF 模型加载到内存。"""
        try:
            from llama_cpp import Llama
        except ImportError:
            logger.warning("llama-cpp-python 未安装 —— LLM 兜底已禁用。")
            return

        logger.info("正在加载 LLM %s ...", self._model_path)
        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            verbose=False,
        )
        self._loaded = True

    def _unload(self):
        self._llm = None
        self._loaded = False

    # -- 对外接口 --------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._loaded and self._llm is not None

    def respond(self, user_input: str) -> str:
        """生成一句话中文回复。不可用时返回空字符串。"""
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
            logger.debug("LLM 回复: %s", reply)
            return reply
        except Exception:
            logger.exception("LLM 推理失败")
            return ""

    def release(self):
        """卸载模型释放内存（导航前调用）。"""
        if self._loaded:
            logger.info("正在释放 LLM 模型 ...")
            self._unload()

    def reload(self):
        """重新加载模型（导航结束后调用）。"""
        if self._model_path and not self._loaded:
            self._load()
