"""中文语音合成模块 —— 使用微软 Edge TTS 免费接口。"""

import logging
import subprocess
from pathlib import Path

import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("cache")


class SpeechSynthesizer:
    """调用 edge-tts CLI 合成中文语音并播放。"""

    def __init__(self, config: dict):
        """
        参数:
            config: TTS 配置字典，包含 voice。
        """
        self._voice = config.get("voice", "zh-CN-XiaoxiaoNeural")
        self._loaded = True
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Edge-TTS 就绪（voice=%s）", self._voice)

    def speak(self, text: str):
        """将文本合成语音并通过默认输出设备播放。"""
        out_path = _CACHE_DIR / "tts_out.mp3"

        try:
            subprocess.run(
                [
                    "edge-tts",
                    "--text", text,
                    "--voice", self._voice,
                    "--write-media", str(out_path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("Edge-TTS 合成失败: %s", e.stderr.decode(errors="replace"))
            return
        except subprocess.TimeoutExpired:
            logger.error("Edge-TTS 合成超时")
            return

        data, sr = sf.read(str(out_path))
        sd.play(data, sr)
        sd.wait()

    def release(self):
        """释放资源（Edge-TTS 无本地模型，无需释放）。"""
        self._loaded = False
