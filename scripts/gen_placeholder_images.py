#!/usr/bin/env python3
"""Генерирует простые PNG-заглушки в static/images (без зависимостей)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)


def write_solid_png(path: Path, width: int, height: int, r: int, g: int, b: int) -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    row = bytes([0]) + bytes([r, g, b] * width)
    for _ in range(height):
        raw.extend(row)
    compressed = zlib.compress(bytes(raw), 9)
    data = sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", compressed) + _png_chunk(b"IEND", b"")
    path.write_bytes(data)


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "static" / "images"
    root.mkdir(parents=True, exist_ok=True)

    stages = [
        ("stage01.png", (255, 224, 102)),
        ("stage02.png", (255, 210, 90)),
        ("stage03.png", (245, 200, 80)),
        ("stage04.png", (235, 190, 70)),
        ("stage05.png", (225, 180, 60)),
        ("stage06.png", (215, 170, 50)),
        ("stage07.png", (205, 160, 45)),
        ("stage08.png", (195, 150, 40)),
    ]
    for name, rgb in stages:
        write_solid_png(root / name, 480, 270, *rgb)

    write_solid_png(root / "tier_bronze.png", 480, 270, 180, 110, 60)
    write_solid_png(root / "tier_silver.png", 480, 270, 190, 195, 200)
    write_solid_png(root / "tier_gold.png", 480, 270, 255, 200, 60)

    print("Written:", root)


if __name__ == "__main__":
    main()
