"""Kiểm thử các module dùng chung trong `backend/shared/` và tính đồng thời không nghẽn."""

from __future__ import annotations

from pathlib import Path

from hbt.jobs import JobManager
from hbt.storage import Storage
from hbt.shared.ffmpeg_utils import (
    FFMPEG_ENCODE_CLAMP,
    FFMPEG_RESOURCE_CLAMP,
    build_acrossfade_filter_graph,
    build_scale_9_16_filter,
)
from hbt.shared.sse_manager import SSEProgressEmitter, format_sse_progress
from hbt.shared.tts_client import resolve_voice_id


def test_shared_tts_and_ffmpeg_and_sse() -> None:
    assert resolve_voice_id(None, "Binh") == "Binh"
    assert resolve_voice_id("vienneu_default", "Binh") == "Binh"
    assert resolve_voice_id("MaiAnh", "Binh") == "MaiAnh"

    assert "-threads" in FFMPEG_RESOURCE_CLAMP
    assert "-crf" in FFMPEG_ENCODE_CLAMP
    assert "1080:1920" in build_scale_9_16_filter(1080, 1920)

    fc, label = build_acrossfade_filter_graph(2, 20.0, crossfade_s=2.0)
    assert "acrossfade=d=2.0" in fc
    assert label == "[bgm]"

    events: list[tuple[float, str, str]] = []
    emitter = SSEProgressEmitter(lambda pct, step, msg, **_kw: events.append((pct, step, msg)))
    payload = emitter.emit(42.34, "voice", "Đang sinh giọng", current=3, total=10)
    assert payload == format_sse_progress(42.34, "voice", "Đang sinh giọng", current=3, total=10)
    assert events == [(42.34, "voice", "Đang sinh giọng")]


def test_job_manager_allows_non_blocking_concurrency(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "workspace", 50)
    jm = JobManager(storage, tmp_path / "library")
    try:
        # Đảm bảo pool có nhiều hơn 1 worker để HBT Core / PostV / Chatting không nghẽn nhau
        assert jm._pool._max_workers >= 3
    finally:
        jm.shutdown()
