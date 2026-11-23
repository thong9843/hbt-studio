"""Mô hình dữ liệu cho Smart Asset Director (dùng chung 4 động cơ)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BeatRole = Literal["setup", "build", "twist", "punchline", "reaction"]
AssetCategory = Literal["memes", "stickers", "sfx", "music"]
AssetOrigin = Literal["local", "online_fetched"]


class BeatCue(BaseModel):
    """Tín hiệu ngữ cảnh cho 1 câu thoại / phân cảnh."""

    index: int
    text: str = ""
    beat_role: str | None = None
    intensity: int = Field(default=2, ge=1, le=5)
    meme_query: str | None = None
    sticker_tag: str | None = None
    sfx_query: str | None = None
    est_time_s: float = 0.0


class PacingPolicy(BaseModel):
    """Luật khóa cứng mật độ meme/sticker/SFX cho từng động cơ."""

    max_visual_memes: int = 7
    visual_ratio_cap: float = 0.30
    target_seconds_per_meme: float = 16.0
    min_gap_beats: int = 2
    min_gap_seconds: float = 6.5
    forbid_consecutive: bool = True
    skip_opening_setup: bool = True
    max_punch_sfx: int = 5
    min_sfx_gap_seconds: float = 6.0
    video_meme_duration_range: tuple[float, float] = (1.2, 3.8)
    static_sticker_duration_range: tuple[float, float] = (0.9, 1.6)

    @classmethod
    def for_engine(cls, engine: str = "chatting") -> PacingPolicy:
        key = (engine or "chatting").strip().lower()
        if key == "postv":
            return cls(
                max_visual_memes=4,
                visual_ratio_cap=0.22,
                min_gap_beats=3,
                min_gap_seconds=8.0,
                max_punch_sfx=4,
                min_sfx_gap_seconds=6.0,
            )
        if key in ("core", "stickv"):
            return cls(
                max_visual_memes=3,
                visual_ratio_cap=0.20,
                min_gap_beats=3,
                min_gap_seconds=8.0,
                max_punch_sfx=4,
                min_sfx_gap_seconds=6.0,
            )
        return cls()


class DirectorConfig(BaseModel):
    """Cấu hình vận hành cho AssetDirector (an toàn cho CPU i5-10400)."""

    auto_fetch_online: bool = True
    cooldown_videos: int = 6
    local_score_threshold: float = 0.55
    search_timeout_s: float = 4.5
    download_timeout_s: float = 10.0
    max_fetch_visual: int = 6
    max_fetch_sfx: int = 3
    max_fetch_bgm: int = 1
    cache_ttl_s: float = 600.0


class AssetCandidate(BaseModel):
    """Một ứng viên tài nguyên (từ kho local hoặc kết quả tìm kiếm online)."""

    asset_id: str
    category: AssetCategory
    file: str
    path: str = ""
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = "local"
    source_id: str = ""
    duration_sec: float = 0.0
    score: float = 0.0


class ResolvedAsset(BaseModel):
    """Tài nguyên đã được chốt và sẵn sàng trên đĩa trong library/."""

    asset_id: str
    category: AssetCategory
    file: str
    path: str
    origin: AssetOrigin = "local"
    source: str = "local"
    source_id: str = ""
    title: str = ""
    duration_sec: float = 0.0
    score: float = 0.0


class DirectorReport(BaseModel):
    """Tóm tắt minh bạch kết quả điều phối của Smart Asset Director."""

    memes_kept: int = 0
    memes_stripped: int = 0
    sfx_kept: int = 0
    sfx_stripped: int = 0
    fetched_online_count: int = 0
    kept_visual_indices: list[int] = Field(default_factory=list)
    kept_sfx_indices: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
