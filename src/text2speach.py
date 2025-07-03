import wave
import io
import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice

# 模型路径（你可以修改为自己的默认位置）
MODEL_PATH = "piper_models/zh_CN-huayan-medium.onnx"
CONFIG_PATH = "piper_models/zh_CN-huayan-medium.onnx.json"

# 提前加载模型（避免每次都重复加载）
_voice = PiperVoice.load(model_path=MODEL_PATH, config_path=CONFIG_PATH)
_sample_rate = _voice.config.sample_rate

def tts(text: str):
    # 使用内存缓冲区生成 WAV 数据
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(_sample_rate)
        _voice.synthesize(text, wf)

    # 播放音频
    buf.seek(0)
    with wave.open(buf, "rb") as wf:
        audio_data = wf.readframes(wf.getnframes())
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        sd.play(audio_array, samplerate=_sample_rate)
        sd.wait()  # 等待播放完成

if __name__ == '__main__':
    tts("这是个测试")