"""Project: danh sách, tạo, đọc/lưu/xoá, nhân bản, ảnh xem trước từng cảnh."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from hbt.api.deps import State, file_url
from hbt.models import MAX_SCENES, MIN_SCENES, Project
from hbt.pipeline.preview import resize_png, scene_preview_png
from hbt.storage import Conflict, NotFound

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1)
    series: str = ""
    scene_count: int = Field(default=8, ge=MIN_SCENES, le=MAX_SCENES)


class ProjectDuplicate(BaseModel):
    title: str | None = None


class ProjectSummary(BaseModel):
    slug: str
    title: str
    updated_at: str
    thumb: str | None  # URL ảnh cảnh 1; None → giao diện dùng ảnh mặc định HBT
    last_render: dict | None
    error: str | None = None


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(state: State):
    items = []
    for item in state.storage.list_projects():
        item["thumb"] = file_url(item["thumb"])
        if item["last_render"]:
            item["last_render"]["video"] = file_url(item["last_render"]["video"])
        items.append(item)
    return items


@router.post("/projects", response_model=Project, status_code=201)
def create_project(body: ProjectCreate, state: State):
    return state.storage.create(body.title, body.series, body.scene_count)


@router.get("/projects/{slug}", response_model=Project)
def get_project(slug: str, state: State):
    return state.storage.load(slug)


@router.put("/projects/{slug}", response_model=Project)
def put_project(slug: str, body: Project, state: State):
    state.storage.load(slug)  # 404 nếu chưa có; PUT không tạo project mới
    return state.storage.save(slug, body)


@router.delete("/projects/{slug}", status_code=204)
def delete_project(slug: str, state: State) -> Response:
    if state.jobs.is_busy(slug):
        raise Conflict("Project đang được dựng, hãy huỷ job trước khi xoá")
    state.storage.delete(slug)
    return Response(status_code=204)


@router.post("/projects/{slug}/duplicate", response_model=Project, status_code=201)
def duplicate_project(slug: str, state: State, body: ProjectDuplicate | None = None):
    return state.storage.duplicate(slug, body.title if body else None)


@router.get("/projects/{slug}/scenes/{scene_index}/preview.png")
def scene_preview(
    slug: str,
    scene_index: int,
    state: State,
    w: int | None = Query(default=None, ge=16, le=1080, description="chiều rộng thu nhỏ (px)"),
) -> Response:
    """`scene_index` tính từ 0 (cảnh đầu tiên là 0)."""
    project = state.storage.load(slug)
    if not 0 <= scene_index < len(project.scenes):
        raise NotFound(
            f"Project '{slug}' không có scene_index {scene_index} (0..{len(project.scenes) - 1})"
        )
    png = scene_preview_png(project, state.storage.project_dir(slug), scene_index, state.brand_dir)
    if w and w < 1080:
        png = resize_png(png, w)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})
