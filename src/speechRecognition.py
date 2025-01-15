from whispercpp import Whisper
w = Whisper('base')

import sounddevice as sd
import wave
import numpy as np

def record_until_silence(output_path, silence_threshold=500, silence_duration=2.5, chunk=1024, rate=44100, channels=1):
    """
    录音直到检测到超过指定时长的静音。

    :param output_path: 保存录音的文件路径
    :param silence_threshold: 静音阈值（幅度值）
    :param silence_duration: 静音持续时长（秒）
    :param chunk: 每次读取的帧数
    :param rate: 采样率
    :param channels: 声道数
    """
    print("Recording... Speak into the microphone.")
    frames = []
    silent_chunks = 0
    max_silent_chunks = int(rate / chunk * silence_duration)
    stop_recording = False  # 标志位

    def audio_callback(indata, frames_per_buffer, time, status):
        nonlocal silent_chunks, stop_recording
        if status:
            print(f"Status: {status}")

        # 将音频数据转换为 NumPy 数组并计算幅度
        audio_data = np.frombuffer(indata, dtype=np.int16)
        volume = np.abs(audio_data).mean()

        frames.append(indata.copy())

        if volume < silence_threshold:
            silent_chunks += 1
        else:
            silent_chunks = 0

        # 如果静音持续足够长的时间，停止录音
        if silent_chunks > max_silent_chunks:
            print("Silence detected. Stopping recording.")
            stop_recording = True
            raise sd.CallbackStop

    try:
        with sd.InputStream(samplerate=rate, channels=channels, dtype='int16',
                            blocksize=chunk, callback=audio_callback):
            while not stop_recording:
                sd.sleep(100)  # 每 100 毫秒检查一次标志位
    except sd.CallbackStop:
        pass

    # 保存音频文件
    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16 的字节数是 2
        wf.setframerate(rate)
        audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)  # 将字节流转为 NumPy 数组
        wf.writeframes(audio_data.tobytes())  # 使用 NumPy 数组保存

    print(f"Recording saved to {output_path}")

def ASR(output_path="cache/output.wav", silence_threshold=500, silence_duration=2.5):
    record_until_silence(output_path, silence_threshold, silence_duration)
    result = w.transcribe(output_path)
    return ''.join(w.extract_text(result))

# 用于测试语音识别功能
if __name__ == '__main__':
    record_until_silence("cache/output.wav")
    result = w.transcribe("cache/output.wav")
    text = w.extract_text(result)
    print(text)