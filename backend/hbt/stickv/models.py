"""Mô hình dữ liệu Pydantic v2 cho động cơ StickV."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

StickvAspect = Literal["9:16", "16:9"]
StickvTheme = Literal["cream", "dark"]
StickvDomain = Literal[
    "paper_classic",
    "physics_science",
    "history_geo",
    "psychology_story",
    "cosmos_mystery",
]
StickvInteraction = Literal["none", "hold_prop", "point_chart", "versus_split"]
StickvAnimationMode = Literal["auto", "static"]
StickvMotion = Literal["bounce", "slide_left", "slide_right", "float", "static"]
StickvCameraShot = Literal["wide_stage", "focus_board", "closeup_react"]
StickvEmotion = Literal[
    "auto",
    "neutral",
    "confident",
    "curious",
    "idea",
    "shock",
    "skeptical",
    "serious",
    "sad",
    "happy",
    "excited",
]
StickvBoardType = Literal[
    "none",
    "bullets",
    "big_number",
    "comparison",
    "flow_steps",
    "card",
    "list",
    "quote",
    "bar_compare",
    "counter_grow",
    "timeline_era",
    "location_map",
    "myth_vs_fact",
    "recap_card",
]
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
    chapter_title: str = Field(default="", max_length=120)
    narration: str = Field(default="", max_length=1200)
    pose: str = Field(default="present_board", max_length=120)
    emotion: StickvEmotion = "auto"
    anim_oneshot: str | None = Field(default=None, max_length=120)
    anim_loop: str = Field(default="talk_explain", max_length=120)
    interaction: StickvInteraction = "none"
    camera_shot: StickvCameraShot = "wide_stage"
    prop_query: str | None = Field(default=None, max_length=120)
    facing: StickvFacing = "right"
    motion: StickvMotion = "bounce"
    sfx_tag: StickvSfxTag = "whoosh"
    board_type: StickvBoardType = "bullets"
    board_title: str = Field(default="", max_length=120)
    board_items: list[str] = Field(default_factory=list)
    takeaway: str = Field(default="", max_length=160)
    board_data: dict[str, Any] = Field(default_factory=dict)
    visual_data: dict[str, Any] = Field(default_factory=dict)
    media_path: str = Field(default="", max_length=260)
    clip_path: str = Field(default="", max_length=260)
    duration_sec: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "visual_type" in out and "board_type" not in out:
            out["board_type"] = out["visual_type"]
        if "text" in out and "narration" not in out:
            out["narration"] = out["text"]
        if "sfx" in out and "sfx_tag" not in out:
            out["sfx_tag"] = out["sfx"]
        if str(out.get("motion") or "").strip().lower() == "shake":
            out["motion"] = "float"

        # Alias v9: bullets -> board_data.items, takeaway ở cấp beat -> board_data.takeaway
        bdata = dict(out.get("board_data") or {}) if isinstance(out.get("board_data"), dict) else {}
        if isinstance(out.get("bullets"), list) and "items" not in bdata:
            bdata["items"] = [str(x).strip() for x in out["bullets"] if str(x).strip()]
            if "board_items" not in out:
                out["board_items"] = list(bdata["items"])
        if str(out.get("takeaway") or "").strip() and "takeaway" not in bdata:
            bdata["takeaway"] = str(out["takeaway"]).strip()[:160]
        elif (
            str(bdata.get("takeaway") or "").strip() and not str(out.get("takeaway") or "").strip()
        ):
            out["takeaway"] = str(bdata["takeaway"]).strip()[:160]
        out["board_data"] = bdata

        raw_emo = str(out.get("emotion") or "auto").strip().lower()
        valid_emos = {
            "auto",
            "neutral",
            "confident",
            "curious",
            "idea",
            "shock",
            "skeptical",
            "serious",
            "sad",
            "happy",
            "excited",
        }
        out["emotion"] = raw_emo if raw_emo in valid_emos else "auto"
        return out


class StickvProject(BaseModel):
    """Dự án StickV lưu tại `workspace/stickv/<slug>/project.json`."""

    slug: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(default="science", max_length=40)
    domain: StickvDomain = "paper_classic"
    animation_mode: StickvAnimationMode = "auto"
    aspect: StickvAspect = "9:16"
    theme: StickvTheme = "cream"
    fps: int = Field(default=30, ge=15, le=60)
    voice_id: str = Field(default="Thanh Bình", max_length=120)
    music_mood: str = Field(default="curious_science", max_length=60)
    pause_scale: float = Field(default=1.0, ge=0.5, le=2.0)
    outro: bool = True
    gemini_model: str = Field(default="", max_length=120)
    target_minutes: float = Field(default=1.0, ge=0.25, le=20.0)
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    beats: list[StickvBeat] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    last_render: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_project_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if str(out.get("domain") or "").strip().lower() == "cosmos":
            out["domain"] = "cosmos_mystery"
        return out
