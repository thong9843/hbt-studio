"""Cổng tìm kiếm & tải Nhạc nền (BGM) và Tiếng động (SFX) từ Pixabay."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

import httpx

from hbt.pipeline.ffutil import media_duration

PIXABAY_AUDIO_API = "https://pixabay.com/api/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


def _safe_slug(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (raw or "audio").strip()).strip("-")
    return s[:64] or "audio"


async def search_pixabay_audio(
    query: str,
    *,
    kind: Literal["music", "sfx"] = "music",
    api_key: str = "",
    per_page: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm nhạc nền (`music`) hoặc SFX (`sfx`) từ Pixabay API."""
    if not api_key.strip():
        return []

    params = {
        "key": api_key.strip(),
        "q": query.strip() or ("lofi chill" if kind == "music" else "pop notification"),
        "media_type": "music" if kind == "music" else "sound_effect",
        "per_page": max(1, min(50, per_page)),
    }

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await c.get(PIXABAY_AUDIO_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits") if isinstance(data, dict) else []
        results: list[dict[str, Any]] = []
        for h in hits or []:
            if not isinstance(h, dict):
                continue
            dl = str(h.get("download_url") or h.get("audio") or h.get("previewURL") or "").strip()
            pv = str(h.get("preview_url") or h.get("previewURL") or dl).strip()
            if not dl and not pv:
                continue
            raw_tags = str(h.get("tags") or "")
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            results.append(
                {
                    "id": str(h.get("id") or ""),
                    "title": str(
                        h.get("title") or h.get("name") or f"Pixabay {kind} #{h.get('id')}"
                    ),
                    "artist": str(h.get("user") or h.get("artist") or "Pixabay Creator"),
                    "duration": float(h.get("duration") or 0),
                    "tags": tags,
                    "preview_url": pv,
                    "download_url": dl or pv,
                    "kind": kind,
                }
            )
        return results

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=5.0, headers=DEFAULT_HEADERS, follow_redirects=True) as c:
        return await _do(c)


async def import_pixabay_audio(
    *,
    item_id: str,
    title: str,
    artist: str,
    download_url: str,
    kind: Literal["music", "sfx"],
    tags: list[str] | None,
    library_dir: Path,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Tải file .mp3 từ Pixabay vào `library/music/` hoặc `library/sfx/` và ghi `index.json`."""
    sub = "music" if kind == "music" else "sfx"
    target_dir = Path(library_dir) / sub
    target_dir.mkdir(parents=True, exist_ok=True)

    fname = f"pixabay-{_safe_slug(item_id or title)}.mp3"
    out_file = target_dir / fname

    async def _download(c: httpx.AsyncClient) -> bytes:
        resp = await c.get(download_url)
        resp.raise_for_status()
        return resp.content

    if client is not None:
        raw_bytes = await _download(client)
    else:
        async with httpx.AsyncClient(
            timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True
        ) as c:
            raw_bytes = await _download(c)

    out_file.write_bytes(raw_bytes)
    try:
        dur = media_duration(out_file) or 0.0
    except Exception:
        dur = 0.0

    idx_path = target_dir / "index.json"
    entries: list[dict[str, Any]] = []
    if idx_path.is_file():
        try:
            loaded = json.loads(idx_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
        except Exception:
            entries = []

    record = {
        "id": f"pixabay-{_safe_slug(item_id or title)}",
        "file": fname,
        "title": title.strip() or fname,
        "artist": artist.strip() or "Pixabay Creator",
        "source": "pixabay",
        "license": "Pixabay Content License",
        "duration": round(float(dur), 2),
        "moods": tags or [],
        "tags": tags or [],
    }
    entries = [e for e in entries if e.get("file") != fname]
    entries.insert(0, record)

    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, idx_path)

    return {"ok": True, "item": record, "path": str(out_file)}
