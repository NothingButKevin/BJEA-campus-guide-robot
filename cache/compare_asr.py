"""ASR 对比测试 —— 录音 5 秒，Whisper vs SenseVoice 并排对比结果和耗时。"""
import sys
sys.path.insert(0, 'src')

import time
import numpy as np
import sounddevice as sd
import wave

SR = 44100
DURATION = 5
WAV_PATH = "cache/asr_test.wav"

# ── 录音 ──
print(f"\n请说话 ({DURATION} 秒)...")
audio = sd.rec(int(DURATION * SR), samplerate=SR, channels=1, dtype='int16')
sd.wait()
with wave.open(WAV_PATH, 'wb') as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes(audio.tobytes())
print("录音完成\n")

# ── Whisper ──
print("=" * 50)
print("Whisper (base):")
import whispercpp
t0 = time.time()
w = whispercpp.Whisper('base')
t1 = time.time()
result = w.transcribe(WAV_PATH)
t2 = time.time()
text = ''.join(w.extract_text(result)).strip()
t3 = time.time()
print(f"  → {text if text else '(空)'}")
print(f"  模型加载: {t1-t0:.2f}s  转写: {t2-t1:.2f}s  后处理: {t3-t2:.3f}s  总计: {t3-t0:.2f}s")

# ── SenseVoice ──
print(f"\n{'─' * 50}")
print("SenseVoice Small:")
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

t0 = time.time()
model = AutoModel(model='iic/SenseVoiceSmall', disable_update=True)
t1 = time.time()
res = model.generate(input=WAV_PATH, language='zh', use_itn=False)
t2 = time.time()
if res:
    raw = res[0]['text']
    clean = rich_transcription_postprocess(raw)
    print(f"  原始: {raw}")
    print(f"  → {clean if clean else '(空)'}")
t3 = time.time()
print(f"  模型加载: {t1-t0:.2f}s  转写: {t2-t1:.2f}s  后处理: {t3-t2:.3f}s  总计: {t3-t0:.2f}s")
print("=" * 50)
