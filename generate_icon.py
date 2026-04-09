"""
Generates icon.ico from the ShelfClip "S" logo at 16, 32, 48, and 256px.
Run once before building — build.bat calls this automatically.
"""
import sys
import struct
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt


def make_pixmap(size: int) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = max(1, size // 8)
    radius = size // 4
    p.setBrush(QColor(91, 156, 246))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(margin, margin, size - 2 * margin, size - 2 * margin, radius, radius)
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Segoe UI", max(1, size // 2), QFont.Weight.Bold))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    p.end()
    return px


def build_ico(sizes=(16, 32, 48, 256)) -> bytes:
    app = QApplication.instance() or QApplication(sys.argv)

    png_chunks = []
    for size in sizes:
        px = make_pixmap(size)
        tmp = Path(tempfile.mktemp(suffix=".png"))
        px.save(str(tmp), "PNG")
        png_chunks.append(tmp.read_bytes())
        tmp.unlink()

    count = len(sizes)
    header = struct.pack("<HHH", 0, 1, count)  # ICONDIR

    entries = b""
    offset = 6 + 16 * count  # after header + all ICONDIRENTRY structs
    for size, data in zip(sizes, png_chunks):
        w = h = 0 if size == 256 else size
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)

    return header + entries + b"".join(png_chunks)


if __name__ == "__main__":
    out = Path(__file__).parent / "icon.ico"
    out.write_bytes(build_ico())
    print(f"icon.ico written to {out}")
