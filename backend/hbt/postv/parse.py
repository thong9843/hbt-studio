"""Tách bài + bình luận từ chữ người dùng dán (IMPLEMENT-POSTV.md mục 5b).

Hàm thuần: không đọc mạng, không ghi đĩa, không chạy mã trong chữ dán. Dạng đã thấy (chữ copy từ
trang bài Threads): từng khối là `handle` / `tuổi hoặc ngày` / thân (1+ dòng). Khối đầu là bài gốc.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel

from hbt.postv.counts import parse_count

MAX_TEXT = 200_000
DEFAULT_PICKED = 3  # chưa biết like: tạm chọn 3 bình luận đầu

HANDLE = re.compile(r"^@?[A-Za-z0-9._]{1,30}$")
AGE = re.compile(r"^(\d{1,3})\s?(s|m|h|d|w|giây|phút|giờ|ngày|tuần)$", re.IGNORECASE)
DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
STAT_LINE = re.compile(r"^\d+(?:[.,]\d+)?\s?[KkMm]?$")
URL_LINE = re.compile(r"^https?://\S+$")
EMBED_URL = re.compile(r'data-text-post-permalink="([^"]+)"')
EMBED_BLOCK = re.compile(r"<blockquote\b.*?</blockquote>", re.IGNORECASE | re.DOTALL)
EMBED_SCRIPT = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
REPLY_TO = re.compile(r"^(reply to|trả lời)\b.*", re.IGNORECASE)
NOISE = {"translate", "dịch", "top", "view activity", "xem hoạt động", "pinned", "đã ghim"}
AGE_UNIT = {"s": "giây", "m": "phút", "h": "giờ", "d": "ngày", "w": "tuần"}


class ParsedPost(BaseModel):
    handle: str
    age: str
    text: str


class ParsedComment(ParsedPost):
    id: str
    same_author: bool = False  # cùng tên với bài gốc: phần tiếp theo của chuỗi tác giả
    picked: bool = False


class StatHint(BaseModel):
    block: int  # 0 = bài gốc, i >= 1 = bình luận thứ i
    raw: str
    value: int | None


class ParseResult(BaseModel):
    guess: Literal["threads_text", "embed", "unknown"]
    source_url: str | None = None
    post: ParsedPost | None = None
    comments: list[ParsedComment] = []
    hints: list[StatHint] = []
    warnings: list[str] = []


def age_label(raw: str) -> str:
    """`17h` → `17 giờ`; `08/25/26` → `25/08/2026` (tháng/ngày/năm; số đầu > 12 thì ngày/tháng)."""
    s = raw.strip()
    m = AGE.match(s)
    if m:
        unit = m.group(2).lower()
        return f"{m.group(1)} {AGE_UNIT.get(unit, unit)}"
    d = DATE.match(s)
    if d:
        a, b, y = int(d.group(1)), int(d.group(2)), int(d.group(3))
        month, day = (b, a) if a > 12 else (a, b)
        year = y + 2000 if y < 100 else y
        return f"{day:02d}/{month:02d}/{year}"
    return s


def _is_age(line: str) -> bool:
    return bool(AGE.match(line) or DATE.match(line))


def _drop_page_counters(lines: list[str]) -> list[str]:
    """Bỏ bộ ba dòng `1`, `/`, `2` (chỉ số phần của chuỗi tác giả)."""
    out, i = [], 0
    while i < len(lines):
        if (
            i + 2 < len(lines)
            and lines[i].strip().isdigit()
            and lines[i + 1].strip() == "/"
            and lines[i + 2].strip().isdigit()
        ):
            i += 3
            continue
        out.append(lines[i])
        i += 1
    return out


def _is_noise(line: str) -> bool:
    s = line.strip()
    return s.casefold() in NOISE or bool(REPLY_TO.match(s))


def _clean_body(lines: list[str], block: int, hints: list[StatHint]) -> str:
    kept: list[str] = []
    for raw in lines:
        s = raw.strip()
        if _is_noise(s):
            continue
        kept.append(s)
    # dòng chỉ gồm số/số kèm K, M: có thể là số liệu → báo, bỏ khỏi chữ (trừ khi là cả thân)
    if any(not STAT_LINE.match(s) for s in kept if s):
        rest = []
        for s in kept:
            if s and STAT_LINE.match(s):
                hints.append(StatHint(block=block, raw=s, value=parse_count(s)))
            else:
                rest.append(s)
        kept = rest
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_threads_text(raw: str) -> ParseResult:
    if len(raw) > MAX_TEXT:
        raise ValueError(f"Chữ dán dài quá {MAX_TEXT:,} ký tự".replace(",", "."))
    text = unicodedata.normalize("NFC", raw).replace("\r\n", "\n").replace("\r", "\n")
    warnings: list[str] = []

    source_url: str | None = None
    embed = EMBED_URL.search(text)
    if embed and embed.group(1).startswith("https://"):
        source_url = embed.group(1)
    # mã nhúng chỉ chứa liên kết: bỏ cả khối, không render, không chạy <script>
    text = EMBED_SCRIPT.sub("", EMBED_BLOCK.sub("", text))

    lines = _drop_page_counters(text.split("\n"))
    headers: list[int] = []
    for i, line in enumerate(lines[:-1]):
        s = line.strip()
        if HANDLE.match(s) and not _is_age(s) and _is_age(lines[i + 1].strip()):
            headers.append(i)

    if not headers:
        if embed:
            warnings.append("Mã nhúng chỉ chứa liên kết, không có chữ. Hãy dán chữ của bài.")
            return ParseResult(guess="embed", source_url=source_url, warnings=warnings)
        return ParseResult(
            guess="unknown",
            warnings=["Không nhận ra bài hay bình luận nào. Hãy sửa tay hoặc dán lại."],
        )

    if source_url is None:  # liên kết dán ở đầu (vd threads.com/share/…): chỉ lưu, không truy cập
        source_url = next(
            (ln.strip() for ln in lines[: headers[0]] if URL_LINE.match(ln.strip())), None
        )

    hints: list[StatHint] = []
    blocks: list[ParsedPost] = []
    for n, start in enumerate(headers):
        end = headers[n + 1] if n + 1 < len(headers) else len(lines)
        handle = lines[start].strip().lstrip("@")
        age = age_label(lines[start + 1].strip())
        body = _clean_body(lines[start + 2 : end], n, hints)
        blocks.append(ParsedPost(handle=handle, age=age, text=body))

    post = blocks[0]
    comments = [
        ParsedComment(
            id=f"c{i}",
            handle=b.handle,
            age=b.age,
            text=b.text,
            same_author=b.handle == post.handle,
            picked=i <= DEFAULT_PICKED,
        )
        for i, b in enumerate(blocks[1:], 1)
    ]
    if not comments:
        warnings.append("Chỉ thấy bài gốc, chưa có bình luận.")
    if hints:
        warnings.append(f"Có {len(hints)} dòng chỉ gồm số, có thể là số liệu: bạn kiểm lại.")
    if any(not c.text for c in comments) or not post.text:
        warnings.append("Có khối không có chữ (có thể chỉ là ảnh): hãy nhập chữ tay.")
    return ParseResult(
        guess="threads_text",
        source_url=source_url,
        post=post,
        comments=comments,
        hints=hints,
        warnings=warnings,
    )
