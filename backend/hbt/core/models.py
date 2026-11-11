"""Mô hình dữ liệu JSON cho HBT Core (Chế độ V1 & V2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

HbtCoreTopic = Literal["history", "fun", "science", "mystery"]
VALID_TOPICS: tuple[str, ...] = ("history", "fun", "science", "mystery")


class HbtCoreSegment(BaseModel):
    """Một phân đoạn trong kịch bản HBT Core."""

    order: int = Field(default=1, ge=1)
    text: str = Field(default="")
    image: str = Field(default="")
    sfx: str = Field(default="whoosh")
    card_text: str | None = Field(default=None)
    punch: bool = Field(default=False)

    @field_validator("text", mode="before")
    @classmethod
    def _clean_text(cls, v: object) -> str:
        return str(v or "").strip()

    @field_validator("image", mode="before")
    @classmethod
    def _clean_image(cls, v: object) -> str:
        return str(v or "").strip()

    @field_validator("sfx", mode="before")
    @classmethod
    def _clean_sfx(cls, v: object) -> str:
        s = str(v or "whoosh").strip().lower()
        return s or "whoosh"


class HbtCoreScript(BaseModel):
    """Cấu trúc kịch bản chuẩn của HBT Core (dùng chung cho V1 & V2)."""

    title: str = Field(min_length=1)
    topic: str = Field(default="science")
    segments: list[HbtCoreSegment] = Field(min_length=1)

    @field_validator("title", mode="before")
    @classmethod
    def _clean_title(cls, v: object) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("Tiêu đề video không được để trống")
        return s

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, v: object) -> str:
        s = str(v or "science").strip().lower()
        if s not in VALID_TOPICS:
            # Ánh xạ tiếng Việt hoặc các bí danh phổ biến
            mapping = {
                "lịch sử": "history",
                "lich su": "history",
                "vui": "fun",
                "hài hước": "fun",
                "hai huoc": "fun",
                "khoa học": "science",
                "khoa hoc": "science",
                "bí ẩn": "mystery",
                "bi an": "mystery",
            }
            return mapping.get(s, "science")
        return s

    @field_validator("segments")
    @classmethod
    def _validate_segments(cls, v: list[HbtCoreSegment]) -> list[HbtCoreSegment]:
        if not v:
            raise ValueError("Kịch bản cần có ít nhất 1 phân đoạn (segment)")
        non_empty = [seg for seg in v if seg.text.strip()]
        if not non_empty:
            raise ValueError("Cần ít nhất 1 phân đoạn có lời thoại tiếng Việt (text)")
        # Chuẩn hóa lại thứ tự order 1..N
        out: list[HbtCoreSegment] = []
        for idx, seg in enumerate(v, start=1):
            out.append(seg.model_copy(update={"order": idx}))
        return out


class SegmentVoiceTiming(BaseModel):
    """Mốc thời gian giọng đọc từng phân đoạn tính bằng micro-giây và giây."""

    order: int
    text: str
    voice_id: str
    wav_path: str
    start_us: int
    end_us: int
    duration_us: int
    start_s: float
    end_s: float
    duration_s: float
    cached: bool = False

