"""Kiểm tra kịch bản PostV: ước thời lượng và từ nhạy cảm (IMPLEMENT-POSTV.md mục 6b, K-39).

Chỉ **nhắc**, không chặn. Không còn nhắc commentary, tỉ lệ biến đổi hay đọc nguyên văn (K-39).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from hbt.pipeline.textmatch import compile_words, find_hits
from hbt.postv.censor import CensorMatcher, find_censor_hits
from hbt.postv.models import PostvProject
from hbt.sensitive import SensitiveWords

READ_CPS = 16.5  # ký tự/giây của giọng VieNeu trên máy cũ (đo PV0: 16,5–18)
LONG_SECONDS = 120.0  # từ mức này trở lên chỉ nhắc (video dưới 2 phút)


@dataclass
class Issue:
    where: str  # "Đoạn 3", "Bài gốc", "Bình luận c2", "Lời dẫn đăng"
    level: str  # "info" | "warn"
    message: str
    word: str | None = None


def voice_chars(text: str) -> int:
    return len(" ".join(text.split()))


def estimate_seconds(chars: int) -> float:
    return round(chars / READ_CPS, 1)


def _where_texts(project: PostvProject) -> list[tuple[str, str]]:
    texts = [("Bài gốc", project.post.text)]
    texts += [(f"Bình luận {c.id}", c.text) for c in project.comments if c.picked]
    texts += [(f"Đoạn {i}", s.voice) for i, s in enumerate(project.segments, 1)]
    texts.append(("Lời dẫn đăng", project.publish.hook))
    return [(w, t) for w, t in texts if t.strip()]


def check_script(
    project: PostvProject,
    censor: list[CensorMatcher],
    hbt_words: SensitiveWords | None = None,
) -> dict:
    segments = []
    total_chars = 0
    for i, seg in enumerate(project.segments, 1):
        chars = voice_chars(seg.voice)
        total_chars += chars
        segments.append(
            {"index": i, "role": seg.role, "chars": chars, "seconds": estimate_seconds(chars)}
        )
    seconds = estimate_seconds(total_chars)

    issues: list[Issue] = []
    if seconds >= LONG_SECONDS:
        issues.append(
            Issue(
                "Cả video",
                "warn",
                f"Video dự kiến dài {seconds:g} s, nên dưới {LONG_SECONDS:g} s (2 phút).",
            )
        )

    censored = 0
    enabled = project.settings.censor.enabled
    for where, text in _where_texts(project):
        for hit in find_censor_hits(text, censor):
            if enabled:
                censored += 1
                issues.append(
                    Issue(where, "info", f'Từ "{hit.word}" sẽ bị che (bíp + làm mờ).', hit.word)
                )
            else:
                issues.append(
                    Issue(where, "warn", f'Từ "{hit.word}" nhạy cảm nhưng chưa bật che.', hit.word)
                )
    if hbt_words is not None:  # mức cảnh báo/thông tin của danh sách HBT: chỉ nhắc, không che
        matchers = [m for m in compile_words(hbt_words) if m.level != "block"]
        for where, text in _where_texts(project):
            for m in find_hits(text, matchers):
                issues.append(
                    Issue(where, "warn", f'Có từ nhạy cảm "{m.word}" (chỉ nhắc).', m.word)
                )

    return {
        "seconds": seconds,
        "chars": total_chars,
        "long": seconds >= LONG_SECONDS,
        "censored": censored,
        "segments": segments,
        "issues": [asdict(i) for i in issues],
    }
