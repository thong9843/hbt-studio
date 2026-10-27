"""Project: danh sách, tạo, đọc/lưu/xoá, nhân bản, ảnh xem trước từng cảnh."""

from __future__ import annotations

import io

from fastapi import APIRouter, Query, Response
from PIL import Image
from pydantic import BaseModel, Field

from hbt.api.deps import State, file_url
from hbt.models import MAX_SCENES, MIN_SCENES, Project, Scene, Theme, Thumbnail
from hbt.pipeline.preview import resize_png, scene_preview_for, scene_preview_png
from hbt.pipeline.thumbnail import LOGO_FILE, render_cover
from hbt.storage import BadRequest, Conflict, NotFound, Unprocessable

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
    cover: str | None = None  # URL cover_9x16.jpg của lần dựng gần nhất có bìa
    last_final: dict | None = None  # bản đẹp mới nhất (cùng dạng last_render), không có → None


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(state: State):
    items = []
    for item in state.storage.list_projects():
        item["thumb"] = file_url(item["thumb"])
        item["cover"] = file_url(item["cover"])
        for key in ("last_render", "last_final"):
            if item[key]:
                item[key]["video"] = file_url(item[key]["video"])
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


class SceneReorder(BaseModel):
    order: list[int] = Field(description="cảnh mới thứ i là cảnh cũ order[i] (hoán vị của 0..n-1)")


@router.post("/projects/{slug}/scenes/reorder", response_model=Project)
def reorder_scenes(slug: str, body: SceneReorder, state: State):
    if state.jobs.is_busy(slug):
        raise Conflict("Project đang được dựng, hãy đợi xong rồi mới đổi thứ tự cảnh")
    return state.storage.reorder_scenes(slug, body.order)


@router.delete("/projects/{slug}/scenes/{scene_index}", response_model=Project)
def delete_scene(slug: str, scene_index: int, state: State):
    """Xoá một cảnh trong project (`scene_index` từ 0), giữ ràng buộc 3–12 cảnh."""
    if state.jobs.is_busy(slug):
        raise Conflict("Project đang được dựng, hãy huỷ job trước khi xoá cảnh")
    return state.storage.delete_scene(slug, scene_index)


class DraftPreview(BaseModel):
    scene: Scene
    theme: Theme | None = None  # bỏ trống → dùng theme đã lưu của project


@router.post("/projects/{slug}/scenes/{scene_index}/preview.png")
def draft_scene_preview(
    slug: str,
    scene_index: int,
    body: DraftPreview,
    state: State,
    w: int | None = Query(default=None, ge=16, le=1080),
) -> Response:
    """Xem trước một cảnh bản nháp (chưa lưu) để thấy kết quả ngay khi đang gõ."""
    project = state.storage.load(slug)
    if scene_index < 0:
        raise BadRequest("scene_index phải >= 0")
    if body.scene.image:
        state.storage.project_file(slug, body.scene.image)  # 422 nếu thoát khỏi thư mục project
    png = scene_preview_for(
        body.scene,
        body.theme or project.theme,
        state.storage.project_dir(slug),
        scene_index,
        state.brand_dir,
    )
    if w and w < 1080:
        png = resize_png(png, w)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})


class DraftThumbnail(BaseModel):
    thumbnail: Thumbnail | None = None  # bỏ trống → dùng khối thumbnail đã lưu của project


@router.post("/projects/{slug}/thumbnail/preview.jpg")
def draft_thumbnail_preview(
    slug: str,
    body: DraftThumbnail,
    state: State,
    w: int | None = Query(default=None, ge=16, le=1080),
) -> Response:
    """Xem trước ảnh bìa 1080×1920 theo bản nháp (chưa lưu); giao diện tự cắt khung 3:4 và 3:2."""
    project = state.storage.load(slug)
    thumb = body.thumbnail or project.thumbnail
    if thumb is None:
        raise Unprocessable("Project chưa có khối thumbnail (ảnh bìa)")
    if thumb.scene > len(project.scenes):
        raise Unprocessable(f"Cảnh nền {thumb.scene} vượt quá số cảnh ({len(project.scenes)})")
    image = project.scenes[thumb.scene - 1].image
    bg = state.storage.project_file(slug, image) if image else None
    if bg is None or not bg.is_file():
        raise Unprocessable(f"Cảnh {thumb.scene} chưa có ảnh để làm nền bìa")
    try:
        cover = render_cover(
            bg, thumb.lines, thumb.series or project.series, thumb.accent,
            state.brand_dir / LOGO_FILE,
        )  # fmt: skip
    except OSError as e:
        raise Unprocessable(f"Không vẽ được ảnh bìa: {e}") from e
    buf = io.BytesIO()
    if w and w < cover.width:
        cover = cover.resize((w, round(cover.height * w / cover.width)), Image.LANCZOS)
    cover.save(buf, format="JPEG", quality=90)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.post("/projects/{slug}/build/clean")
def clean_build(slug: str, state: State):
    """Dọn file tạm trong `build/` (giữ `timing.json`). 409 khi project đang được dựng."""
    state.storage.load(slug)  # 404 nếu không có project
    if state.jobs.is_busy(slug):
        raise Conflict("Project đang được dựng, hãy đợi xong hoặc huỷ job rồi mới dọn file tạm")
    return state.storage.clean_build(slug)


@router.get("/projects/{slug}/renders")
def list_renders(slug: str, state: State):
    """Lịch sử các lần xuất (mới nhất trước); đường dẫn file đã đổi thành URL."""
    state.storage.load(slug)
    items = state.storage.list_renders(slug)
    for item in items:
        for key in ("video", "srt", "publish", "log", "cover", "youtube_cover"):
            item[key] = file_url(item[key])
    return items
