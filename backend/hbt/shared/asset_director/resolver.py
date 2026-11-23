"""Lớp 3B — AssetResolver: Local-First -> Smart Auto-Fetch Online -> Lưu vĩnh viễn vào library/."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from hbt.app_settings import resolve_online_api_key
from hbt.shared.asset_director.freshness import FreshnessMemory
from hbt.shared.asset_director.models import (
    AssetCandidate,
    AssetCategory,
    DirectorConfig,
    ResolvedAsset,
)
from hbt.shared.online_sources.freesound_audio import (
    import_freesound_audio,
    search_freesound_audio,
)
from hbt.shared.online_sources.greenmeme import import_greenmeme, search_greenmeme
from hbt.shared.online_sources.meme_tagging import _fold_text, auto_tag_meme
from hbt.shared.online_sources.pixabay_audio import import_pixabay_audio, search_pixabay_audio
from hbt.shared.online_sources.stickers_online import import_giphy_sticker, search_giphy_stickers
from hbt.shared.online_sources.tuna_sfx import import_tuna_sfx, search_tuna_sfx

logger = logging.getLogger(__name__)

# Ánh xạ đồng nghĩa Việt-Anh cơ bản cho khâu khớp từ khóa local
VI_EN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "soc": ("shock", "shocked", "surprised", "omg", "bat_ngo", "wtf", "mind blown"),
    "bat ngo": ("shock", "shocked", "surprised", "omg", "bat_ngo"),
    "ca khia": ("side eye", "smirk", "smug", "troll", "sassy", "ca_khia"),
    "khinh": ("side eye", "smug", "disgust", "ca_khia"),
    "bo tay": ("facepalm", "bruh", "disappointed", "bat_luc", "fail"),
    "bat luc": ("facepalm", "bruh", "skull", "dead", "bat_luc", "that_vong"),
    "cuoi": ("laugh", "funny", "haha", "lol", "hai_huoc", "giggle"),
    "gian": ("angry", "mad", "rage", "furious", "tuc_gian"),
    "tuc": ("angry", "mad", "rage", "tuc_gian"),
    "khoc": ("cry", "sad", "tears", "that_vong"),
    "ngai": ("awkward", "shy", "embarrassed", "ngai_ngung"),
    "meo": ("cat", "kitty", "meow", "meo"),
    "tien": ("money", "cash", "rich", "broke", "tien_bac"),
    "ok": ("ok", "thumbs", "clap", "nice", "vo_tay"),
}

_VISUAL_EXTS = {".mp4", ".mov", ".webm", ".gif", ".webp", ".png", ".jpg", ".jpeg"}
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}

# Cache tìm kiếm online trong bộ nhớ (TTL 10 phút mặc định)
_SEARCH_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


def clear_search_cache() -> None:
    """Xóa cache tìm kiếm trong bộ nhớ (hữu ích cho test)."""
    _SEARCH_CACHE.clear()


@dataclass
class FetchBudget:
    """Trần tải online cho 1 phiên sinh kịch bản (3 visual, 3 SFX, 1 BGM)."""

    visual: int = 0
    sfx: int = 0
    bgm: int = 0


def _run_coro(coro: Any) -> Any:
    """Chạy coroutine an toàn dù đang ở sync thread hay trong event loop đang chạy."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _expand_query_tokens(query: str) -> set[str]:
    folded = _fold_text(query)
    tokens = {w for w in folded.split() if len(w) >= 2}
    extras: set[str] = set()
    for vi_key, en_vals in VI_EN_SYNONYMS.items():
        if vi_key in folded or any(ev in folded for ev in en_vals):
            extras.add(vi_key.replace(" ", "_"))
            for ev in en_vals:
                extras.update(w for w in _fold_text(ev).split() if len(w) >= 2)
    return tokens | extras


