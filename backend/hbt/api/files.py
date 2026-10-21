"""GET /api/files/{path}: phục vụ file trong workspace (chặn `..`, hỗ trợ Range cho video)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from hbt.api.deps import State
from hbt.storage import NotFound

router = APIRouter(tags=["files"])


def resolve_in_workspace(root: Path, rel: str) -> Path:
    """Đường dẫn tuyệt đối của `rel` bên trong `root`; NotFound nếu thoát ra ngoài hoặc không có.

    Chặn `..`, đường dẫn tuyệt đối, ký tự `\\` và mọi thư mục ẩn (bắt đầu bằng dấu chấm)."""
    parts = Path(rel.replace("\\", "/")).parts
    if not parts or any(p in ("..", "/") or p.startswith(".") or ":" in p for p in parts):
        raise NotFound("Không có file")
    base = root.resolve()
    target = (base / Path(*parts)).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise NotFound("Không có file")
    return target


@router.get("/files/{path:path}")
def get_file(path: str, state: State) -> FileResponse:
    target = resolve_in_workspace(state.settings.workspace_dir, path)
    return FileResponse(target, headers={"Cache-Control": "no-cache"})
