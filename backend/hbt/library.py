"""Thư viện nhạc `library/music/index.json` (IMPLEMENT.md mục 6.2)."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from hbt.storage import (
    AUDIO_EXTENSIONS,
    BadRequest,
    NotFound,
    Unprocessable,
    _audio_extension,
    slugify,
)

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _unique_id(base: str, used: set[str]) -> str:
    """`base`, nếu trùng thì `base-2`, `base-3`…"""
    candidate, n = base, 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _check_relative_file(file: str) -> str:
    """`file` phải là đường dẫn tương đối trong library/music/ (cho thư mục con, dấu '/')."""
    if not file or "\\" in file or file.startswith("/") or re.match(r"^[A-Za-z]:", file):
        raise ValueError("phải là đường dẫn tương đối trong library/music/, dùng dấu '/'")
    parts = file.split("/")
    if any(part in ("", ".", "..") or not SAFE_SEGMENT.match(part) for part in parts):
        raise ValueError("đường dẫn không hợp lệ (không '..', không ký tự lạ)")
    if Path(file).suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError("đuôi file nhạc không hợp lệ: " + ", ".join(sorted(AUDIO_EXTENSIONS)))
    return file


class MusicEntry(BaseModel):
    id: str  # slug từ tiêu đề, tạo một lần, không đổi
    file: str  # đường dẫn tương đối so với library/music/
    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: str = ""
    license: str = Field(min_length=1)
    moods: list[str] = Field(default_factory=list)
    bpm: int | None = Field(default=None, ge=30, le=300)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not ID_PATTERN.match(v):
            raise ValueError("id chỉ gồm chữ thường, số và dấu '-'")
        return v

    @field_validator("file")
    @classmethod
    def _valid_file(cls, v: str) -> str:
        return _check_relative_file(v)

    @property
    def credit(self) -> str:
        """Dòng ghi công, ví dụ "The Wacky Sprint – nkbloom (Pixabay)"."""
        return f"{self.title} – {self.artist} ({self.source})"


class MusicLibrary:
    def __init__(self, library_dir: Path):
        self.root = Path(library_dir) / "music"

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def _write(self, entries: list[MusicEntry]) -> None:
        tmp = self.index_path.with_name("index.json.tmp")
        data = [e.model_dump() for e in entries]
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.index_path)

    def list(self) -> list[MusicEntry]:
        """Đọc index. Bài thiếu `id` được gán id từ tiêu đề (theo thứ tự), ghi lại một lần."""
        if not self.index_path.is_file():
            return []
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or not all(isinstance(e, dict) for e in raw):
                raise ValueError("phải là một danh sách các bài")
            used = {e["id"] for e in raw if isinstance(e.get("id"), str)}
            assigned = False
            for item in raw:
                if "id" not in item:
                    title = item.get("title")
                    base = slugify(title) if isinstance(title, str) else "bai-nhac"
                    item["id"] = _unique_id(base, used)
                    used.add(item["id"])
                    assigned = True
            entries = [MusicEntry.model_validate(e) for e in raw]
            ids = [e.id for e in entries]
            if len(set(ids)) != len(ids):
                raise ValueError("có id bị trùng")
        except (json.JSONDecodeError, ValueError) as e:
            raise BadRequest(f"library/music/index.json không hợp lệ: {e}") from e
        if assigned:
            self._write(entries)
        return entries

    def find(self, music_id: str) -> tuple[MusicEntry, Path]:
        """Bài trong thư viện theo id: id sai định dạng → 422, không có → 404."""
        if not ID_PATTERN.match(music_id):
            raise Unprocessable("Id bài nhạc không hợp lệ")
        entry = next((e for e in self.list() if e.id == music_id), None)
        if entry is None:
            raise NotFound(f"Không có bài '{music_id}' trong thư viện nhạc")
        root = self.root.resolve()
        target = (root / entry.file).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise NotFound(f"Không có file nhạc của bài '{music_id}' trong thư viện")
        return entry, target

    def add(self, src: Path, filename: str, meta: dict) -> MusicEntry:
        """Thêm một bài: kiểm tra âm thanh, đặt file vào thư viện và ghi vào index."""
        try:  # kiểm tra thông tin ghi công trước khi động tới file
            MusicEntry.model_validate({**meta, "id": "x", "file": "x.mp3"})
        except ValidationError as e:
            detail = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            raise BadRequest(f"Thông tin bài nhạc không hợp lệ: {detail}") from e
        ext = _audio_extension(src, filename)
        entries = self.list()
        stem = slugify(meta.get("title", "")) or "bai-nhac"
        name, n = f"{stem}.{ext}", 2
        while (self.root / name).exists() or any(e.file == name for e in entries):
            name = f"{stem}-{n}.{ext}"
            n += 1
        entry = MusicEntry.model_validate(
            {**meta, "id": _unique_id(stem, {e.id for e in entries}), "file": name}
        )
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.move(src, self.root / name)
        self._write([*entries, entry])
        return entry


__all__ = ["AUDIO_EXTENSIONS", "MusicEntry", "MusicLibrary"]
