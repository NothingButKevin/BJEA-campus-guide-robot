"""中文语音合成模块 —— 使用 Piper ONNX 模型本地推理。"""

import io
import logging
import wave

import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice

logger = logging.getLogger(__name__)


class SpeechSynthesizer:
    """加载 Piper ONNX 中文语音模型，将文本合成并播放。"""

    def __init__(self, config: dict):
        """
        参数:
            config: TTS 配置字典，包含 model_path, config_path。
        """
        model_path = config["model_path"]
        config_path = config["config_path"]

        logger.info("正在加载 Piper 语音模型 ...")
        self._voice = PiperVoice.load(model_path=model_path, config_path=config_path)
        self._sample_rate = self._voice.config.sample_rate
        self._loaded = True

    def speak(self, text: str):
        """将文本合成语音并通过默认输出设备播放。"""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._sample_rate)
            self._voice.synthesize(text, wf)

        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            audio_data = wf.readframes(wf.getnframes())
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            sd.play(audio_array, samplerate=self._sample_rate)
            sd.wait()

    def release(self):
        """释放模型以在导航期间腾出内存。"""
        self._loaded = False
        self._voice = None


# ------------------------------------------------------------------
# 独立测试入口
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = {
        "model_path": "piper_models/zh_CN-huayan-medium.onnx",
        "config_path": "piper_models/zh_CN-huayan-medium.onnx.json",
    }
    tts = SpeechSynthesizer(cfg)
    tts.speak("这是测试")
