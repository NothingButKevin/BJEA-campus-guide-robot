"""Speech recognition using Whisper.cpp with silence-based auto-stop recording."""

import logging
import wave

import numpy as np
import sounddevice as sd
from whispercpp import Whisper

logger = logging.getLogger(__name__)


class SpeechRecognizer:
    """Records mic input until silence, then transcribes with Whisper.cpp."""

    def __init__(self, config: dict):
        """
        Args:
            config: ASR config dict with keys:
                model, silence_threshold, silence_duration,
                sample_rate, output_path
        """
        self.model_name = config["model"]
        self.silence_threshold = config["silence_threshold"]
        self.silence_duration = config["silence_duration"]
        self.sample_rate = config["sample_rate"]
        self.output_path = config["output_path"]

        logger.info("Loading Whisper model '%s' ...", self.model_name)
        self._whisper = Whisper(self.model_name)
        self._is_running = False

    # ------------------------------------------------------------------
    # Internal recording
    # ------------------------------------------------------------------

    def _record_until_silence(self, chunk: int = 1024, channels: int = 1):
        """Record from the default microphone until silence is detected.

        Returns the path to the saved WAV file.
        """
        frames: list = []
        # Give the user a 3 s grace period before silence detection kicks in.
        silent_chunks = -int(self.sample_rate / chunk * 3)
        max_silent_chunks = int(self.sample_rate / chunk * self.silence_duration)
        stop_recording = False

        def _audio_callback(indata, frames_per_buffer, time, status):
            nonlocal silent_chunks, stop_recording
            if status:
                logger.warning("Audio status: %s", status)

            audio_data = np.frombuffer(indata, dtype=np.int16)
            volume = np.abs(audio_data).mean()

            frames.append(indata.copy())

            if volume < self.silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks > max_silent_chunks:
                logger.debug("Silence detected – stopping recording.")
                stop_recording = True
                raise sd.CallbackStop

        logger.info("Recording ... speak into the microphone.")
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
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.sample_rate)
            audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
            wf.writeframes(audio_data.tobytes())

        logger.debug("Recording saved to %s", self.output_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recognize(self) -> str:
        """Record speech and return the transcribed Chinese text."""
        self._record_until_silence()
        result = self._whisper.transcribe(self.output_path)
        text = "".join(self._whisper.extract_text(result))
        logger.info("Recognised: %s", text)
        return text

    def stop(self):
        """Release resources (e.g. before model swap during navigation)."""
        self._is_running = False


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = {
        "model": "base",
        "silence_threshold": 500,
        "silence_duration": 2.5,
        "sample_rate": 44100,
        "output_path": "cache/output.wav",
    }
    rec = SpeechRecognizer(cfg)
    print(rec.recognize())
