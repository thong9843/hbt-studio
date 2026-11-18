"""Cổng tìm kiếm & tải Nhạc nền không lời từ Jamendo API v3."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from hbt.pipeline.ffutil import media_duration, run_ffmpeg
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP

JAMENDO_TRACKS_API = "https://api.jamendo.com/v3.0/tracks/"

JAMENDO_MOOD_TAGS: dict[str, str] = {
    "curious_science": "ambient+electronic+documentary",
    "history_epic": "cinematic+orchestral+epic",
    "funny_quirky": "comedy+quirky+happy",
    "mysterious_tense": "mystery+dark+suspense",
    "calm_lofi": "chillout+lofi+acoustic",
}


def _safe_slug(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (raw or "jamendo").strip()).strip("-")
    return s[:64] or "jamendo"


def _normalize_mp3_lufs(src_file: Path, target_lufs: float = -14.0) -> None:
    tmp = src_file.with_suffix(".norm.mp3")
    try:
        run_ffmpeg(
            [
                *FFMPEG_RESOURCE_CLAMP,
                "-i",
                str(src_file),
                "-af",
                f"loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=11",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(tmp),
            ]
        )
        if tmp.is_file() and tmp.stat().st_size > 0:
            os.replace(tmp, src_file)
    except Exception:
        tmp.unlink(missing_ok=True)


async def search_jamendo_music(
    query: str = "",
    *,
    mood: str = "",
    client_id: str = "",
    limit: int = 15,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm nhạc nền không lời trên Jamendo API v3 (timeout 4.5s)."""
    cid = client_id.strip()
    if not cid:
        return []

    params: dict[str, Any] = {
        "client_id": cid,
        "format": "json",
        "limit": max(1, min(30, int(limit))),
        "vocalinstrumental": "instrumental",
        "audioformat": "mp32",
        "include": "musicinfo",
    }
    q = (query or "").strip()
    mood_key = (mood or "").strip().lower()
    if mood_key in JAMENDO_MOOD_TAGS and not q:
        params["tags"] = JAMENDO_MOOD_TAGS[mood_key]
    elif q in JAMENDO_MOOD_TAGS:
        params["tags"] = JAMENDO_MOOD_TAGS[q]
    elif q:
        params["search"] = q
    else:
        params["tags"] = JAMENDO_MOOD_TAGS["curious_science"]

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await c.get(JAMENDO_TRACKS_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("results") if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            audio_url = str(r.get("audio") or r.get("audiodownload") or "").strip()
            if not audio_url:
                continue
            musicinfo = r.get("musicinfo") if isinstance(r.get("musicinfo"), dict) else {}
            tags_raw = musicinfo.get("tags") if isinstance(musicinfo, dict) else {}
            genres = tags_raw.get("genres") if isinstance(tags_raw, dict) else []
            tags = [str(g) for g in (genres or []) if str(g).strip()]
            out.append(
                {
                    "id": str(r.get("id") or ""),
                    "title": str(r.get("name") or f"Jamendo #{r.get('id')}"),
                    "artist": str(r.get("artist_name") or "Jamendo Artist"),
                    "duration": float(r.get("duration") or 0),
                    "tags": tags,
                    "preview_url": audio_url,
                    "download_url": str(r.get("audiodownload") or audio_url),
                    "license": str(r.get("license_ccurl") or "Creative Commons (Jamendo)"),
                    "source": "jamendo",
                    "kind": "music",
                }
            )
        return out

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=4.5, follow_redirects=True) as c:
        return await _do(c)


async def import_jamendo_music(
    *,
    item_id: str,
    title: str,
    artist: str,
    download_url: str,
    tags: list[str] | None = None,
    moods: list[str] | None = None,
    license_url: str = "",
    library_dir: Path,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Tải .mp3 từ Jamendo về `library/music/`, chuẩn hóa -14 LUFS và ghi `index.json`."""
    target_dir = Path(library_dir) / "music"
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = f"jamendo-{_safe_slug(item_id or title)}.mp3"
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
    _normalize_mp3_lufs(out_file, target_lufs=-14.0)

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

    merged_moods = list(dict.fromkeys([*(moods or []), *(tags or [])]))
    record = {
        "id": f"jamendo-{_safe_slug(item_id or title)}",
        "file": fname,
        "title": title.strip() or fname,
        "artist": artist.strip() or "Jamendo Artist",
        "source": "jamendo",
        "license": license_url.strip() or "Creative Commons (Jamendo)",
        "duration": round(float(dur), 2),
        "moods": merged_moods,
        "tags": list(tags or []),
    }
    entries = [e for e in entries if e.get("file") != fname]
    entries.insert(0, record)

    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, idx_path)
    return {"ok": True, "item": record, "path": str(out_file)}
