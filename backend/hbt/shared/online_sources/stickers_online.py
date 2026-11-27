"""Cổng Sticker động trực tuyến: Giphy Stickers API & SigStick Pack Importer."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from hbt.shared.fs_utils import safe_slug
from hbt.shared.online_sources.meme_tagging import auto_tag_meme

GIPHY_SEARCH_URL = "https://api.giphy.com/v1/stickers/search"
GIPHY_TRENDING_URL = "https://api.giphy.com/v1/stickers/trending"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

_STICKER_URL_RE = re.compile(
    r'https?://[^\s"\'<>\\]+\.(?:webp|png|webm|gif)(?:\?[^\s"\'<>\\]*)?',
    re.IGNORECASE,
)


def _safe_slug(raw: str) -> str:
    return safe_slug(raw, default="sticker", max_len=64, lowercase=True)


def _infer_emotion_tag(name: str) -> str:
    tags, _ = auto_tag_meme(name)
    mapping = {
        "hai_huoc": "cuoi",
        "bat_ngo": "soc",
        "that_vong": "khoc",
        "tuc_gian": "gian",
        "ngai_ngung": "ngai",
        "vo_tay": "ok",
    }
    for t in tags:
        if t in mapping:
            return mapping[t]
    return "vui"


async def search_giphy_stickers(
    query: str,
    *,
    api_key: str,
    limit: int = 24,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm sticker nền trong suốt từ Giphy Stickers API (hoặc trending khi query trống)."""
    if not api_key.strip():
        return []

    q = query.strip()
    url = GIPHY_SEARCH_URL if q else GIPHY_TRENDING_URL
    params: dict[str, Any] = {
        "api_key": api_key.strip(),
        "limit": max(1, min(48, limit)),
        "rating": "pg-13",
    }
    if q:
        params["q"] = q

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await c.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("data") if isinstance(payload, dict) else []
        out: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            images = row.get("images") or {}
            orig = images.get("original") or {}
            fixed = images.get("fixed_height") or orig
            webp_url = str(orig.get("webp") or fixed.get("webp") or "").strip()
            gif_url = str(orig.get("url") or fixed.get("url") or "").strip()
            mp4_url = str(orig.get("mp4") or "").strip()
            preview_url = webp_url or gif_url or mp4_url
            download_url = webp_url or gif_url or mp4_url
            if not download_url:
                continue
            out.append(
                {
                    "id": str(row.get("id") or ""),
                    "title": str(row.get("title") or f"Giphy Sticker #{row.get('id')}"),
                    "preview_url": preview_url,
                    "download_url": download_url,
                    "ext": ".webp" if webp_url else (".gif" if gif_url else ".mp4"),
                    "source": "giphy",
                }
            )
        return out

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True) as c:
        return await _do(c)


async def import_giphy_sticker(
    *,
    sticker_id: str,
    title: str,
    download_url: str,
    library_dir: Path,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Tải 1 sticker Giphy về `library/stickers/` và cập nhật `index.json`."""
    stickers_dir = Path(library_dir) / "stickers"
    stickers_dir.mkdir(parents=True, exist_ok=True)

    path_part = urlparse(download_url).path.lower()
    ext = ".webp" if ".webp" in path_part else (".mp4" if ".mp4" in path_part else ".gif")
    slug = _safe_slug(sticker_id or title)
    fname = f"giphy-{slug}{ext}"
    out_file = stickers_dir / fname

    async def _dl(c: httpx.AsyncClient) -> bytes:
        r = await c.get(download_url)
        r.raise_for_status()
        return r.content

    if client is not None:
        raw = await _dl(client)
    else:
        async with httpx.AsyncClient(
            timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True
        ) as c:
            raw = await _dl(c)

    out_file.write_bytes(raw)
    tag = _infer_emotion_tag(title or slug)

    idx_path = stickers_dir / "index.json"
    entries: list[dict[str, Any]] = []
    if idx_path.is_file():
        try:
            loaded = json.loads(idx_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
        except Exception:
            entries = []

    record = {
        "id": f"giphy-{slug}",
        "file": fname,
        "title": title.strip() or fname,
        "tag": tag,
        "source": "giphy",
    }
    entries = [e for e in entries if e.get("file") != fname]
    entries.insert(0, record)
    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, idx_path)

    return {"ok": True, "item": record, "path": str(out_file)}


async def import_sigstick_pack(
    url: str,
    *,
    library_dir: Path,
    max_items: int = 30,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Bóc tách và tải trọn bộ sticker từ link SigStick (`sigstick.com/pack/...`)."""
    parsed_url = urlparse(url.strip())
    if "sigstick.com" not in (parsed_url.netloc or "").lower():
        raise ValueError(
            "URL phải thuộc tên miền sigstick.com (ví dụ: https://www.sigstick.com/pack/...)"
        )

    parts = [p for p in parsed_url.path.split("/") if p]
    pack_slug = _safe_slug(parts[-1] if parts else "sigstick-pack")
    pack_dir = Path(library_dir) / "stickers" / pack_slug
    pack_dir.mkdir(parents=True, exist_ok=True)

    async def _run(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await c.get(url.strip())
        resp.raise_for_status()
        page_html = resp.text

        raw_urls = _STICKER_URL_RE.findall(page_html)
        sticker_urls: list[str] = []
        seen: set[str] = set()
        for u in raw_urls:
            clean_u = html.unescape(u.replace("\\u002F", "/").replace("\\/", "/"))
            lower_u = clean_u.lower()
            # Bỏ qua favicon / logo / asset trang web chung
            if any(skip in lower_u for skip in ("favicon", "logo", "og-image", "avatar")):
                continue
            if clean_u not in seen:
                seen.add(clean_u)
                sticker_urls.append(clean_u)
            if len(sticker_urls) >= max_items:
                break

        imported: list[dict[str, Any]] = []
        for idx, s_url in enumerate(sticker_urls):
            try:
                s_resp = await c.get(s_url)
                s_resp.raise_for_status()
                ext = Path(urlparse(s_url).path).suffix.lower()
                if ext not in {".webp", ".png", ".webm", ".gif"}:
                    ext = ".webp"
                fname = f"stk_{idx + 1:02d}{ext}"
                (pack_dir / fname).write_bytes(s_resp.content)
                tag = _infer_emotion_tag(f"{pack_slug} {Path(s_url).stem}")
                imported.append(
                    {
                        "id": f"{pack_slug}-{idx + 1:02d}",
                        "file": f"{pack_slug}/{fname}",
                        "title": f"{pack_slug} #{idx + 1}",
                        "tag": tag,
                        "source": "sigstick",
                    }
                )
            except Exception:
                continue
        return imported

    if client is not None:
        imported_items = await _run(client)
    else:
        async with httpx.AsyncClient(
            timeout=15.0, headers=DEFAULT_HEADERS, follow_redirects=True
        ) as c:
            imported_items = await _run(c)

    idx_path = pack_dir / "index.json"
    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(imported_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, idx_path)

    return {
        "ok": True,
        "pack_slug": pack_slug,
        "count": len(imported_items),
        "items": imported_items,
    }
