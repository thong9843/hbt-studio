"""API cho thư viện Meme & Sticker phông xanh (greenscreenmemes.com)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from hbt.api.deps import State
from hbt.postv.memes import MemeEntry

router = APIRouter(tags=["memes"])


class DownloadMemeBody(BaseModel):
    meme_id: str
    video_url: str
    title: str
    poster_url: str = ""
    source: str = ""
    license: str = "chưa rõ"


@router.get("/memes/search", response_model=list[MemeEntry])
async def search_memes(
    state: State,
    q: str = Query(default="", description="Từ khoá tìm kiếm meme"),
    count: int = Query(default=12, ge=1, le=24),
):
    """Tìm kiếm meme phông xanh từ greenscreenmemes.com (hoặc thư viện cục bộ)."""
    return await state.memes.search_online(query=q, count=count)


@router.get("/memes/library", response_model=list[MemeEntry])
def list_library_memes(state: State):
    """Danh sách meme đã tải về máy."""
    return state.memes.list()


@router.post("/memes/download", response_model=MemeEntry)
def download_meme_endpoint(body: DownloadMemeBody, state: State):
    """Tải một meme về lưu trữ cục bộ tại library/memes/."""
    return state.memes.download(
        meme_id=body.meme_id,
        video_url=body.video_url,
        title=body.title,
        poster_url=body.poster_url,
        source=body.source,
        license=body.license,
    )


@router.delete("/memes/{meme_id}")
def delete_meme_endpoint(meme_id: str, state: State):
    """Xoá một meme khỏi thư viện cục bộ."""
    state.memes.delete(meme_id)
    return {"status": "ok", "deleted": meme_id}
