"""音频播报模块 —— 使用 TTS 合成替代预录制 WAV 播放。"""

import logging

logger = logging.getLogger(__name__)

_LOCATION_NAMES = {
    "8th_building": "八号楼",
    "9th_building": "九号楼",
    "10th_building": "十号楼",
    "11th_building": "十一号楼",
}


def _loc_name(key: str) -> str:
    return _LOCATION_NAMES.get(key, key)


class AudioPlayer:
    """使用 TTS 合成器播报系统语音（问候 / 确认 / 到达）。"""

    def __init__(self, synthesizer):
        self._tts = synthesizer

    def greeting(self):
        self._tts.speak("你好！我是 BJEA 校园导览机器人，请问要去哪里？")

    def confirm(self, location: str):
        name = _loc_name(location)
        self._tts.speak(f"确认前往{name}，请说确认或取消。")

    def arrived(self, location: str):
        name = _loc_name(location)
        self._tts.speak(f"已到达{name}，感谢使用校园导览服务。")

    def error_path_not_found(self):
        self._tts.speak("抱歉，我不认识这条路。")

    def error_not_understood(self):
        self._tts.speak("抱歉，我不太明白您的意思。")
