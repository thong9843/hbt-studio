"""Chuyển media giữa hai máy (`python -m cli pack-media` / `unpack-media`).

Chỉ dùng `zipfile` + `hashlib` của Python, không mạng. `pack` gói thư viện nền, thư viện nhạc, mô
hình giọng VieNeu và dự án mẫu thành các file zip cùng `manifest.json` (sha256 từng file). `unpack`
kiểm sha256 từng file trước khi ghi, không ghi đè file git đang theo dõi (riêng `index.json` của
thư viện chỉ chép khi có `with_index`) và không bao giờ ghi ra ngoài thư mục gốc repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MANIFEST = "manifest.json"
INDEX_NAME = "index.json"
SKIP_SUFFIXES = (".lock", ".incomplete", ".part", ".pyc")
CHUNK = 1024 * 1024

# nhóm → (thư mục con của repo, chỉ lấy file ngay trong thư mục đó?)
GROUPS: dict[str, tuple[str, bool]] = {
    "backgrounds": ("library/backgrounds", True),
    "music": ("library/music", True),
    "stickers": ("library/stickers", False),
    "hf_vieneu": ("models/hf_vieneu", False),
    "samples": ("workspace/samples", False),
}
ALLOWED_PREFIXES = tuple(f"{rel}/" for rel, _ in GROUPS.values())


class TransferError(Exception):
    pass


@dataclass
class UnpackReport:
    written: list[str] = field(default_factory=list)
    same: list[str] = field(default_factory=list)  # đã có, sha256 trùng
    protected: list[str] = field(default_factory=list)  # file git đang theo dõi
    differs: list[str] = field(default_factory=list)  # đã có nhưng khác, chưa có `force`


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _files(root: Path, rel: str, flat: bool) -> list[Path]:
    base = root / rel
    if not base.is_dir():
        return []
    it: Iterable[Path] = base.glob("*") if flat else base.rglob("*")
    return sorted(
        p
        for p in it
        if p.is_file() and not p.name.endswith(SKIP_SUFFIXES) and "__pycache__" not in p.parts
    )


def plan_pack(root: Path, groups: Iterable[str] | None = None) -> dict[str, list[Path]]:
    names = list(groups) if groups else list(GROUPS)
    unknown = [g for g in names if g not in GROUPS]
    if unknown:
        raise TransferError(f"Nhóm không có: {', '.join(unknown)} (có: {', '.join(GROUPS)})")
    return {g: _files(root, *GROUPS[g]) for g in names}


def pack(
    root: Path,
    out_dir: Path,
    groups: Iterable[str] | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> dict:
    """Ghi `<nhóm>.zip` và `manifest.json` vào `out_dir`; trả về manifest. Không nén lại (media và
    trọng số vốn đã nén) nên nhanh và zip xấp xỉ tổng kích thước."""
    plan = plan_pack(root, groups)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"version": 1, "groups": {}}
    for group, files in plan.items():
        if not files:
            log(f"{group}: không có file, bỏ qua")
            continue
        zip_path = out_dir / f"{group}.zip"
        entries = []
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for p in files:
                rel = p.relative_to(root).as_posix()
                h = hashlib.sha256()
                info = zipfile.ZipInfo.from_file(p, rel, strict_timestamps=False)
                info.compress_type = zipfile.ZIP_STORED
                with p.open("rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                    while chunk := src.read(CHUNK):
                        h.update(chunk)
                        dst.write(chunk)
                entries.append({"path": rel, "size": p.stat().st_size, "sha256": h.hexdigest()})
        manifest["groups"][group] = {"zip": zip_path.name, "files": entries}
        size_mb = zip_path.stat().st_size / 1e6
        log(f"{group}: {len(entries)} file → {zip_path.name} ({size_mb:.1f} MB)")
    (out_dir / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _safe_target(root: Path, rel: str) -> Path:
    """Đường dẫn trong manifest phải tương đối, nằm trong các thư mục media đã biết."""
    posix = PurePosixPath(rel)
    if posix.is_absolute() or ".." in posix.parts or "\\" in rel or ":" in rel:
        raise TransferError(f"Đường dẫn không an toàn trong manifest: {rel}")
    if not rel.startswith(ALLOWED_PREFIXES):
        raise TransferError(f"Đường dẫn ngoài thư mục media cho phép: {rel}")
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise TransferError(f"Đường dẫn ra ngoài repo: {rel}")
    return target


def unpack(
    root: Path,
    src_dir: Path,
    *,
    tracked: set[str],
    with_index: bool = False,
    force: bool = False,
    groups: Iterable[str] | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> UnpackReport:
    """Chép từ `src_dir` vào `root`. `tracked`: đường dẫn (posix, tương đối) git đang theo dõi.
    Mỗi file được ghi ra `.part`, kiểm sha256 rồi mới đổi tên; sai sha256 thì dừng và báo lỗi."""
    try:
        manifest = json.loads((src_dir / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise TransferError(f"Không đọc được {src_dir / MANIFEST}: {e}") from e
    wanted = set(groups) if groups else None
    report = UnpackReport()
    for group, info in manifest.get("groups", {}).items():
        if wanted is not None and group not in wanted:
            continue
        zip_path = src_dir / info["zip"]
        if zip_path.name != info["zip"] or not zip_path.is_file():
            raise TransferError(f"Thiếu file {info['zip']} cạnh manifest")
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            for entry in info["files"]:
                rel, want = entry["path"], entry["sha256"]
                target = _safe_target(root, rel)
                if rel not in names:
                    raise TransferError(f"{info['zip']} thiếu {rel}")
                is_index = PurePosixPath(rel).name == INDEX_NAME
                if rel in tracked and not (is_index and with_index):
                    report.protected.append(rel)
                    continue
                if target.is_file() and rel not in tracked:
                    if sha256_of(target) == want:
                        report.same.append(rel)
                        continue
                    if not force:
                        report.differs.append(rel)
                        continue
                target.parent.mkdir(parents=True, exist_ok=True)
                part = target.with_name(target.name + ".part")
                h = hashlib.sha256()
                try:
                    with zf.open(rel) as s, part.open("wb") as d:
                        while chunk := s.read(CHUNK):
                            h.update(chunk)
                            d.write(chunk)
                    if h.hexdigest() != want:
                        raise TransferError(f"Sai sha256: {rel} (file zip hỏng hoặc bị sửa)")
                    os.replace(part, target)
                finally:
                    part.unlink(missing_ok=True)
                report.written.append(rel)
        log(f"{group}: xong")
    return report
