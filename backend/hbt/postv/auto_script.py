"""Tự động hoá PostV: mẫu phong cách lời đọc, làm sạch chữ trích, lọc bình luận.

Theo IMPLEMENT-POSTV §6d: gộp xử lý styles, clean text, filter comments và tạo kịch bản tự động.
"""

from __future__ import annotations

import json
import logging
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.postv.models import PostvComment, PostvHook, PostvProject, PostvSegment

log = logging.getLogger(__name__)

DEFAULT_STYLES_PATH = Path(__file__).resolve().parent / "data" / "script_styles.json"

ABBREVIATIONS = {
    "ko": "không",
    "k": "không",
    "khum": "không",
    "dc": "được",
    "đc": "được",
    "vs": "với",
    "trc": "trước",
    "bh": "bây giờ",
    "bjo": "bây giờ",
    "ng": "người",
    "ntn": "như thế nào",
    "mn": "mọi người",
    "j": "gì",
    "cx": "cũng",
    "thik": "thích",
    "a": "anh",
    "e": "em",
    "c": "chị",
}

# Regex nhận diện emoticon phổ biến
EMOTICON_RE = re.compile(
    r"(?:=+\)+|=+\(+|:\)+|:\(+|:D+|:d+|:v+|:V+|\^\^|-_-|T_T|x_x|xD+|XD+|\._\.|;-\;|>\.<|>_<|@@)",
    re.IGNORECASE,
)

# Regex nhận diện Emoji unicode
EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\ufe00-\ufe0f]",
    flags=re.UNICODE,
)

# Regex URL
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


@dataclass(frozen=True)
class ScriptStyle:
    id: str
    name: str
    hook: list[str]
    intro_post: list[str]
    intro_comment: list[str]
    commentary: list[str]
    outro: list[str]

    def view(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.name,
            "hook": list(self.hook),
            "intro_post": list(self.intro_post),
            "intro_comment": list(self.intro_comment),
            "commentary": list(self.commentary),
            "outro": list(self.outro),
        }


def load_script_styles(settings_dir: Path | None = None) -> list[ScriptStyle]:
    """Nạp danh sách 5 phong cách kịch bản. Ưu tiên workspace/settings/postv_script_styles.json."""
    data_bytes: bytes | None = None
    if settings_dir is not None:
        user_file = settings_dir / "postv_script_styles.json"
        if user_file.is_file():
            try:
                data_bytes = user_file.read_bytes()
            except OSError as e:
                log.warning("Không đọc được %s: %s", user_file, e)

    if data_bytes is None:
        data_bytes = DEFAULT_STYLES_PATH.read_bytes()

    raw = json.loads(data_bytes.decode("utf-8"))
    out: list[ScriptStyle] = []
    for item in raw:
        out.append(
            ScriptStyle(
                id=str(item["id"]),
                name=str(item["name"]),
                hook=list(item.get("hook", [])),
                intro_post=list(item.get("intro_post", [])),
                intro_comment=list(item.get("intro_comment", [])),
                commentary=list(item.get("commentary", [])),
                outro=list(item.get("outro", [])),
            )
        )
    return out


