"""语音控制行进 demo。

监听移动指令（前进 / 后退 / 左转 / 右转 / 停止 / 结束）并下发给电机
控制器。桌面端自动使用 Mock 电机控制器，输出日志而非实际驱动硬件。
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
    """运行 demo 循环。*config_path* 指向 config.yaml。"""

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 从配置组装模块
    tts = SpeechSynthesizer(cfg["tts"])
    recognizer = SpeechRecognizer(cfg["asr"])
    motor = create_motor(cfg["motor"])

    # 只匹配移动动作，不匹配地点或闲聊意图
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
# 直接调用入口（不通过 main.py 时使用）
# ------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run("config.yaml")
