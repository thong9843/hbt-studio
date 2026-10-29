"""Danh sách từ che của PostV (K-27, K-29, K-41).

Riêng với danh sách nhạy cảm của HBT để video HBT không đổi hành vi. Từ che = mọi từ mức `block`
của danh sách HBT (chỉ đọc) + danh sách riêng của PostV. So khớp **có dấu**, không phân biệt hoa
thường, theo ranh giới từ ("đéo" không trùng "đeo"), khác `textmatch.fold` của HBT.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from hbt.sensitive import SensitiveWords

DEFAULT_FILE = Path(__file__).parent / "data" / "censor_words.json"


class CensorStore:
    """Danh sách riêng của PostV: bản mặc định trên Git, bản người dùng sửa ở workspace."""

    def __init__(self, workspace_dir: Path):
        self.user_file = Path(workspace_dir) / "settings" / "postv_censor_words.json"

    def load(self) -> SensitiveWords:
        path = self.user_file if self.user_file.is_file() else DEFAULT_FILE
        return SensitiveWords.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, words: SensitiveWords) -> SensitiveWords:
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.user_file.with_name(self.user_file.name + ".tmp")
        tmp.write_text(
            json.dumps(words.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp, self.user_file)
        return words


@dataclass(frozen=True)
class CensorMatcher:
    word: str
    category: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class CensorHit:
    word: str
    category: str
    start: int  # vị trí trong chữ đã chuẩn hoá (`normalize`)
    end: int


def normalize(text: str) -> str:
    """NFC + chữ thường. Độ dài giữ nguyên với tiếng Việt thường gặp nên vị trí dùng được."""
    return unicodedata.normalize("NFC", text).casefold()


def compile_censor(
    *lists: SensitiveWords, levels: tuple[str, ...] = ("block",)
) -> list[CensorMatcher]:
    """Ghép các danh sách, chỉ lấy nhóm có mức trong `levels` (mặc định chỉ mức chặn, K-29)."""
    out: list[CensorMatcher] = []
    seen: set[str] = set()
    for words in lists:
        for cat in words.categories:
            if cat.level not in levels:
                continue
            for word in cat.words:
                norm = normalize(word).strip()
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                body = r"\s+".join(re.escape(part) for part in norm.split())
                out.append(CensorMatcher(word, cat.id, re.compile(r"(?<!\w)" + body + r"(?!\w)")))
    return out


def find_censor_hits(text: str, matchers: list[CensorMatcher]) -> list[CensorHit]:
    """Mọi chỗ xuất hiện của từ che, theo thứ tự trong văn bản."""
    norm = normalize(text)
    hits = [
        CensorHit(m.word, m.category, h.start(), h.end())
        for m in matchers
        for h in m.pattern.finditer(norm)
    ]
    return sorted(hits, key=lambda h: h.start)
