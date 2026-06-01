"""Chinese TTS synthesis using Piper (ONNX model, locally run)."""

import io
import logging
import wave

import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice

logger = logging.getLogger(__name__)


class SpeechSynthesizer:
    """Loads a Piper ONNX voice model and speaks text aloud."""

    def __init__(self, config: dict):
        """
        Args:
            config: TTS config dict with keys model_path, config_path.
        """
        model_path = config["model_path"]
        config_path = config["config_path"]

        logger.info("Loading Piper voice model ...")
        self._voice = PiperVoice.load(model_path=model_path, config_path=config_path)
        self._sample_rate = self._voice.config.sample_rate
        self._loaded = True

    def speak(self, text: str):
        """Synthesise *text* and play it through the default output device."""
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
        """Release the model to free memory during navigation."""
        self._loaded = False
        self._voice = None


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = {
        "model_path": "piper_models/zh_CN-huayan-medium.onnx",
        "config_path": "piper_models/zh_CN-huayan-medium.onnx.json",
    }
    tts = SpeechSynthesizer(cfg)
    tts.speak("这是测试")
