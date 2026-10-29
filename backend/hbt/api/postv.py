"""PostV: tách chữ dán, kiểm tra kịch bản, danh sách từ che (IMPLEMENT-POSTV.md mục 5)."""

from __future__ import annotations

import io
from typing import Literal

from fastapi import APIRouter, Query, Response
from PIL import Image
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.postv.card import composite_preview, load_template, render_project_card
from hbt.postv.censor import compile_censor
from hbt.postv.models import PostvProject
from hbt.postv.parse import MAX_TEXT, ParseResult, parse_threads_text
from hbt.postv.script import check_script
from hbt.sensitive import SensitiveWords
from hbt.storage import BadRequest, Conflict, NotFound, StorageError, Unprocessable

router = APIRouter(tags=["postv"])


class ParseBody(BaseModel):
    text: str = Field(max_length=MAX_TEXT)


@router.post("/postv/parse", response_model=ParseResult)
def parse(body: ParseBody):
    """Hàm thuần: tách bài + bình luận từ chữ dán. Không ghi gì, không truy cập mạng."""
    if not body.text.strip():
        raise Unprocessable("Chưa có chữ để tách")
    return parse_threads_text(body.text)


@router.post("/projects/{slug}/postv/script/check")
def script_check(slug: str, state: State):
    """Ước thời lượng và nhắc từ nhạy cảm của dự án PostV (chỉ nhắc, không chặn)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    if state.jobs.is_busy(slug):
        raise Conflict("Dự án đang được dựng, hãy đợi xong rồi kiểm tra")
    hbt_words = state.sensitive.load()
    censor = compile_censor(hbt_words, state.postv_words.load())
    return check_script(project, censor, hbt_words)


@router.get("/settings/postv-words", response_model=SensitiveWords)
def get_postv_words(state: State):
    return state.postv_words.load()


@router.put("/settings/postv-words", response_model=SensitiveWords)
def put_postv_words(body: SensitiveWords, state: State):
    return state.postv_words.save(body)


def _preview_background(project: PostvProject, state) -> Image.Image | None:
    """Khung nền để xem thẻ: clip đầu của dự án, không có thì của thư viện, không có thì None."""
    ids = project.background.clip_ids or [e.id for e in state.backgrounds.list()]
    for clip_id in ids:
        try:
            return Image.open(state.backgrounds.thumb_path(clip_id)).copy()
        except (StorageError, OSError):
            continue
    return None


@router.get("/projects/{slug}/postv/card.png")
def card_png(
    slug: str,
    state: State,
    kind: Literal["hook", "post", "comment"] = "post",
    ref: str | None = None,
    w: int | None = Query(default=None, ge=16, le=1080, description="chiều rộng thu nhỏ (px)"),
    layer: bool = Query(default=False, description="true: lớp thẻ trong suốt 1080×1920"),
) -> Response:
    """Thẻ bài vẽ bằng Pillow theo dữ liệu đã lưu: tiêu đề, bài gốc hoặc một bình luận (`ref`)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    cfg = project.settings.censor
    censor = (
        compile_censor(state.sensitive.load(), state.postv_words.load())
        if cfg.enabled and cfg.blur_card
        else None
    )
    tpl = load_template(project.template if project.template == "story_cards" else "story_cards")
    if kind == "comment":
        if ref is None:
            raise Unprocessable("Cần `ref` (id bình luận) cho thẻ bình luận")
        if not any(c.id == ref for c in project.comments):
            raise NotFound(f"Không có bình luận '{ref}'")
    image = render_project_card(project, kind, ref, tpl, censor, cfg.text)
    out = image if layer else composite_preview(image, _preview_background(project, state))
    if w and w < out.width:
        out = out.resize((w, round(out.height * w / out.width)), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})
