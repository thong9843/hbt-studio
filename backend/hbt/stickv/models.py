"""Mô hình dữ liệu Pydantic v2 cho động cơ StickV."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StickvAspect = Literal["9:16", "16:9"]
StickvTheme = Literal["cream", "dark"]
StickvMotion = Literal["bounce", "slide_left", "slide_right", "shake", "float", "static"]
StickvBoardType = Literal["none", "bullets", "big_number", "comparison", "flow_steps"]
StickvSfxTag = Literal["none", "whoosh", "pop", "vine_boom", "ding"]
StickvFacing = Literal["left", "right"]

STICKV_ASPECT_SIZES: dict[StickvAspect, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class StickvBeat(BaseModel):
    """Một beat ngắn trong kịch bản StickV (neo thời gian theo giọng đọc)."""

    id: str = Field(min_length=1, max_length=64)
    chapter: int = Field(default=1, ge=1, le=50)
    narration: str = Field(default="", max_length=1200)
    pose: str = Field(default="explain", max_length=120)
    facing: StickvFacing = "right"
    motion: StickvMotion = "bounce"
    sfx_tag: StickvSfxTag = "whoosh"
    board_type: StickvBoardType = "bullets"
    board_title: str = Field(default="", max_length=120)
    board_data: dict[str, Any] = Field(default_factory=dict)
    media_path: str = Field(default="", max_length=260)
    duration_sec: float = Field(default=0.0, ge=0.0)


class StickvProject(BaseModel):
    """Dự án StickV lưu tại `workspace/stickv/<slug>/project.json`."""

    slug: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(default="science", max_length=40)
    aspect: StickvAspect = "9:16"
    theme: StickvTheme = "cream"
    fps: int = Field(default=30, ge=15, le=60)
    voice_id: str = Field(default="vienneu_default", max_length=120)
    music_mood: str = Field(default="science", max_length=60)
    gemini_model: str = Field(default="", max_length=120)
    target_minutes: float = Field(default=1.0, ge=0.25, le=20.0)
    beats: list[StickvBeat] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    last_render: dict[str, Any] | None = None
