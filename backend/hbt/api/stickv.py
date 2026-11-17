"""Router API cho động cơ StickV (`/api/stickv`)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.shared.llm import AVAILABLE_GEMINI_MODELS, GEMINI_MODEL, GeminiClientError
from hbt.stickv.llm import generate_stickv_script
from hbt.stickv.models import StickvAspect, StickvBeat, StickvProject, StickvTheme
from hbt.stickv.storage import (
    create_stickv_project,
    delete_stickv_project,
    list_stickv_projects,
    load_stickv_project,
    save_stickv_project,
    stickv_project_dir,
)
from hbt.storage import BadRequest, NotFound, Unprocessable

router = APIRouter(tags=["stickv"])

ALLOWED_MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class StickvCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str = "science"
    aspect: StickvAspect = "9:16"
    theme: StickvTheme = "cream"
    target_minutes: float = Field(default=1.0, ge=0.25, le=20.0)
    gemini_model: str = ""
    beats: list[StickvBeat] = Field(default_factory=list)


class StickvGenerateBody(BaseModel):
    idea: str = Field(min_length=1, max_length=2000)
    topic: str = "science"
    aspect: StickvAspect = "9:16"
    theme: StickvTheme = "cream"
    target_minutes: float = Field(default=1.0, ge=0.25, le=20.0)
    model: str = ""
    slug: str = ""


class StickvRenderBody(BaseModel):
    preview: bool = False


@router.get("/stickv")
def list_stickv(state: State) -> dict[str, Any]:
    projects = list_stickv_projects(state.settings.workspace_dir)
    return {
        "items": [p.model_dump(mode="json") for p in projects],
        "gemini_models": list(AVAILABLE_GEMINI_MODELS),
        "default_model": GEMINI_MODEL,
    }


@router.post("/stickv", status_code=201)
def create_stickv(body: StickvCreateBody, state: State) -> dict[str, Any]:
    proj = create_stickv_project(
        state.settings.workspace_dir,
        title=body.title,
        topic=body.topic,
        aspect=body.aspect,
        theme=body.theme,
        target_minutes=body.target_minutes,
        gemini_model=body.gemini_model,
        beats=body.beats,
    )
    return {"project": proj.model_dump(mode="json")}


@router.post("/stickv/generate")
def generate_stickv(body: StickvGenerateBody, state: State) -> dict[str, Any]:
    try:
        title, beats, meta = generate_stickv_script(
            idea=body.idea,
            topic=body.topic,
            aspect=body.aspect,
            target_minutes=body.target_minutes,
            model=body.model or None,
        )
    except GeminiClientError as exc:
        raise Unprocessable(str(exc)) from exc
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc

    if body.slug:
        proj = load_stickv_project(state.settings.workspace_dir, body.slug)
        proj = proj.model_copy(
            update={
                "title": title,
                "topic": body.topic,
                "aspect": body.aspect,
                "theme": body.theme,
                "target_minutes": body.target_minutes,
                "gemini_model": body.model or GEMINI_MODEL,
                "beats": beats,
            }
        )
        proj = save_stickv_project(state.settings.workspace_dir, proj)
    else:
        proj = create_stickv_project(
            state.settings.workspace_dir,
            title=title,
            topic=body.topic,
            aspect=body.aspect,
            theme=body.theme,
            target_minutes=body.target_minutes,
            gemini_model=body.model or GEMINI_MODEL,
            beats=beats,
        )
    return {"project": proj.model_dump(mode="json"), "meta": meta}


@router.get("/stickv/{slug}")
def get_stickv(slug: str, state: State) -> dict[str, Any]:
    proj = load_stickv_project(state.settings.workspace_dir, slug)
    return {"project": proj.model_dump(mode="json")}


@router.put("/stickv/{slug}")
def update_stickv(slug: str, body: StickvProject, state: State) -> dict[str, Any]:
    load_stickv_project(state.settings.workspace_dir, slug)
    if body.slug != slug:
        body = body.model_copy(update={"slug": slug})
    saved = save_stickv_project(state.settings.workspace_dir, body)
    return {"project": saved.model_dump(mode="json")}


@router.delete("/stickv/{slug}")
def remove_stickv(slug: str, state: State) -> dict[str, Any]:
    delete_stickv_project(state.settings.workspace_dir, slug)
    return {"ok": True, "deleted": slug}


@router.post("/stickv/{slug}/beats/{beat_id}/media")
async def upload_beat_media(
    slug: str,
    beat_id: str,
    state: State,
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    proj = load_stickv_project(state.settings.workspace_dir, slug)
    raw_name = Path(file.filename or "clip.mp4").name
    ext = Path(raw_name).suffix.lower()
    if ext not in ALLOWED_MEDIA_EXTS:
        raise Unprocessable(f"Định dạng '{ext}' chưa hỗ trợ cho beat StickV")

    safe_stem = _SAFE_RE.sub("-", Path(raw_name).stem).strip("-.") or beat_id
    pdir = stickv_project_dir(state.settings.workspace_dir, slug)
    media_dir = pdir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    target = media_dir / f"{beat_id}_{safe_stem}{ext}"
    target.write_bytes(await file.read())
    rel_path = f"media/{target.name}"

    updated_beats = [
        b.model_copy(update={"media_path": rel_path}) if b.id == beat_id else b for b in proj.beats
    ]
    saved = save_stickv_project(
        state.settings.workspace_dir, proj.model_copy(update={"beats": updated_beats})
    )
    return {"ok": True, "media_path": rel_path, "project": saved.model_dump(mode="json")}


@router.post("/stickv/{slug}/render", status_code=202)
def render_stickv_endpoint(
    slug: str,
    body: StickvRenderBody,
    state: State,
) -> dict[str, Any]:
    proj = load_stickv_project(state.settings.workspace_dir, slug)
    if not proj.beats:
        raise Unprocessable("Kịch bản StickV chưa có beat nào để dựng")
    job = state.jobs.submit_stickv_render(slug, preview=body.preview)
    return {"job_id": job.id, "slug": slug, "preview": body.preview}


@router.get("/stickv/{slug}/renders/{filename}")
def serve_stickv_render(slug: str, filename: str, state: State) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise Unprocessable("Tên tệp không hợp lệ")
    pdir = stickv_project_dir(state.settings.workspace_dir, slug)
    target = (pdir / "renders" / filename).resolve()
    if not target.is_file():
        raise NotFound(f"Không tìm thấy video '{filename}'")
    return FileResponse(target)
