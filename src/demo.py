import text2speach as tts
import keywordsMapping as km
import speechRecognition as sr
import motorControl as mc

car = mc.CarControl()
matcher = km.KeywordMatcher("resources/demoActions.json")

if __name__ == '__main__':
    tts.tts("这是BJEA校园向导机器人测试版本0.0.1，语音控制行进")
    while True:
        tts.tts("请说要做什么？")
        action = matcher.match(sr.ASR())
        if action == "forward":
            tts.tts("正在前进")
            car.drive_forward()
        elif action == "stop":
            tts.tts("停止行驶")
            car.drive_stop()
        elif action == "left":
            tts.tts("左转弯")
            car.steer_left()
        elif action == "right":
            tts.tts("右转弯")
            car.steer_right()
        elif action == "end":
            tts.tts("结束")
            car.cleanup()
            break
        else:
            tts.tts("抱歉，我不明白您的意思。")