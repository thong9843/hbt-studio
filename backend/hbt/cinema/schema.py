"""Hợp đồng dữ liệu IR v1 (TimelineSpec) cho Lõi Dựng Phim Hợp Nhất (`backend/hbt/cinema`)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

AspectRatio = Literal["9:16", "16:9"]
ASPECT_DIMENSIONS: dict[AspectRatio, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

ShotType = Literal[
    "desk_wide",
    "card_hero",
    "split_compare",
    "data_spotlight",
    "puppet_closeup",
    "recap_grid",
]
SHOT_TYPES: tuple[ShotType, ...] = (
    "desk_wide",
    "card_hero",
    "split_compare",
    "data_spotlight",
    "puppet_closeup",
    "recap_grid",
)

TransitionType = Literal["editorial_cut", "whip_pan", "paper_slide"]
TRANSITION_TYPES: tuple[TransitionType, ...] = ("editorial_cut", "whip_pan", "paper_slide")

EngineSource = Literal["stickv", "core", "cinema"]
CinemaTheme = Literal["cream", "dark"]


class BBox(BaseModel):
    """Hộp giới hạn hình học 2D (tọa độ pixel top-left + width/height)."""

    x: float
    y: float
    w: float = Field(ge=0.0)
    h: float = Field(ge=0.0)

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def intersects(self, other: BBox, margin: float = 0.0) -> bool:
        """Kiểm tra va chạm AABB có tính khoảng đệm an toàn `margin`."""
        return not (
            self.x2 + margin <= other.x
            or other.x2 + margin <= self.x
            or self.y2 + margin <= other.y
            or other.y2 + margin <= self.y
        )

    def intersection_area(self, other: BBox) -> float:
        """Tính diện tích giao nhau (px²) giữa hai hộp."""
        ix0 = max(self.x, other.x)
        iy0 = max(self.y, other.y)
        ix1 = min(self.x2, other.x2)
        iy1 = min(self.y2, other.y2)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        return (ix1 - ix0) * (iy1 - iy0)

    def clamp(
        self,
        max_w: float,
        max_h: float,
        *,
        min_x: float = 0.0,
        min_y: float = 0.0,
    ) -> BBox:
        """Kẹp hộp hình học vào trong khung hợp lệ (co kích thước nếu vượt quá giới hạn)."""
        avail_w = max(1.0, max_w - min_x)
        avail_h = max(1.0, max_h - min_y)
        w = min(self.w, avail_w)
        h = min(self.h, avail_h)
        x = max(min_x, min(self.x, max_w - w))
        y = max(min_y, min(self.y, max_h - h))
        return BBox(x=round(x, 2), y=round(y, 2), w=round(w, 2), h=round(h, 2))


class AudioCue(BaseModel):
    """Mốc điều khiển âm thanh/Foley/nhịp cắt J/L-cut trong beat."""

    kind: Literal["foley", "sfx", "silence_drop", "j_cut", "l_cut"]
    tag: str = Field(default="none", max_length=64)
    offset_ms: int = 0
    duration_ms: int = Field(default=0, ge=0)
    gain_db: float = 0.0


class BoardSpec(BaseModel):
    """Đặc tả bảng tri thức HBT Tactile Desk trên sân khấu."""

    board_type: str = Field(default="bullets", max_length=48)
    title: str = Field(default="", max_length=160)
    bullets: list[str] = Field(default_factory=list)
    takeaway: str = Field(default="", max_length=200)
    data: dict[str, Any] = Field(default_factory=dict)
    bbox: BBox | None = None


class PuppetSpec(BaseModel):
    """Đặc tả nhân vật MC Puppet 2D hoặc Stickman cho 1 beat."""

    enabled: bool = True
    pose: str = Field(default="present_board", max_length=120)
    emotion: str = Field(default="auto", max_length=64)
    facing: Literal["left", "right"] = "right"
    interaction: str = Field(default="none", max_length=64)
    prop_query: str | None = Field(default=None, max_length=120)
    bbox: BBox | None = None


class BeatSpec(BaseModel):
    """Đơn vị dựng độc lập (Beat) làm chuẩn khóa cache nội dung & preflight."""

    id: str = Field(min_length=1, max_length=64)
    chapter: int = Field(default=1, ge=1, le=50)
    chapter_title: str = Field(default="", max_length=120)
    narration: str = Field(default="", max_length=2000)
    duration_sec: float = Field(default=3.0, gt=0.0, le=300.0)
    shot_type: ShotType = "desk_wide"
    transition_in: TransitionType = "editorial_cut"
    board: BoardSpec = Field(default_factory=BoardSpec)
    puppet: PuppetSpec = Field(default_factory=PuppetSpec)
    karaoke_bbox: BBox | None = None
    audio_cues: list[AudioCue] = Field(default_factory=list)
    media_path: str = Field(default="", max_length=260)
    image_prompt: str = Field(default="", max_length=600)
    sfx_tag: str = Field(default="whoosh", max_length=64)
    punch: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)

    def content_hash(
        self,
        *,
        aspect: AspectRatio = "9:16",
        fps: int = 30,
        theme: CinemaTheme = "cream",
        domain: str = "paper_classic",
    ) -> str:
        """Tính khóa SHA-256 quyết định của beat dựa trên hình ảnh, lời thoại & thông số dựng."""
        payload = {
            "render": {
                "aspect": aspect,
                "fps": int(fps),
                "theme": theme,
                "domain": str(domain),
            },
            "beat": self.model_dump(mode="json", exclude={"meta"}),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AudioPlan(BaseModel):
    """Cấu hình tổng thể của AudioDirector cho toàn bộ timeline."""

    voice_id: str = Field(default="Thanh Bình", max_length=120)
    music_mood: str = Field(default="curious_science", max_length=64)
    target_lufs: float = Field(default=-14.0, ge=-24.0, le=-8.0)
    max_breath_ms: int = Field(default=120, ge=0, le=1000)
    silence_drop_ms: int = Field(default=320, ge=0, le=2000)
    jl_cut_ms: int = Field(default=160, ge=0, le=1000)


class TimelineSpec(BaseModel):
    """Hợp đồng JSON duy nhất (IR v1) kết nối StickV/Core với Lõi Dựng Phim Hợp Nhất."""

    schema_version: Literal["1.0"] = "1.0"
    slug: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    source_engine: EngineSource = "cinema"
    topic: str = Field(default="science", max_length=64)
    domain: str = Field(default="paper_classic", max_length=64)
    theme: CinemaTheme = "cream"
    aspect: AspectRatio = "9:16"
    fps: int = Field(default=30, ge=15, le=60)
    outro: bool = True
    audio: AudioPlan = Field(default_factory=AudioPlan)
    beats: list[BeatSpec] = Field(default_factory=list)
    preflight_passed: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not str(out.get("domain") or "").strip():
            out["domain"] = "paper_classic"
        if str(out.get("domain")).strip().lower() == "cosmos":
            out["domain"] = "cosmos_mystery"
        return out

    @property
    def width(self) -> int:
        return ASPECT_DIMENSIONS[self.aspect][0]

    @property
    def height(self) -> int:
        return ASPECT_DIMENSIONS[self.aspect][1]

    @property
    def total_duration_sec(self) -> float:
        return round(sum(float(b.duration_sec) for b in self.beats), 3)
