"""Kho ảnh tư liệu StickV v2 (`v2_entity_strict`): Wikimedia -> Pixabay -> Cloudflare Flux 2D."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image

from hbt.app_settings import resolve_online_api_key
from hbt.shared.image_gen.cloudflare_flux import (
    CloudflareImageError,
    generate_illustration_image,
)
from hbt.shared.online_sources.iconify_props import resolve_prop_png

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
PIXABAY_IMAGE_API = "https://pixabay.com/api/"
WIKIMEDIA_USER_AGENT = "HBTStudio/1.0 (https://github.com/thong9843/hbt-studio; local desktop app)"

REF_CACHE_VERSION = "v2_entity_strict"
MIN_IMAGE_DIM = 300
MIN_LONG_EDGE = 480
MIN_ASPECT_RATIO = 0.55
MAX_ASPECT_RATIO = 2.4
MIN_RELEVANCE_SCORE = 0.45
DEFAULT_AI_IMAGE_BUDGET = 6

_ALLOWED_MIMES = {"image/jpeg", "image/jpg", "image/png"}
_CACHE_TTL_S = 30 * 60
_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}

WIKIMEDIA_JUNK_PATTERNS: tuple[str, ...] = (
    "coin",
    "numismat",
    "medal",
    "stamp",
    "postage",
    "ruler",
    "scale bar",
    "caliper",
    "shutter",
    "window shutter",
    "warehouse",
    "shed",
    "storage",
    "coat of arms",
    "seal of",
    "emblem",
    "logo",
    "flag of",
    "signature",
    "autograph",
    "grave",
    "tombstone",
    "plaque",
    "signpost",
    "diagram",
    "chart",
    "page ",
    "scan",
    "manuscript",
    "book cover",
    "screenshot",
    "icon",
    "button",
    "floorplan",
    "blueprint",
)

_JUNK_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(
        r"\bnumismat"
        if p == "numismat"
        else r"\bscan(?:ned|ning)?\b"
        if p == "scan"
        else r"\bpage\b"
        if p == "page "
        else rf"\b{re.escape(p.strip())}s?\b"
    )
    for p in WIKIMEDIA_JUNK_PATTERNS
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_QUERY_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "in", "on", "at", "for", "with", "and", "to", "by", "from"}
)


def _safe_slug(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (raw or "ref").strip().lower()).strip("-")
    return s[:48] or "ref"


def _normalize_match_text(text: str) -> str:
    stripped = _HTML_TAG_RE.sub(" ", text or "")
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def _core_tokens(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9]+", _normalize_match_text(text))
        if len(w) >= 2 and w not in _QUERY_STOPWORDS
    ]


def is_junk_reference_candidate(title: str, metadata_text: str = "") -> bool:
    """Chặn cứng ảnh rác Wikimedia/stock (đồng xu, thước đo, cửa chớp, nhà kho, scan tài liệu)."""
    norm = _normalize_match_text(f"{title} {metadata_text}")
    if not norm:
        return False
    return any(rx.search(norm) is not None for rx in _JUNK_REGEXES)


def _valid_image_geometry(width: int, height: int) -> bool:
    if width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
        return False
    if max(width, height) < MIN_LONG_EDGE:
        return False
    aspect = width / max(1.0, float(height))
    return MIN_ASPECT_RATIO <= aspect <= MAX_ASPECT_RATIO


def _is_dense_bw_text_scan(img: Image.Image) -> bool:
    """Phát hiện trang scan tài liệu trắng đen chữ dày đặc (nền giấy trắng > 60%, độ bão hòa ~0)."""
    small = img.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR)
    try:
        arr = np.asarray(small, dtype=np.float32)
    finally:
        small.close()
    chroma = float(np.mean(np.max(arr, axis=2) - np.min(arr, axis=2)))
    if chroma >= 8.0:
        return False
    luma = np.mean(arr, axis=2)
    bright_ratio = float(np.mean(luma > 210.0))
    dark_ratio = float(np.mean(luma < 80.0))
    return bright_ratio > 0.60 and dark_ratio > 0.03


def score_candidate_relevance(
    cand: dict[str, Any],
    query: str,
    primary_entity_en: str = "",
) -> float:
    """Chấm điểm độ khớp [0.0..1.0] dựa trên tỷ lệ khớp thực thể chính & token truy vấn."""
    title_norm = _normalize_match_text(str(cand.get("title") or ""))
    meta_norm = _normalize_match_text(str(cand.get("metadata_text") or ""))
    title_toks = set(_core_tokens(title_norm))
    meta_toks = set(_core_tokens(meta_norm))

    def _token_hit_ratio(tokens: list[str]) -> float:
        if not tokens:
            return 0.0
        uniq = list(dict.fromkeys(tokens))
        pts = 0.0
        for tok in uniq:
            if tok in title_toks:
                pts += 1.0
            elif tok in meta_toks:
                pts += 0.75
        return pts / len(uniq)

    q_toks = _core_tokens(query)
    q_ratio = _token_hit_ratio(q_toks)
    ent_norm = _normalize_match_text(primary_entity_en)
    e_toks = _core_tokens(ent_norm)

    if e_toks:
        e_ratio = _token_hit_ratio(e_toks)
        if e_ratio < 0.5:
            return round(min(0.2, e_ratio * 0.4), 3)
        e_set = set(e_toks)
        ctx_toks = [t for t in q_toks if t not in e_set]
        if ctx_toks:
            ctx_ratio = _token_hit_ratio(ctx_toks)
            if ctx_ratio <= 0.0:
                # Khớp tên thực thể nhưng 0% khớp bối cảnh cụ thể của beat -> để Flux 2D vẽ sát ý
                return round(min(0.35, 0.35 * e_ratio), 3)
            score = 0.55 * e_ratio + 0.45 * ctx_ratio
        else:
            score = e_ratio
        if len(e_toks) >= 2 and ent_norm in title_norm:
            score = min(1.0, score + 0.12)
        return round(min(1.0, score), 3)

    score = q_ratio
    q_norm = _normalize_match_text(query)
    if len(q_toks) >= 2 and q_norm in title_norm:
        score = min(1.0, score + 0.10)
    return round(min(1.0, score), 3)


def clear_reference_image_cache() -> None:
    _SEARCH_CACHE.clear()


def _extract_wikimedia_extmetadata(info: dict[str, Any]) -> str:
    ext = info.get("extmetadata")
    if not isinstance(ext, dict):
        return ""
    parts: list[str] = []
    for key in ("ObjectName", "ImageDescription", "Categories"):
        node = ext.get(key)
        if isinstance(node, dict):
            val = str(node.get("value") or "").strip()
            if val:
                parts.append(_HTML_TAG_RE.sub(" ", val)[:240])
    return " ".join(parts)


def search_wikimedia_images(
    query: str,
    *,
    limit: int = 10,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh tư liệu JPEG/PNG sạch (>= 480px cạnh dài, lọc rác & tỷ lệ cực đoan) từ Wikimedia."""
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(12, int(limit)))
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{q} filetype:bitmap",
        "gsrnamespace": "6",
        "gsrlimit": str(max(lim * 2, 16)),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1024",
        "format": "json",
    }
    headers = {"User-Agent": WIKIMEDIA_USER_AGENT}
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=8.0, follow_redirects=True)
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
            if not _valid_image_geometry(w, h):
                continue
            img_url = str(info.get("thumburl") or info.get("url") or "").strip()
            if not img_url:
                continue
            title = str(page.get("title") or "").removeprefix("File:").strip()
            meta_text = _extract_wikimedia_extmetadata(info)
            if is_junk_reference_candidate(title, meta_text):
                continue
            out.append(
                {
                    "id": f"wiki:{page.get('pageid') or len(out)}",
                    "title": title[:100],
                    "metadata_text": meta_text[:300],
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
    limit: int = 8,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Tìm ảnh minh họa / tư liệu sạch từ Pixabay API (`image_type=illustration` fallback `all`)."""
    q = (query or "").strip()
    if not q:
        return []
    key = (api_key or "").strip() or resolve_online_api_key("PIXABAY_API_KEY", workspace_dir)
    if not key:
        return []
    lim = max(1, min(12, int(limit)))
    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=8.0, follow_redirects=True)
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
                    "per_page": str(max(6, lim * 2)),
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
            if not _valid_image_geometry(w, h):
                continue
            img_url = str(hit.get("webformatURL") or hit.get("largeImageURL") or "").strip()
            if not img_url:
                continue
            tags = str(hit.get("tags") or q).strip()
            if is_junk_reference_candidate(tags):
                continue
            out.append(
                {
                    "id": f"pixabay:{hit.get('id') or len(out)}",
                    "title": tags[:100],
                    "metadata_text": tags[:200],
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
    limit: int = 8,
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


def resolve_reference_image_detailed(
    query: str,
    library_dir: Path,
    *,
    workspace_dir: Path | None = None,
    pixabay_key: str = "",
    accent_color: tuple[int, int, int, int] = (217, 35, 46, 255),
    client: httpx.Client | None = None,
    illustration_prompt: str = "",
    primary_entity_en: str = "",
    allow_ai_fallback: bool = True,
    cf_account_id: str = "",
    cf_api_token: str = "",
    ai_budget: list[int] | None = None,
) -> dict[str, Any]:
    """Tải & cache ảnh 3 tầng (`v2_entity_strict`) kèm điểm độ khớp & tên nguồn."""
    ref_dir = Path(library_dir) / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)
    clean_q = (query or "").strip()
    clean_prompt = (illustration_prompt or "").strip()
    clean_entity = (primary_entity_en or "").strip()

    digest = hashlib.sha1(
        f"{REF_CACHE_VERSION}|{clean_q.lower()}|{clean_prompt.lower()}|{clean_entity.lower()}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]
    cached_jpg = ref_dir / f"{REF_CACHE_VERSION}_{digest}.jpg"
    if cached_jpg.is_file() and cached_jpg.stat().st_size > 0:
        return {
            "path": cached_jpg,
            "source": "cache",
            "score": 1.0,
            "title": cached_jpg.name,
            "query": clean_q,
        }

    # Chỉ tìm bằng truy vấn đầy đủ (không rút gọn 2 từ chung chung hay xóa bối cảnh beat)
    query_variants: list[str] = [clean_q] if clean_q else ([clean_entity] if clean_entity else [])

    scored_candidates: list[tuple[float, int, dict[str, Any]]] = []
    seen_urls: set[str] = set()

    # Tầng 1: Wikimedia Commons (tối đa 10 ứng viên sạch, chấm điểm độ khớp thực thể)
    for qv in query_variants:
        hits = search_wikimedia_images(qv, limit=10, client=client)
        for it in hits:
            if it["url"] in seen_urls:
                continue
            seen_urls.add(it["url"])
            sc = score_candidate_relevance(it, clean_q or qv, primary_entity_en=clean_entity)
            if sc >= MIN_RELEVANCE_SCORE:
                scored_candidates.append((sc, 1, it))
        if scored_candidates:
            break

    # Tầng 2: Pixabay (tối đa 8 ứng viên sạch nếu Wikimedia chưa có ứng viên đạt ngưỡng)
    if not scored_candidates:
        for qv in query_variants:
            hits = search_pixabay_images(
                qv,
                api_key=pixabay_key,
                workspace_dir=workspace_dir,
                limit=8,
                client=client,
            )
            for it in hits:
                if it["url"] in seen_urls:
                    continue
                seen_urls.add(it["url"])
                sc = score_candidate_relevance(it, clean_q or qv, primary_entity_en=clean_entity)
                if sc >= MIN_RELEVANCE_SCORE:
                    scored_candidates.append((sc, 0, it))
            if scored_candidates:
                break

    scored_candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)

    own_client = client is None
    http = client if client is not None else httpx.Client(timeout=8.0, follow_redirects=True)
    try:
        for sc, _prio, cand in scored_candidates:
            try:
                resp = http.get(cand["url"], headers={"User-Agent": WIKIMEDIA_USER_AGENT})
                resp.raise_for_status()
                with Image.open(BytesIO(resp.content)) as raw:
                    if not _valid_image_geometry(raw.width, raw.height):
                        continue
                    if _is_dense_bw_text_scan(raw):
                        continue
                    rgb = raw.convert("RGB")
                    try:
                        rgb.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
                        rgb.save(cached_jpg, format="JPEG", quality=90)
                    finally:
                        rgb.close()
                return {
                    "path": cached_jpg,
                    "source": str(cand.get("source") or "wikimedia"),
                    "score": sc,
                    "title": str(cand.get("title") or ""),
                    "query": clean_q,
                }
            except Exception:
                continue
    finally:
        if own_client:
            http.close()

    # Tầng 3: Cloudflare Workers AI 2D (flux-1-schnell, 768x512, ưu tiên khi Stock không khớp sát)
    budget_ok = ai_budget is None or (len(ai_budget) > 0 and ai_budget[0] > 0)
    if allow_ai_fallback and budget_ok:
        acc_id = (cf_account_id or "").strip() or resolve_online_api_key(
            "CLOUDFLARE_ACCOUNT_ID", workspace_dir
        )
        token = (cf_api_token or "").strip() or resolve_online_api_key(
            "CLOUDFLARE_API_TOKEN", workspace_dir
        )
        if acc_id and token:
            flux_prompt = clean_prompt or clean_q
            if clean_entity and clean_entity.lower() not in flux_prompt.lower():
                flux_prompt = f"{clean_entity} — {flux_prompt}" if flux_prompt else clean_entity
            try:
                generate_illustration_image(
                    flux_prompt,
                    cached_jpg,
                    account_id=acc_id,
                    api_token=token,
                    width=768,
                    height=512,
                    client=client,
                )
                if ai_budget is not None and len(ai_budget) > 0:
                    ai_budget[0] = max(0, ai_budget[0] - 1)
                return {
                    "path": cached_jpg,
                    "source": "cloudflare_flux",
                    "score": 1.0,
                    "title": flux_prompt[:80],
                    "query": clean_q,
                }
            except CloudflareImageError as exc:
                logging.getLogger(__name__).warning("Cloudflare Flux 2D fallback thất bại: %s", exc)

    fallback_path = resolve_prop_png(clean_q, library_dir, accent_color=accent_color)
    return {
        "path": fallback_path,
        "source": "iconify",
        "score": 0.0,
        "title": fallback_path.name,
        "query": clean_q,
    }


def resolve_reference_image(
    query: str,
    library_dir: Path,
    *,
    workspace_dir: Path | None = None,
    pixabay_key: str = "",
    accent_color: tuple[int, int, int, int] = (217, 35, 46, 255),
    client: httpx.Client | None = None,
    illustration_prompt: str = "",
    primary_entity_en: str = "",
    allow_ai_fallback: bool = True,
    cf_account_id: str = "",
    cf_api_token: str = "",
    ai_budget: list[int] | None = None,
) -> tuple[Path, str]:
    """Tải & cache ảnh 3 tầng về `library/reference_images/v2_entity_strict_<sha1>.jpg`."""
    res = resolve_reference_image_detailed(
        query,
        library_dir,
        workspace_dir=workspace_dir,
        pixabay_key=pixabay_key,
        accent_color=accent_color,
        client=client,
        illustration_prompt=illustration_prompt,
        primary_entity_en=primary_entity_en,
        allow_ai_fallback=allow_ai_fallback,
        cf_account_id=cf_account_id,
        cf_api_token=cf_api_token,
        ai_budget=ai_budget,
    )
    return res["path"], str(res["source"])
