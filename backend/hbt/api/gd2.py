"""GĐ2: kiểm và tạo dự án từ JSON nháp `hbt_draft` (docs/gd2/IMPLEMENT-GD2.md mục 4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hbt.api.deps import State
from hbt.gd2.service import check_draft
from hbt.gd2.store import (
    build_draft_doc,
    effective_draft,
    read_draft,
    set_approved,
    set_prompt,
    write_draft,
)
from hbt.script import check_script
from hbt.storage import BadRequest

router = APIRouter(tags=["gd2"])


class DraftBody(BaseModel):
    draft: Any  # chuỗi JSON người dùng dán, hoặc giá trị đã đọc


class DraftCreateBody(DraftBody):
    title: str | None = None


@router.post("/gd2/draft/check")
def check(body: DraftBody, state: State):
    """Chỉ kiểm, không ghi gì."""
    res = check_draft(body.draft, state.sensitive.load(), state.settings.library_dir)
    return res.to_dict()


@router.post("/gd2/draft/create")
def create(body: DraftCreateBody, state: State):
    words = state.sensitive.load()
    res = check_draft(body.draft, words, state.settings.library_dir)
    if not res.ok or res.script_check is None or res.script_check.merged is None:
        return JSONResponse(
            {"detail": f"JSON nháp có {len(res.errors)} lỗi, chưa tạo", "errors": res.errors},
            status_code=422,
        )
    split = res.split
    title = (body.title or "").strip() or split.topic
    if not title:
        raise BadRequest("Thiếu tiêu đề")
    project = state.storage.create(title, split.series_hint, scene_count=split.scene_count)
    slug = project.slug
    warnings = list(res.warnings)
    try:
        merged = check_script(project, split.script, words)
        if not merged.ok or merged.merged is None:  # không xảy ra khi check ở trên đã ok
            raise BadRequest(
                "JSON nháp không áp được: " + "; ".join(e["message"] for e in merged.errors)
            )
        state.storage.save(slug, merged.merged)
        write_draft(state.storage.project_dir(slug), build_draft_doc(split, res.prompt_ok))
        if res.music.entry is not None and res.music.path is not None:
            state.storage.attach_music(slug, res.music.path, res.music.entry.credit)
    except Exception:
        state.storage.delete(slug)  # không để lại dự án dở
        raise
    return {
        "slug": slug,
        "project": state.storage.load(slug).model_dump(mode="json"),
        "warnings": warnings,
        "music_match": res.to_dict()["music_match"],
    }


def _images(state: State, slug: str) -> list[str]:
    return [scene.image for scene in state.storage.load(slug).scenes]


@router.get("/projects/{slug}/draft")
def get_draft(slug: str, state: State):
    """Nháp kèm trạng thái duyệt ảnh tính tại lúc đọc (không ghi)."""
    folder = state.storage.project_dir(slug)
    doc = read_draft(folder)  # 404 khi không có nháp
    return effective_draft(doc, _images(state, slug))


class ApprovedBody(BaseModel):
    approved: bool


@router.put("/projects/{slug}/draft/images-approved")
def put_images_approved(slug: str, body: ApprovedBody, state: State):
    folder = state.storage.project_dir(slug)
    read_draft(folder)  # 404 trước khi đọc ảnh
    images = _images(state, slug)
    return effective_draft(set_approved(folder, body.approved, images), images)


class PromptBody(BaseModel):
    image_prompt: str


@router.put("/projects/{slug}/draft/scenes/{index}/prompt")
def put_prompt(slug: str, index: int, body: PromptBody, state: State):
    folder = state.storage.project_dir(slug)
    read_draft(folder)
    return effective_draft(set_prompt(folder, index, body.image_prompt), _images(state, slug))
