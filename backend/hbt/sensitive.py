"""Danh sách từ nhạy cảm (IMPLEMENT.md mục 7). M2 chỉ lưu/đọc; bộ kiểm tra từ làm ở M4.

Bản mặc định nằm trong `hbt/data/sensitive_words.json` (nằm trên Git). Khi người dùng sửa danh sách,
bản của họ được lưu ở `workspace/settings/sensitive_words.json` và được ưu tiên.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_FILE = Path(__file__).parent / "data" / "sensitive_words.json"
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class Category(BaseModel):
    id: str
    level: Literal["info", "warn", "block"]
    words: list[str] = Field(default_factory=list)
    hint: str = ""

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("id chỉ gồm chữ thường, số, dấu gạch dưới và bắt đầu bằng chữ")
        return v

    @field_validator("words")
    @classmethod
    def _words(cls, v: list[str]) -> list[str]:
        cleaned = [w.strip() for w in v]
        if any(not w for w in cleaned):
            raise ValueError("Từ trong danh sách không được để trống")
        return cleaned


class SensitiveWords(BaseModel):
    categories: list[Category]

    @model_validator(mode="after")
    def _unique_ids(self) -> SensitiveWords:
        ids = [c.id for c in self.categories]
        if len(ids) != len(set(ids)):
            raise ValueError("id nhóm bị trùng")
        return self


class SensitiveStore:
    def __init__(self, workspace_dir: Path):
        self.user_file = Path(workspace_dir) / "settings" / "sensitive_words.json"

    def load(self) -> SensitiveWords:
        path = self.user_file if self.user_file.is_file() else DEFAULT_FILE
        return SensitiveWords.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, words: SensitiveWords) -> SensitiveWords:
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.user_file.with_name(self.user_file.name + ".tmp")
        text = json.dumps(words.model_dump(), ensure_ascii=False, indent=2)
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, self.user_file)
        return words