def _keyword_match_score(query_tokens: set[str], candidate: AssetCandidate) -> float:
    if not query_tokens:
        return 0.35
    haystack_text = " ".join([candidate.asset_id, candidate.title, candidate.file, *candidate.tags])
    cand_tokens = {w for w in _fold_text(haystack_text).split() if len(w) >= 2}
    if not cand_tokens:
        return 0.0
    overlap = len(query_tokens & cand_tokens)
    if overlap == 0:
        # Khớp chuỗi con cho từ khóa ngắn (vd: "shock" trong "shocked")
        partial = sum(1 for qt in query_tokens if any(qt in ct or ct in qt for ct in cand_tokens))
        return min(0.75, partial / max(1, len(query_tokens)) * 0.7)
    ratio = overlap / max(1, min(len(query_tokens), 4))
    return min(1.0, round(0.45 + ratio * 0.55, 4))


def _load_json_list(idx_path: Path) -> list[dict[str, Any]]:
    if not idx_path.is_file():
        return []
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict)]
        if isinstance(data, dict) and isinstance(data.get("memes"), list):
            return [e for e in data["memes"] if isinstance(e, dict)]
    except Exception:
        pass
    return []


def _upsert_index_metadata(
    target_dir: Path,
    *,
    file_name: str,
    source: str,
    source_id: str,
    extra_tags: list[str] | None = None,
) -> None:
    """Đảm bảo `source`, `source_id` và `tags` luôn được lưu chuẩn vào `index.json`."""
    idx_path = target_dir / "index.json"
    entries = _load_json_list(idx_path)
    changed = False
    for entry in entries:
        if str(entry.get("file") or "") == file_name:
            if source and not entry.get("source"):
                entry["source"] = source
                changed = True
            if source_id and entry.get("source_id") != source_id:
                entry["source_id"] = source_id
                changed = True
            if extra_tags:
                cur_tags = list(entry.get("tags") or [])
                if entry.get("tag") and entry["tag"] not in cur_tags:
                    cur_tags.append(str(entry["tag"]))
                for t in extra_tags:
                    if t and t not in cur_tags:
                        cur_tags.append(t)
                        changed = True
                entry["tags"] = cur_tags[:10]
            break
    if changed:
        tmp = idx_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, idx_path)


def _existing_source_ids(target_dir: Path) -> set[str]:
    ids: set[str] = set()
    for entry in _load_json_list(target_dir / "index.json"):
        sid = str(entry.get("source_id") or "").strip()
        if sid:
            ids.add(sid)
        eid = str(entry.get("id") or "").strip()
        if eid:
            ids.add(eid)
    return ids


