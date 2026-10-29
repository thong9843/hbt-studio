"""PostV: tách chữ dán, kiểm tra kịch bản, danh sách từ che (IMPLEMENT-POSTV.md mục 5)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.postv.censor import compile_censor
from hbt.postv.models import PostvProject
from hbt.postv.parse import MAX_TEXT, ParseResult, parse_threads_text
from hbt.postv.script import check_script
from hbt.sensitive import SensitiveWords
from hbt.storage import BadRequest, Conflict, Unprocessable

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
