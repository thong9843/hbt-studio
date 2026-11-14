"""Router API cho Thư viện tài nguyên (Asset Hub) và Kho Video đã xuất hợp nhất.

Quản lý nguyên liệu đầu vào:
- assets/music
- assets/backgrounds
- assets/stickers
- assets/memes
- assets/watermarks
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from hbt.api.deps import State
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


def _serialize_item(category: str, path: Path) -> dict[str, Any]:
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    return {
        "name": path.name,
        "category": category,
        "kind": _file_kind(path),
        "size": stat.st_size,
        "modified_at": mtime,
        "url": f"/api/asset-hub/files/{quote(category)}/{quote(path.name)}",
    }


@router.get("/asset-hub/{category}")
def list_asset_hub_items(category: str, state: State) -> dict[str, Any]:
    folder = _category_dir(state, category)
    files = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "category": category,
        "items": [_serialize_item(category, p) for p in files],
    }


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
    return {"ok": True, "item": _serialize_item(category, target)}


@router.delete("/asset-hub/{category}/{filename}")
def delete_asset_hub_item(category: str, filename: str, state: State) -> dict[str, Any]:
    folder = _category_dir(state, category)
    clean_name = _validate_existing_filename(filename)
    target = (folder / clean_name).resolve()
    if target.parent != folder.resolve() or not target.is_file():
        raise NotFound(f"Không tìm thấy tệp '{clean_name}' trong '{category}'")
    target.unlink()
    return {"ok": True, "deleted": clean_name}


@router.get("/asset-hub/files/{category}/{filename}")
def serve_asset_hub_file(category: str, filename: str, state: State) -> FileResponse:
    folder = _category_dir(state, category)
    clean_name = _validate_existing_filename(filename)
    target = (folder / clean_name).resolve()
    if target.parent != folder.resolve() or not target.is_file():
        raise NotFound(f"Không tìm thấy tệp '{clean_name}' trong '{category}'")
    return FileResponse(target)


def _db_path(state: State) -> Path:
    return state.settings.workspace_dir / "studio.db"


@router.get("/renders")
def list_unified_renders(state: State, engine: str | None = None) -> dict[str, Any]:
    """Liệt kê hợp nhất toàn bộ Video đã xuất từ 3 động cơ (core, postv, chatting)."""
    db = _db_path(state)
    renders_root = state.settings.assets_dir / "renders"
    sync_renders_dir(renders_root, db_path=db, workspace_dir=state.settings.workspace_dir)
    rows = list_renders(engine=engine if engine in ("core", "postv", "chatting") else None, db_path=db)
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
def serve_unified_render_media(
    render_id: str, state: State, kind: str = "video"
) -> FileResponse:
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
