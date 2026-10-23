"""Kiểm tra nội dung trước khi xuất (IMPLEMENT.md mục 4d và 7).

`lint_project` gom: độ dài lời đọc (warn), từ nhạy cảm theo danh sách (mức của từng nhóm) và số
chưa ghi cách đọc (info). Từ nhạy cảm chỉ được kiểm khi truyền `words`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from hbt.models import Project
from hbt.pipeline.text import RAW_TOKEN_RE
from hbt.pipeline.textmatch import Matcher, compile_words, find_hits
from hbt.sensitive import SensitiveWords

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


NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _sensitive_issues(
    scene_index: int | None, field: str, label: str, text: str, matchers: list[Matcher]
) -> list[LintIssue]:
    return [
        LintIssue(
            scene_index=scene_index,
            field=field,
            category=m.category,
            level=m.level,  # type: ignore[arg-type]
            message=f'Có từ nhạy cảm "{m.word}" trong {label}.',
            word=m.word,
            hint=m.hint,
        )
        for m in find_hits(text, matchers)
    ]


def _unread_numbers(voice: str) -> list[str]:
    """Số trần trong lời đọc: token có chữ số mà không có `{cách đọc}` đi kèm."""
    found: list[str] = []
    for token in RAW_TOKEN_RE.findall(voice):
        if "{" in token:
            continue
        found += [n for n in NUMBER_RE.findall(token) if n not in found]
    return found


def describe_issue(issue: LintIssue) -> str:
    """Một dòng cho người dùng: "Cảnh 2: Có từ nhạy cảm …" hoặc "Cả video: …"."""
    where = f"Cảnh {issue.scene_index + 1}" if issue.scene_index is not None else "Cả video"
    return f"{where}: {issue.message}"


def lint_project(project: Project, words: SensitiveWords | None = None) -> list[LintIssue]:
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
    matchers = compile_words(words) if words is not None else []
    for i, scene in enumerate(project.scenes):
        if matchers:
            card = "\n".join(line.text for line in scene.card.lines)
            issues += _sensitive_issues(i, "card.lines", "thẻ chữ", card, matchers)
            labels = "\n".join(label.text for label in scene.labels)
            issues += _sensitive_issues(i, "labels", "nhãn", labels, matchers)
            # Quét cả chữ hiển thị lẫn chữ đọc trong {…}; `|` `{}` thành dấu cách.
            spoken = re.sub(r"[|{}]", " ", scene.voice)
            issues += _sensitive_issues(i, "voice", "lời đọc", spoken, matchers)
        numbers = _unread_numbers(scene.voice)
        if numbers:  # một dòng cho mỗi cảnh, liệt kê các số
            listed = ", ".join(numbers)
            issues.append(
                LintIssue(
                    scene_index=i,
                    field="voice",
                    category="number_reading",
                    level="info",
                    message=f"Số chưa ghi cách đọc: {listed}.",
                    word=listed,
                    hint="Viết số{cách đọc}, ví dụ 100{một trăm}.",
                )
            )
    if matchers:
        hook = project.publish.hook
        issues += _sensitive_issues(None, "publish.hook", "lời dẫn đăng", hook, matchers)
        if project.thumbnail:
            thumb = "\n".join(project.thumbnail.lines)
            issues += _sensitive_issues(None, "thumbnail.lines", "dòng chữ bìa", thumb, matchers)
    return issues
