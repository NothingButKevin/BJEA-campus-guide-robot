import RPi.GPIO as GPIO
import time
from mpu6050 import mpu6050

class CarControl:
    def __init__(self, drive_pin=27, steer_pin=17, freq=50):
        GPIO.setmode(GPIO.BCM)
        self.drive_pin = drive_pin
        self.steer_pin = steer_pin

        GPIO.setup(self.drive_pin, GPIO.OUT)
        GPIO.setup(self.steer_pin, GPIO.OUT)

        self.pwm_drive = GPIO.PWM(self.drive_pin, freq)
        self.pwm_steer = GPIO.PWM(self.steer_pin, freq)

        self.pwm_drive.start(7.5)
        self.pwm_steer.start(7.5)

        # 新增：初始化陀螺仪
        self.sensor = mpu6050(0x68)

    def drive_forward(self, cm_or_duty=8):
        # 如果是 float/int 且小于 20，则认为是距离（cm）
        if isinstance(cm_or_duty, (int, float)) and cm_or_duty < 20:
            self.pwm_steer.ChangeDutyCycle(7.5)  # 中立方向
            speed_cm_s = 10  # ⚠️ 自己标定
            duration = cm_or_duty / speed_cm_s
            self.pwm_drive.ChangeDutyCycle(8)
            time.sleep(duration)
            self.pwm_drive.ChangeDutyCycle(7.5)
        else:
            self.pwm_drive.ChangeDutyCycle(cm_or_duty)

    def drive_stop(self):
        self.pwm_drive.ChangeDutyCycle(7.5)
        self.pwm_steer.ChangeDutyCycle(7.5)

    def steer_left(self, deg_or_duty=7):
        if isinstance(deg_or_duty, (int, float)) and deg_or_duty > 7.5:
            self.pwm_steer.ChangeDutyCycle(7)  # 左打
            time.sleep(0.3)
            self.pwm_drive.ChangeDutyCycle(8)
            self._turn_by_gyro(-abs(deg_or_duty))
            self.drive_stop()
        else:
            self.pwm_steer.ChangeDutyCycle(deg_or_duty)

    def steer_right(self, deg_or_duty=8):
        if isinstance(deg_or_duty, (int, float)) and deg_or_duty > 7.5:
            self.pwm_steer.ChangeDutyCycle(8)  # 右打
            time.sleep(0.3)
            self.pwm_drive.ChangeDutyCycle(8)
            self._turn_by_gyro(abs(deg_or_duty))
            self.drive_stop()
        else:
            self.pwm_steer.ChangeDutyCycle(deg_or_duty)

    def steer_center(self):
        self.pwm_steer.ChangeDutyCycle(7.5)

    def cleanup(self):
        self.pwm_drive.stop()
        self.pwm_steer.stop()
        GPIO.cleanup()

    def _turn_by_gyro(self, target_deg):
        angle = 0.0
        interval = 0.01
        for _ in range(int(10 / interval)):  # 最长转 10 秒
            gyro_z = self.sensor.get_gyro_data()['z']
            angle += gyro_z * interval
            time.sleep(interval)
            if abs(angle) >= abs(target_deg):
                break