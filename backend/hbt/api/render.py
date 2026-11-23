"""Dựng video: POST /projects/{slug}/render, GET /jobs/{id}, SSE /jobs/{id}/events, huỷ job."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from hbt.api.deps import State, file_url
from hbt.jobs import Job

router = APIRouter(tags=["render"])

URL_KEYS = (
    "video", "srt", "publish", "log", "cover", "youtube_cover", "trimmed_tail", "voice",
)  # fmt: skip
POLL_SECONDS = 0.2


class RenderRequest(BaseModel):
    preview: bool = False
    fps: Literal[30, 50, 60] | None = None
    outro: bool | None = None  # None → theo settings.outro của project
    # Xem nhanh chỉ dựng chừng này giây đầu; None = cả video (UI gửi 10)
    preview_seconds: float | None = Field(default=None, gt=0, le=60)
    allow_long_trim: bool = False  # chỉ sau khi đã nghe và xác nhận phần giọng bị cắt (> 8 s)
    aspect_mode: Literal["fill", "fit"] | None = None


class JobCreated(BaseModel):
    job_id: str


def _public_kind(job: Job) -> str:
    raw = getattr(job, "kind", "render")
    if raw in ("stickv", "stickv_render"):
        return "stickv"
    if raw in ("postv_quick", "postv_auto", "voice", "hbt_core_auto", "hbt_core_images"):
        return raw
    return "preview" if job.preview else "final"


def _format_output_url(val: object) -> object:
    if isinstance(val, str) and val.startswith("/api/"):
        return val
    return file_url(val) if isinstance(val, str) or val is None else val


def job_view(job: Job) -> dict:
    output = None
    if job.output is not None:
        output = {k: (_format_output_url(v) if k in URL_KEYS else v) for k, v in job.output.items()}
    return {
        "id": job.id,
        "project": job.slug,
        "slug": job.slug,
        "kind": _public_kind(job)
        if getattr(job, "kind", "") in ("stickv", "stickv_render")
        else getattr(job, "kind", "render"),
        "mode": getattr(job, "mode", "") or ("preview" if job.preview else "final"),
        "status": job.status,
        "progress": round(job.progress, 1),
        "step": job.step,
        "stage": getattr(job, "stage", "") or job.step,
        "current_beat": getattr(job, "current_beat", None),
        "total_beats": getattr(job, "total_beats", None),
        "log_tail": job.log_tail(),
        "output": output,
        "error": job.error,
        "needs_confirmation": job.needs_confirmation,
        "cut_audio": file_url(job.cut_audio),
        "preview": job.preview,
        "preview_seconds": job.preview_seconds,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def _job_list_row(j: Job) -> dict:
    view_out = job_view(j)["output"] if j.output is not None else None
    return {
        "id": j.id,
        "slug": j.slug,
        "kind": _public_kind(j),
        "mode": getattr(j, "mode", "") or ("preview" if j.preview else "final"),
        "status": j.status,
        "progress": round(j.progress, 1),
        "step": j.step,
        "stage": getattr(j, "stage", "") or j.step,
        "current_beat": getattr(j, "current_beat", None),
        "total_beats": getattr(j, "total_beats", None),
        "started_at": j.started_at,
        "finished_at": j.finished_at,
        "output": view_out,
        "error": j.error,
    }


@router.post("/projects/{slug}/render", response_model=JobCreated, status_code=202)
def start_render(slug: str, state: State, body: RenderRequest | None = None):
    body = body or RenderRequest()
    job = state.jobs.submit(
        slug,
        preview=body.preview,
        fps=body.fps,
        outro=body.outro,
        allow_long_trim=body.allow_long_trim,
        preview_seconds=body.preview_seconds,
        aspect_mode=body.aspect_mode,
    )
    return {"job_id": job.id}


@router.get("/jobs")
def list_active_jobs(state: State, include_recent: bool = False):
    """Chỉ đọc: job đang chạy/chờ; thêm `include_recent=true` để kèm các job vừa hoàn tất."""
    jobs_list = state.jobs.recent() if include_recent else state.jobs.active()
    return [_job_list_row(j) for j in jobs_list]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, state: State):
    return job_view(state.jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, state: State):
    return job_view(state.jobs.cancel(job_id))


@router.post("/projects/{slug}/unlock")
def unlock_project(slug: str, state: State):
    """Huỷ tác vụ bị kẹt và giải phóng toàn bộ cờ khoá của dự án."""
    return state.jobs.unlock_project(slug)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request, state: State):
    """SSE: `event: progress` với `{progress, step, message}`; kết thúc bằng `event: end` với
    `{status, error, output}`. Người nối sau vẫn nhận lại các sự kiện từ đầu."""
    job = state.jobs.get(job_id)

    async def stream():
        sent = 0
        while True:
            events = job.events_since(sent)
            for kind, data in events:
                if kind == "end" and data.get("output"):
                    data = {**data, "output": job_view(job)["output"]}
                yield {"event": kind, "data": json.dumps(data, ensure_ascii=False)}
            sent += len(events)
            if job.finished and not job.events_since(sent):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(POLL_SECONDS)

    return EventSourceResponse(stream())
