"""Cổng tìm kiếm & tải Nhạc nền Ambience / SFX từ Freesound API v2."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import httpx

from hbt.pipeline.ffutil import media_duration
from hbt.shared.audio_utils import normalize_audio_lufs
from hbt.shared.fs_utils import safe_slug

FREESOUND_SEARCH_API = "https://freesound.org/apiv2/search/text/"

FREESOUND_MOOD_QUERIES: dict[str, str] = {
    "curious_science": "ambient electronic documentary music",
    "history_epic": "cinematic orchestral epic music",
    "funny_quirky": "quirky comedy happy music",
    "mysterious_tense": "mystery dark suspense ambient",
    "calm_lofi": "chillout lofi acoustic music",
}


def _safe_slug(raw: str) -> str:
    return safe_slug(raw, default="freesound", max_len=64)


def _normalize_mp3_lufs(src_file: Path, target_lufs: float) -> None:
    normalize_audio_lufs(src_file, target_lufs=target_lufs)


async def search_freesound_audio(
    query: str = "",
    *,
    kind: Literal["music", "sfx"] = "music",
    mood: str = "",
    api_key: str = "",
    page_size: int = 15,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm nhạc nền / ambience hoặc SFX từ Freesound API v2 (timeout 4.5s)."""
    key = api_key.strip()
    if not key:
        return []

    mood_key = (mood or "").strip().lower()
    q = (query or "").strip()
    if not q and mood_key in FREESOUND_MOOD_QUERIES:
        q = FREESOUND_MOOD_QUERIES[mood_key]
    elif q in FREESOUND_MOOD_QUERIES:
        q = FREESOUND_MOOD_QUERIES[q]
    elif not q:
        q = "ambient music" if kind == "music" else "whoosh"

    params: dict[str, Any] = {
        "query": q,
        "token": key,
        "fields": "id,name,duration,previews,tags,license,username",
        "page_size": max(1, min(30, int(page_size))),
    }
    if kind == "music":
        params["filter"] = "duration:[15 TO 300]"

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await c.get(FREESOUND_SEARCH_API, params=params)
        if resp.status_code in (401, 403):
            raise ValueError(
                "FREESOUND_API_KEY không hợp lệ hoặc chưa được kích hoạt. "
                "Vui lòng kiểm tra lại trong Cài đặt."
            )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("results") if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            previews = r.get("previews") if isinstance(r.get("previews"), dict) else {}
            hq = str(previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or "").strip()
            if not hq:
                continue
            raw_tags = r.get("tags") if isinstance(r.get("tags"), list) else []
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "title": str(r.get("name") or f"Freesound #{r.get('id')}"),
                    "artist": str(r.get("username") or "Freesound Creator"),
                    "duration": float(r.get("duration") or 0),
                    "tags": [str(t) for t in raw_tags if str(t).strip()],
                    "preview_url": hq,
                    "download_url": hq,
                    "license": str(r.get("license") or "Creative Commons (Freesound)"),
                    "source": "freesound",
                    "kind": kind,
                }
            )
        return out

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=4.5, follow_redirects=True) as c:
        return await _do(c)


async def import_freesound_audio(
    *,
    item_id: str,
    title: str,
    artist: str,
    download_url: str,
    kind: Literal["music", "sfx"] = "music",
    tags: list[str] | None = None,
    license_url: str = "",
    library_dir: Path,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Tải preview-hq-mp3 từ Freesound về `library/music/` (-14 LUFS) hoặc `library/sfx/`."""
    sub = "music" if kind == "music" else "sfx"
    target_dir = Path(library_dir) / sub
    target_dir.mkdir(parents=True, exist_ok=True)

    fname = f"freesound-{_safe_slug(item_id or title)}.mp3"
    out_file = target_dir / fname

    async def _dl(c: httpx.AsyncClient) -> bytes:
        resp = await c.get(download_url)
        resp.raise_for_status()
        return resp.content

    if client is not None:
        raw_bytes = await _dl(client)
    else:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
            raw_bytes = await _dl(c)

    out_file.write_bytes(raw_bytes)
    _normalize_mp3_lufs(out_file, target_lufs=-14.0 if kind == "music" else -16.0)

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
        "id": f"freesound-{_safe_slug(item_id or title)}",
        "file": fname,
        "title": title.strip() or fname,
        "artist": artist.strip() or "Freesound Creator",
        "source": "freesound",
        "license": license_url.strip() or "Creative Commons (Freesound)",
        "duration": round(float(dur), 2),
        "moods": list(tags or []),
        "tags": list(tags or []),
    }
    entries = [e for e in entries if e.get("file") != fname]
    entries.insert(0, record)

    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, idx_path)
    return {"ok": True, "item": record, "path": str(out_file)}
