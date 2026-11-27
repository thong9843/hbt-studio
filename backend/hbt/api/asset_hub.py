"""Router API cho Thư viện tài nguyên (Asset Hub) và Kho Video đã xuất hợp nhất.

Quản lý và quét kết hợp nguyên liệu thực tế từ `library/`, `assets/` và `brand/`:
- music: library/music/ + assets/music/
- backgrounds: library/backgrounds/ + assets/backgrounds/
- stickers: library/stickers/ + backend/hbt/chatting/stickers/ + assets/stickers/
- memes: library/memes/ + assets/memes/
- watermarks: brand/hbt-logo-mark.png + assets/watermarks/
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote, unquote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from hbt.api.deps import State
from hbt.app_settings import resolve_online_api_key
from hbt.config import BRAND_DIR, REPO_ROOT
from hbt.pipeline.ffutil import ffmpeg_exe
from hbt.shared.db.media_index import (
    delete_render,
    init_db,
    list_renders,
)
from hbt.shared.online_sources import (
    batch_auto_tag_memes,
    import_freesound_audio,
    import_giphy_sticker,
    import_greenmeme,
    import_pixabay_audio,
    import_sigstick_pack,
    import_tuna_sfx,
    search_freesound_audio,
    search_giphy_stickers,
    search_greenmeme,
    search_pixabay_audio,
    search_tuna_sfx,
    update_meme_metadata,
)
from hbt.stickv.poses_init import (
    convert_stickman_dir_to_transparent,
    ensure_default_poses,
    remove_white_background,
)
from hbt.stickv.puppet import (
    PUPPET_SLOTS,
    auto_segment_puppet,
    clean_puppet_sprite,
    get_puppet_status,
)
from hbt.storage import BadRequest, NotFound, Unprocessable

router = APIRouter(tags=["asset_hub"])

_ONLINE_CACHE_TTL_S = 600.0
_ONLINE_SEARCH_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}

VALID_CATEGORIES = ("music", "backgrounds", "stickers", "memes", "watermarks", "stickman")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
CHATTING_STICKERS_DIR = REPO_ROOT / "backend" / "hbt" / "chatting" / "stickers"


def _category_dir(state: State, category: str) -> Path:
    if category not in VALID_CATEGORIES:
        raise Unprocessable(
            f"Danh mục không hợp lệ: '{category}'. Chỉ chấp nhận: {', '.join(VALID_CATEGORIES)}"
        )
    folder = state.settings.assets_dir / category
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_filename(raw_name: str) -> str:
    base = Path(raw_name or "file").name.strip()
    if not base or base in (".", ".."):
        raise BadRequest("Tên tệp không hợp lệ")
    stem = Path(base).stem
    suffix = Path(base).suffix.lower()
    clean_stem = _SAFE_NAME_RE.sub("-", stem).strip("-.") or "asset"
    if suffix and suffix not in ALLOWED_EXTS:
        raise Unprocessable(f"Định dạng tệp '{suffix}' chưa được hỗ trợ trong Asset Hub")
    return f"{clean_stem}{suffix}"


def _validate_existing_filename(filename: str) -> str:
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or ".." in filename
        or filename.startswith(".")
    ):
        raise Unprocessable("Tên tệp không hợp lệ")
    return filename


def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return "other"


def _read_index_map(folder: Path) -> dict[str, dict[str, Any]]:
    idx_file = folder / "index.json"
    if not idx_file.is_file():
        return {}
    try:
        raw = json.loads(idx_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {
                str(entry.get("file") or entry.get("filename") or ""): entry
                for entry in raw
                if isinstance(entry, dict) and (entry.get("file") or entry.get("filename"))
            }
    except Exception:
        pass
    return {}


def _probe_and_thumb_video_pose(
    video_path: Path, thumb_dir: Path
) -> tuple[float, int, int, Path | None]:
    """Đo duration_sec, width, height bằng `probe_media_info` và tạo thumbnail .jpg."""
    from hbt.shared.ffmpeg_utils import probe_media_info

    info = probe_media_info(video_path, timeout=10.0)
    dur = round(info.duration_s, 2)
    w, h = info.width, info.height

    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / f"{video_path.stem}.jpg"
    if not thumb_path.is_file():
        seek_s = "0.5" if dur <= 0 or dur >= 0.6 else "0.0"
        try:
            subprocess.run(
                [
                    ffmpeg_exe(),
                    "-y",
                    "-ss",
                    seek_s,
                    "-i",
                    str(video_path),
                    "-vframes",
                    "1",
                    "-vf",
                    "scale=360:-2",
                    "-q:v",
                    "4",
                    str(thumb_path),
                ],
                capture_output=True,
                timeout=12,
                check=False,
            )
        except Exception:
            pass
    return dur, w, h, (thumb_path if thumb_path.is_file() else None)


def _serialize_item(
    category: str,
    path: Path,
    *,
    source: str = "assets",
    relpath: str | None = None,
    meta: dict[str, Any] | None = None,
    thumb_url: str | None = None,
    readonly: bool = False,
) -> dict[str, Any]:
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    rel = relpath or path.name
    if source == "assets" and rel == path.name:
        url = f"/api/asset-hub/files/{quote(category)}/{quote(path.name)}"
    else:
        url = f"/api/asset-hub/file/{quote(source)}/{quote(category)}/{quote(rel, safe='/')}"
    m = meta or {}
    kind = _file_kind(path)
    return {
        "id": str(m.get("id") or path.stem),
        "name": path.name,
        "category": category,
        "kind": kind,
        "media_type": "video" if kind == "video" else "image",
        "size": stat.st_size,
        "modified_at": mtime,
        "url": url,
        "file_url": url,
        "source": source,
        "readonly": readonly,
        "title": str(m.get("title") or path.stem),
        "artist": str(m.get("artist") or ""),
        "moods": list(m.get("moods") or []),
        "tags": list(m.get("tags") or []),
        "topic": str(m.get("topic") or ""),
        "duration": float(m.get("duration") or m.get("duration_sec") or 0.0),
        "duration_sec": float(m.get("duration_sec") or m.get("duration") or 0.0),
        "width": int(m.get("width") or 0),
        "height": int(m.get("height") or 0),
        "thumb_url": thumb_url,
        "anim_group": str(m.get("anim_group") or ""),
    }


def _collect_dir_items(
    folder: Path,
    category: str,
    *,
    source: str,
    seen_paths: set[Path],
    allowed_exts: set[str] | None = None,
    recursive: bool = False,
) -> list[dict[str, Any]]:
    if not folder.is_dir():
        return []
    index_map = _read_index_map(folder)
    out: list[dict[str, Any]] = []
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    for p in iterator:
        if not p.is_file() or p.name.startswith("."):
            continue
        if (
            p.name == "index.json"
            or "thumbs" in p.relative_to(folder).parts
            or any(part.startswith(".") for part in p.relative_to(folder).parts)
        ):
            continue
        ext = p.suffix.lower()
        if allowed_exts is not None and ext not in allowed_exts:
            continue
        if ext not in ALLOWED_EXTS:
            continue
        resolved = p.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        rel = p.relative_to(folder).as_posix()
        meta = index_map.get(p.name) or index_map.get(rel)
        thumb_url: str | None = None
        if category == "backgrounds":
            thumb_file = folder / "thumbs" / f"{p.stem}.jpg"
            if thumb_file.is_file():
                thumb_url = (
                    f"/api/asset-hub/file/{quote(source)}/{quote(category)}"
                    f"/thumbs/{quote(thumb_file.name)}"
                )
        elif category == "stickman":
            anim_group = "pose"
            if rel.startswith("animations/oneshot/"):
                anim_group = "oneshot"
            elif rel.startswith("animations/loop/"):
                anim_group = "loop"
            if _file_kind(p) == "video":
                dur, vw, vh, thumb_file = _probe_and_thumb_video_pose(p, folder / "thumbs")
                meta = {
                    **(meta or {}),
                    "duration_sec": dur,
                    "width": vw,
                    "height": vh,
                    "anim_group": anim_group,
                }
                if thumb_file is not None:
                    thumb_url = (
                        f"/api/asset-hub/file/{quote(source)}/{quote(category)}"
                        f"/thumbs/{quote(thumb_file.name)}"
                    )
            else:
                meta = {**(meta or {}), "anim_group": anim_group}
        out.append(
            _serialize_item(
                category,
                p,
                source=source,
                relpath=rel,
                meta=meta,
                thumb_url=thumb_url,
            )
        )
    return out


class PixabayImportBody(BaseModel):
    item_id: str
    title: str
    artist: str = "Pixabay Creator"
    download_url: str
    kind: Literal["music", "sfx"] = "music"
    tags: list[str] = []


class GreenMemeImportBody(BaseModel):
    meme_id: str
    title: str
    video_url: str
    poster_url: str = ""


class GiphyImportBody(BaseModel):
    sticker_id: str
    title: str
    download_url: str


class SigStickImportBody(BaseModel):
    url: str


class TunaImportBody(BaseModel):
    item_id: str
    title: str
    preview_url: str
    tags: list[str] = []


class FreesoundImportBody(BaseModel):
    item_id: str
    title: str
    artist: str = "Freesound Creator"
    download_url: str
    kind: Literal["music", "sfx"] = "music"
    tags: list[str] = []
    license_url: str = ""


class MemePatchBody(BaseModel):
    tags: list[str] | None = None
    topic: str | None = None
    title: str | None = None


def clear_online_search_cache() -> None:
    _ONLINE_SEARCH_CACHE.clear()


@router.get("/asset-hub/online/search")
async def online_search_unified(
    state: State,
    category: Literal["music", "sfx", "memes", "stickers"] = Query(default="music"),
    source: str = Query(default=""),
    q: str = Query(default=""),
) -> dict[str, Any]:
    """Cổng tìm kiếm tài nguyên online thống nhất kèm In-Memory TTL Cache (10 phút)."""
    chosen_src = source.strip().lower()
    if not chosen_src:
        chosen_src = (
            "tuna"
            if category == "sfx"
            else "freesound"
            if category == "music"
            else "greenmeme"
            if category == "memes"
            else "giphy"
        )
    norm_q = (q or "").strip().lower()
    cache_key = (category, chosen_src, norm_q)
    now = time.monotonic()
    cached = _ONLINE_SEARCH_CACHE.get(cache_key)
    if cached is not None and (now - cached[0]) < _ONLINE_CACHE_TTL_S:
        return {**cached[1], "cached": True}

    try:
        if category == "sfx" and chosen_src == "tuna":
            tuna_key = resolve_online_api_key("VOICEMOD_TUNA_API_KEY", state.settings.workspace_dir)
            items = await search_tuna_sfx(q or "meme", api_key=tuna_key)
            res: dict[str, Any] = {
                "items": items,
                "missing_key": False,
                "source": "tuna",
                "category": "sfx",
            }
        elif category in ("music", "sfx") and chosen_src == "freesound":
            fkey = resolve_online_api_key("FREESOUND_API_KEY", state.settings.workspace_dir)
            if not fkey:
                return {
                    "items": [],
                    "missing_key": True,
                    "source": "freesound",
                    "category": category,
                }
            items = await search_freesound_audio(q, kind=category, api_key=fkey)
            res = {
                "items": items,
                "missing_key": False,
                "source": "freesound",
                "category": category,
            }
        elif category in ("music", "sfx"):
            api_key = resolve_online_api_key("PIXABAY_API_KEY", state.settings.workspace_dir)
            if not api_key:
                return {
                    "items": [],
                    "missing_key": True,
                    "source": "pixabay",
                    "category": category,
                }
            items = await search_pixabay_audio(q, kind=category, api_key=api_key)
            res = {
                "items": items,
                "missing_key": False,
                "source": "pixabay",
                "category": category,
            }
        elif category == "memes":
            items = await search_greenmeme(q)
            res = {
                "items": items,
                "missing_key": False,
                "source": "greenmeme",
                "category": "memes",
            }
        else:
            api_key = resolve_online_api_key("GIPHY_API_KEY", state.settings.workspace_dir)
            if not api_key:
                return {
                    "items": [],
                    "missing_key": True,
                    "source": "giphy",
                    "category": "stickers",
                }
            items = await search_giphy_stickers(q, api_key=api_key)
            res = {
                "items": items,
                "missing_key": False,
                "source": "giphy",
                "category": "stickers",
            }
    except ValueError as exc:
        return {
            "items": [],
            "missing_key": False,
            "source": chosen_src,
            "category": category,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "items": [],
            "missing_key": False,
            "source": chosen_src,
            "category": category,
            "error": (
                f"Nguồn {chosen_src} tạm thời không phản hồi ({exc.__class__.__name__}). "
                "Vui lòng thử lại."
            ),
        }

    _ONLINE_SEARCH_CACHE[cache_key] = (now, res)
    return {**res, "cached": False}


@router.get("/asset-hub/online/pixabay")
async def online_search_pixabay(
    state: State,
    q: str = Query(default=""),
    kind: Literal["music", "sfx"] = Query(default="music"),
    source: Literal["pixabay", "tuna"] = Query(default="pixabay"),
) -> dict[str, Any]:
    if source == "tuna" and kind == "sfx":
        items = await search_tuna_sfx(q or "meme")
        return {"items": items, "missing_key": False, "source": "tuna"}
    api_key = resolve_online_api_key("PIXABAY_API_KEY", state.settings.workspace_dir)
    if not api_key:
        return {"items": [], "missing_key": True}
    items = await search_pixabay_audio(q, kind=kind, api_key=api_key)
    return {"items": items, "missing_key": False, "source": "pixabay"}


@router.get("/asset-hub/online/tuna")
async def online_search_tuna(q: str = Query(default="meme")) -> dict[str, Any]:
    items = await search_tuna_sfx(q)
    return {"items": items, "missing_key": False, "source": "tuna"}


@router.post("/asset-hub/online/tuna/import")
async def online_import_tuna(body: TunaImportBody, state: State) -> dict[str, Any]:
    return await import_tuna_sfx(
        item_id=body.item_id,
        title=body.title,
        preview_url=body.preview_url,
        tags=body.tags,
        library_dir=state.settings.library_dir,
    )


@router.post("/asset-hub/online/freesound/import")
async def online_import_freesound(body: FreesoundImportBody, state: State) -> dict[str, Any]:
    return await import_freesound_audio(
        item_id=body.item_id,
        title=body.title,
        artist=body.artist,
        download_url=body.download_url,
        kind=body.kind,
        tags=body.tags,
        license_url=body.license_url,
        library_dir=state.settings.library_dir,
    )


@router.post("/asset-hub/online/pixabay/import")
async def online_import_pixabay(body: PixabayImportBody, state: State) -> dict[str, Any]:
    return await import_pixabay_audio(
        item_id=body.item_id,
        title=body.title,
        artist=body.artist,
        download_url=body.download_url,
        kind=body.kind,
        tags=body.tags,
        library_dir=state.settings.library_dir,
    )


@router.get("/asset-hub/online/greenmeme")
async def online_search_greenmeme(q: str = Query(default="")) -> dict[str, Any]:
    items = await search_greenmeme(q)
    return {"items": items}


@router.post("/asset-hub/online/greenmeme/import")
async def online_import_greenmeme(body: GreenMemeImportBody, state: State) -> dict[str, Any]:
    return await import_greenmeme(
        meme_id=body.meme_id,
        title=body.title,
        video_url=body.video_url,
        poster_url=body.poster_url,
        library_dir=state.settings.library_dir,
    )


@router.get("/asset-hub/online/giphy")
async def online_search_giphy(state: State, q: str = Query(default="")) -> dict[str, Any]:
    api_key = resolve_online_api_key("GIPHY_API_KEY", state.settings.workspace_dir)
    if not api_key:
        return {"items": [], "missing_key": True}
    items = await search_giphy_stickers(q, api_key=api_key)
    return {"items": items, "missing_key": False}


@router.post("/asset-hub/online/giphy/import")
async def online_import_giphy(body: GiphyImportBody, state: State) -> dict[str, Any]:
    return await import_giphy_sticker(
        sticker_id=body.sticker_id,
        title=body.title,
        download_url=body.download_url,
        library_dir=state.settings.library_dir,
    )


@router.post("/asset-hub/online/sigstick/import")
async def online_import_sigstick(body: SigStickImportBody, state: State) -> dict[str, Any]:
    try:
        return await import_sigstick_pack(body.url, library_dir=state.settings.library_dir)
    except ValueError as e:
        raise Unprocessable(str(e)) from e


@router.post("/asset-hub/memes/auto-tag")
def auto_tag_memes_endpoint(state: State) -> dict[str, Any]:
    memes_dir = state.settings.library_dir / "memes"
    return batch_auto_tag_memes(memes_dir)


@router.patch("/asset-hub/memes/{meme_id}")
def patch_meme_endpoint(meme_id: str, body: MemePatchBody, state: State) -> dict[str, Any]:
    memes_dir = state.settings.library_dir / "memes"
    updated = update_meme_metadata(
        memes_dir,
        meme_id,
        tags=body.tags,
        topic=body.topic,
        title=body.title,
    )
    if updated is None:
        raise NotFound(f"Không tìm thấy meme '{meme_id}'")
    return {"ok": True, "item": updated}


@router.get("/asset-hub/stickman/puppet")
def get_stickman_puppet_status(state: State) -> dict[str, Any]:
    """Trạng thái bộ linh kiện 7 mảnh Puppet 2D trong thư viện."""
    return get_puppet_status(state.settings.library_dir, state.settings.assets_dir)


@router.post("/asset-hub/stickman/puppet/{slot}", status_code=201)
async def upload_stickman_puppet_slot(
    slot: str,
    state: State,
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    """Tải lên 1 mảnh linh kiện Puppet 2D vào `library/stickman/puppet/<slot>.png`."""
    if slot not in PUPPET_SLOTS:
        raise Unprocessable(f"Slot Puppet không hợp lệ: '{slot}'")

    puppet_dir = state.settings.library_dir / "stickman" / "puppet"
    puppet_dir.mkdir(parents=True, exist_ok=True)
    raw_bytes = await file.read()
    tmp_raw = puppet_dir / f".raw_{slot}_{_safe_filename(file.filename or 'part.png')}"
    tmp_raw.write_bytes(raw_bytes)
    target = puppet_dir / f"{slot}.png"
    try:
        from PIL import Image

        with Image.open(tmp_raw) as raw_img:
            cleaned = clean_puppet_sprite(raw_img, padding=4)
        try:
            cleaned.save(target, format="PNG")
        finally:
            cleaned.close()
    finally:
        tmp_raw.unlink(missing_ok=True)

    segmented = False
    if slot == "base_character":
        auto_segment_puppet(target, puppet_dir / ".segments")
        segmented = True

    return {
        "ok": True,
        "slot": slot,
        "segmented": segmented,
        "status": get_puppet_status(state.settings.library_dir, state.settings.assets_dir),
    }


@router.get("/asset-hub/{category}")
def list_asset_hub_items(category: str, state: State) -> dict[str, Any]:
    assets_folder = _category_dir(state, category)
    lib_dir = state.settings.library_dir
    seen_paths: set[Path] = set()
    items: list[dict[str, Any]] = []

    if category == "music":
        items.extend(
            _collect_dir_items(
                assets_folder,
                category,
                source="assets",
                seen_paths=seen_paths,
                allowed_exts=AUDIO_EXTS,
            )
        )
        items.extend(
            _collect_dir_items(
                lib_dir / "music",
                category,
                source="library",
                seen_paths=seen_paths,
                allowed_exts=AUDIO_EXTS,
            )
        )
    elif category == "backgrounds":
        items.extend(
            _collect_dir_items(
                assets_folder,
                category,
                source="assets",
                seen_paths=seen_paths,
                allowed_exts=VIDEO_EXTS,
            )
        )
        items.extend(
            _collect_dir_items(
                lib_dir / "backgrounds",
                category,
                source="library",
                seen_paths=seen_paths,
                allowed_exts=VIDEO_EXTS,
            )
        )
    elif category == "memes":
        items.extend(
            _collect_dir_items(
                assets_folder,
                category,
                source="assets",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
            )
        )
        items.extend(
            _collect_dir_items(
                lib_dir / "memes",
                category,
                source="library",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
            )
        )
    elif category == "stickers":
        items.extend(
            _collect_dir_items(
                assets_folder,
                category,
                source="assets",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
            )
        )
        items.extend(
            _collect_dir_items(
                lib_dir / "stickers",
                category,
                source="library",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
                recursive=True,
            )
        )
        if CHATTING_STICKERS_DIR.is_dir():
            items.extend(
                _collect_dir_items(
                    CHATTING_STICKERS_DIR,
                    category,
                    source="chatting",
                    seen_paths=seen_paths,
                    allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
                    recursive=True,
                )
            )
    elif category == "watermarks":
        items.extend(
            _collect_dir_items(
                assets_folder,
                category,
                source="assets",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS,
            )
        )
        brand_logo = BRAND_DIR / "hbt-logo-mark.png"
        if brand_logo.is_file() and brand_logo.resolve() not in seen_paths:
            seen_paths.add(brand_logo.resolve())
            items.append(
                _serialize_item(
                    "watermarks",
                    brand_logo,
                    source="brand",
                    relpath="hbt-logo-mark.png",
                    meta={"title": "Logo HBT Studio (Mặc định)"},
                    readonly=True,
                )
            )
    elif category == "stickman":
        convert_stickman_dir_to_transparent(assets_folder)
        convert_stickman_dir_to_transparent(lib_dir / "stickman" / "poses")
        ensure_default_poses(lib_dir / "stickman" / "poses")
        items.extend(
            _collect_dir_items(
                assets_folder,
                category,
                source="assets",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
                recursive=True,
            )
        )
        items.extend(
            _collect_dir_items(
                lib_dir / "stickman",
                category,
                source="library",
                seen_paths=seen_paths,
                allowed_exts=IMAGE_EXTS | VIDEO_EXTS,
                recursive=True,
            )
        )

    items.sort(key=lambda x: str(x["modified_at"]), reverse=True)
    return {"category": category, "items": items}


@router.post("/asset-hub/{category}", status_code=201)
async def upload_asset_hub_item(
    category: str,
    state: State,
    file: Annotated[UploadFile, File(...)],
    anim_group: Annotated[str, Form()] = "pose",
) -> dict[str, Any]:
    clean_group = anim_group if anim_group in {"pose", "oneshot", "loop"} else "pose"
    is_anim_slot = category == "stickman" and clean_group in {"oneshot", "loop"}
    if is_anim_slot:
        base_lib = state.settings.library_dir / "stickman"
        folder = base_lib / "animations" / clean_group
        folder.mkdir(parents=True, exist_ok=True)
        dest_source = "library"
    else:
        base_lib = _category_dir(state, category)
        folder = base_lib
        dest_source = "assets"

    safe_name = _safe_filename(file.filename or "asset.bin")
    target = folder / safe_name

    # Tránh ghi đè tệp trùng tên bằng hậu tố -2, -3...
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        idx = 2
        while (folder / f"{stem}-{idx}{suffix}").exists():
            idx += 1
        target = folder / f"{stem}-{idx}{suffix}"

    content = await file.read()
    target.write_bytes(content)

    meta_override: dict[str, Any] | None = (
        {"anim_group": clean_group} if category == "stickman" else None
    )
    thumb_url: str | None = None
    if (
        category == "stickman"
        and not is_anim_slot
        and target.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ):
        png_target = target.with_suffix(".png")
        final_path, _ = remove_white_background(target, png_target)
        if final_path != target and target.is_file() and final_path.is_file():
            target.unlink(missing_ok=True)
            target = final_path
    elif category == "stickman" and target.suffix.lower() in VIDEO_EXTS:
        dur, vw, vh, thumb_file = _probe_and_thumb_video_pose(target, base_lib / "thumbs")
        meta_override = {"duration_sec": dur, "width": vw, "height": vh, "anim_group": clean_group}
        if thumb_file is not None:
            thumb_url = (
                f"/api/asset-hub/file/{quote(dest_source)}/stickman/thumbs/{quote(thumb_file.name)}"
            )

    relpath = f"animations/{clean_group}/{target.name}" if is_anim_slot else None
    return {
        "ok": True,
        "item": _serialize_item(
            category,
            target,
            source=dest_source,
            relpath=relpath,
            meta=meta_override,
            thumb_url=thumb_url,
        ),
    }


@router.post("/asset-hub/stickman/{filename}/remove-bg")
def remove_stickman_background(
    filename: str,
    state: State,
    source: str | None = None,
) -> dict[str, Any]:
    """Tách nền trắng bên ngoài cho ảnh nhân vật Stickman."""
    clean_name = _validate_existing_filename(filename)
    assets_dir = _category_dir(state, "stickman")
    candidates: list[tuple[str, Path]] = []
    if source in (None, "assets"):
        candidates.append(("assets", assets_dir / clean_name))
    if source in (None, "library"):
        candidates.append(("library", state.settings.library_dir / "stickman" / clean_name))
        candidates.append(
            ("library", state.settings.library_dir / "stickman" / "poses" / clean_name)
        )

    for src_name, path in candidates:
        if path.is_file():
            png_target = path.with_suffix(".png")
            final_path, removed = remove_white_background(path, png_target)
            if final_path != path and path.is_file() and final_path.is_file():
                path.unlink(missing_ok=True)
            return {
                "ok": True,
                "removed": removed,
                "item": _serialize_item("stickman", final_path, source=src_name),
            }

    raise NotFound(f"Không tìm thấy nhân vật '{clean_name}'")


@router.post("/asset-hub/stickman/{filename}/set-default")
def set_default_stickman(filename: str, state: State) -> dict[str, Any]:
    """Đặt ảnh nhân vật người dùng upload làm nhân vật mặc định (default.png) cho StickV."""
    clean_name = _validate_existing_filename(filename)
    assets_dir = _category_dir(state, "stickman")
    src = (assets_dir / clean_name).resolve()
    if not src.is_file():
        src_lib = (state.settings.library_dir / "stickman" / clean_name).resolve()
        src = src_lib if src_lib.is_file() else src
    if not src.is_file():
        raise NotFound(f"Không tìm thấy nhân vật '{clean_name}'")

    dest = assets_dir / "default.png"
    if src != dest.resolve():
        dest.write_bytes(src.read_bytes())
    return {"ok": True, "item": _serialize_item("stickman", dest, source="assets")}


@router.delete("/asset-hub/{category}/{filename}")
def delete_asset_hub_item(
    category: str,
    filename: str,
    state: State,
    source: str | None = None,
) -> dict[str, Any]:
    if source == "brand":
        raise Unprocessable("Không thể xóa Logo thương hiệu mặc định")
    folder = _category_dir(state, category)
    clean_name = _validate_existing_filename(filename)
    candidates: list[Path] = []
    if source in (None, "assets"):
        candidates.append(folder)
        if category == "stickman":
            candidates.extend(
                [
                    folder / "animations" / "oneshot",
                    folder / "animations" / "loop",
                ]
            )
    if source in (None, "library"):
        lib_cat = state.settings.library_dir / category
        candidates.append(lib_cat)
        if category == "stickman":
            candidates.extend(
                [
                    lib_cat / "poses",
                    lib_cat / "animations" / "oneshot",
                    lib_cat / "animations" / "loop",
                ]
            )

    for base in candidates:
        base_res = base.resolve()
        target = (base / clean_name).resolve()
        if target.parent == base_res and target.is_file():
            target.unlink()
            return {"ok": True, "deleted": clean_name}

    raise NotFound(f"Không tìm thấy tệp '{clean_name}' trong '{category}'")


@router.get("/asset-hub/files/{category}/{filename}")
def serve_asset_hub_file(category: str, filename: str, state: State) -> FileResponse:
    folder = _category_dir(state, category)
    clean_name = _validate_existing_filename(filename)
    target = (folder / clean_name).resolve()
    if target.parent != folder.resolve() or not target.is_file():
        raise NotFound(f"Không tìm thấy tệp '{clean_name}' trong '{category}'")
    return FileResponse(target)


@router.get("/asset-hub/file/{source}/{category}/{relpath:path}")
def serve_asset_hub_source_file(
    source: str, category: str, relpath: str, state: State
) -> FileResponse:
    if category not in VALID_CATEGORIES:
        raise Unprocessable(f"Danh mục không hợp lệ: '{category}'")
    if not relpath or ".." in Path(relpath).parts:
        raise Unprocessable("Đường dẫn tệp không hợp lệ")

    if source == "assets":
        root = (state.settings.assets_dir / category).resolve()
    elif source == "library":
        root = (state.settings.library_dir / category).resolve()
    elif source == "brand":
        root = BRAND_DIR.resolve()
    elif source == "chatting":
        root = CHATTING_STICKERS_DIR.resolve()
    else:
        raise Unprocessable(f"Nguồn tài nguyên không hợp lệ: '{source}'")

    target = (root / relpath).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise Unprocessable("Đường dẫn tệp vượt khỏi phạm vi cho phép") from exc

    if not target.is_file():
        raise NotFound(f"Không tìm thấy tệp '{relpath}'")
    return FileResponse(target)


def _db_path(state: State) -> Path:
    return state.settings.workspace_dir / "studio.db"


@router.get("/renders")
def list_unified_renders(state: State, engine: str | None = None) -> dict[str, Any]:
    """Liệt kê hợp nhất toàn bộ Video đã xuất từ 4 động cơ (core, postv, chatting, stickv)."""
    from hbt.shared.db.media_index import resolve_media_path, sync_renders_from_disk

    db = _db_path(state)
    base_dir = state.settings.workspace_dir.parent
    renders_root = state.settings.assets_dir / "renders"
    sync_renders_from_disk(renders_root, db_path=db, workspace_dir=state.settings.workspace_dir)
    valid_eng = engine if engine in ("core", "postv", "chatting", "stickv") else None
    rows = list_renders(engine=valid_eng, db_path=db)
    items: list[dict[str, Any]] = []
    for r in rows:
        rid = str(r["id"])
        enc_id = quote(rid, safe="")
        abs_video = resolve_media_path(str(r.get("file_path") or ""), base_dir=base_dir)
        size_bytes = abs_video.stat().st_size if abs_video.is_file() else 0
        size_mb = float(r.get("size_mb") or 0.0)
        if size_mb <= 0.0 and size_bytes > 0:
            size_mb = round(size_bytes / (1024 * 1024), 2)
        cover_raw = str(r.get("cover_path") or "")
        abs_cover = resolve_media_path(cover_raw, base_dir=base_dir) if cover_raw else Path("")
        has_cover = bool(cover_raw) and abs_cover.is_file()
        cover_url = f"/api/renders/media/{enc_id}?kind=cover" if has_cover else None
        items.append(
            {
                "id": rid,
                "slug": r.get("slug", ""),
                "title": r.get("title", ""),
                "engine": r.get("engine", "core"),
                "duration_sec": float(r.get("duration_sec") or 0.0),
                "size_mb": size_mb,
                "size_bytes": size_bytes,
                "publish_text": r.get("source_credit") or "",
                "created_at": r.get("created_at") or "",
                "video_url": f"/api/renders/media/{enc_id}?kind=video",
                "cover_url": cover_url,
                "thumb_url": cover_url,
            }
        )
    return {"items": items}


def _find_render_row(conn: Any, render_id: str, base_dir: Path) -> Any:
    from hbt.shared.db.media_index import normalize_media_path

    decoded = unquote(render_id)
    candidates = list(dict.fromkeys([render_id, decoded]))
    for cand in candidates:
        row = conn.execute("SELECT * FROM renders WHERE id = ?", (cand,)).fetchone()
        if row is not None:
            return row
    for cand in candidates:
        norm = normalize_media_path(cand, base_dir=base_dir)
        row = conn.execute("SELECT * FROM renders WHERE file_path = ?", (norm,)).fetchone()
        if row is not None:
            return row
    return None


@router.get("/renders/media/{render_id:path}")
def serve_unified_render_media(
    render_id: str,
    state: State,
    kind: str = "video",
    download: bool = False,
) -> FileResponse:
    from hbt.shared.db.media_index import resolve_media_path

    db = _db_path(state)
    base_dir = state.settings.workspace_dir.parent
    conn = init_db(db)
    try:
        row = _find_render_row(conn, render_id, base_dir)
    finally:
        conn.close()
    if row is None:
        raise NotFound(f"Không tìm thấy bản xuất '{render_id}'")
    target_str = str(row["cover_path"] if kind == "cover" else row["file_path"])
    if not target_str:
        raise NotFound("Không có tệp media tương ứng")
    target = resolve_media_path(target_str, base_dir=base_dir)
    if not target.is_file():
        raise NotFound("Tệp media không còn tồn tại trên ổ đĩa")
    if download:
        slug = str(row["slug"] or target.stem).strip() or target.stem
        dl_name = f"{slug}{target.suffix or '.mp4'}"
        return FileResponse(
            target,
            filename=dl_name,
            media_type="video/mp4" if kind != "cover" else None,
            content_disposition_type="attachment",
        )
    return FileResponse(target, media_type="video/mp4" if kind != "cover" else None)


@router.delete("/renders/{render_id:path}")
def delete_unified_render(render_id: str, state: State) -> dict[str, Any]:
    from hbt.shared.db.media_index import (
        normalize_media_path,
        record_deleted_render_path,
        resolve_media_path,
    )

    db = _db_path(state)
    base_dir = state.settings.workspace_dir.parent
    conn = init_db(db)
    try:
        row = _find_render_row(conn, render_id, base_dir)
        if row is None:
            raise NotFound(f"Không tìm thấy bản xuất '{render_id}'")
        row_id = str(row["id"])
        row_fp = str(row["file_path"] or "")
        norm_fp = normalize_media_path(row_fp, base_dir=base_dir) if row_fp else ""
        fp = resolve_media_path(row_fp, base_dir=base_dir) if row_fp else Path("")
        # Luôn xóa bản ghi DB trước để thao tác xóa của người dùng luôn trả HTTP 200
        conn.execute("DELETE FROM renders WHERE id = ? OR file_path = ?", (row_id, norm_fp))
        conn.commit()
    finally:
        conn.close()
    delete_render(row_id, db_path=db)

    deferred_unlink = False
    if fp.is_file():
        for attempt in range(3):
            try:
                fp.unlink(missing_ok=True)
                deferred_unlink = False
                break
            except PermissionError:
                deferred_unlink = True
                if attempt < 2:
                    time.sleep(0.1)
            except OSError:
                deferred_unlink = True
                break
        if deferred_unlink and norm_fp:
            record_deleted_render_path(norm_fp, db_path=db)

    return {"ok": True, "deleted": row_id, "deferred_unlink": deferred_unlink}