class AssetResolver:
    """Tìm tài nguyên local trước; tự tải online nếu thiếu/cooldown; luôn fail-safe về local."""

    def __init__(
        self,
        library_dir: Path,
        workspace_dir: Path,
        memory: FreshnessMemory,
        *,
        config: DirectorConfig | None = None,
    ) -> None:
        self.library_dir = Path(library_dir)
        self.workspace_dir = Path(workspace_dir)
        self.memory = memory
        self.config = config or DirectorConfig()

    def _scan_category(self, category: AssetCategory) -> list[AssetCandidate]:
        sub_dir = self.library_dir / category
        if not sub_dir.is_dir():
            return []
        allowed_exts = _VISUAL_EXTS if category in ("memes", "stickers") else _AUDIO_EXTS
        candidates: list[AssetCandidate] = []
        seen_files: set[str] = set()

        for entry in _load_json_list(sub_dir / "index.json"):
            fname = str(entry.get("file") or "").strip()
            if not fname:
                continue
            fpath = sub_dir / fname
            if not fpath.is_file() or fpath.suffix.lower() not in allowed_exts:
                continue
            seen_files.add(fname)
            tags = [str(t) for t in (entry.get("tags") or []) if str(t).strip()]
            if entry.get("tag") and str(entry["tag"]) not in tags:
                tags.append(str(entry["tag"]))
            if entry.get("moods"):
                for m in entry["moods"]:
                    if str(m).strip() and str(m) not in tags:
                        tags.append(str(m))
            if entry.get("topic"):
                tags.append(str(entry["topic"]))
            aid = str(entry.get("id") or fpath.stem)
            candidates.append(
                AssetCandidate(
                    asset_id=aid,
                    category=category,
                    file=fname,
                    path=str(fpath),
                    title=str(entry.get("title") or fpath.stem),
                    tags=tags,
                    source=str(entry.get("source") or "local"),
                    source_id=str(entry.get("source_id") or ""),
                    duration_sec=float(entry.get("duration_sec") or entry.get("duration") or 0.0),
                )
            )

        # Quét thêm các file có sẵn trên đĩa nhưng chưa vào index.json
        for fpath in sorted(sub_dir.iterdir(), key=lambda p: p.name.lower()):
            if (
                not fpath.is_file()
                or fpath.name in seen_files
                or fpath.name.endswith("_thumb.jpg")
                or fpath.suffix.lower() not in allowed_exts
            ):
                continue
            inferred_tags, _ = auto_tag_meme(fpath.stem)
            candidates.append(
                AssetCandidate(
                    asset_id=fpath.stem,
                    category=category,
                    file=fpath.name,
                    path=str(fpath),
                    title=fpath.stem.replace("-", " ").replace("_", " ").strip(),
                    tags=inferred_tags,
                    source="local",
                    duration_sec=0.0,
                )
            )
        return candidates

    def _score_local(
        self,
        candidates: list[AssetCandidate],
        query: str,
        *,
        exclude_ids: set[str],
        video_seq: int | None,
        min_duration_s: float = 0.0,
    ) -> list[tuple[float, bool, AssetCandidate]]:
        q_tokens = _expand_query_tokens(query)
        scored: list[tuple[float, bool, AssetCandidate]] = []
        for cand in candidates:
            if cand.asset_id in exclude_ids or cand.file in exclude_ids:
                continue
            if min_duration_s > 0 and cand.duration_sec > 0 and cand.duration_sec < min_duration_s:
                continue
            kw_score = _keyword_match_score(q_tokens, cand)
            in_cd = self.memory.is_in_cooldown(cand.category, cand.asset_id, video_seq=video_seq)
            penalty = self.memory.total_penalty(cand.category, cand.asset_id, video_seq=video_seq)
            final_score = round(kw_score - penalty, 4)
            cand.score = final_score
            scored.append((final_score, in_cd, cand))
        scored.sort(key=lambda x: (not x[1], x[0]), reverse=True)
        return scored

    def _cached_search(
        self,
        provider: str,
        query: str,
        coro_factory: Any,
    ) -> list[dict[str, Any]]:
        key = (provider, _fold_text(query).strip())
        now = time.monotonic()
        hit = _SEARCH_CACHE.get(key)
        if hit is not None and (now - hit[0]) < self.config.cache_ttl_s:
            return hit[1]
        rows = _run_coro(coro_factory())
        if isinstance(rows, list):
            _SEARCH_CACHE[key] = (now, rows)
            return rows
        return []

    def _fetch_visual_online(
        self,
        query: str,
        *,
        prefer_greenmeme: bool,
        exclude_ids: set[str],
    ) -> ResolvedAsset | None:
        q = (query or "").strip() or "reaction"
        order = ("greenmeme", "giphy") if prefer_greenmeme else ("giphy", "greenmeme")
        query_tags = [w for w in _fold_text(q).split() if len(w) >= 2][:4]

        for provider in order:
            try:
                if provider == "giphy":
                    api_key = resolve_online_api_key("GIPHY_API_KEY", self.workspace_dir)
                    if not api_key:
                        continue

                    async def _search_g(key: str = api_key) -> list[dict[str, Any]]:
                        async with httpx.AsyncClient(
                            timeout=self.config.search_timeout_s, follow_redirects=True
                        ) as c:
                            return await search_giphy_stickers(q, api_key=key, limit=6, client=c)

                    hits = self._cached_search("giphy", q, _search_g)
                    existing = _existing_source_ids(self.library_dir / "stickers")
                    for hit in hits[:6]:
                        sid = str(hit.get("id") or "").strip()
                        dl_url = str(hit.get("download_url") or "").strip()
                        if not sid or not dl_url:
                            continue
                        cand_id = f"giphy-{sid.lower()}"
                        if sid in existing or cand_id in existing or cand_id in exclude_ids:
                            continue

                        async def _imp_g(h: dict[str, Any] = hit) -> dict[str, Any]:
                            async with httpx.AsyncClient(
                                timeout=self.config.download_timeout_s, follow_redirects=True
                            ) as c:
                                return await import_giphy_sticker(
                                    sticker_id=str(h.get("id") or ""),
                                    title=str(h.get("title") or q),
                                    download_url=str(h.get("download_url") or ""),
                                    library_dir=self.library_dir,
                                    client=c,
                                )

                        res = _run_coro(_imp_g())
                        item = res.get("item") or {}
                        fname = str(item.get("file") or "")
                        _upsert_index_metadata(
                            self.library_dir / "stickers",
                            file_name=fname,
                            source="giphy",
                            source_id=sid,
                            extra_tags=query_tags,
                        )
                        return ResolvedAsset(
                            asset_id=str(item.get("id") or cand_id),
                            category="stickers",
                            file=fname,
                            path=str(res.get("path") or (self.library_dir / "stickers" / fname)),
                            origin="online_fetched",
                            source="giphy",
                            source_id=sid,
                            title=str(item.get("title") or q),
                            score=0.9,
                        )

                elif provider == "greenmeme":

                    async def _search_gm() -> list[dict[str, Any]]:
                        async with httpx.AsyncClient(
                            timeout=self.config.search_timeout_s, follow_redirects=True
                        ) as c:
                            return await search_greenmeme(q, per_page=6, client=c)

                    hits = self._cached_search("greenmeme", q, _search_gm)
                    existing = _existing_source_ids(self.library_dir / "memes")
                    for hit in hits[:6]:
                        sid = str(hit.get("id") or "").strip()
                        v_url = str(hit.get("video_url") or "").strip()
                        if not sid or not v_url:
                            continue
                        if sid in existing or sid in exclude_ids:
                            continue

                        async def _imp_gm(h: dict[str, Any] = hit) -> dict[str, Any]:
                            async with httpx.AsyncClient(
                                timeout=self.config.download_timeout_s, follow_redirects=True
                            ) as c:
                                return await import_greenmeme(
                                    meme_id=str(h.get("id") or ""),
                                    title=str(h.get("title") or q),
                                    video_url=str(h.get("video_url") or ""),
                                    poster_url=str(h.get("poster_url") or ""),
                                    library_dir=self.library_dir,
                                    client=c,
                                )

                        res = _run_coro(_imp_gm())
                        item = res.get("item") or {}
                        fname = str(item.get("file") or "")
                        _upsert_index_metadata(
                            self.library_dir / "memes",
                            file_name=fname,
                            source="greenscreenmemes.com",
                            source_id=sid,
                            extra_tags=query_tags,
                        )
                        return ResolvedAsset(
                            asset_id=str(item.get("id") or sid),
                            category="memes",
                            file=fname,
                            path=str(res.get("path") or (self.library_dir / "memes" / fname)),
                            origin="online_fetched",
                            source="greenscreenmemes.com",
                            source_id=sid,
                            title=str(item.get("title") or q),
                            duration_sec=float(item.get("duration_sec") or 0.0),
                            score=0.92,
                        )
            except Exception as exc:
                logger.warning(
                    "Auto-fetch visual (%s, q=%r) thất bại, rơi về nguồn khác: %s", provider, q, exc
                )
        return None

    def _fetch_sfx_online(self, query: str, *, exclude_ids: set[str]) -> ResolvedAsset | None:
        q = (query or "").strip() or "meme"
        query_tags = [w for w in _fold_text(q).split() if len(w) >= 2][:4]
        existing = _existing_source_ids(self.library_dir / "sfx")

        # 1. Voicemod Tuna (ưu tiên #1)
        try:
            tuna_key = resolve_online_api_key("VOICEMOD_TUNA_API_KEY", self.workspace_dir)

            async def _search_t() -> list[dict[str, Any]]:
                async with httpx.AsyncClient(
                    timeout=self.config.search_timeout_s, follow_redirects=True
                ) as c:
                    return await search_tuna_sfx(q, per_page=6, api_key=tuna_key, client=c)

            hits = self._cached_search("tuna", q, _search_t)
            for hit in hits[:6]:
                sid = str(hit.get("id") or "").strip()
                p_url = str(hit.get("preview_url") or "").strip()
                if not sid or not p_url or sid in existing or f"tuna-{sid[:10]}" in exclude_ids:
                    continue

                async def _imp_t(h: dict[str, Any] = hit) -> dict[str, Any]:
                    async with httpx.AsyncClient(
                        timeout=self.config.download_timeout_s, follow_redirects=True
                    ) as c:
                        return await import_tuna_sfx(
                            item_id=str(h.get("id") or ""),
                            title=str(h.get("title") or q),
                            preview_url=str(h.get("preview_url") or ""),
                            tags=list(h.get("tags") or query_tags),
                            library_dir=self.library_dir,
                            client=c,
                        )

                res = _run_coro(_imp_t())
                item = res.get("item") or {}
                fname = str(item.get("file") or "")
                _upsert_index_metadata(
                    self.library_dir / "sfx",
                    file_name=fname,
                    source="tuna",
                    source_id=sid,
                    extra_tags=query_tags,
                )
                return ResolvedAsset(
                    asset_id=str(item.get("id") or fname),
                    category="sfx",
                    file=fname,
                    path=str(res.get("file_path") or (self.library_dir / "sfx" / fname)),
                    origin="online_fetched",
                    source="tuna",
                    source_id=sid,
                    title=str(item.get("title") or q),
                    duration_sec=float(item.get("duration_sec") or 0.0),
                    score=0.9,
                )
        except Exception as exc:
            logger.warning("Auto-fetch SFX Tuna (q=%r) thất bại: %s", q, exc)

        # 2. Freesound fallback
        try:
            fkey = resolve_online_api_key("FREESOUND_API_KEY", self.workspace_dir)
            if fkey:

                async def _search_fs() -> list[dict[str, Any]]:
                    async with httpx.AsyncClient(
                        timeout=self.config.search_timeout_s, follow_redirects=True
                    ) as c:
                        return await search_freesound_audio(
                            q, kind="sfx", api_key=fkey, page_size=6, client=c
                        )

                hits = self._cached_search("freesound_sfx", q, _search_fs)
                for hit in hits[:6]:
                    sid = str(hit.get("id") or "").strip()
                    dl_url = str(hit.get("download_url") or "").strip()
                    cand_id = f"freesound-{sid}"
                    if not sid or not dl_url or sid in existing or cand_id in exclude_ids:
                        continue

                    async def _imp_fs(h: dict[str, Any] = hit) -> dict[str, Any]:
                        async with httpx.AsyncClient(
                            timeout=self.config.download_timeout_s, follow_redirects=True
                        ) as c:
                            return await import_freesound_audio(
                                item_id=str(h.get("id") or ""),
                                title=str(h.get("title") or q),
                                artist=str(h.get("artist") or "Freesound"),
                                download_url=str(h.get("download_url") or ""),
                                kind="sfx",
                                tags=list(h.get("tags") or query_tags),
                                license_url=str(h.get("license") or ""),
                                library_dir=self.library_dir,
                                client=c,
                            )

                    res = _run_coro(_imp_fs())
                    item = res.get("item") or {}
                    fname = str(item.get("file") or "")
                    _upsert_index_metadata(
                        self.library_dir / "sfx",
                        file_name=fname,
                        source="freesound",
                        source_id=sid,
                        extra_tags=query_tags,
                    )
                    return ResolvedAsset(
                        asset_id=str(item.get("id") or cand_id),
                        category="sfx",
                        file=fname,
                        path=str(res.get("path") or (self.library_dir / "sfx" / fname)),
                        origin="online_fetched",
                        source="freesound",
                        source_id=sid,
                        title=str(item.get("title") or q),
                        duration_sec=float(item.get("duration") or 0.0),
                        score=0.85,
                    )
        except Exception as exc:
            logger.warning("Auto-fetch SFX Freesound (q=%r) thất bại: %s", q, exc)

        # 3. Pixabay fallback
        try:
            pkey = resolve_online_api_key("PIXABAY_API_KEY", self.workspace_dir)
            if pkey:

                async def _search_px() -> list[dict[str, Any]]:
                    async with httpx.AsyncClient(
                        timeout=self.config.search_timeout_s, follow_redirects=True
                    ) as c:
                        return await search_pixabay_audio(
                            q, kind="sfx", api_key=pkey, per_page=6, client=c
                        )

                hits = self._cached_search("pixabay_sfx", q, _search_px)
                for hit in hits[:6]:
                    sid = str(hit.get("id") or "").strip()
                    dl_url = str(hit.get("download_url") or "").strip()
                    cand_id = f"pixabay-{sid}"
                    if not sid or not dl_url or sid in existing or cand_id in exclude_ids:
                        continue

                    async def _imp_px(h: dict[str, Any] = hit) -> dict[str, Any]:
                        async with httpx.AsyncClient(
                            timeout=self.config.download_timeout_s, follow_redirects=True
                        ) as c:
                            return await import_pixabay_audio(
                                item_id=str(h.get("id") or ""),
                                title=str(h.get("title") or q),
                                artist=str(h.get("artist") or "Pixabay"),
                                download_url=str(h.get("download_url") or ""),
                                kind="sfx",
                                tags=list(h.get("tags") or query_tags),
                                library_dir=self.library_dir,
                                client=c,
                            )

                    res = _run_coro(_imp_px())
                    item = res.get("item") or {}
                    fname = str(item.get("file") or "")
                    _upsert_index_metadata(
                        self.library_dir / "sfx",
                        file_name=fname,
                        source="pixabay",
                        source_id=sid,
                        extra_tags=query_tags,
                    )
                    return ResolvedAsset(
                        asset_id=str(item.get("id") or cand_id),
                        category="sfx",
                        file=fname,
                        path=str(res.get("path") or (self.library_dir / "sfx" / fname)),
                        origin="online_fetched",
                        source="pixabay",
                        source_id=sid,
                        title=str(item.get("title") or q),
                        duration_sec=float(item.get("duration") or 0.0),
                        score=0.82,
                    )
        except Exception as exc:
            logger.warning("Auto-fetch SFX Pixabay (q=%r) thất bại: %s", q, exc)

        return None

    def _fetch_bgm_online(
        self, mood_or_query: str, *, exclude_ids: set[str]
    ) -> ResolvedAsset | None:
        q = (mood_or_query or "").strip() or "lofi chill"
        existing = _existing_source_ids(self.library_dir / "music")

        # 1. Freesound (>= 50s)
        try:
            fkey = resolve_online_api_key("FREESOUND_API_KEY", self.workspace_dir)
            if fkey:

                async def _search_fs() -> list[dict[str, Any]]:
                    async with httpx.AsyncClient(
                        timeout=self.config.search_timeout_s, follow_redirects=True
                    ) as c:
                        return await search_freesound_audio(
                            q, kind="music", api_key=fkey, page_size=8, client=c
                        )

                hits = self._cached_search("freesound_bgm", q, _search_fs)
                for hit in hits[:6]:
                    sid = str(hit.get("id") or "").strip()
                    dl_url = str(hit.get("download_url") or "").strip()
                    dur = float(hit.get("duration") or 0.0)
                    cand_id = f"freesound-{sid}"
                    if not sid or not dl_url or (dur > 0 and dur < 50.0):
                        continue
                    if sid in existing or cand_id in exclude_ids:
                        continue

                    async def _imp_fs(h: dict[str, Any] = hit) -> dict[str, Any]:
                        async with httpx.AsyncClient(
                            timeout=self.config.download_timeout_s, follow_redirects=True
                        ) as c:
                            return await import_freesound_audio(
                                item_id=str(h.get("id") or ""),
                                title=str(h.get("title") or q),
                                artist=str(h.get("artist") or "Freesound"),
                                download_url=str(h.get("download_url") or ""),
                                kind="music",
                                tags=list(h.get("tags") or [q]),
                                license_url=str(h.get("license") or ""),
                                library_dir=self.library_dir,
                                client=c,
                            )

                    res = _run_coro(_imp_fs())
                    item = res.get("item") or {}
                    fname = str(item.get("file") or "")
                    _upsert_index_metadata(
                        self.library_dir / "music",
                        file_name=fname,
                        source="freesound",
                        source_id=sid,
                        extra_tags=[q],
                    )
                    return ResolvedAsset(
                        asset_id=str(item.get("id") or cand_id),
                        category="music",
                        file=fname,
                        path=str(res.get("path") or (self.library_dir / "music" / fname)),
                        origin="online_fetched",
                        source="freesound",
                        source_id=sid,
                        title=str(item.get("title") or q),
                        duration_sec=float(item.get("duration") or dur),
                        score=0.9,
                    )
        except Exception as exc:
            logger.warning("Auto-fetch BGM Freesound (q=%r) thất bại: %s", q, exc)

        # 2. Pixabay fallback
        try:
            pkey = resolve_online_api_key("PIXABAY_API_KEY", self.workspace_dir)
            if pkey:

                async def _search_px() -> list[dict[str, Any]]:
                    async with httpx.AsyncClient(
                        timeout=self.config.search_timeout_s, follow_redirects=True
                    ) as c:
                        return await search_pixabay_audio(
                            q, kind="music", api_key=pkey, per_page=8, client=c
                        )

                hits = self._cached_search("pixabay_bgm", q, _search_px)
                for hit in hits[:6]:
                    sid = str(hit.get("id") or "").strip()
                    dl_url = str(hit.get("download_url") or "").strip()
                    dur = float(hit.get("duration") or 0.0)
                    cand_id = f"pixabay-{sid}"
                    if not sid or not dl_url or (dur > 0 and dur < 50.0):
                        continue
                    if sid in existing or cand_id in exclude_ids:
                        continue

                    async def _imp_px(h: dict[str, Any] = hit) -> dict[str, Any]:
                        async with httpx.AsyncClient(
                            timeout=self.config.download_timeout_s, follow_redirects=True
                        ) as c:
                            return await import_pixabay_audio(
                                item_id=str(h.get("id") or ""),
                                title=str(h.get("title") or q),
                                artist=str(h.get("artist") or "Pixabay"),
                                download_url=str(h.get("download_url") or ""),
                                kind="music",
                                tags=list(h.get("tags") or [q]),
                                library_dir=self.library_dir,
                                client=c,
                            )

                    res = _run_coro(_imp_px())
                    item = res.get("item") or {}
                    fname = str(item.get("file") or "")
                    _upsert_index_metadata(
                        self.library_dir / "music",
                        file_name=fname,
                        source="pixabay",
                        source_id=sid,
                        extra_tags=[q],
                    )
                    return ResolvedAsset(
                        asset_id=str(item.get("id") or cand_id),
                        category="music",
                        file=fname,
                        path=str(res.get("path") or (self.library_dir / "music" / fname)),
                        origin="online_fetched",
                        source="pixabay",
                        source_id=sid,
                        title=str(item.get("title") or q),
                        duration_sec=float(item.get("duration") or dur),
                        score=0.85,
                    )
        except Exception as exc:
            logger.warning("Auto-fetch BGM Pixabay (q=%r) thất bại: %s", q, exc)

        return None

    def resolve_visual(
        self,
        query: str,
        *,
        exclude_ids: set[str] | None = None,
        auto_fetch_online: bool | None = None,
        prefer_greenmeme: bool = False,
        budget: FetchBudget | None = None,
        video_seq: int | None = None,
    ) -> ResolvedAsset | None:
        excluded = set(exclude_ids or ())
        allow_online = (
            self.config.auto_fetch_online if auto_fetch_online is None else auto_fetch_online
        )
        cands = self._scan_category("memes") + self._scan_category("stickers")
        scored = self._score_local(cands, query, exclude_ids=excluded, video_seq=video_seq)

        # 1. Local-first: dùng ngay nếu khớp >= threshold và không bị cooldown
        if scored:
            best_score, in_cd, best_cand = scored[0]
            if best_score >= self.config.local_score_threshold and not in_cd:
                return ResolvedAsset(
                    asset_id=best_cand.asset_id,
                    category=best_cand.category,
                    file=best_cand.file,
                    path=best_cand.path,
                    origin="local",
                    source=best_cand.source,
                    source_id=best_cand.source_id,
                    title=best_cand.title,
                    duration_sec=best_cand.duration_sec,
                    score=best_score,
                )

        # 2. Smart Auto-Fetch Online nếu cho phép & còn hạn mức phiên
        b = budget if budget is not None else FetchBudget()
        if allow_online and b.visual < self.config.max_fetch_visual:
            fetched = self._fetch_visual_online(
                query, prefer_greenmeme=prefer_greenmeme, exclude_ids=excluded
            )
            if fetched is not None:
                b.visual += 1
                return fetched

        # 3. Fallback êm về file local ít dùng nhất (không bao giờ crash)
        if scored:
            best_score, _in_cd, fallback_cand = scored[0]
            return ResolvedAsset(
                asset_id=fallback_cand.asset_id,
                category=fallback_cand.category,
                file=fallback_cand.file,
                path=fallback_cand.path,
                origin="local",
                source=fallback_cand.source,
                source_id=fallback_cand.source_id,
                title=fallback_cand.title,
                duration_sec=fallback_cand.duration_sec,
                score=best_score,
            )
        return None

    def resolve_sfx(
        self,
        query: str,
        *,
        exclude_ids: set[str] | None = None,
        auto_fetch_online: bool | None = None,
        budget: FetchBudget | None = None,
        video_seq: int | None = None,
    ) -> ResolvedAsset | None:
        excluded = set(exclude_ids or ())
        allow_online = (
            self.config.auto_fetch_online if auto_fetch_online is None else auto_fetch_online
        )
        cands = self._scan_category("sfx")
        scored = self._score_local(cands, query, exclude_ids=excluded, video_seq=video_seq)

        if scored:
            best_score, in_cd, best_cand = scored[0]
            if best_score >= self.config.local_score_threshold and not in_cd:
                return ResolvedAsset(
                    asset_id=best_cand.asset_id,
                    category="sfx",
                    file=best_cand.file,
                    path=best_cand.path,
                    origin="local",
                    source=best_cand.source,
                    source_id=best_cand.source_id,
                    title=best_cand.title,
                    duration_sec=best_cand.duration_sec,
                    score=best_score,
                )

        b = budget if budget is not None else FetchBudget()
        if allow_online and b.sfx < self.config.max_fetch_sfx:
            fetched = self._fetch_sfx_online(query, exclude_ids=excluded)
            if fetched is not None:
                b.sfx += 1
                return fetched

        if scored:
            best_score, _in_cd, fallback_cand = scored[0]
            return ResolvedAsset(
                asset_id=fallback_cand.asset_id,
                category="sfx",
                file=fallback_cand.file,
                path=fallback_cand.path,
                origin="local",
                source=fallback_cand.source,
                source_id=fallback_cand.source_id,
                title=fallback_cand.title,
                duration_sec=fallback_cand.duration_sec,
                score=best_score,
            )
        return None

    def resolve_bgm(
        self,
        mood_or_query: str,
        *,
        exclude_ids: set[str] | None = None,
        auto_fetch_online: bool | None = None,
        budget: FetchBudget | None = None,
        video_seq: int | None = None,
    ) -> ResolvedAsset | None:
        excluded = set(exclude_ids or ())
        allow_online = (
            self.config.auto_fetch_online if auto_fetch_online is None else auto_fetch_online
        )
        cands = self._scan_category("music")
        scored = self._score_local(
            cands, mood_or_query, exclude_ids=excluded, video_seq=video_seq, min_duration_s=50.0
        )

        if scored:
            best_score, in_cd, best_cand = scored[0]
            if best_score >= self.config.local_score_threshold and not in_cd:
                return ResolvedAsset(
                    asset_id=best_cand.asset_id,
                    category="music",
                    file=best_cand.file,
                    path=best_cand.path,
                    origin="local",
                    source=best_cand.source,
                    source_id=best_cand.source_id,
                    title=best_cand.title,
                    duration_sec=best_cand.duration_sec,
                    score=best_score,
                )

        b = budget if budget is not None else FetchBudget()
        if allow_online and b.bgm < self.config.max_fetch_bgm:
            fetched = self._fetch_bgm_online(mood_or_query, exclude_ids=excluded)
            if fetched is not None:
                b.bgm += 1
                return fetched

        if scored:
            best_score, _in_cd, fallback_cand = scored[0]
            return ResolvedAsset(
                asset_id=fallback_cand.asset_id,
                category="music",
                file=fallback_cand.file,
                path=fallback_cand.path,
                origin="local",
                source=fallback_cand.source,
                source_id=fallback_cand.source_id,
                title=fallback_cand.title,
                duration_sec=fallback_cand.duration_sec,
                score=best_score,
            )
        return None
