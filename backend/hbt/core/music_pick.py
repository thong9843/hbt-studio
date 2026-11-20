"""Chọn nhạc theo `music_mood` (E5). Chỉ ĐỌC `library/music/index.json`, không bao giờ ghi:
`MusicLibrary.list()` tự gán id và ghi lại index nên không dùng ở đây."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from hbt.library import ID_PATTERN, MusicEntry


def norm_mood(text: str) -> str:
    """Chữ thường, bỏ dấu, gọn khoảng trắng: 'Tò mò' → 'to mo'."""
    s = text.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " ".join(s.split())


@dataclass
class MusicPick:
    entry: MusicEntry | None = None
    path: Path | None = None
    warning: str | None = None


def pick_music(library_dir: Path, mood: str) -> MusicPick:
    if not mood.strip():
        return MusicPick()
    index = library_dir / "index.json"
    if not index.is_file():
        return MusicPick()
    try:
        raw = json.loads(index.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not all(isinstance(e, dict) for e in raw):
            raise ValueError("phải là một danh sách các bài")
    except (OSError, ValueError) as e:
        return MusicPick(warning=f"Không đọc được thư viện nhạc ({e}), để trống nhạc")
    if any(not isinstance(e.get("id"), str) or not ID_PATTERN.match(e["id"]) for e in raw):
        return MusicPick(
            warning="library/music/index.json có bài thiếu id, mở trang Nhạc để gán; để trống nhạc"
        )
    want = norm_mood(mood)
    root = library_dir.resolve()
    for item in raw:
        moods = item.get("moods")
        if not isinstance(moods, list) or want not in {
            norm_mood(m) for m in moods if isinstance(m, str)
        }:
            continue
        try:
            entry = MusicEntry.model_validate(item)
        except ValueError:
            continue
        target = (root / entry.file).resolve()
        if target.is_relative_to(root) and target.is_file():
            return MusicPick(entry=entry, path=target)
    return MusicPick()
