import RPi.GPIO as GPIO
import time

# 设置 GPIO 模式为 BCM（GPIO编号）
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# 左轮
LEFT_IN1 = 17
LEFT_IN2 = 18

# 右轮
RIGHT_IN1 = 22
RIGHT_IN2 = 23

# 设置为输出模式
GPIO.setup(LEFT_IN1, GPIO.OUT)
GPIO.setup(LEFT_IN2, GPIO.OUT)
GPIO.setup(RIGHT_IN1, GPIO.OUT)
GPIO.setup(RIGHT_IN2, GPIO.OUT)

# 定义控制函数
def stop():
    GPIO.output(LEFT_IN1, GPIO.LOW)
    GPIO.output(LEFT_IN2, GPIO.LOW)
    GPIO.output(RIGHT_IN1, GPIO.LOW)
    GPIO.output(RIGHT_IN2, GPIO.LOW)

def forward():
    GPIO.output(LEFT_IN1, GPIO.HIGH)
    GPIO.output(LEFT_IN2, GPIO.LOW)
    GPIO.output(RIGHT_IN1, GPIO.HIGH)
    GPIO.output(RIGHT_IN2, GPIO.LOW)

def backward():
    GPIO.output(LEFT_IN1, GPIO.LOW)
    GPIO.output(LEFT_IN2, GPIO.HIGH)
    GPIO.output(RIGHT_IN1, GPIO.LOW)
    GPIO.output(RIGHT_IN2, GPIO.HIGH)

def turn_left():
    GPIO.output(LEFT_IN1, GPIO.LOW)
    GPIO.output(LEFT_IN2, GPIO.HIGH)
    GPIO.output(RIGHT_IN1, GPIO.HIGH)
    GPIO.output(RIGHT_IN2, GPIO.LOW)

def turn_right():
    GPIO.output(LEFT_IN1, GPIO.HIGH)
    GPIO.output(LEFT_IN2, GPIO.LOW)
    GPIO.output(RIGHT_IN1, GPIO.LOW)
    GPIO.output(RIGHT_IN2, GPIO.HIGH)

# 简单测试
try:
    print("前进")
    forward()
    time.sleep(2)

    print("左转")
    turn_left()
    time.sleep(1)

    print("右转")
    turn_right()
    time.sleep(1)

    print("后退")
    backward()
    time.sleep(2)

    print("停止")
    stop()

except KeyboardInterrupt:
    stop()

finally:
    GPIO.cleanup()  # 清除引脚状态
