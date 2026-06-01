"""Voice-controlled motion demo.

Listens for movement commands (forward / backward / left / right / stop /
end) and dispatches them to the motor controller.  On the desktop this
uses MockMotorController which logs to the console.
"""

import logging
import time

import yaml

from hardware.motor import create_motor
from matching.keyword_matcher import KeywordMatcher, load_json
from speech.recognizer import SpeechRecognizer
from speech.synthesizer import SpeechSynthesizer

logger = logging.getLogger(__name__)


def run(config_path: str = "config.yaml"):
    """Run the demo loop.  *config_path* points to config.yaml."""

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # assemble modules from config
    tts = SpeechSynthesizer(cfg["tts"])
    recognizer = SpeechRecognizer(cfg["asr"])
    motor = create_motor(cfg["motor"])

    # Only match movement actions, not locations or chat intents.
    actions_data = load_json(cfg["resources"]["actions_file"])
    matcher = KeywordMatcher(actions_data)

    tts.speak("这是 BJEA 校园向导机器人测试版本。语音控制行进。")

    try:
        while True:
            tts.speak("请说要做什么")
            action = matcher.match(recognizer.recognize())

            if action == "forward":
                tts.speak("正在前进")
                motor.forward(0.3)
                time.sleep(1.5)
                motor.stop()

            elif action == "backward":
                tts.speak("正在后退")
                motor.backward(0.3)
                time.sleep(1.5)
                motor.stop()

            elif action == "stop":
                tts.speak("停止行驶")
                motor.stop()

            elif action == "left":
                tts.speak("左转弯")
                motor.steer(-0.5)
                time.sleep(1.5)
                motor.center_steering()

            elif action == "right":
                tts.speak("右转弯")
                motor.steer(0.5)
                time.sleep(1.5)
                motor.center_steering()

            elif action == "end":
                tts.speak("结束")
                break

            else:
                tts.speak("抱歉，我不明白您的意思。")
    finally:
        motor.cleanup()


# ------------------------------------------------------------------
# Direct invocation (for testing without main.py)
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run("config.yaml")
