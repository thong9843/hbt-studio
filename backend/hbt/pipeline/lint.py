"""Kiểm tra nội dung trước khi xuất.

M1 chỉ có quy tắc độ dài lời đọc (IMPLEMENT.md 4d). Từ nhạy cảm (mục 7) làm ở M4:
`lint_project` là chỗ để gắn thêm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from hbt.models import Project

VOICE_CHAR_LIMIT = 750  # gói Vbee giới hạn 3.000 ký tự/ngày

Level = Literal["info", "warn", "block"]


@dataclass(frozen=True)
class LintIssue:
    scene_index: int | None  # chỉ số cảnh từ 0; None nếu áp dụng cho cả video
    field: str
    category: str
    level: Level
    message: str
    word: str | None = None
    hint: str = ""


def voice_text(text: str) -> str:
    """Lời đọc dạng gửi cho Vbee: bỏ ký hiệu `|` `{` `}`, gộp khoảng trắng."""
    return re.sub(r"\s+", " ", re.sub(r"[|{}]", "", text)).strip()


def voice_char_count(project: Project) -> int:
    """Tổng ký tự lời đọc của video (tính cả dấu cách; các cảnh nối bằng một dấu cách)."""
    return len(" ".join(voice_text(s.voice) for s in project.scenes))


def lint_project(project: Project) -> list[LintIssue]:
    issues: list[LintIssue] = []
    count = voice_char_count(project)
    if count > VOICE_CHAR_LIMIT:
        issues.append(
            LintIssue(
                scene_index=None,
                field="voice",
                category="voice_length",
                level="warn",
                message=f"Lời đọc dài {count} ký tự, vượt giới hạn {VOICE_CHAR_LIMIT}.",
                hint="Gói Vbee giới hạn 3.000 ký tự mỗi ngày.",
            )
        )
    return issues
