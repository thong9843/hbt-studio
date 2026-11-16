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
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from hbt.api.deps import State
from hbt.config import BRAND_DIR, REPO_ROOT
from hbt.shared.db.media_index import (
    delete_render,
    init_db,
    list_renders,
    sync_renders_dir,
)
from hbt.storage import BadRequest, NotFound, Unprocessable

router = APIRouter(tags=["asset_hub"])

VALID_CATEGORIES = ("music", "backgrounds", "stickers", "memes", "watermarks")
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
    return {
        "name": path.name,
        "category": category,
        "kind": _file_kind(path),
        "size": stat.st_size,
        "modified_at": mtime,
        "url": url,
        "source": source,
        "readonly": readonly,
        "title": str(m.get("title") or path.stem),
        "artist": str(m.get("artist") or ""),
        "moods": list(m.get("moods") or []),
        "duration": float(m.get("duration") or 0.0),
        "thumb_url": thumb_url,
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
        if p.name == "index.json" or "thumbs" in p.relative_to(folder).parts:
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

    items.sort(key=lambda x: str(x["modified_at"]), reverse=True)
    return {"category": category, "items": items}


@router.post("/asset-hub/{category}", status_code=201)
async def upload_asset_hub_item(
    category: str,
    state: State,
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    folder = _category_dir(state, category)
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
    return {"ok": True, "item": _serialize_item(category, target, source="assets")}


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
    if source in (None, "library"):
        candidates.append(state.settings.library_dir / category)

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
    """Liệt kê hợp nhất toàn bộ Video đã xuất từ 3 động cơ (core, postv, chatting)."""
    db = _db_path(state)
    renders_root = state.settings.assets_dir / "renders"
    sync_renders_dir(renders_root, db_path=db, workspace_dir=state.settings.workspace_dir)
    valid_eng = engine if engine in ("core", "postv", "chatting") else None
    rows = list_renders(engine=valid_eng, db_path=db)
    items: list[dict[str, Any]] = []
    for r in rows:
        rid = str(r["id"])
        enc_id = quote(rid, safe="")
        has_cover = bool(r.get("cover_path")) and Path(str(r["cover_path"])).is_file()
        items.append(
            {
                "id": rid,
                "slug": r.get("slug", ""),
                "title": r.get("title", ""),
                "engine": r.get("engine", "core"),
                "duration_sec": float(r.get("duration_sec") or 0.0),
                "size_mb": float(r.get("size_mb") or 0.0),
                "publish_text": r.get("source_credit") or "",
                "created_at": r.get("created_at") or "",
                "video_url": f"/api/renders/media/{enc_id}?kind=video",
                "cover_url": f"/api/renders/media/{enc_id}?kind=cover" if has_cover else None,
            }
        )
    return {"items": items}


@router.get("/renders/media/{render_id:path}")
def serve_unified_render_media(render_id: str, state: State, kind: str = "video") -> FileResponse:
    db = _db_path(state)
    conn = init_db(db)
    try:
        row = conn.execute("SELECT * FROM renders WHERE id = ?", (render_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFound(f"Không tìm thấy bản xuất '{render_id}'")
    target_str = str(row["cover_path"] if kind == "cover" else row["file_path"])
    if not target_str:
        raise NotFound("Không có tệp media tương ứng")
    target = Path(target_str).resolve()
    if not target.is_file():
        raise NotFound("Tệp media không còn tồn tại trên ổ đĩa")
    return FileResponse(target)


@router.delete("/renders/{render_id:path}")
def delete_unified_render(render_id: str, state: State) -> dict[str, Any]:
    db = _db_path(state)
    conn = init_db(db)
    try:
        row = conn.execute("SELECT * FROM renders WHERE id = ?", (render_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFound(f"Không tìm thấy bản xuất '{render_id}'")
    fp = Path(str(row["file_path"]))
    if fp.is_file():
        fp.unlink(missing_ok=True)
    delete_render(render_id, db_path=db)
    return {"ok": True, "deleted": render_id}
