"""Thư viện nhạc `library/music/index.json` (IMPLEMENT.md mục 6.2)."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from hbt.storage import (
    AUDIO_EXTENSIONS,
    BadRequest,
    NotFound,
    Unprocessable,
    _audio_extension,
    slugify,
)

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class MusicEntry(BaseModel):
    file: str  # đường dẫn tương đối so với library/music/
    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: str = ""
    license: str = Field(min_length=1)
    moods: list[str] = Field(default_factory=list)
    bpm: int | None = Field(default=None, ge=30, le=300)

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

    def list(self) -> list[MusicEntry]:
        if not self.index_path.is_file():
            return []
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            return [MusicEntry.model_validate(e) for e in raw]
        except (json.JSONDecodeError, ValueError) as e:
            raise BadRequest(f"library/music/index.json không hợp lệ: {e}") from e

    def find(self, file: str) -> tuple[MusicEntry, Path]:
        """Bài trong thư viện theo tên file. Chỉ nhận tên nằm trong thư mục thư viện;
        chặn '/', '\\', '..', đường dẫn tuyệt đối; chỉ đuôi mp3/wav/m4a/ogg.
        """
        if not file or "/" in file or "\\" in file or ".." in file:
            raise Unprocessable("Tên file nhạc không hợp lệ")
        p = Path(file)
        if p.is_absolute() or re.match(r"^[A-Za-z]:", file) or file.startswith(("/", "\\")):
            raise Unprocessable("Tên file nhạc không hợp lệ: không được là đường dẫn tuyệt đối")
        ext = p.suffix.lower()
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS))
            raise Unprocessable(f"Đuôi file nhạc không hợp lệ: chỉ chấp nhận {allowed}")
        if not SAFE_NAME.match(file):
            raise Unprocessable("Tên file nhạc không hợp lệ")
        target = (self.root / file).resolve()
        if not target.is_relative_to(self.root.resolve()) or target.parent != self.root.resolve():
            raise Unprocessable("Tên file nhạc không hợp lệ")
        entry = next((e for e in self.list() if e.file == file), None)
        if entry is None or not target.is_file():
            raise NotFound(f"Không có bài '{file}' trong thư viện nhạc")
        return entry, target

    def add(self, src: Path, filename: str, meta: dict) -> MusicEntry:
        """Thêm một bài: kiểm tra âm thanh, đặt file vào thư viện và ghi vào index."""
        try:  # kiểm tra thông tin ghi công trước khi động tới file
            MusicEntry.model_validate({**meta, "file": "x"})
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
        entry = MusicEntry.model_validate({**meta, "file": name})
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.move(src, self.root / name)
        tmp = self.index_path.with_name("index.json.tmp")
        data = [e.model_dump() for e in [*entries, entry]]
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.index_path)
        return entry


__all__ = ["AUDIO_EXTENSIONS", "MusicEntry", "MusicLibrary"]
