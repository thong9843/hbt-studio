"""Khối JSON kịch bản và sao lưu: script/check, script/apply, backups (IMPLEMENT.md 13.B4.7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from hbt.api.deps import State
from hbt.backups import (
    check_backup_id,
    create_backup,
    list_backups,
    read_backup,
    write_project_bytes,
)
from hbt.models import Project
from hbt.script import check_script
from hbt.storage import BadRequest, Conflict, NotFound, Unprocessable

router = APIRouter(tags=["script"])


class ScriptCheckBody(BaseModel):
    script: Any  # chuỗi JSON người dùng dán, hoặc giá trị đã đọc
    extra: Literal["add", "trim"] | None = None


class ScriptApplyBody(ScriptCheckBody):
    base_hash: str


def _folder(state: State, slug: str) -> Path:
    folder = state.storage.project_dir(slug)  # 422 nếu slug sai
    if not (folder / "project.json").is_file():
        raise NotFound(f"Không có project '{slug}'")
    return folder


def _read(folder: Path) -> tuple[str, Project]:
    """(SHA-256 byte `project.json`, project). Chỉ đọc: không dời ảnh, không ghi gì."""
    raw = (folder / "project.json").read_bytes()
    try:
        return hashlib.sha256(raw).hexdigest(), Project.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as e:
        raise BadRequest(f"project.json không hợp lệ: {e}") from e


def _ensure_idle(state: State, slug: str, action: str) -> None:
    if state.jobs.is_busy(slug):
        raise Conflict(f"Project đang được dựng, hãy đợi xong hoặc huỷ job rồi mới {action}")


@router.post("/projects/{slug}/script/check")
def check(slug: str, body: ScriptCheckBody, state: State):
    """Kiểm khối JSON, trả khác biệt và cảnh báo. Không ghi gì."""
    base_hash, project = _read(_folder(state, slug))
    result = check_script(project, body.script, state.sensitive.load(), body.extra)
    return {**result.to_dict(), "base_hash": base_hash}


@router.post("/projects/{slug}/script/apply")
def apply(slug: str, body: ScriptApplyBody, state: State):
    folder = _folder(state, slug)
    _ensure_idle(state, slug, "áp JSON")
    base_hash, project = _read(folder)
    if base_hash != body.base_hash:
        raise Conflict("Project đã đổi sau lần kiểm, hãy kiểm lại")
    result = check_script(project, body.script, state.sensitive.load(), body.extra)
    if not result.ok or result.merged is None:
        return JSONResponse(
            {"detail": f"JSON có {len(result.errors)} lỗi, chưa áp", "errors": result.errors},
            status_code=422,
        )
    backup_id = create_backup(folder, "apply")
    state.storage.save(slug, result.merged)
    new_hash, saved = _read(folder)
    return {"project": saved.model_dump(mode="json"), "backup_id": backup_id, "base_hash": new_hash}


@router.get("/projects/{slug}/backups")
def backups(slug: str, state: State):
    return list_backups(_folder(state, slug))


@router.post("/projects/{slug}/backups/{backup_id}/restore")
def restore(slug: str, backup_id: str, state: State):
    folder = _folder(state, slug)
    check_backup_id(backup_id)
    _ensure_idle(state, slug, "khôi phục")
    data = read_backup(folder, backup_id)  # đọc trước: bản sao lưu mới có thể dọn bản này
    try:
        restored = Project.model_validate(json.loads(data))
    except (ValueError, ValidationError) as e:
        raise Unprocessable(f"Bản sao lưu không hợp lệ: {e}") from e
    if restored.slug != slug:
        raise Unprocessable("Bản sao lưu thuộc project khác")
    new_backup = create_backup(folder, "restore")  # sao lưu bản hiện tại trước khi ghi đè
    write_project_bytes(folder, data)
    new_hash, project = _read(folder)
    return {
        "project": project.model_dump(mode="json"),
        "backup_id": new_backup,
        "base_hash": new_hash,
    }
