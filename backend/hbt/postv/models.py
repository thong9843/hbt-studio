"""Mô hình dữ liệu project PostV (IMPLEMENT-POSTV.md mục 3) và union với project HBT.

Project HBT không có trường `kind`; PostV có `kind: "postv"`. `AnyProject` chọn đúng loại theo
`kind` nên `project.json` cũ không phải sửa và `hbt.models` không đổi.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import Discriminator, Field, Tag, field_validator, model_validator

from hbt.config import ALLOWED_FPS
from hbt.models import (
    Music,
    Project,
    Publish,
    Theme,
    Thumbnail,
    _check_color,
    _Model,
    check_slug,
)

POSTV_FPS = 60  # fps mặc định của PostV (K-11); khác `DEFAULT_FPS` của video HBT
MAX_SEGMENTS = 40
MAX_COMMENTS = 200
COMMENT_ID = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

SegmentRole = Literal["hook", "post", "comment", "commentary"]
CardKind = Literal["hook", "post", "comment", "none"]
Count = Annotated[int | None, Field(default=None, ge=0)]


class PostvSource(_Model):
    """Nguồn chỉ lưu chuỗi: app không bao giờ truy cập `url` (docs/postv D2, D3)."""

    url: str = ""
    note: str = ""
    pasted_at: str | None = None


class PostvStats(_Model):
    """Số liệu chỉ để hiển thị trên thẻ, nhập tay (K-31)."""

    views: Count = None
    likes: Count = None
    replies: Count = None
    reposts: Count = None
    shares: Count = None


class PostvPost(PostvStats):
    handle: str = ""
    age: str = ""
    text: str = ""
    card_text: str | None = None  # chữ hiện trên thẻ; None = lấy câu đầu của `text`


class PostvComment(PostvStats):
    id: str = Field(pattern=COMMENT_ID, max_length=40)
    handle: str = ""
    age: str = ""
    text: str = ""
    parent: str | None = None
    picked: bool = True


class PostvSegment(_Model):
    role: SegmentRole
    card: CardKind | None = None  # None = theo `role` (`commentary` → none)
    voice: str = ""  # chữ thường cho VieNeu: không dùng `{cách đọc}` hay `|` (K-33)
    ref: str | None = None  # id bình luận khi role == "comment"
    # ai đọc đoạn: "narrator", "post" hoặc id bình luận; None = theo `role` (6d)
    speaker: str | None = Field(default=None, max_length=40)


class PostvHook(_Model):
    """Thẻ tiêu đề ở giây đầu: chữ và cụm nhấn (ô màu bo góc). Trống = lấy câu đầu của bài."""

    text: str = ""
    accent: str = ""


class PostvBackground(_Model):
    mode: Literal["auto", "manual"] = "auto"
    clip_ids: list[str] = Field(default_factory=list)
    seed: int = 1
    start_offset: float | None = Field(default=None, ge=0)


class PostvVoice(_Model):
    """Giọng đọc: sinh bằng VieNeu (`vieneu`) hoặc file nhập vào (`file`)."""

    engine: Literal["vieneu", "file"] = "vieneu"
    voice_id: str | None = None
    file: str | None = None
    trim_end: float | None = Field(default=None, gt=0)
    # chỉ giọng người dùng chọn tay: {speaker: voice_id}; người chưa gán bốc theo `seed` (6d)
    cast: dict[str, str] = Field(default_factory=dict)
    seed: int = 1


class CaptionStyle(_Model):
    preset: Literal["hbt", "sample"] = "hbt"
    highlight_color: str | None = None  # màu từ đang đọc; None = theo preset

    @field_validator("highlight_color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        return None if v is None else _check_color(v, allow_names=False)


class PostvStyle(_Model):
    caption: CaptionStyle = Field(default_factory=CaptionStyle)


class Censor(_Model):
    """Che từ nhạy cảm mức chặn (K-27, K-29): bíp đè lên giọng + làm mờ hoặc `***`."""

    enabled: bool = True
    sfx: Literal["bleep"] = "bleep"
    blur_card: bool = True
    text: Literal["blur", "stars"] = "blur"


class PostvSettings(_Model):
    fps: int = POSTV_FPS
    captions: bool = True
    aligner: Literal["auto", "whisper", "silence"] = "auto"
    outro: bool = True
    card_animation: Literal["smooth", "bounce"] = "smooth"
    count_up: bool = True  # số like, bình luận, chia sẻ trên thẻ đếm từ 0 (D20)
    censor: Censor = Field(default_factory=Censor)

    @field_validator("fps")
    @classmethod
    def _fps(cls, v: int) -> int:
        if v not in ALLOWED_FPS:
            raise ValueError(f"fps phải là một trong {ALLOWED_FPS}")
        return v


class PostvAutoOptions(_Model):
    """Tùy chọn ghi nhớ lần tạo tự động gần nhất (PVA)."""

    style: str = "ke-chuyen"
    comments: int = Field(default=3, ge=2, le=5)
    voices: Literal["random", "manual"] = "random"
    seed: int = 1


class PostvProject(_Model):
    version: Literal[1] = 1
    kind: Literal["postv"] = "postv"
    slug: str
    title: str
    series: str = ""
    theme: Theme = Field(default_factory=Theme)
    source: PostvSource = Field(default_factory=PostvSource)
    post: PostvPost = Field(default_factory=PostvPost)
    comments: list[PostvComment] = Field(default_factory=list, max_length=MAX_COMMENTS)
    segments: list[PostvSegment] = Field(default_factory=list, max_length=MAX_SEGMENTS)
    template: Literal["story_cards", "fixed_card"] = "story_cards"
    hook: PostvHook = Field(default_factory=PostvHook)
    style: PostvStyle = Field(default_factory=PostvStyle)
    background: PostvBackground = Field(default_factory=PostvBackground)
    voice: PostvVoice = Field(default_factory=PostvVoice)
    music: Music | None = None
    settings: PostvSettings = Field(default_factory=PostvSettings)
    publish: Publish = Field(default_factory=Publish)
    thumbnail: Thumbnail | None = None
    auto: PostvAutoOptions = Field(default_factory=PostvAutoOptions)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return check_slug(v)

    @model_validator(mode="after")
    def _references(self) -> PostvProject:
        ids = [c.id for c in self.comments]
        if len(set(ids)) != len(ids):
            raise ValueError("id bình luận bị trùng")
        known = set(ids)
        for c in self.comments:
            if c.parent is not None and c.parent not in known:
                raise ValueError(f"Bình luận '{c.id}' trả lời bình luận không có: '{c.parent}'")
        for i, seg in enumerate(self.segments, 1):
            if seg.ref is not None and seg.ref not in known:
                raise ValueError(f"Đoạn {i} dẫn tới bình luận không có: '{seg.ref}'")
        people = {"narrator", "post", *known}
        for i, seg in enumerate(self.segments, 1):
            if seg.speaker is not None and seg.speaker not in people:
                raise ValueError(f"Đoạn {i} có người đọc không có: '{seg.speaker}'")
        for who in self.voice.cast:
            if who not in people:
                raise ValueError(f"Giọng chọn cho người không có: '{who}'")
        return self

    def render_problems(self) -> list[str]:
        """Những thứ còn thiếu để dựng được video PostV (rỗng nếu đủ). Kiểm tra nền: PV3."""
        problems = []
        if not self.post.text.strip():
            problems.append("Chưa có chữ bài gốc")
        if not any(s.voice.strip() for s in self.segments):
            problems.append("Chưa có đoạn nào có lời đọc")
        if not (self.voice.file or "").strip():
            problems.append("Chưa có file giọng đọc")
        return problems


def project_kind(data: Any) -> Literal["video", "postv"]:
    """`kind` của dữ liệu thô (dict) hoặc của một model; không có `kind` → "video"."""
    kind = data.get("kind") if isinstance(data, dict) else getattr(data, "kind", None)
    return "postv" if kind == "postv" else "video"


AnyProject = Annotated[
    Union[Annotated[Project, Tag("video")], Annotated[PostvProject, Tag("postv")]],  # noqa: UP007
    Discriminator(project_kind),
]

__all__ = ["AnyProject", "PostvAutoOptions", "PostvProject", "POSTV_FPS", "project_kind"]
