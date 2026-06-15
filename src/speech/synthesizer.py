"""中文语音合成模块 —— 使用微软 Edge TTS 免费接口。"""

import logging
import shutil
import subprocess
from pathlib import Path

import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("cache")

# 查找 edge-tts CLI（piwheels 装到 ~/.local/bin，可能不在 PATH 里）
_EDGE_TTS_BIN = shutil.which("edge-tts")
if _EDGE_TTS_BIN is None:
    # fallback: 检查常见的用户安装路径
    _candidates = [
        Path.home() / ".local/bin/edge-tts",
    ]
    for _c in _candidates:
        if _c.exists():
            _EDGE_TTS_BIN = str(_c)
            break

if _EDGE_TTS_BIN:
    logger.debug("edge-tts 路径: %s", _EDGE_TTS_BIN)
else:
    logger.warning("edge-tts 未找到，TTS 将不可用")


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
        if _EDGE_TTS_BIN is None:
            logger.error("edge-tts 未安装，请执行: pip install edge-tts")
            return

        out_path = _CACHE_DIR / "tts_out.mp3"

        try:
            subprocess.run(
                [
                    _EDGE_TTS_BIN,
                    "--text", text,
                    "--voice", self._voice,
                    "--write-media", str(out_path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except FileNotFoundError:
            logger.error("edge-tts 未安装，请执行: pip install edge-tts")
            return
        except subprocess.CalledProcessError as e:
            logger.error("Edge-TTS 合成失败: %s", e.stderr.decode(errors="replace"))
            return
        except subprocess.TimeoutExpired:
            logger.error("Edge-TTS 合成超时")
            return

        try:
            data, sr = sf.read(str(out_path))
            self._play(data, sr)
        except Exception as e:
            logger.error("TTS 音频播放失败: %s", e)

    def _play(self, data, sr: int):
        """播放音频，必要时重采样到设备支持的采样率。"""
        import numpy as np

        try:
            sd.play(data, sr)
            sd.wait()
            return
        except sd.PortAudioError as e:
            if "Invalid sample rate" not in str(e):
                raise

        # 边缘设备（如 Pi USB 声卡）可能不支持低采样率，尝试重采样
        target_sr = int(sd.query_devices(kind="output")["default_samplerate"]) or 44100
        logger.debug("采样率 %d → %d Hz 重采样", sr, target_sr)
        duration = len(data) / sr
        try:
            from scipy.signal import resample
            data = resample(data, int(duration * target_sr)).astype(np.float32)
        except ImportError:
            indices = np.linspace(0, len(data) - 1, int(duration * target_sr))
            data = np.interp(indices, np.arange(len(data)), data.astype(np.float64)).astype(np.float32)

        sd.play(data, target_sr)
        sd.wait()

    def release(self):
        """释放资源（Edge-TTS 无本地模型，无需释放）。"""
        self._loaded = False
