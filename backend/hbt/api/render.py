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


class JobCreated(BaseModel):
    job_id: str


def job_view(job: Job) -> dict:
    output = None
    if job.output is not None:
        output = {k: (file_url(v) if k in URL_KEYS else v) for k, v in job.output.items()}
    return {
        "id": job.id,
        "project": job.slug,
        "status": job.status,
        "progress": round(job.progress, 1),
        "step": job.step,
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
    )
    return {"job_id": job.id}


@router.get("/jobs")
def list_active_jobs(state: State):
    """Chỉ đọc: job đang chạy và đang chờ (để giao diện nối lại sau khi tải lại trang)."""
    return [
        {
            "id": j.id,
            "slug": j.slug,
            "kind": "voice" if j.kind == "voice" else ("preview" if j.preview else "final"),
            "status": j.status,
            "progress": round(j.progress, 1),
            "step": j.step,
        }
        for j in state.jobs.active()
    ]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, state: State):
    return job_view(state.jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, state: State):
    return job_view(state.jobs.cancel(job_id))


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
