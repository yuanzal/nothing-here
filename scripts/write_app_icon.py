"""Regenerate assets/app.ico from the tray N mark.

Usage (from repo root, venv with PyQt6):
  python scripts/write_app_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import QBuffer, QIODevice  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def write_ico(path: Path) -> Path:
    QApplication.instance() or QApplication(["write_app_icon"])
    from nothing_here.ui.app_mark import render_mark

    images = [_png_bytes(render_mark, size) for size in SIZES]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pack_ico(images))
    return path


def _png_bytes(render_mark, size: int) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    render_mark(size).save(buffer, "PNG")
    return bytes(buffer.data())


def _pack_ico(pngs: list[bytes]) -> bytes:
    count = len(pngs)
    offset = 6 + 16 * count
    chunks = [struct.pack("<HHH", 0, 1, count)]
    payload = bytearray()
    for png in pngs:
        width, height = struct.unpack(">II", png[16:24])
        entry_w = 0 if width >= 256 else width
        entry_h = 0 if height >= 256 else height
        chunks.append(struct.pack("<BBBBHHII", entry_w, entry_h, 0, 0, 1, 32, len(png), offset))
        payload.extend(png)
        offset += len(png)
    return b"".join(chunks) + bytes(payload)


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "app.ico"
    write_ico(dest)
    print(dest)