def clean_voice_text(text: str) -> str:
    """Làm sạch chữ cho VieNeu đọc: bỏ emoji, emoticon, link, mở rộng viết tắt."""
    if not text:
        return ""

    # Bỏ URLs
    t = URL_RE.sub(" ", text)

    # Bỏ emoji và emoticon
    t = EMOJI_RE.sub(" ", t)
    t = EMOTICON_RE.sub(" ", t)

    # Bỏ các ký tự cú pháp HBT cũ: { }, |
    t = re.sub(r"[{}\[\]|]", " ", t)

    # Mở rộng từ viết tắt (so khớp theo ranh giới từ nguyên vẹn \b)
    def _expand(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        repl = ABBREVIATIONS.get(lower, word)
        if word.isupper():
            return repl.upper()
        if word.istitle():
            return repl.title()
        return repl

    keys = sorted(ABBREVIATIONS.keys(), key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.IGNORECASE)
    t = pattern.sub(_expand, t)

    # Gộp khoảng trắng thừa
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return t.strip()


def shorten_comment(text: str, max_chars: int = 220) -> str:
    """Rút gọn bình luận dài hơn max_chars ở dấu câu gần nhất."""
    cleaned = clean_voice_text(text)
    if len(cleaned) <= max_chars:
        return cleaned

    sub = cleaned[:max_chars]
    # Tìm dấu câu gần nhất
    punct = [sub.rfind("."), sub.rfind("!"), sub.rfind("?"), sub.rfind(","), sub.rfind(";")]
    best = max(punct)
    if best > 40:  # Có dấu câu hợp lý
        return sub[: best + 1].strip()

    # Cắt ở khoảng trắng gần nhất
    space = sub.rfind(" ")
    if space > 40:
        return sub[:space].strip() + "..."
    return sub.strip() + "..."


def filter_comments(
    comments: Sequence[PostvComment],
    max_comments: int = 3,
    max_seconds: float = 100.0,
) -> list[PostvComment]:
    """Lọc và sắp xếp bình luận theo ưu tiên like, bỏ rác/trùng, giới hạn thời lượng."""
    max_comments = max(2, min(max_comments, 5))
    valid: list[PostvComment] = []
    seen_texts: set[str] = set()

    for c in comments:
        raw = c.text.strip()
        if len(raw) < 8:
            continue
        if URL_RE.search(raw):
            continue
        cleaned = clean_voice_text(raw).lower()
        if cleaned in seen_texts:
            continue
        seen_texts.add(cleaned)
        valid.append(c)

    # Ưu tiên theo likes giảm dần (None coi như 0)
    def _likes(c: PostvComment) -> int:
        if isinstance(c.likes, int):
            return c.likes
        return 0

    sorted_comments = sorted(valid, key=_likes, reverse=True)
    picked = sorted_comments[:max_comments]

    # Ước thời lượng: ký tự / 16.5
    def _est_sec(comm_list: list[PostvComment]) -> float:
        total_chars = sum(len(shorten_comment(c.text)) for c in comm_list)
        return total_chars / 16.5

    while len(picked) > 1 and _est_sec(picked) > max_seconds:
        picked.pop()

    return picked


def extract_hook_text(post_text: str, max_chars: int = 60) -> str:
    """Trích câu đầu tiên của bài gốc làm tiêu đề hook, <= max_chars."""
    lines = [line.strip() for line in post_text.splitlines() if line.strip()]
    first_block = lines[0] if lines else post_text.strip()
    sentences = re.split(r"[.!?\n]", first_block)
    first_sentence = sentences[0].strip() if sentences else first_block
    cleaned = clean_voice_text(first_sentence)
    if len(cleaned) <= max_chars:
        return cleaned
    space = cleaned[:max_chars].rfind(" ")
    if space > 20:
        return cleaned[:space].strip()
    return cleaned[:max_chars].strip()


def build_auto_script(
    project: PostvProject,
    style_id: str = "ke-chuyen",
    comments_count: int = 3,
    voices_mode: str = "random",
    seed: int = 1,
    styles: list[ScriptStyle] | None = None,
) -> PostvProject:
    """Tạo kịch bản tự động cho dự án PostV theo mẫu phong cách (PVA).

    Tạo hook, intro_post, post, intro_comment, comment, commentary theo seed.
    """
    if styles is None:
        styles = load_script_styles()

    style_map = {s.id: s for s in styles}
    style = style_map.get(style_id) or styles[0]

    rng = random.Random(seed)

    # 1. Hook
    hook_text = extract_hook_text(project.post.text)
    hook_template = rng.choice(style.hook) if style.hook else "{text}"
    hook_voice = hook_template.replace("{text}", hook_text)

    # 2. Bài gốc
    intro_post = rng.choice(style.intro_post) if style.intro_post else "Một bạn chia sẻ:"
    post_cleaned = clean_voice_text(project.post.text)

    # 3. Bình luận
    chosen_comments = filter_comments(project.comments, max_comments=comments_count)
    chosen_ids = {c.id for c in chosen_comments}

    # Cập nhật cờ picked cho comments trong project
    for c in project.comments:
        c.picked = c.id in chosen_ids

    # 4. Tạo segments
    segments: list[PostvSegment] = []

    # Đoạn 1: Hook
    segments.append(
        PostvSegment(
            role="hook",
            card="hook",
            voice=hook_voice,
            speaker="narrator",
        )
    )

    # Đoạn 2: Dẫn vào bài gốc
    segments.append(
        PostvSegment(
            role="post",
            card="post",
            voice=intro_post,
            speaker="narrator",
        )
    )

    # Đoạn 3: Nội dung bài gốc
    segments.append(
        PostvSegment(
            role="post",
            card="post",
            voice=post_cleaned,
            speaker="post",
        )
    )

    # Đoạn 4+: Từng bình luận
    intros = style.intro_comment or ["Bình luận bên dưới:"]
    for i, c in enumerate(chosen_comments):
        intro_text = intros[i % len(intros)]
        segments.append(
            PostvSegment(
                role="comment",
                card="comment",
                voice=intro_text,
                ref=c.id,
                speaker="narrator",
            )
        )
        comment_voice = shorten_comment(c.text)
        segments.append(
            PostvSegment(
                role="comment",
                card="comment",
                voice=comment_voice,
                ref=c.id,
                speaker=c.id,
            )
        )

    # Đoạn kết: Commentary & Outro
    commentary_text = rng.choice(style.commentary) if style.commentary else "Bạn thấy thế nào?"
    segments.append(
        PostvSegment(
            role="commentary",
            card="none",
            voice=commentary_text,
            speaker="narrator",
        )
    )

    if style.outro:
        outro_text = rng.choice(style.outro)
        segments.append(
            PostvSegment(
                role="commentary",
                card="none",
                voice=outro_text,
                speaker="narrator",
            )
        )

    # Cập nhật project
    project.segments = segments
    project.hook = PostvHook(text=hook_text, accent="")
    project.voice.seed = seed
    if voices_mode == "random":
        project.voice.cast = {}

    return project
