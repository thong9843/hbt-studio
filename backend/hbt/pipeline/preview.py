"""Ảnh xem trước một cảnh: ảnh + nhãn + thẻ chữ + phụ đề mẫu (cụm đầu), IMPLEMENT.md mục 9.

Dùng đúng mã vẽ của lúc dựng (`visual.py`, `captions.py`) nên ảnh khớp với khung hình video.
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

from PIL import Image

from hbt.models import Project

from . import cache
from . import captions as _captions
from . import visual as _visual
from .captions import caption_y_for, split_phrases
from .text import parse_voice
from .visual import build_scene_layers, render_caption

AVATAR = "hay-biet-tuot_avatar.png"  # ảnh mặc định cho cảnh chưa có ảnh (IMPLEMENT.md 10.1)
_CODE = cache.code_digest(_visual, _captions, sys.modules[__name__])


def first_phrase_words(voice: str) -> list[str]:
    """Các chữ của cụm đầu tiên trong lời đọc (cách chia cụm giống lúc dựng)."""
    tokens = parse_voice(voice)
    if not tokens:
        return []
    ids = split_phrases(tokens, [0] * len(tokens))[0]
    return [tokens[i]["disp"] for i in ids]


def scene_preview_png(
    project: Project, project_dir: Path, scene_index: int, brand_dir: Path
) -> bytes:
    """PNG 1080×1920 của cảnh `scene_index` (từ 0). Có cache trong `build/previews/`."""
    scene = project.scenes[scene_index]
    image = project_dir / scene.image if scene.image else None
    if image is None or not image.is_file():
        image = brand_dir / AVATAR
    theme = project.theme.model_dump()
    words = first_phrase_words(scene.voice)
    key = cache.digest(
        "preview", image, scene.model_dump(exclude={"punch", "image"}), theme, words, _CODE
    )
    out_dir = project_dir / "build" / "previews"
    out = out_dir / f"p{scene_index}-{key[:16]}.png"
    if out.is_file():
        return out.read_bytes()

    with tempfile.TemporaryDirectory() as tmp:
        base_png, card_png = Path(tmp) / "base.png", Path(tmp) / "card.png"
        _, bottom = build_scene_layers(scene.model_dump(), image, base_png, card_png, theme)
        frame = Image.open(base_png).convert("RGBA")
        frame.alpha_composite(Image.open(card_png).convert("RGBA"))
        if words:
            cap_png = Path(tmp) / "caption.png"
            render_caption(words, 0, str(cap_png), caption_y_for(scene.caption_y, bottom))
            frame.alpha_composite(Image.open(cap_png).convert("RGBA"))
        buf = io.BytesIO()
        frame.convert("RGB").save(buf, format="PNG")
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    return buf.getvalue()


def resize_png(png: bytes, width: int) -> bytes:
    """Thu nhỏ theo chiều rộng (giữ tỉ lệ) cho khung xem trước nhỏ."""
    with Image.open(io.BytesIO(png)) as im:
        height = max(1, round(im.height * width / im.width))
        buf = io.BytesIO()
        im.resize((width, height), Image.LANCZOS).save(buf, format="PNG")
        return buf.getvalue()
