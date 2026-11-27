"""Kho Vector/Icon tự động qua Iconify Public REST API + cache cục bộ `library/props/`."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from hbt.config import REPO_ROOT
from hbt.shared.fs_utils import safe_slug

ICONIFY_SEARCH_API = "https://api.iconify.design/search"
ICONIFY_PNG_URL = "https://api.iconify.design/{prefix}/{name}.png?height=360"
_CACHE_TTL_S = 30 * 60
_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list[dict[str, str]]]] = {}


def _safe_slug(raw: str) -> str:
    return safe_slug(raw, default="prop", max_len=64, lowercase=True)


def clear_iconify_cache() -> None:
    _SEARCH_CACHE.clear()


def search_iconify_icons(query: str, limit: int = 6) -> list[dict[str, str]]:
    """Tìm icon trên Iconify API (miễn phí, không cần key, TTL cache 30 phút)."""
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(20, int(limit)))
    cache_key = (q.lower(), lim)
    now = time.monotonic()
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    out: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=3.5, follow_redirects=True) as client:
            resp = client.get(ICONIFY_SEARCH_API, params={"query": q, "limit": lim})
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            icons = payload.get("icons") or []
            for icon_id in icons:
                if not isinstance(icon_id, str) or ":" not in icon_id:
                    continue
                prefix, name = icon_id.split(":", 1)
                out.append(
                    {
                        "id": icon_id,
                        "prefix": prefix,
                        "name": name,
                        "png_url": ICONIFY_PNG_URL.format(prefix=prefix, name=name),
                    }
                )
    except Exception:
        return []

    _SEARCH_CACHE[cache_key] = (now, out)
    return out


def _draw_fallback_badge(
    dest: Path,
    label: str,
    accent_color: tuple[int, int, int, int],
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 320
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 18
    draw.ellipse(
        (pad, pad, size - pad, size - pad),
        fill=(255, 255, 255, 240),
        outline=accent_color,
        width=8,
    )
    font_path = REPO_ROOT / "backend" / "hbt" / "fonts" / "BeVietnamPro-ExtraBold.ttf"
    try:
        font = (
            ImageFont.truetype(str(font_path), size=36)
            if font_path.is_file()
            else ImageFont.load_default()
        )
    except Exception:
        font = ImageFont.load_default()

    short = (label or "ICON").strip().upper()[:12]
    bb = draw.textbbox((0, 0), short, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    draw.text(
        ((size - tw) // 2, (size - th) // 2 - 4),
        short,
        font=font,
        fill=accent_color,
    )
    img.save(dest, format="PNG")
    img.close()
    return dest


def resolve_prop_png(
    prop_query: str,
    library_dir: Path,
    *,
    accent_color: tuple[int, int, int, int] = (217, 35, 46, 255),
) -> Path:
    """Tải & cache icon PNG về `library/props/{slug}.png`; lỗi mạng tự vẽ huy hiệu fallback."""
    props_dir = Path(library_dir) / "props"
    props_dir.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(prop_query)
    cached_png = props_dir / f"{slug}.png"
    if cached_png.is_file() and cached_png.stat().st_size > 0:
        return cached_png

    icons = search_iconify_icons(prop_query, limit=6)
    for icon in icons:
        try:
            with httpx.Client(timeout=4.0, follow_redirects=True) as client:
                resp = client.get(icon["png_url"])
                resp.raise_for_status()
                with Image.open(BytesIO(resp.content)) as raw:
                    rgba = raw.convert("RGBA")
                    rgba.save(cached_png, format="PNG")
                return cached_png
        except Exception:
            continue

    fallback_png = props_dir / f"{slug}_fallback.png"
    return _draw_fallback_badge(fallback_png, prop_query, accent_color)
