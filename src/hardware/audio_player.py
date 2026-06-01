"""预录制 WAV 音频播放模块。"""

import logging
import os

from playsound import playsound

logger = logging.getLogger(__name__)


class AudioPlayer:
    """播放预录制的系统音频（问候、确认、路径指引、错误提示等）。"""

    def __init__(self, audio_dir: str = "resources/audio"):
        self._dir = audio_dir

    def _play(self, *segments: str):
        for seg in segments:
            path = os.path.join(self._dir, seg)
            if not os.path.exists(path):
                logger.warning("音频文件不存在: %s", path)
                continue
            playsound(path)

    # ------------------------------------------------------------------
    def simple_playing(self, name: str):
        """播放单个音频片段（不含扩展名）。"""
        self._play(f"{name}.wav")

    def confirm_playing(self, location: str):
        """播放确认提示音 + 地点专属音频。"""
        self._play("confirm.wav", f"location/{location}.wav")

    def final_playing(self, location: str):
        """播放终点播报：开场 + 地点介绍 + 结尾。"""
        self._play("finalPt1.wav", f"location/{location}.wav", "finalPt2.wav")


# ------------------------------------------------------------------
# 独立测试入口
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    player = AudioPlayer("resources/audio")
    player.simple_playing("greeting")
    player.confirm_playing("8th_building")
    player.final_playing("11th_building")
