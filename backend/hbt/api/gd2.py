"""GĐ2: kiểm và tạo dự án từ JSON nháp `hbt_draft` (docs/gd2/IMPLEMENT-GD2.md mục 4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hbt.api.deps import State, file_url
from hbt.api.render import JobCreated
from hbt.gd2.service import check_draft
from hbt.gd2.store import (
    build_draft_doc,
    effective_draft,
    read_draft,
    set_approved,
    set_prompt,
    write_draft,
)
from hbt.gd2.prefs import Gd2Prefs
from hbt.gd2.voice import is_stale, read_meta, spoken_chunks
from hbt.models import Project
from hbt.postv.voice import CHARS_PER_SECOND, VoiceError
from hbt.script import check_script
from hbt.storage import BadRequest, ServiceUnavailable, Unprocessable

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


@router.get("/projects/{slug}/draft/exists")
def draft_exists(slug: str, state: State):
    """Có bản nháp không? Trả 200 cả khi không có, để giao diện ẩn mục mà không sinh lỗi 404."""
    return {"exists": (state.storage.project_dir(slug) / "draft.json").is_file()}


# ------------------------------------------------------------------ giọng VieNeu cho HBT (G3)
def _hbt(state: State, slug: str) -> Project:
    project = state.storage.load_any(slug)
    if not isinstance(project, Project):
        raise BadRequest(f"'{slug}' là dự án PostV, giọng PostV nằm ở bước Kịch bản và giọng")
    return project


def _known_voices(state: State) -> set[str] | None:
    """Mã giọng VieNeu có sẵn; None khi chưa cài (không kiểm được)."""
    if not state.voice.status().ok:
        return None
    try:
        return {v.id for v in state.voice.list_voices()}
    except VoiceError as e:
        raise ServiceUnavailable(str(e)) from e


class VoicePrefBody(BaseModel):
    voice_id: str | None = None


@router.get("/gd2/voice/preferences")
def get_voice_preferences(state: State):
    """Giọng HBT chọn lần trước (nhớ ở `workspace/settings/gd2.json`)."""
    return {"voice_id": Gd2Prefs(state.settings.workspace_dir).voice_id()}


@router.put("/gd2/voice/preferences")
def put_voice_preferences(body: VoicePrefBody, state: State):
    voice_id = (body.voice_id or "").strip() or None
    known = _known_voices(state) if voice_id else None
    if voice_id and known is not None and voice_id not in known:
        raise Unprocessable("Giọng đã chọn không có trong danh sách giọng VieNeu")
    Gd2Prefs(state.settings.workspace_dir).set_voice_id(voice_id)
    return {"voice_id": voice_id}


@router.get("/projects/{slug}/draft/voice")
def hbt_voice_info(slug: str, state: State):
    """Giọng của dự án HBT: file hiện có, giọng đã chọn, lời đã đổi sau khi sinh chưa.

    Chưa cài VieNeu thì vẫn trả (`available=false`) để giao diện hiện ghi chú và dùng đường thả file."""
    project = _hbt(state, slug)
    folder = state.storage.project_dir(slug)
    status = state.voice.status()
    v = project.voice
    has_file = bool(v and (folder / v.file).is_file())
    meta = read_meta(folder)
    chars = sum(len(c) for s in project.scenes for c in spoken_chunks(s.voice))
    return {
        "available": status.ok,
        "note": None if status.ok else status.note,
        "voice_id": Gd2Prefs(state.settings.workspace_dir).voice_id(),
        "has_file": has_file,
        "file": v.file if has_file and v else None,
        "url": file_url(f"projects/{slug}/{v.file}") if has_file and v else None,
        "from_vieneu": bool(has_file and v and v.file == "voice.wav" and meta),
        "seconds": meta.get("seconds") if meta else None,
        "used_voice_id": meta.get("voice_id") if meta else None,
        "stale": is_stale(project, folder) if has_file else None,
        "scenes": sum(1 for s in project.scenes if spoken_chunks(s.voice)),
        "estimated_seconds": round(chars / CHARS_PER_SECOND, 1),
    }


class HbtVoiceBody(BaseModel):
    voice_id: str | None = None  # bỏ trống = giọng đã nhớ


@router.post("/projects/{slug}/draft/voice", response_model=JobCreated, status_code=202)
def hbt_voice_synthesize(slug: str, state: State, body: HbtVoiceBody | None = None):
    """Sinh giọng VieNeu cho cả video HBT như một job (tiến độ theo cảnh, huỷ được: `/jobs/{id}`).

    Giọng đã dùng được nhớ cho lần sau."""
    _hbt(state, slug)
    prefs = Gd2Prefs(state.settings.workspace_dir)
    voice_id = ((body.voice_id if body else None) or prefs.voice_id() or "").strip()
    if not voice_id:
        raise Unprocessable("Chưa chọn giọng đọc")
    job = state.jobs.submit_hbt_voice(slug, voice_id)
    prefs.set_voice_id(voice_id)
    return {"job_id": job.id}

