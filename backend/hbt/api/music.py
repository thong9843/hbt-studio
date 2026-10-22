"""Thư viện nhạc: GET /music, POST /music (tải bài mới kèm thông tin ghi công)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from hbt.api.assets import MAX_BYTES, save_upload
from hbt.api.deps import State
from hbt.library import MusicEntry
from hbt.models import Project
from hbt.storage import BadRequest

router = APIRouter(tags=["music"])


@router.get("/music", response_model=list[MusicEntry])
def list_music(state: State):
    return state.library.list()


@router.post("/music", response_model=MusicEntry, status_code=201)
def add_music(
    state: State,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    artist: Annotated[str, Form()],
    source: Annotated[str, Form()],
    license: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    moods: Annotated[str, Form(description="các tâm trạng, cách nhau bằng dấu phẩy")] = "",
    bpm: Annotated[int | None, Form()] = None,
):
    meta = {
        "title": title.strip(),
        "artist": artist.strip(),
        "source": source.strip(),
        "license": license.strip(),
        "url": url.strip(),
        "moods": [m.strip() for m in moods.split(",") if m.strip()],
        "bpm": bpm,
    }
    missing = [k for k in ("title", "artist", "source", "license") if not meta[k]]
    if missing:
        raise BadRequest("Thiếu thông tin ghi công: " + ", ".join(missing))
    tmp = save_upload(file, state.settings.workspace_dir / ".uploads", MAX_BYTES["music"])
    try:
        return state.library.add(tmp, file.filename or "", meta)
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/library/music/{file}")
def get_library_music(file: str, state: State) -> FileResponse:
    """Nghe thử một bài trong thư viện."""
    _, path = state.library.find(file)
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


class FromLibrary(BaseModel):
    file: str


@router.post("/projects/{slug}/music/from-library", response_model=Project)
def attach_library_music(slug: str, body: FromLibrary, state: State):
    """Dùng một bài trong thư viện cho project: chép file và đặt ghi công theo thư viện."""
    state.storage.load(slug)  # 404 trước nếu project không có
    entry, path = state.library.find(body.file)
    _, project = state.storage.attach_music(slug, path, entry.credit)
    return project
