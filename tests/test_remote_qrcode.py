"""测试 QR 码生成工具。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from remote.qrcode_util import generate_qr_png, get_local_ip


class TestQRCode:
    """QR 码生成测试。"""

    def test_generate_qr_png(self):
        path = generate_qr_png("http://192.168.1.100:8080")
        if path is not None:  # qrcode 可能未安装
            assert path.exists()
            assert path.suffix == ".png"
            path.unlink()  # 清理

    def test_get_local_ip(self):
        ip = get_local_ip()
        # 应该是合法 IP 格式
        parts = ip.split(".")
        assert len(parts) == 4
        for p in parts:
            assert 0 <= int(p) <= 255
