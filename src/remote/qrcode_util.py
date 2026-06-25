"""QR 码生成工具 —— 生成 PNG 图片 + 终端 ASCII 二维码。

使用 qrcode 库（纯 Python）+ Pillow 后端。Pillow 已在项目依赖中。
"""

import logging
import socket
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 缓存目录（项目根下的 cache/）
_QR_DIR = Path(__file__).resolve().parent.parent.parent / "cache"


def get_local_ip() -> str:
    """获取本机局域网 IP（通过 UDP socket 连接公网 DNS，不实际发包）。

    返回本机在局域网中的 IP 地址。失败时返回 127.0.0.1。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 连接到一个公网地址（UDP 无连接，不实际发包），以确定出网接口
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        # 回退：尝试广播地址
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()


def generate_qr_png(url: str) -> Optional[Path]:
    """生成 URL 的二维码 PNG 图片，返回文件路径。失败返回 None。"""
    try:
        import qrcode
    except ImportError:
        logger.warning("qrcode 库未安装 —— 跳过二维码图片生成")
        return None

    _QR_DIR.mkdir(parents=True, exist_ok=True)
    qr_path = _QR_DIR / "remote_control_qr.png"

    img = qrcode.make(url, box_size=8, border=2)
    img.save(str(qr_path))
    logger.info("二维码已保存: %s", qr_path)
    return qr_path


def print_qr_ascii(url: str):
    """在终端打印 ASCII 二维码（不需要文件 I/O）。"""
    try:
        import qrcode
    except ImportError:
        return

    qr = qrcode.QRCode(box_size=2, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def _terminal_hyperlink(text: str, url: str) -> str:
    """生成 OSC 8 终端超链接（现代终端模拟器支持点击打开）。"""
    import sys
    if not sys.stdout.isatty():
        return url
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def display_qr(url: str, title: str = "遥控模式", exit_hint: str = "按 'q' + Enter 退出遥控模式"):
    """生成二维码并打印终端信息（ASCII 码 + URL + PNG 路径）。"""
    border = "=" * 52

    print()
    print(border)
    print(f"    BJEA 校园导览机器人 —— {title}")
    print()
    print(f"    在手机上打开此链接:")
    print(f"    {_terminal_hyperlink(url, url)}")
    print()

    # 终端 ASCII 二维码
    print_qr_ascii(url)

    # PNG 文件路径
    png_path = generate_qr_png(url)
    if png_path and png_path.exists():
        print(f"    或扫描二维码图片: file://{png_path.resolve()}")
        print()

    print(f"    {exit_hint}")
    print(border)
    print()
