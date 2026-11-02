"""Cảnh báo K16–K18 của JSON nháp (IMPLEMENT-GD2 mục 3). Không chặn tạo dự án."""

from __future__ import annotations

import re
from typing import Any

from hbt.script import _issue

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
BRACES = re.compile(r"\{[^{}]*\}")
FORBIDDEN = re.compile(r"(?<!\w)(vietnam map|text|chữ|map|bản đồ)(?!\w)", re.IGNORECASE)
NEGATIVE_PROMPT = "no text, no letters, no signs, no map, no Vietnam map"


def numbers_of(text: str) -> set[str]:
    """Các số trong `text`, bỏ dấu phân cách ('27,6' và '1.000' → '276', '1000')."""
    return {re.sub(r"[.,]", "", m) for m in NUMBER.findall(text)}


def spoken_numbers(voice: str) -> list[str]:
    """Số trong lời đọc theo thứ tự, bỏ phần `{cách đọc}`."""
    return [re.sub(r"[.,]", "", m) for m in NUMBER.findall(BRACES.sub("", voice))]


def check_sources_for_numbers(voices: list[str], sources: list[dict]) -> list[dict]:
    """K16: số trong lời đọc không xuất hiện trong `claim` của bất kỳ nguồn nào."""
    known: set[str] = set()
    for s in sources:
        known |= numbers_of(s.get("claim", ""))
    out: list[dict] = []
    for i, voice in enumerate(voices):
        for num in dict.fromkeys(spoken_numbers(voice)):
            if num not in known:
                out.append(
                    _issue(
                        "K16",
                        f"scenes[{i}].voice",
                        f"Cảnh {i + 1}: số {num} chưa có nguồn trong sources[].claim",
                        i,
                    )
                )
    return out


def check_prompts(prompts: list[Any]) -> tuple[list[dict], list[bool]]:
    """K17 (từ cấm) và K18 (thiếu / rỗng). Trả (cảnh báo, `image_prompt_ok` từng cảnh)."""
    out: list[dict] = []
    ok: list[bool] = []
    for i, p in enumerate(prompts):
        if not isinstance(p, str) or not p.strip():
            out.append(
                _issue(
                    "K18",
                    f"scenes[{i}].image_prompt",
                    f"Cảnh {i + 1}: thiếu image_prompt, cảnh này đi đường tay",
                    i,
                )
            )
            ok.append(False)
            continue
        ok.append(True)
        words = list(dict.fromkeys(m.group(1).lower() for m in FORBIDDEN.finditer(p)))
        if words:
            out.append(
                _issue(
                    "K17",
                    f"scenes[{i}].image_prompt",
                    f"Cảnh {i + 1}: image_prompt có từ cấm: {', '.join(words)}",
                    i,
                )
            )
    return out, ok


def full_prompt(prompt: str) -> str:
    """Prompt gửi trình tạo ảnh: nối phần phủ định (không lưu vào `image_prompt`)."""
    return f"{prompt.strip().rstrip('.,')}. {NEGATIVE_PROMPT}"
