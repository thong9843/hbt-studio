"""Sao lưu `project.json` trước khi áp JSON kịch bản hoặc khôi phục (IMPLEMENT.md 13.B4.7).

`workspace/projects/<slug>/backups/project-YYYYMMDD-HHMMSS[-n].json` kèm một file phụ cùng tên
`….meta.json` ghi `{reason, created_at}`. Giữ 10 bản mới nhất (xoá cả cặp). `id` là phần giữa
`project-` và `.json`, chỉ gồm `[0-9-]` đúng dạng nên không thể chứa đường dẫn.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from hbt.storage import NotFound, Unprocessable

log = logging.getLogger(__name__)

BACKUP_DIR = "backups"
BACKUP_KEEP = 10
ID_RE = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?$")
_FILE_RE = re.compile(r"^project-(\d{8}-\d{6}(?:-\d+)?)\.json$")
Reason = Literal["apply", "restore"]


def check_backup_id(backup_id: str) -> str:
    """Trả về `backup_id` nếu đúng dạng `YYYYMMDD-HHMMSS[-n]`; không thì Unprocessable (422)."""
    if not ID_RE.fullmatch(backup_id):
        raise Unprocessable("Mã bản sao lưu không hợp lệ")
    return backup_id


def _sort_key(backup_id: str) -> tuple[str, int]:
    m = ID_RE.fullmatch(backup_id)
    return (m.group(1), int(m.group(2) or 0)) if m else ("", 0)


def _file(folder: Path, backup_id: str) -> Path:
    return folder / BACKUP_DIR / f"project-{backup_id}.json"


def _meta(folder: Path, backup_id: str) -> Path:
    return folder / BACKUP_DIR / f"project-{backup_id}.meta.json"


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _ids(folder: Path) -> list[str]:
    """Mã các bản sao lưu, mới nhất trước."""
    backups = folder / BACKUP_DIR
    if not backups.is_dir():
        return []
    found = [m.group(1) for f in backups.iterdir() if f.is_file() and (m := _FILE_RE.match(f.name))]
    return sorted(found, key=_sort_key, reverse=True)


def create_backup(folder: Path, reason: Reason, now: datetime | None = None) -> str:
    """Chép nguyên byte `project.json` hiện tại vào `backups/`, ghi file phụ, dọn bản cũ."""
    source = folder / "project.json"
    if not source.is_file():
        raise NotFound("Project chưa có project.json để sao lưu")
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    (folder / BACKUP_DIR).mkdir(exist_ok=True)
    backup_id, n = stamp, 0
    while _file(folder, backup_id).exists():
        n += 1
        backup_id = f"{stamp}-{n}"
    _write_atomic(_file(folder, backup_id), source.read_bytes())
    meta = {"reason": reason, "created_at": now.isoformat().replace("+00:00", "Z")}
    _write_atomic(_meta(folder, backup_id), json.dumps(meta, ensure_ascii=False).encode("utf-8"))
    _prune(folder)
    return backup_id


def _prune(folder: Path) -> None:
    for old in _ids(folder)[BACKUP_KEEP:]:
        for path in (_file(folder, old), _meta(folder, old)):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("Không xoá được bản sao lưu cũ %s", path)


def _created_at(folder: Path, backup_id: str) -> tuple[str, str | None]:
    """(created_at, reason) từ file phụ; thiếu hoặc hỏng thì lấy giờ sửa file, reason = None."""
    try:
        meta = json.loads(_meta(folder, backup_id).read_text(encoding="utf-8"))
        created, reason = meta.get("created_at"), meta.get("reason")
        if isinstance(created, str):
            return created, reason if isinstance(reason, str) else None
    except (OSError, ValueError):
        pass
    mtime = _file(folder, backup_id).stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=UTC).isoformat().replace("+00:00", "Z"), None


def list_backups(folder: Path) -> list[dict]:
    """`[{id, created_at, reason}]`, mới nhất trước, tối đa `BACKUP_KEEP`."""
    out = []
    for backup_id in _ids(folder)[:BACKUP_KEEP]:
        created, reason = _created_at(folder, backup_id)
        out.append({"id": backup_id, "created_at": created, "reason": reason})
    return out


def read_backup(folder: Path, backup_id: str) -> bytes:
    """Nội dung bản sao lưu; 422 nếu `backup_id` sai dạng, 404 nếu không có."""
    check_backup_id(backup_id)
    path = _file(folder, backup_id)
    if not path.is_file():
        raise NotFound(f"Không có bản sao lưu '{backup_id}'")
    return path.read_bytes()


def write_project_bytes(folder: Path, data: bytes) -> None:
    """Ghi đè `project.json` bằng đúng các byte này (qua file tạm rồi `os.replace`)."""
    _write_atomic(folder / "project.json", data)
