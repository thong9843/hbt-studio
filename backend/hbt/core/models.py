"""Mô hình dữ liệu JSON cho HBT Core (Chế độ V1 & V2 — Chuẩn Hay Biết Tốt, không giới hạn từ)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

HbtCoreTopic = Literal["history", "fun", "science", "mystery"]
VALID_TOPICS: tuple[str, ...] = ("history", "fun", "science", "mystery")

STICKER_TO_SFX: dict[str, str] = {
    "shock": "impact",
    "warning": "impact",
    "question": "whoosh",
    "think": "pop",
    "laugh": "pop",
    "check": "pop",
}

_TOPIC_EXACT_ALIASES: dict[str, str] = {
    "history": "history",
    "lịch sử": "history",
    "lich su": "history",
    "fun": "fun",
    "vui": "fun",
    "hài hước": "fun",
    "hai huoc": "fun",
    "science": "science",
    "khoa học": "science",
    "khoa hoc": "science",
    "mystery": "mystery",
    "bí ẩn": "mystery",
    "bi an": "mystery",
}


def infer_music_topic(topic: str, fallback_text: str = "") -> str:
    """Ánh xạ chủ đề tự do sang một trong 4 nhóm BGM (`history/fun/science/mystery`)."""
    raw = (topic or "").strip().lower()
    if raw in _TOPIC_EXACT_ALIASES:
        return _TOPIC_EXACT_ALIASES[raw]
    hay = f"{raw} {(fallback_text or '').lower()}"
    if any(k in hay for k in ("lịch sử", "lich su", "cổ đại", "la mã", "chiến", "vua", "triều")):
        return "history"
    if any(k in hay for k in ("bí ẩn", "bi an", "huyền bí", "tam giác", "ma quái", "vũ trụ")):
        return "mystery"
    if any(k in hay for k in ("hài", "vui", "cười", "thú vị", "mẹo")):
        return "fun"
    return "science"


class HbtCoreSegment(BaseModel):
    """Một phân đoạn trong kịch bản HBT Core (chuẩn Hay Biết Tốt, không giới hạn từ)."""

    id: int = Field(default=1, ge=1)
    order: int = Field(default=1, ge=1)
    title: str = Field(default="")
    text: str = Field(default="")
    sticker: str = Field(default="question")
    image_prompt: str = Field(default="")
    image: str = Field(default="")
    sfx: str = Field(default="whoosh")
    card_text: str | None = Field(default=None)
    punch: bool = Field(default=False)
    duration: float | None = Field(default=None)
    audio_path: str | None = Field(default=None)
    start_time: float | None = Field(default=None)
    end_time: float | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _sync_fields_before(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "id" in out and "order" not in out:
            out["order"] = out["id"]
        elif "order" in out and "id" not in out:
            out["id"] = out["order"]

        title_val = str(out.get("title") or "").strip()
        card_val = str(out.get("card_text") or "").strip()
        if title_val and not card_val:
            out["card_text"] = title_val
        elif card_val and not title_val:
            out["title"] = card_val

        if not str(out.get("sfx") or "").strip():
            stk = str(out.get("sticker") or "").strip().lower()
            out["sfx"] = STICKER_TO_SFX.get(stk, "whoosh")
        return out

    @field_validator("title", mode="before")
    @classmethod
    def _clean_title(cls, v: object) -> str:
        return str(v or "").strip()

    @field_validator("text", mode="before")
    @classmethod
    def _clean_text(cls, v: object) -> str:
        return str(v or "").strip()

    @field_validator("sticker", mode="before")
    @classmethod
    def _clean_sticker(cls, v: object) -> str:
        s = str(v or "question").strip().lower()
        return s or "question"

    @field_validator("image_prompt", mode="before")
    @classmethod
    def _clean_image_prompt(cls, v: object) -> str:
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
    """Cấu trúc kịch bản chuẩn của HBT Core (dùng chung cho V1 & V2, hỗ trợ đầy đủ Hay Biết Tốt)."""

    topic: str = Field(default="science")
    total_segments: int = Field(default=0, ge=0)
    title: str = Field(default="")
    segments: list[HbtCoreSegment] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _sync_root_before(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        topic_val = str(out.get("topic") or "").strip()
        title_val = str(out.get("title") or "").strip()
        if not title_val and topic_val:
            out["title"] = topic_val
        elif title_val and not topic_val:
            out["topic"] = "science"
        return out

    @field_validator("title", mode="before")
    @classmethod
    def _clean_title(cls, v: object) -> str:
        return str(v or "").strip()

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, v: object) -> str:
        s = str(v or "science").strip()
        if not s:
            return "science"
        return _TOPIC_EXACT_ALIASES.get(s.lower(), s)

    @field_validator("segments")
    @classmethod
    def _validate_segments(cls, v: list[HbtCoreSegment]) -> list[HbtCoreSegment]:
        if not v:
            raise ValueError("Kịch bản cần có ít nhất 1 phân đoạn (segment)")
        non_empty = [seg for seg in v if seg.text.strip()]
        if not non_empty:
            raise ValueError("Cần ít nhất 1 phân đoạn có lời thoại tiếng Việt (text)")
        out: list[HbtCoreSegment] = []
        for idx, seg in enumerate(v, start=1):
            out.append(seg.model_copy(update={"id": idx, "order": idx}))
        return out

    @model_validator(mode="after")
    def _finalize_totals(self) -> HbtCoreScript:
        self.total_segments = len(self.segments)
        if not self.title:
            first_headline = next(
                (s.title or s.card_text or s.text[:60] for s in self.segments if s.text),
                "",
            )
            self.title = self.topic or first_headline or "Video Hay Biết Tốt"
        return self


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
