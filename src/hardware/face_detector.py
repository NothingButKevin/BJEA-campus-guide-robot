"""人脸检测模块 —— OpenCV Haar 级联，触发机器人唤醒。"""

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)

# Haar 级联模型路径（OpenCV 自带）
_CASCADE_PATH = "haarcascade_frontalface_default.xml"


class FaceDetector:
    """使用摄像头 + OpenCV Haar 级联检测人脸。"""

    H = None

    def __init__(self, config: dict, debug: bool = False):
        self._camera_id = config.get("camera_id", 0)
        self._scale_factor = config.get("scale_factor", 1.1)
        self._min_neighbors = config.get("min_neighbors", 5)
        self._interval = config.get("detection_interval", 0.2)
        self._debug = debug

        self._cap = None
        self._classifier = None
        self._last_frame = None  # debug 模式缓存最近一帧
        self._last_faces = None  # debug 模式缓存最近的人脸坐标
        self._available = self._init_camera()

    # ------------------------------------------------------------------
    def _init_camera(self) -> bool:
        """初始化摄像头和级联分类器。返回是否可用。"""
        try:
            import cv2
            self.H = cv2

            self._classifier = cv2.CascadeClassifier(
                cv2.data.haarcascades + _CASCADE_PATH
            )
            if self._classifier.empty():
                logger.error("Haar 级联模型加载失败")
                return False

            self._cap = cv2.VideoCapture(self._camera_id)
            if not self._cap.isOpened():
                logger.warning("无法打开摄像头 %d", self._camera_id)
                return False

            logger.info("人脸检测器就绪（camera=%d）", self._camera_id)
            return True
        except ImportError:
            logger.warning("OpenCV 不可用，人脸检测已禁用。使用 CLI 'w' 手动唤醒。")
            return False
        except Exception as e:
            logger.warning("人脸检测器初始化失败: %s", e)
            return False

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._available

    def detect(self) -> bool:
        """单帧检测，返回是否在画面中找到正脸。"""
        if not self._available:
            return False

        ret, frame = self._cap.read()
        if not ret:
            return False

        gray = self.H.cvtColor(frame, self.H.COLOR_BGR2GRAY)
        faces = self._classifier.detectMultiScale(
            gray,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbors,
            minSize=(80, 80),
        )

        # debug: 缓存帧和人脸坐标供预览窗口
        if self._debug:
            self._last_frame = frame.copy()
            self._last_faces = faces

        return len(faces) > 0

    def show_debug_window(self):
        """调试用：在 OpenCV 窗口中显示摄像头画面 + 人脸框。"""
        if not self._available:
            return
        if self._last_frame is None:
            return

        frame = self._last_frame.copy()
        if self._last_faces is not None:  # 注意: 空 tuple 也是 True
            for (x, y, w, h) in self._last_faces:
                self.H.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        self.H.imshow("Face Detection (Debug)", frame)
        self.H.waitKey(1)  # 1ms 刷新，不阻塞

    def wait_for_face(self, min_seconds: float = 5.0, progress_callback=None) -> None:
        """阻塞直到连续检测到人脸满 *min_seconds* 秒。

        人脸消失则重新计时。progress_callback(0.0-1.0) 用于 GUI 进度条。
        """
        if not self._available:
            logger.info("人脸检测不可用，跳过等待。")
            if progress_callback:
                progress_callback(1.0)
            return

        logger.info("待机中，等待人脸唤醒...")
        accumulated = 0.0
        while accumulated < min_seconds:
            if self.detect():
                accumulated += self._interval
            else:
                accumulated = max(0.0, accumulated - self._interval * 2)
            progress = min(1.0, accumulated / min_seconds)
            if progress_callback:
                progress_callback(progress)
            time.sleep(self._interval)
        logger.info("检测到人脸 —— 唤醒！")

    def cleanup(self):
        """释放摄像头资源。"""
        if self._cap is not None:
            self._cap.release()
        if self._debug and self.H is not None:
            self.H.destroyWindow("Face Detection (Debug)")
