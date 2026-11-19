"""Router REST API cho Lõi Dựng Phim Hợp Nhất (`/api/cinema`)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.cinema.adapters import core_script_to_timeline, stickv_to_timeline
from hbt.cinema.cache import BeatCache
from hbt.cinema.compositor import DirtyRectCompositor
from hbt.cinema.contact_sheet import render_contact_sheet
from hbt.cinema.hardware import detect_hardware
from hbt.cinema.preflight import PreflightQualityGate
from hbt.cinema.schema import AspectRatio, CinemaTheme, TimelineSpec
from hbt.core.models import HbtCoreScript
from hbt.shared.tts.worker_pool import WarmTTSPool
from hbt.stickv.models import StickvProject
from hbt.stickv.storage import load_stickv_project
from hbt.storage import BadRequest, NotFound

router = APIRouter(prefix="/cinema", tags=["cinema"])

_SAFE_JPG_RE = re.compile(r"^[A-Za-z0-9._-]+\.(?:jpg|jpeg|png)$", re.IGNORECASE)
_SAFE_MP4_RE = re.compile(r"^[A-Za-z0-9_-]+\.mp4$", re.IGNORECASE)
_TTS_POOLS: dict[str, WarmTTSPool] = {}


def _get_tts_pool(models_dir: Path) -> WarmTTSPool:
    key = str(Path(models_dir).resolve())
    pool = _TTS_POOLS.get(key)
    if pool is None:
        pool = WarmTTSPool(Path(models_dir), idle_ttl_sec=600.0)
        _TTS_POOLS[key] = pool
    return pool


class _CinemaSourceBody(BaseModel):
    timeline: TimelineSpec | None = None
    stickv_slug: str | None = None
    stickv_project: StickvProject | None = None
    core_script: HbtCoreScript | None = None
    aspect: AspectRatio = "9:16"
    fps: int = Field(default=30, ge=15, le=60)
    theme: CinemaTheme = "cream"


class CinemaPreflightBody(_CinemaSourceBody):
    auto_fix: bool = True


class CinemaContactSheetBody(_CinemaSourceBody):
    cols: int = Field(default=4, ge=1, le=6)
    run_preflight: bool = True


class CinemaRenderBeatBody(_CinemaSourceBody):
    beat_id: str | None = None
    beat_index: int = Field(default=0, ge=0)
    preview: bool = True


def _resolve_timeline(body: _CinemaSourceBody, state: State) -> TimelineSpec:
    if body.timeline is not None:
        return body.timeline
    if body.stickv_project is not None:
        return stickv_to_timeline(body.stickv_project, run_director=False, run_preflight=False)
    if body.stickv_slug:
        proj = load_stickv_project(state.settings.workspace_dir, body.stickv_slug)
        return stickv_to_timeline(proj, run_director=False, run_preflight=False)
    if body.core_script is not None:
        return core_script_to_timeline(
            body.core_script,
            aspect=body.aspect,
            fps=body.fps,
            theme=body.theme,
            run_director=False,
            run_preflight=False,
        )
    raise BadRequest("Cần cung cấp `timeline`, `stickv_slug`, `stickv_project` hoặc `core_script`")


def _cinema_dirs(state: State) -> tuple[Path, Path]:
    base = state.settings.workspace_dir / "cinema"
    sheets_dir = base / "contact_sheets"
    cache_dir = base / "beat_cache"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return sheets_dir, cache_dir


@router.get("/hardware")
def get_cinema_hardware() -> dict[str, Any]:
    """Trả về hồ sơ CPU/GPU thực tế sau bước 1-frame NVENC probe."""
    return detect_hardware().model_dump(mode="json")


@router.post("/preflight")
def run_cinema_preflight(body: CinemaPreflightBody, state: State) -> dict[str, Any]:
    """Chạy PreflightQualityGate (AABB Auto-Reflow + Anti-Parrot + Pacing) trên timeline."""
    spec = _resolve_timeline(body, state)
    report = PreflightQualityGate().validate_and_reflow(spec, auto_fix=body.auto_fix)
    return report.model_dump(mode="json")


@router.post("/contact-sheet")
def generate_cinema_contact_sheet(body: CinemaContactSheetBody, state: State) -> dict[str, Any]:
    """Xuất ảnh Contact Sheet 1 trang cho toàn bộ beat (< 2 giây)."""
    spec = _resolve_timeline(body, state)
    report = (
        PreflightQualityGate().validate_and_reflow(spec, auto_fix=True)
        if body.run_preflight
        else None
    )
    target_spec = report.repaired_spec if report is not None else spec
    sheets_dir, _ = _cinema_dirs(state)
    digest = hashlib.sha256(
        json.dumps(target_spec.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    safe_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", target_spec.slug).strip("-") or "cinema"
    filename = f"sheet_{safe_slug}_{digest}.jpg"
    out_jpg = sheets_dir / filename
    meta = render_contact_sheet(
        target_spec,
        out_jpg,
        cols=body.cols,
        preflight_report=report,
    )
    return {
        "ok": True,
        "filename": filename,
        "url": f"/api/cinema/contact-sheet/{filename}",
        "preflight_ok": report.ok if report is not None else target_spec.preflight_passed,
        "preflight_fixed": report.fixed_count if report is not None else 0,
        **meta,
    }


@router.get("/contact-sheet/{filename}")
def serve_cinema_contact_sheet(filename: str, state: State) -> FileResponse:
    """Trả về ảnh Contact Sheet đã sinh (chặn path traversal)."""
    if "/" in filename or "\\" in filename or ".." in filename or not _SAFE_JPG_RE.match(filename):
        raise BadRequest("Tên tệp Contact Sheet không hợp lệ")
    sheets_dir, _ = _cinema_dirs(state)
    target = (sheets_dir / filename).resolve()
    if target.parent != sheets_dir.resolve() or not target.is_file():
        raise NotFound("Không tìm thấy Contact Sheet")
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.post("/render-beat")
def render_cinema_beat(body: CinemaRenderBeatBody, state: State) -> dict[str, Any]:
    """Dựng 1 beat qua DirtyRectCompositor + BeatCache để xem nhanh tức thì."""
    t0 = time.perf_counter()
    spec = _resolve_timeline(body, state)
    clean_spec = PreflightQualityGate().validate_and_reflow(spec, auto_fix=True).repaired_spec
    if not clean_spec.beats:
        raise BadRequest("Timeline chưa có beat nào để dựng")

    target_beat = None
    if body.beat_id:
        target_beat = next((b for b in clean_spec.beats if b.id == body.beat_id), None)
    if target_beat is None:
        idx = min(body.beat_index, len(clean_spec.beats) - 1)
        target_beat = clean_spec.beats[idx]

    w, h = clean_spec.width, clean_spec.height
    if body.preview:
        w, h = (540, 960) if clean_spec.aspect == "9:16" else (960, 540)

    b_hash = target_beat.content_hash(
        aspect=clean_spec.aspect,
        fps=clean_spec.fps,
        theme=clean_spec.theme,
        domain=clean_spec.domain,
    )
    cache_key = f"{b_hash[:40]}_{'prev' if body.preview else 'full'}"

    _, cache_dir = _cinema_dirs(state)
    bcache = BeatCache(cache_dir)
    cached = bcache.lookup(cache_key)
    if cached is not None:
        return {
            "ok": True,
            "beat_id": target_beat.id,
            "cache_hit": True,
            "cache_key": cache_key,
            "filename": cached.name,
            "url": f"/api/cinema/beat-file/{cached.name}",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "width": w,
            "height": h,
        }

    work_dir = state.settings.workspace_dir / "cinema" / "tmp"
    work_dir.mkdir(parents=True, exist_ok=True)
    beat_wav = work_dir / f"{cache_key}.wav"
    raw_mp4 = work_dir / f"{cache_key}.mp4"

    tts_pool = _get_tts_pool(state.settings.models_dir)
    tts_pool.synthesize(
        target_beat.narration or "Xin chào HBT Studio",
        clean_spec.audio.voice_id,
        beat_wav,
    )

    comp = DirtyRectCompositor()
    try:
        comp.render_beat_to_mp4(
            target_beat,
            clean_spec,
            raw_mp4,
            wav_path=beat_wav,
            library_dir=state.settings.library_dir,
            assets_dir=state.settings.assets_dir,
            width=w,
            height=h,
        )
        stored = bcache.store_from_file(cache_key, raw_mp4)
    finally:
        comp.layer_cache.close()
        raw_mp4.unlink(missing_ok=True)
        beat_wav.unlink(missing_ok=True)

    return {
        "ok": True,
        "beat_id": target_beat.id,
        "cache_hit": False,
        "cache_key": cache_key,
        "filename": stored.name,
        "url": f"/api/cinema/beat-file/{stored.name}",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "width": w,
        "height": h,
    }


@router.get("/beat-file/{filename}")
def serve_cinema_beat_file(filename: str, state: State) -> FileResponse:
    """Phục vụ video beat MP4 từ BeatCache (chặn path traversal)."""
    if "/" in filename or "\\" in filename or ".." in filename or not _SAFE_MP4_RE.match(filename):
        raise BadRequest("Tên tệp beat không hợp lệ")
    _, cache_dir = _cinema_dirs(state)
    target = (cache_dir / filename).resolve()
    if target.parent != cache_dir.resolve() or not target.is_file():
        raise NotFound("Không tìm thấy video beat")
    return FileResponse(target, media_type="video/mp4", headers={"Cache-Control": "no-cache"})
