import RPi.GPIO as GPIO
import time

# 设置 GPIO 模式
GPIO.setmode(GPIO.BCM)

# 定义电机引脚
motor_pins = [17, 18, 22, 23]

# 设置引脚为输出
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)

# 设置 PWM 信号（频率 100Hz）
pwm_left_forward = GPIO.PWM(17, 100)
pwm_left_backward = GPIO.PWM(18, 100)
pwm_right_forward = GPIO.PWM(22, 100)
pwm_right_backward = GPIO.PWM(23, 100)

# 启动 PWM，初始占空比为 0（不转）
pwm_left_forward.start(0)
pwm_left_backward.start(0)
pwm_right_forward.start(0)
pwm_right_backward.start(0)

# 向前转，速度为 70%
def forward():
    pwm_left_forward.ChangeDutyCycle(70)
    pwm_right_forward.ChangeDutyCycle(70)
    time.sleep(2)

#向右转，速度为70%
def right():
    pwm_left_forward.ChangeDutyCycle(70)
    pwm_right_backward.ChangeDutyCycle(0)
    time.sleep(2)


# 向左转，速度为70%
def left():
    pwm_left_backward.ChangeDutyCycle(0)
    pwm_right_forward.ChangeDutyCycle(70)
    time.sleep(2)
    

# 停止所有转动
for pwm in [pwm_left_forward, pwm_left_backward, pwm_right_forward, pwm_right_backward]:
    pwm.ChangeDutyCycle(0)

GPIO.cleanup()
