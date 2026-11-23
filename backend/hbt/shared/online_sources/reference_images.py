"""Kho ảnh tư liệu tự động cho StickV: Wikimedia Commons (0 key) -> Pixabay -> Iconify fallback."""

from __future__ import annotations

import hashlib
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from hbt.app_settings import resolve_online_api_key
from hbt.shared.online_sources.iconify_props import resolve_prop_png

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
PIXABAY_IMAGE_API = "https://pixabay.com/api/"
WIKIMEDIA_USER_AGENT = "HBTStudio/1.0 (https://github.com/thong9843/hbt-studio; local desktop app)"
MIN_IMAGE_DIM = 300
_ALLOWED_MIMES = {"image/jpeg", "image/jpg", "image/png"}
_CACHE_TTL_S = 30 * 60
_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}


def _safe_slug(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (raw or "ref").strip().lower()).strip("-")
    return s[:48] or "ref"


def clear_reference_image_cache() -> None:
    _SEARCH_CACHE.clear()


def search_wikimedia_images(
    query: str,
    *,
    limit: int = 6,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh tư liệu JPEG/PNG (>= 300px) từ Wikimedia Commons API (miễn phí, không cần key)."""
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(12, int(limit)))
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{q} filetype:bitmap",
        "gsrnamespace": "6",
        "gsrlimit": str(max(lim * 2, 8)),
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": "1024",
        "format": "json",
    }
    headers = {"User-Agent": WIKIMEDIA_USER_AGENT}
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=6.0, follow_redirects=True)
    out: list[dict[str, Any]] = []
    try:
        resp = http.get(WIKIMEDIA_API, params=params, headers=headers)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
        pages = (payload.get("query") or {}).get("pages") or {}
        if not isinstance(pages, dict):
            return []
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            infos = page.get("imageinfo") or []
            if not infos or not isinstance(infos[0], dict):
                continue
            info = infos[0]
            mime = str(info.get("mime") or "").lower()
            if mime not in _ALLOWED_MIMES:
                continue
            w = int(info.get("width") or 0)
            h = int(info.get("height") or 0)
            if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
                continue
            img_url = str(info.get("thumburl") or info.get("url") or "").strip()
            if not img_url:
                continue
            title = str(page.get("title") or "").removeprefix("File:").strip()
            out.append(
                {
                    "id": f"wiki:{page.get('pageid') or len(out)}",
                    "title": title[:80],
                    "url": img_url,
                    "thumb_url": img_url,
                    "width": w,
                    "height": h,
                    "source": "wikimedia",
                }
            )
            if len(out) >= lim:
                break
    except Exception:
        return []
    finally:
        if own_client:
            http.close()
    return out


def search_pixabay_images(
    query: str,
    *,
    api_key: str = "",
    workspace_dir: Path | None = None,
    limit: int = 6,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh minh họa / tư liệu từ Pixabay API (`image_type=illustration` fallback `all`)."""
    q = (query or "").strip()
    if not q:
        return []
    key = (api_key or "").strip() or resolve_online_api_key("PIXABAY_API_KEY", workspace_dir)
    if not key:
        return []
    lim = max(1, min(12, int(limit)))
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=6.0, follow_redirects=True)
    out: list[dict[str, Any]] = []
    try:
        hits: list[Any] = []
        for img_type in ("illustration", "all"):
            resp = http.get(
                PIXABAY_IMAGE_API,
                params={
                    "key": key,
                    "q": q,
                    "image_type": img_type,
                    "safesearch": "true",
                    "per_page": str(max(3, lim)),
                },
            )
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            hits = payload.get("hits") or []
            if hits:
                break
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            w = int(hit.get("imageWidth") or hit.get("webformatWidth") or 0)
            h = int(hit.get("imageHeight") or hit.get("webformatHeight") or 0)
            if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
                continue
            img_url = str(hit.get("webformatURL") or hit.get("largeImageURL") or "").strip()
            if not img_url:
                continue
            out.append(
                {
                    "id": f"pixabay:{hit.get('id') or len(out)}",
                    "title": str(hit.get("tags") or q)[:80],
                    "url": img_url,
                    "thumb_url": str(hit.get("previewURL") or img_url),
                    "width": w,
                    "height": h,
                    "source": "pixabay",
                }
            )
            if len(out) >= lim:
                break
    except Exception:
        return []
    finally:
        if own_client:
            http.close()
    return out


