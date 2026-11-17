"""Cổng tìm kiếm & tải Meme SFX từ Voicemod Tuna (https://tuna.voicemod.net)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from hbt.pipeline.ffutil import media_duration, run_ffmpeg
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP

TUNA_SEARCH_API = "https://api.tuna.voicemod.net/v1/sounds/search"
TUNA_TAG_PAGE = "https://tuna.voicemod.net/sounds/tag/{tag}"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _safe_slug(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (raw or "sfx").strip().lower()).strip("-")
    return s[:64] or "sfx"


def _normalize_sound_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    preview = str(
        item.get("oggPath")
        or item.get("mp3Path")
        or item.get("soundPath")
        or item.get("preview_url")
        or item.get("url")
        or ""
    ).strip()
    # Ưu tiên mp3Path nếu có để tương thích rộng
    mp3 = str(item.get("mp3Path") or "").strip()
    if mp3:
        preview = mp3
    if not preview or not preview.startswith("http"):
        return None
    sid = str(item.get("id") or item.get("uuid") or _safe_slug(str(item.get("name") or "")))
    title = str(item.get("name") or item.get("title") or f"Tuna SFX #{sid[:8]}").strip()
    raw_dur = item.get("duration") or item.get("duration_sec") or 0.0
    try:
        dur = float(raw_dur)
        if dur > 100:  # ms -> s
            dur = dur / 1000.0
    except (TypeError, ValueError):
        dur = 0.0
    raw_tags = item.get("tags") or []
    tags = (
        [str(t).strip() for t in raw_tags if str(t).strip()] if isinstance(raw_tags, list) else []
    )
    return {
        "id": sid,
        "title": title,
        "duration_sec": round(dur, 2),
        "preview_url": preview,
        "source": "tuna",
        "tags": tags[:6],
    }


def _extract_from_html(html: str) -> list[dict[str, Any]]:
    """Fallback bóc tách danh sách âm thanh từ __NEXT_DATA__ trên trang tag Tuna."""
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return []

    found: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for el in node:
                _walk(el)
        elif isinstance(node, dict):
            if ("mp3Path" in node or "oggPath" in node or "soundPath" in node) and (
                "name" in node or "title" in node
            ):
                norm = _normalize_sound_item(node)
                if norm is not None:
                    found.append(norm)
            else:
                for v in node.values():
                    _walk(v)

    _walk(data)
    return found


async def search_tuna_sfx(
    query: str = "meme",
    *,
    per_page: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm Meme SFX trên Voicemod Tuna; fallback sang trang tag hoặc [] khi lỗi mạng."""
    q = (query or "").strip() or "meme"
    limit = max(1, min(40, per_page))

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            resp = await c.get(TUNA_SEARCH_API, params={"search": q, "size": limit})
            if resp.status_code == 200:
                payload = resp.json()
                raw_items = (
                    payload
                    if isinstance(payload, list)
                    else (
                        payload.get("items") or payload.get("sounds") or payload.get("data") or []
                    )
                )
                out = [norm for it in raw_items if (norm := _normalize_sound_item(it)) is not None]
                if out:
                    return out[:limit]
        except Exception:
            pass

        # Fallback sang bóc tách HTML trang tag
        try:
            tag_slug = quote(_safe_slug(q))
            page = await c.get(TUNA_TAG_PAGE.format(tag=tag_slug))
            if page.status_code == 200:
                return _extract_from_html(page.text)[:limit]
        except Exception:
            pass
        return []

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=4.5, headers=DEFAULT_HEADERS, follow_redirects=True) as c:
        return await _do(c)


async def import_tuna_sfx(
    *,
    item_id: str,
    title: str,
    preview_url: str,
    tags: list[str] | None = None,
    library_dir: Path,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Tải Meme SFX từ Tuna về `library/sfx/`, chuẩn hóa -16 LUFS và ghi `index.json`."""
    sfx_dir = Path(library_dir) / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)

    slug = _safe_slug(title)
    short_id = _safe_slug(item_id)[:10] or "tuna"
    out_file = sfx_dir / f"tuna-{slug}-{short_id}.mp3"
    tmp_file = sfx_dir / f".tmp-{slug}-{short_id}.mp3"

    async def _download(c: httpx.AsyncClient) -> bytes:
        r = await c.get(preview_url)
        r.raise_for_status()
        return r.content

    if client is not None:
        raw_bytes = await _download(client)
    else:
        async with httpx.AsyncClient(
            timeout=20.0, headers=DEFAULT_HEADERS, follow_redirects=True
        ) as c:
            raw_bytes = await _download(c)

    tmp_file.write_bytes(raw_bytes)
    try:
        # Chuẩn hóa âm lượng về -16 LUFS để không rè khi trộn video
        try:
            run_ffmpeg(
                [
                    *FFMPEG_RESOURCE_CLAMP,
                    "-i",
                    str(tmp_file),
                    "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    str(out_file),
                ]
            )
        except Exception:
            tmp_file.replace(out_file)
    finally:
        tmp_file.unlink(missing_ok=True)

    dur = 0.0
    try:
        dur = float(media_duration(out_file) or 0.0)
    except Exception:
        dur = 0.0

    index_path = sfx_dir / "index.json"
    entries: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = [e for e in loaded if isinstance(e, dict)]
        except Exception:
            entries = []

    entry = {
        "id": f"tuna-{short_id}",
        "title": title.strip() or out_file.stem,
        "file": out_file.name,
        "tags": list(tags or ["meme", "sfx"]),
        "duration_sec": round(dur, 2),
        "source": "tuna",
    }
    entries = [e for e in entries if e.get("file") != out_file.name]
    entries.insert(0, entry)
    index_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"ok": True, "item": entry, "file_path": str(out_file)}


download_tuna_sfx = import_tuna_sfx
