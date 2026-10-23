"""So khớp từ nhạy cảm trong tiếng Việt (IMPLEMENT.md mục 7).

Quy tắc: chuẩn hoá NFC, không phân biệt hoa thường, khớp theo ranh giới từ, KHÔNG bỏ dấu
(nên "bia" không khớp "bìa"). Riêng dấu thanh ở cụm `oa`, `oe`, `uy` có hai cách đặt
("hoá"/"hóa", "tuý"/"túy", "thuỷ"/"thủy"): cả văn bản lẫn từ khoá được đưa về cách đặt dấu ở
nguyên âm thứ hai ("hoá", "tuý", "thuỷ") trước khi so.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from hbt.sensitive import SensitiveWords

TONES = frozenset("̣̀́̃̉")  # huyền, sắc, ngã, hỏi, nặng
TONE_PAIRS = {("o", "a"), ("o", "e"), ("u", "y")}
LETTERS = re.compile(r"[^\W\d_]+")


def _split_tone(ch: str) -> tuple[str, str]:
    decomposed = unicodedata.normalize("NFD", ch)
    tone = "".join(c for c in decomposed if c in TONES)
    base = unicodedata.normalize("NFC", "".join(c for c in decomposed if c not in TONES))
    return base, tone


def _canonical_tone_position(run: str) -> str:
    parts = [list(_split_tone(c)) for c in run]
    for i in range(len(parts) - 1):
        (b1, t1), (b2, t2) = parts[i], parts[i + 1]
        if (b1, b2) in TONE_PAIRS and t1 and not t2:
            parts[i][1], parts[i + 1][1] = "", t1
    return unicodedata.normalize("NFC", "".join(b + t for b, t in parts))


def fold(text: str) -> str:
    """Dạng so khớp: NFC, chữ thường, dấu thanh ở vị trí chuẩn, khoảng trắng gộp thành một."""
    text = unicodedata.normalize("NFC", text).lower()
    text = LETTERS.sub(lambda m: _canonical_tone_position(m.group()), text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Matcher:
    word: str  # đúng như trong danh sách của người dùng
    category: str
    level: str
    hint: str
    pattern: re.Pattern[str]


def compile_words(words: SensitiveWords) -> list[Matcher]:
    matchers = []
    for cat in words.categories:
        for word in cat.words:
            folded = fold(word)
            if not folded:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(folded) + r"(?!\w)")
            matchers.append(Matcher(word, cat.id, cat.level, cat.hint, pattern))
    return matchers


def find_hits(text: str, matchers: list[Matcher]) -> list[Matcher]:
    """Các từ khoá xuất hiện trong `text` (mỗi từ một lần, theo thứ tự trong danh sách)."""
    folded = fold(text)
    return [m for m in matchers if m.pattern.search(folded)]
