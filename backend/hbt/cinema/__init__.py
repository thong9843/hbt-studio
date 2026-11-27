"""Lõi Dựng Phim Độc Bản Hợp Nhất (Unified Editorial Cinema Core — HBT Studio v10.0)."""

from __future__ import annotations

from hbt.cinema.cache import (
    BEAT_AUDIO_CHANNELS,
    BEAT_AUDIO_RATE,
    BEAT_PIX_FMT,
    BEAT_VIDEO_TIMESCALE,
    BeatCache,
    build_normalized_beat_flags,
)
from hbt.cinema.hardware import (
    CPU_LAYER_CACHE_MB,
    GPU_LAYER_CACHE_MB,
    HardwareProfile,
    detect_hardware,
    probe_nvenc_one_frame,
    reset_hardware_cache,
)
from hbt.cinema.layer_cache import FontCache, LayerCache, estimate_image_bytes
from hbt.cinema.schema import (
    ASPECT_DIMENSIONS,
    SHOT_TYPES,
    TRANSITION_TYPES,
    AspectRatio,
    AudioCue,
    AudioPlan,
    BBox,
    BeatSpec,
    BoardSpec,
    CinemaTheme,
    EngineSource,
    PuppetSpec,
    ShotType,
    TimelineSpec,
    TransitionType,
)
from hbt.shared.ffmpeg_utils import resolve_filter_complex_script_flag

__all__ = [
    "ASPECT_DIMENSIONS",
    "BEAT_AUDIO_CHANNELS",
    "BEAT_AUDIO_RATE",
    "BEAT_PIX_FMT",
    "BEAT_VIDEO_TIMESCALE",
    "CPU_LAYER_CACHE_MB",
    "GPU_LAYER_CACHE_MB",
    "SHOT_TYPES",
    "TRANSITION_TYPES",
    "AspectRatio",
    "AudioCue",
    "AudioPlan",
    "BBox",
    "BeatCache",
    "BeatSpec",
    "BoardSpec",
    "CinemaTheme",
    "EngineSource",
    "FontCache",
    "HardwareProfile",
    "LayerCache",
    "PuppetSpec",
    "ShotType",
    "TimelineSpec",
    "TransitionType",
    "build_normalized_beat_flags",
    "detect_hardware",
    "estimate_image_bytes",
    "probe_nvenc_one_frame",
    "reset_hardware_cache",
    "resolve_filter_complex_script_flag",
]
