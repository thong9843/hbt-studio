"""Thư viện nền gameplay của PostV: danh sách, thêm clip, phát thử, ảnh xem nhanh."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from hbt.api.assets import save_upload
from hbt.api.deps import State
from hbt.postv.backgrounds import BackgroundEntry
from hbt.postv.models import PostvProject
from hbt.storage import BadRequest, Conflict

router = APIRouter(tags=["backgrounds"])

MAX_BACKGROUND_BYTES = 2 << 30  # 2 GB


@router.get("/backgrounds", response_model=list[BackgroundEntry])
def list_backgrounds(state: State):
    return state.backgrounds.list()


@router.post("/backgrounds", response_model=BackgroundEntry, status_code=201)
def add_background(
    state: State,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    source: Annotated[str, Form()] = "",
    license: Annotated[str, Form()] = "",
    url: Annotated[str, Form()] = "",
    tags: Annotated[str, Form(description="cách nhau bằng dấu phẩy")] = "",
):
    clean_title = title.strip()
    if not clean_title:
        raise BadRequest("Thiếu tiêu đề clip nền")
    meta = {
        "title": clean_title,
        "source": source.strip(),
        "license": license.strip(),
        "url": url.strip(),
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    }
    tmp = save_upload(file, state.settings.workspace_dir / ".uploads", MAX_BACKGROUND_BYTES)
    try:
        return state.backgrounds.add(tmp, file.filename or "", meta)
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/backgrounds/{clip_id}/video")
def get_background_video(clip_id: str, state: State) -> FileResponse:
    """Phát thử clip (có Range)."""
    _, path = state.backgrounds.find(clip_id)
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@router.get("/backgrounds/{clip_id}/thumb")
def get_background_thumb(clip_id: str, state: State) -> FileResponse:
    return FileResponse(
        state.backgrounds.thumb_path(clip_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.delete("/backgrounds/{clip_id}", status_code=204)
def delete_background(clip_id: str, state: State) -> None:
    """Xoá clip nền; nếu đang được dự án PostV nào dùng thì 409 kèm tên dự án."""
    for summary in state.storage.list_projects():
        if summary.get("kind") == "postv":
            slug = summary.get("slug")
            if slug:
                p = state.storage.load_any(slug)
                if isinstance(p, PostvProject) and clip_id in p.background.clip_ids:
                    raise Conflict(f"Clip nền '{clip_id}' đang được dự án '{p.title}' sử dụng")
    state.backgrounds.remove(clip_id)
