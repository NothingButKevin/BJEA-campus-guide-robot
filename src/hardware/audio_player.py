"""Playback of pre-recorded WAV audio clips."""

import logging
import os

from playsound import playsound

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Plays pre-recorded system audio (greeting, confirm, directions, errors)."""

    def __init__(self, audio_dir: str = "resources/audio"):
        self._dir = audio_dir

    def _play(self, *segments: str):
        for seg in segments:
            path = os.path.join(self._dir, seg)
            if not os.path.exists(path):
                logger.warning("Audio file not found: %s", path)
                continue
            playsound(path)

    # ------------------------------------------------------------------
    def simple_playing(self, name: str):
        """Play a single clip by name (without extension)."""
        self._play(f"{name}.wav")

    def confirm_playing(self, location: str):
        """Play confirm prompt + location-specific audio."""
        self._play("confirm.wav", f"location/{location}.wav")

    def final_playing(self, location: str):
        """Play final directions: part 1 + location + part 2."""
        self._play("finalPt1.wav", f"location/{location}.wav", "finalPt2.wav")


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    player = AudioPlayer("resources/audio")
    player.simple_playing("greeting")
    player.confirm_playing("8th_building")
    player.final_playing("11th_building")
