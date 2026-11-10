"""Quản lý thư viện meme / sticker local (library/memes/) theo §6 và CH5."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PIL import Image

from hbt.chatting.models import VALID_STICKER_TAGS
from hbt.pipeline.ffutil import run_ffmpeg

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTS = {".png", ".webp", ".gif", ".jpg", ".jpeg"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def get_memes_dir(library_dir: Path) -> Path:
    memes_dir = Path(library_dir) / "memes"
    if memes_dir.is_dir():
        return memes_dir
    # Fallback thư mục cũ nếu có
    stickers_dir = Path(library_dir) / "stickers"
    return stickers_dir if stickers_dir.is_dir() else memes_dir


def load_index(library_dir: Path) -> dict[str, list[str]]:
    """Đọc index.json từ library/memes/."""
    memes_dir = get_memes_dir(library_dir)
    index_file = memes_dir / "index.json"
    if index_file.is_file():
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning("Không đọc được memes/index.json: %s", e)

    return {tag: [] for tag in sorted(VALID_STICKER_TAGS)}


def count_stickers_per_tag(library_dir: Path) -> dict[str, int]:
    """Đếm số meme/sticker theo từng tag."""
    index = load_index(library_dir)
    return {tag: len(index.get(tag, [])) for tag in sorted(VALID_STICKER_TAGS)}


def pick_sticker(library_dir: Path, tag: str, seed: int = 0) -> Path | None:
    """Chọn file meme/sticker theo tag cảm xúc và seed."""
    if tag not in VALID_STICKER_TAGS:
        logger.warning("Tag sticker không hợp lệ: %s", tag)
        return None

    memes_dir = get_memes_dir(library_dir)
    index = load_index(library_dir)
    files = index.get(tag, [])

    if not files:
        logger.warning("Tag '%s' chưa có file meme nào trong %s", tag, memes_dir)
        return None

    chosen_file = files[abs(seed) % len(files)]
    full_path = memes_dir / chosen_file
    if full_path.is_file():
        return full_path

    # Fallback cấu trúc thư mục con <tag>/<file>
    sub_path = memes_dir / tag / chosen_file
    if sub_path.is_file():
        return sub_path

    logger.warning("File meme không tồn tại: %s", full_path)
    return None


def remove_green_screen(img: Image.Image) -> Image.Image:
    """Tách phông xanh lá (colorkey #00FF00) sang nền trong suốt qua bytearray."""
    rgba = img.convert("RGBA")
    raw_bytes = bytearray(rgba.tobytes())
    for i in range(0, len(raw_bytes), 4):
        r = raw_bytes[i]
        g = raw_bytes[i + 1]
        b = raw_bytes[i + 2]
        a = raw_bytes[i + 3]
        if g > 115 and g > r * 1.25 and g > b * 1.25:
            raw_bytes[i + 3] = 0
        elif g > 100 and g > r * 1.15 and g > b * 1.15:
            edge_alpha = max(0, int(a * (1.0 - (g - max(r, b)) / 60.0)))
            raw_bytes[i + 3] = edge_alpha

    return Image.frombytes("RGBA", rgba.size, bytes(raw_bytes))


def load_sticker_or_meme_image(
    file_path: Path, cache_dir: Path | None = None
) -> Image.Image | None:
    """Nạp ảnh sticker từ file ảnh hoặc trích frame video meme phông xanh."""
    if not file_path.is_file():
        return None

    ext = file_path.suffix.lower()

    # 1. Nếu là file ảnh tĩnh
    if ext in SUPPORTED_IMAGE_EXTS:
        try:
            return Image.open(file_path).convert("RGBA")
        except Exception as e:
            logger.warning("Lỗi mở ảnh %s: %s", file_path, e)
            return None

    # 2. Nếu là clip video phông xanh (mp4, mov, webm)
    if ext in SUPPORTED_VIDEO_EXTS:
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            frame_png = cache_dir / f"{file_path.stem}.png"
        else:
            frame_png = file_path.with_suffix(".thumb.png")

        if not frame_png.is_file():
            try:
                run_ffmpeg(
                    [
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        "0.3",
                        "-i",
                        str(file_path),
                        "-vframes",
                        "1",
                        str(frame_png),
                    ]
                )
            except Exception as e:
                logger.warning("Lỗi trích frame từ video meme %s: %s", file_path, e)
                return None

        if frame_png.is_file():
            try:
                raw_img = Image.open(frame_png)
                return remove_green_screen(raw_img)
            except Exception as e:
                logger.warning("Lỗi xử lý frame meme %s: %s", frame_png, e)
                return None

    return None
