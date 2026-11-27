"""Cổng tìm kiếm & tải Meme phông xanh từ GreenScreenMemes.com (REST API + HTML fallback)."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import httpx

from hbt.pipeline.ffutil import media_duration, run_ffmpeg
from hbt.shared.fs_utils import safe_slug
from hbt.shared.online_sources.meme_tagging import (
    auto_tag_meme,
    load_memes_index,
    save_memes_index,
)

GREENSCREEN_WP_API = "https://greenscreenmemes.com/wp-json/wp/v2/posts"
GREENSCREEN_BASE = "https://greenscreenmemes.com/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9",
}

_MP4_RE = re.compile(r'https?://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?', re.IGNORECASE)
_POSTER_RE = re.compile(r'poster=["\']([^"\']+)["\']', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_title(raw: str) -> str:
    return html.unescape(_TAG_RE.sub("", raw or "")).strip()


def _safe_slug(raw: str) -> str:
    return safe_slug(raw, default="meme", max_len=64, lowercase=True)


def _parse_wp_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        content_html = ""
        if isinstance(p.get("content"), dict):
            content_html = str(p["content"].get("rendered") or "")
        mp4_matches = _MP4_RE.findall(content_html)
        if not mp4_matches:
            continue
        video_url = html.unescape(mp4_matches[0])
        poster_match = _POSTER_RE.search(content_html)
        poster_url = html.unescape(poster_match.group(1)) if poster_match else ""

        if not poster_url and isinstance(p.get("_embedded"), dict):
            media_list = p["_embedded"].get("wp:featuredmedia") or []
            if media_list and isinstance(media_list[0], dict):
                poster_url = str(media_list[0].get("source_url") or "")

        raw_title = (
            p["title"].get("rendered") if isinstance(p.get("title"), dict) else p.get("title")
        )
        title = _clean_title(str(raw_title or f"Meme #{p.get('id')}"))
        slug = _safe_slug(str(p.get("slug") or title or p.get("id")))
        results.append(
            {
                "id": slug,
                "title": title,
                "video_url": video_url,
                "poster_url": poster_url,
                "source": "greenscreenmemes.com",
            }
        )
    return results


def _parse_html_fallback(page_html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, url in enumerate(_MP4_RE.findall(page_html)):
        clean_url = html.unescape(url)
        if clean_url in seen:
            continue
        seen.add(clean_url)
        stem = Path(clean_url.split("?")[0]).stem
        results.append(
            {
                "id": _safe_slug(stem or f"gsm-{idx + 1}"),
                "title": stem.replace("-", " ").replace("_", " ").strip()
                or f"Green Meme {idx + 1}",
                "video_url": clean_url,
                "poster_url": "",
                "source": "greenscreenmemes.com",
            }
        )
    return results


async def search_greenmeme(
    query: str,
    *,
    per_page: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm meme phông xanh trên greenscreenmemes.com (WP REST API + HTML fallback)."""
    q = query.strip()

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            params: dict[str, Any] = {"per_page": max(1, min(40, per_page)), "_embed": 1}
            if q:
                params["search"] = q
            resp = await c.get(GREENSCREEN_WP_API, params=params)
            if resp.status_code == 200:
                posts = resp.json()
                if isinstance(posts, list):
                    parsed = _parse_wp_posts(posts)
                    if parsed:
                        return parsed
        except Exception:
            pass

        # Fallback: quét HTML trang tìm kiếm hoặc trang chủ
        html_resp = await c.get(GREENSCREEN_BASE, params={"s": q} if q else None)
        html_resp.raise_for_status()
        return _parse_html_fallback(html_resp.text)

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True) as c:
        return await _do(c)


async def import_greenmeme(
    *,
    meme_id: str,
    title: str,
    video_url: str,
    poster_url: str = "",
    library_dir: Path,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Tải file .mp4 về `library/memes/`, tạo thumbnail .jpg, tự gắn tag và ghi `index.json`."""
    memes_dir = Path(library_dir) / "memes"
    memes_dir.mkdir(parents=True, exist_ok=True)

    slug = _safe_slug(meme_id or title)
    fname = f"{slug}.mp4"
    video_path = memes_dir / fname
    thumb_name = f"{slug}_thumb.jpg"
    thumb_path = memes_dir / thumb_name

    async def _download(c: httpx.AsyncClient) -> tuple[bytes, bytes | None]:
        v_resp = await c.get(video_url)
        v_resp.raise_for_status()
        p_bytes: bytes | None = None
        if poster_url.strip():
            try:
                p_resp = await c.get(poster_url.strip())
                if p_resp.status_code == 200:
                    p_bytes = p_resp.content
            except Exception:
                p_bytes = None
        return v_resp.content, p_bytes

    if client is not None:
        v_bytes, p_bytes = await _download(client)
    else:
        async with httpx.AsyncClient(
            timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True
        ) as c:
            v_bytes, p_bytes = await _download(c)

    video_path.write_bytes(v_bytes)
    if p_bytes:
        thumb_path.write_bytes(p_bytes)
    else:
        try:
            run_ffmpeg(
                [
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    "0.2",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(thumb_path),
                ]
            )
        except Exception:
            pass

    try:
        dur = media_duration(video_path) or 0.0
    except Exception:
        dur = 0.0
    tags, topic = auto_tag_meme(title or slug)

    items = load_memes_index(memes_dir)
    record = {
        "id": slug,
        "file": fname,
        "title": title.strip() or slug,
        "source": "greenscreenmemes.com",
        "thumb": thumb_name if thumb_path.is_file() else "",
        "duration_sec": round(float(dur), 2),
        "tags": tags,
        "topic": topic,
    }
    items = [it for it in items if str(it.get("id")) != slug and str(it.get("file")) != fname]
    items.insert(0, record)
    save_memes_index(memes_dir, items)

    return {"ok": True, "item": record, "path": str(video_path)}
