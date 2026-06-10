"""语音识别模块 —— 静音检测录音 + FunASR SenseVoice Small 转写。"""

import logging
import wave

import numpy as np
import sounddevice as sd
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

logger = logging.getLogger(__name__)


class SpeechRecognizer:
    """录音直到静音，然后用 SenseVoice Small 转写为中文文本。"""

    def __init__(self, config: dict):
        """
        参数:
            config: ASR 配置字典，包含 model, silence_threshold,
                    silence_duration, sample_rate, output_path
        """
        self.model_name = config.get("model", "iic/SenseVoiceSmall")
        self.silence_threshold = config["silence_threshold"]
        self.silence_duration = config["silence_duration"]
        self.sample_rate = config["sample_rate"]
        self.output_path = config["output_path"]

        logger.info("正在加载 SenseVoice 模型 '%s' ...", self.model_name)
        self._model = AutoModel(
            model=self.model_name,
            disable_update=True,
        )
        self._is_running = False

        # 实时音频电平（供 GUI 波形图读取）
        self.current_volume: float = 0.0

    # ------------------------------------------------------------------
    # 内部录音逻辑
    # ------------------------------------------------------------------

    def _record_until_silence(self, chunk: int = 1024, channels: int = 1):
        """从默认麦克风录音，检测到静音后自动停止。

        返回保存的 WAV 文件路径。
        """
        frames: list = []
        silent_chunks = -int(self.sample_rate / chunk * 3)
        max_silent_chunks = int(self.sample_rate / chunk * self.silence_duration)
        stop_recording = False

        def _audio_callback(indata, frames_per_buffer, time, status):
            nonlocal silent_chunks, stop_recording
            if status:
                logger.warning("音频状态异常: %s", status)

            audio_data = np.frombuffer(indata, dtype=np.int16)
            volume = np.abs(audio_data).mean()

            self.current_volume = float(volume)

            frames.append(indata.copy())

            if volume < self.silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks > max_silent_chunks:
                logger.debug("检测到静音 —— 停止录音。")
                stop_recording = True
                raise sd.CallbackStop

        logger.info("正在录音 ... 请对着麦克风说话。")
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=channels,
                dtype="int16",
                blocksize=chunk,
                callback=_audio_callback,
            ):
                while not stop_recording:
                    sd.sleep(100)
        except sd.CallbackStop:
            pass

        with wave.open(self.output_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
            wf.writeframes(audio_data.tobytes())

        logger.debug("录音已保存至 %s", self.output_path)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def recognize(self) -> str:
        """录音并返回转写的中文文本。"""
        self._record_until_silence()
        result = self._model.generate(
            input=self.output_path,
            language="zh",
            use_itn=False,
        )
        if result and result[0].get("text"):
            text = rich_transcription_postprocess(result[0]["text"])
        else:
            text = ""
        logger.info("识别结果: %s", text)
        return text

    def release(self):
        """释放模型（导航期间腾出内存时调用）。"""
        self._is_running = False
        self._model = None


# ------------------------------------------------------------------
# 独立测试入口
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = {
        "model": "iic/SenseVoiceSmall",
        "silence_threshold": 500,
        "silence_duration": 2.5,
        "sample_rate": 44100,
        "output_path": "cache/output.wav",
    }
    rec = SpeechRecognizer(cfg)
    print(rec.recognize())