def search_reference_images(
    query: str,
    *,
    limit: int = 6,
    workspace_dir: Path | None = None,
    pixabay_key: str = "",
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh tư liệu ưu tiên Wikimedia Commons -> bổ sung Pixabay (cache 30 phút)."""
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(12, int(limit)))
    cache_key = (q.lower(), lim)
    now = time.monotonic()
    if client is None:
        cached = _SEARCH_CACHE.get(cache_key)
        if cached and (now - cached[0]) < _CACHE_TTL_S:
            return cached[1]

    items = search_wikimedia_images(q, limit=lim, client=client)
    if len(items) < lim:
        seen_urls = {it["url"] for it in items}
        extra = search_pixabay_images(
            q,
            api_key=pixabay_key,
            workspace_dir=workspace_dir,
            limit=lim - len(items),
            client=client,
        )
        for it in extra:
            if it["url"] not in seen_urls:
                items.append(it)
                seen_urls.add(it["url"])

    if client is None:
        _SEARCH_CACHE[cache_key] = (now, items)
    return items


def download_reference_image_url(
    url: str,
    dest_dir: Path,
    *,
    slug_hint: str = "ref",
    client: httpx.Client | None = None,
) -> Path:
    """Tải 1 ảnh tư liệu từ URL, kiểm tra hợp lệ bằng Pillow và lưu PNG vào `dest_dir`."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    dest = dest_dir / f"{_safe_slug(slug_hint)}_{digest}.png"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=8.0, follow_redirects=True)
    try:
        resp = http.get(url, headers={"User-Agent": WIKIMEDIA_USER_AGENT})
        resp.raise_for_status()
        with Image.open(BytesIO(resp.content)) as raw:
            if raw.width < 120 or raw.height < 120:
                raise ValueError("Ảnh quá nhỏ để ghim bảng")
            rgb = raw.convert("RGB")
            try:
                rgb.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
                rgb.save(dest, format="PNG")
            finally:
                rgb.close()
        return dest
    finally:
        if own_client:
            http.close()


def resolve_reference_image(
    query: str,
    library_dir: Path,
    *,
    workspace_dir: Path | None = None,
    pixabay_key: str = "",
    accent_color: tuple[int, int, int, int] = (217, 35, 46, 255),
    client: httpx.Client | None = None,
) -> tuple[Path, str]:
    """Tải & cache ảnh tư liệu về `library/reference_images/` (Wikimedia -> Pixabay -> Iconify)."""
    ref_dir = Path(library_dir) / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(query)
    cached = ref_dir / f"{slug}.png"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached, "cache"

    candidates = search_reference_images(
        query,
        limit=6,
        workspace_dir=workspace_dir,
        pixabay_key=pixabay_key,
        client=client,
    )
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=8.0, follow_redirects=True)
    try:
        for cand in candidates:
            try:
                resp = http.get(cand["url"], headers={"User-Agent": WIKIMEDIA_USER_AGENT})
                resp.raise_for_status()
                with Image.open(BytesIO(resp.content)) as raw:
                    if raw.width < 160 or raw.height < 160:
                        continue
                    rgb = raw.convert("RGB")
                    try:
                        rgb.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
                        rgb.save(cached, format="PNG")
                    finally:
                        rgb.close()
                return cached, str(cand.get("source") or "wikimedia")
            except Exception:
                continue
    finally:
        if own_client:
            http.close()

    fallback_path = resolve_prop_png(query, library_dir, accent_color=accent_color)
    return fallback_path, "iconify"
