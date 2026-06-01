# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Campus guide robot for BJEA (Beijing No. 80 High School International Department), running on **Raspberry Pi 5 with Pi OS**. The robot navigates campus locations, interacting via Chinese voice commands — speech recognition in, TTS and pre-recorded audio out.

## Commands

```bash
# Install dependencies (on Raspberry Pi)
pip install -r requirements.txt

# Full campus navigation workflow
python src/TEST.py

# Voice-controlled motion demo (forward/backward/left/right/stop)
python src/demo.py

# Test individual modules
python src/speechRecognition.py   # record & transcribe
python src/text2speach.py         # TTS synthesis test
python src/keywordsMapping.py     # interactive keyword matching test
python src/audioPlaying.py        # pre-recorded audio playback test
```

There is no test runner, linter, or type checker configured. `src/main.py` is a placeholder (`pass`).

## Architecture

```
User speech ──▶ speechRecognition.py ──▶ keywordsMapping.py ──▶ action dispatch
                    (Whisper.cpp)         (RapidFuzz + Pinyin)      │
                                                                   ├── motorControl.py (GPIO/PWM)
                                                                   ├── text2speach.py  (Piper TTS)
                                                                   └── audioPlaying.py (pre-recorded WAVs)
```

### Module responsibilities

- **`speechRecognition.py`** — Records mic input via `sounddevice` until silence is detected (2.5s threshold), then transcribes with Whisper.cpp (`base` model). Exposes `ASR()` which returns the transcribed Chinese text string.

- **`keywordsMapping.py`** — Fuzzy-matches Chinese speech input to predefined keywords. Converts both input and keyword lists to pinyin (via `xpinyin`), then uses `rapidfuzz` partial-ratio scoring across all candidates. Returns the matched key (e.g. `"8th_building"`) or `"none"` if confidence is too low or ambiguous (score gap < 10). Keyword sets are loaded from JSON files in `resources/`.

- **`text2speach.py`** — Synthesizes Chinese speech using Piper TTS with the `zh_CN-huayan-medium` ONNX model. Generates WAV in-memory and plays via `sounddevice`. The model is loaded once at module import.

- **`motorControl.py`** — `CarControl` class drives a PWM-controlled car chassis via `RPi.GPIO` (GPIO 27 for drive, 17 for steer, both at 50Hz). Duty cycles around 7.5 are neutral; 8 = forward/right, 7 = left. **Only runs on Raspberry Pi** — `RPi.GPIO` is not available on other platforms.

- **`audioPlaying.py`** — Plays pre-recorded `.wav` files from `resources/audio/` using `playsound`. Follows a three-step flow: greeting → confirm location → final directions (part 1 + location + part 2).

### Data files

- `resources/demoActions.json` — movement command keywords (forward, backward, left, right, stop, end)
- `resources/locationKeywords.json` — campus location keywords + confirmation phrases
- `resources/audio/` — pre-recorded WAV clips: `greeting.wav`, `confirm.wav`, `finalPt1.wav`/`finalPt2.wav`, `misunderstoodError.wav`, `notUnderstandError.wav`, and per-location files under `location/`
- `piper_models/zh_CN-huayan-medium.onnx` (+ `.json` config) — Chinese TTS voice model
- `cache/` — temporary audio recordings from speech recognition

### Two workflow entry points

1. **`TEST.py`** — Full campus navigation: greeting → listen for destination → confirm with user → play final directions. Uses `locationKeywords.json`.
2. **`demo.py`** — Voice-controlled motion test: listen for movement command → execute motor action (motor calls commented out, plays TTS feedback instead). Uses `demoActions.json`.

## Platform notes

- The `RPi.GPIO` import in `motorControl.py` means that module (and anything importing it) only works on a Raspberry Pi. The `demo.py` file has motor calls commented out so it can run/test on a desktop.
- The repo contains a compiled `whispercpp.cpython-311-darwin.so` (macOS), but on the Raspberry Pi the `whispercpp` pip package handles the native library.
- All speech is Chinese (Mandarin). The keyword matching uses pinyin normalization to handle pronunciation variations and fuzzy input.
