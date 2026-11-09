"""Quản lý thư viện sticker local (library/stickers/<tag>/) theo §6."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from hbt.chatting.models import VALID_STICKER_TAGS

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".png", ".webp", ".gif"}


def get_stickers_dir(library_dir: Path) -> Path:
    return Path(library_dir) / "stickers"


def build_index(library_dir: Path) -> dict[str, list[str]]:
    """Quét library/stickers/<tag>/ và ghi file index.json."""
    stickers_dir = get_stickers_dir(library_dir)
    index: dict[str, list[str]] = {tag: [] for tag in sorted(VALID_STICKER_TAGS)}

    if stickers_dir.is_dir():
        for tag in VALID_STICKER_TAGS:
            tag_dir = stickers_dir / tag
            if tag_dir.is_dir():
                files = [
                    f.name
                    for f in tag_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
                ]
                index[tag] = sorted(files)

    index_file = stickers_dir / "index.json"
    stickers_dir.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def load_index(library_dir: Path) -> dict[str, list[str]]:
    """Đọc index.json nếu có, nếu chưa thì quét trực tiếp."""
    stickers_dir = get_stickers_dir(library_dir)
    index_file = stickers_dir / "index.json"
    if index_file.is_file():
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning("Không đọc được stickers/index.json: %s", e)

    return build_index(library_dir)


def count_stickers_per_tag(library_dir: Path) -> dict[str, int]:
    """Đếm số sticker theo từng tag."""
    index = load_index(library_dir)
    return {tag: len(index.get(tag, [])) for tag in sorted(VALID_STICKER_TAGS)}


def pick_sticker(library_dir: Path, tag: str, seed: int = 0) -> Path | None:
    """Chọn file sticker theo tag và seed.

    Nếu tag thiếu file: trả về None, ghi cảnh báo, không lỗi.
    """
    if tag not in VALID_STICKER_TAGS:
        logger.warning("Tag sticker không hợp lệ: %s", tag)
        return None

    stickers_dir = get_stickers_dir(library_dir)
    index = load_index(library_dir)
    files = index.get(tag, [])

    if not files:
        logger.warning("Tag '%s' chưa có file sticker nào trong %s", tag, stickers_dir / tag)
        return None

    chosen_file = files[abs(seed) % len(files)]
    full_path = stickers_dir / tag / chosen_file
    if full_path.is_file():
        return full_path

    logger.warning("File sticker không tồn tại: %s", full_path)
    return None
