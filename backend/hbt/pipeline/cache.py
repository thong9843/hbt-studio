"""Cache theo hash trong `build/` (IMPLEMENT.md mục 4).

Bước nào có đầu ra khớp hash đầu vào thì bỏ qua."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_file_digests: dict[tuple[str, int, int], str] = {}


def file_digest(path: str | Path) -> str:
    """SHA-1 nội dung file (nhớ tạm theo đường dẫn + kích thước + thời điểm sửa)."""
    p = Path(path)
    st = p.stat()
    memo = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    if memo not in _file_digests:
        h = hashlib.sha1()
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        _file_digests[memo] = h.hexdigest()
    return _file_digests[memo]


def digest(*parts: Any) -> str:
    """Hash của các tham số đầu vào. `Path` được thay bằng hash nội dung file; còn lại dùng JSON."""

    def norm(x: Any) -> Any:
        if isinstance(x, Path):
            return file_digest(x)
        if isinstance(x, (list, tuple)):
            return [norm(i) for i in x]
        if isinstance(x, dict):
            return {str(k): norm(v) for k, v in sorted(x.items())}
        return x

    payload = json.dumps(norm(list(parts)), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def code_digest(*modules: Any) -> str:
    """Hash mã nguồn của các module: đổi thuật toán thì cache cũ tự mất hiệu lực."""
    h = hashlib.sha1()
    for m in modules:
        h.update(Path(m.__file__).read_bytes())
    return h.hexdigest()[:12]


def _key_file(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + ".key")


def is_fresh(artifact: Path, key: str) -> bool:
    kf = _key_file(artifact)
    return artifact.exists() and kf.exists() and kf.read_text(encoding="utf-8").strip() == key


def mark(artifact: Path, key: str) -> None:
    _key_file(artifact).write_text(key, encoding="utf-8")


def publish_atomic(tmp: Path, final: Path) -> None:
    """Đổi tên file tạm thành file thật (tránh để lại file dở nếu bị ngắt giữa chừng)."""
    os.replace(tmp, final)
