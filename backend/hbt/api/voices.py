"""Giọng đọc PostV: danh sách giọng VieNeu, hiện trạng giọng của dự án, job sinh giọng (6c, 6d)."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import FileResponse

from hbt.api.deps import State, file_url
from hbt.api.render import JobCreated
from hbt.postv.models import PostvProject
from hbt.postv.voice import (
    CHARS_PER_SECOND,
    DEFAULT_NARRATOR,
    VoiceError,
    build_plan,
    plan_signature,
    speakers_of,
)
from hbt.storage import BadRequest, ServiceUnavailable

router = APIRouter(tags=["voice"])


def _postv(state: State, slug: str) -> PostvProject:
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    return project


@router.get("/voices")
def list_voices(state: State):
    """Giọng VieNeu có sẵn (cùng nhãn nam/nữ). 503 khi chưa cài gói hoặc thiếu trọng số."""
    status = state.voice.status()
    if not status.ok:
        raise ServiceUnavailable(status.note)
    try:
        voices = state.voice.list_voices()
    except VoiceError as e:
        raise ServiceUnavailable(str(e)) from e
    return {"default": DEFAULT_NARRATOR, "voices": [v.view() for v in voices]}


@router.get("/voices/{voice_id}/sample")
def voice_sample(voice_id: str, state: State):
    """Nghe thử 1 câu mẫu của giọng VieNeu (có cache file trên disk)."""
    ws_dir = getattr(state.storage, "workspace_dir", None)
    if not ws_dir:
        from pathlib import Path

        ws_dir = Path("workspace")
    cache_dir = ws_dir / "cache" / "voice_samples"
    cache_dir.mkdir(parents=True, exist_ok=True)
    sample_file = cache_dir / f"{voice_id}.wav"
    if not sample_file.is_file():
        text = "Xin chào, đây là giọng đọc thử nghiệm của HBT Studio."
        data = None
        if state.voice is not None:
            try:
                data = state.voice.synthesize(text, voice_id)
            except Exception:
                data = None
        if data:
            sample_file.write_bytes(data)
        else:
            from hbt.postv.voice import _write_tone

            _write_tone(sample_file, 1.5, voice_id)
    return FileResponse(str(sample_file), media_type="audio/wav")


@router.get("/projects/{slug}/voice")
def voice_info(slug: str, state: State):
    """Giọng của dự án: file hiện có, ai đọc bằng giọng nào, và lời đã đổi sau khi sinh chưa.

    Chưa cài VieNeu thì vẫn trả (available=false, speakers rỗng) để UI dùng đường nhập file."""
    project = _postv(state, slug)
    folder = state.storage.project_dir(slug)
    v = project.voice
    status = state.voice.status()
    chars = sum(len(s.voice.strip()) for s in project.segments)
    info: dict = {
        "engine": v.engine,
        "file": v.file,
        "url": file_url(v.file) if v.file and (folder / v.file).is_file() else None,
        "available": status.ok,
        "note": None if status.ok else status.note,
        "seed": v.seed,
        "manual": dict(v.cast),
        "speakers": [],
        "segments": None,
        "seconds": None,
        "stale": None,
        "estimated_seconds": round(chars / CHARS_PER_SECOND, 1),
    }
    meta_path = folder / "build" / "voice_segments.json"
    meta = None
    if v.engine == "vieneu" and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
    if meta:
        info["segments"], info["seconds"] = meta.get("segments"), meta.get("seconds")
    if status.ok:
        try:
            plan, cast = build_plan(project, state.voice.list_voices())
        except VoiceError:
            return info  # kịch bản trống hoặc giọng chọn tay không còn: để UI nhắc
        info["speakers"] = [
            {"speaker": s, "voice_id": cast[s], "manual": s in v.cast} for s in speakers_of(project)
        ]
        if meta:
            info["stale"] = meta.get("signature") != plan_signature(plan)
    return info


@router.post("/projects/{slug}/voice/synthesize", response_model=JobCreated, status_code=202)
def synthesize(slug: str, state: State):
    """Sinh giọng cho cả kịch bản như một job (tiến độ theo đoạn, huỷ được: dùng `/jobs/{id}`)."""
    job = state.jobs.submit_voice(slug)
    return {"job_id": job.id}
