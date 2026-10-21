"""Thư viện nhạc `library/music/index.json` (IMPLEMENT.md mục 6.2)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from hbt.storage import AUDIO_EXTENSIONS, BadRequest, _audio_extension, slugify


class MusicEntry(BaseModel):
    file: str  # đường dẫn tương đối so với library/music/
    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: str = ""
    license: str = Field(min_length=1)
    moods: list[str] = Field(default_factory=list)
    bpm: int | None = Field(default=None, ge=30, le=300)


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

    def add(self, src: Path, filename: str, meta: dict) -> MusicEntry:
        """Thêm một bài: kiểm tra âm thanh, đặt file vào thư viện và ghi vào index."""
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
