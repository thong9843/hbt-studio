"""POST /api/projects/{slug}/assets: tải ảnh (theo cảnh), giọng đọc hoặc nhạc lên project."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.exceptions import HTTPException

from hbt.api.deps import State
from hbt.storage import BadRequest, Conflict

router = APIRouter(tags=["assets"])

MAX_BYTES = {"image": 30 << 20, "voice": 200 << 20, "music": 200 << 20}
CHUNK = 1 << 20


def save_upload(upload: UploadFile, folder: Path, limit: int) -> Path:
    """Chép file tải lên vào file tạm trong `folder`, chặn khi vượt `limit` byte."""
    folder.mkdir(parents=True, exist_ok=True)
    fd = tempfile.NamedTemporaryFile(dir=folder, prefix="upload-", suffix=".tmp", delete=False)
    path = Path(fd.name)
    written = 0
    try:
        with fd:
            while chunk := upload.file.read(CHUNK):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        413, f"File vượt giới hạn {limit >> 20} MB (đã nhận {written >> 20} MB)"
                    )
                fd.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    if written == 0:
        path.unlink(missing_ok=True)
        raise BadRequest("File rỗng")
    return path


@router.post("/projects/{slug}/assets")
def upload_asset(
    slug: str,
    state: State,
    kind: Annotated[str, Form(description="image | voice | music")],
    file: Annotated[UploadFile, File()],
    scene_index: Annotated[int | None, Form(description="chỉ số cảnh từ 0 (chỉ với ảnh)")] = None,
):
    if kind not in MAX_BYTES:
        raise BadRequest("`kind` phải là image, voice hoặc music")
    state.storage.load(slug)  # 404 sớm, trước khi nhận file lớn
    if state.jobs.is_busy(slug):
        raise Conflict("Project đang được dựng, hãy chờ hoặc huỷ job trước khi thay file")
    tmp = save_upload(file, state.settings.workspace_dir / ".uploads", MAX_BYTES[kind])
    try:
        rel, project = state.storage.save_asset(slug, kind, tmp, file.filename or "", scene_index)
    finally:
        tmp.unlink(missing_ok=True)  # đã được di chuyển thì không còn gì để xoá
    return {"kind": kind, "path": rel, "project": project}
