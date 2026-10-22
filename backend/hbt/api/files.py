"""GET /api/files/{path}: phục vụ file trong workspace (chặn `..`, hỗ trợ Range cho video)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from hbt.api.deps import State
from hbt.models import check_slug
from hbt.storage import NotFound, Unprocessable

router = APIRouter(tags=["files"])


def resolve_in_workspace(root: Path, rel: str) -> Path:
    """Đường dẫn tuyệt đối của `rel` bên trong `root`.

    Unprocessable (422) nếu đường dẫn sai: `..`, tuyệt đối, ổ đĩa, thư mục ẩn (bắt đầu bằng dấu
    chấm) hoặc `projects/<slug>` với slug không hợp lệ. NotFound (404) nếu hợp lệ mà không có."""
    parts = Path(rel.replace("\\", "/")).parts
    if not parts or any(p in ("..", "/") or p.startswith(".") or ":" in p for p in parts):
        raise Unprocessable("Đường dẫn file không hợp lệ")
    if parts[0] == "projects" and len(parts) > 1:
        try:
            check_slug(parts[1])
        except ValueError as e:
            raise Unprocessable(f"Slug không hợp lệ: {e}") from e
    base = root.resolve()
    target = (base / Path(*parts)).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise NotFound("Không có file")
    return target


@router.get("/files/{path:path}")
def get_file(path: str, state: State) -> FileResponse:
    target = resolve_in_workspace(state.settings.workspace_dir, path)
    return FileResponse(target, headers={"Cache-Control": "no-cache"})
