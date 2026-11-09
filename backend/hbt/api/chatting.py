"""Router API cho Chatting theo §11."""

from __future__ import annotations

import json
import os
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.chatting.llm import OllamaClient
from hbt.chatting.models import ChatDoc, Message
from hbt.chatting.sources import parse_link
from hbt.chatting.stickers import count_stickers_per_tag
from hbt.chatting.store import (
    delete_project,
    get_project_dir,
    list_projects,
    load_chat,
    load_source,
    save_avatar,
    save_chat,
    save_source,
)

router = APIRouter(tags=["chatting"])


class CreateChatBody(BaseModel):
    input: str = Field(min_length=1, max_length=10000)
    platform: Literal["messenger", "zalo"] = "messenger"
    background: str = "minecraft4-1080p60"


class RenderChatBody(BaseModel):
    preview: bool = False


@router.get("/chatting/status")
def get_chatting_status(state: State) -> dict[str, Any]:
    """Kiểm tra trạng thái Ollama và thư viện sticker (không bao giờ trả về lỗi 500)."""
    default_m = "qwen2.5:3b-instruct"
    model_name = os.environ.get(
        "CHATTING_MODEL", getattr(state.settings, "chatting_model", default_m)
    )
    client = OllamaClient(model=model_name)
    ollama_info = client.check_status()
    sticker_counts = count_stickers_per_tag(state.settings.library_dir)

    return {
        **ollama_info,
        "stickers": sticker_counts,
        "total_stickers": sum(sticker_counts.values()),
    }


@router.get("/chatting/projects")
def list_chatting_projects(state: State) -> list[dict[str, Any]]:
    """Danh sách các dự án Chatting."""
    return list_projects(state.settings.workspace_dir)


@router.post("/chatting")
def create_chatting_project(body: CreateChatBody, state: State) -> dict[str, Any]:
    """Tạo dự án Chatting và khởi động job chatting_auto 4 pha."""
    raw_input = body.input.strip()
    kind, _ = parse_link(raw_input)

    # 1. Kiểm tra link Threads (bản này chưa hỗ trợ)
    if kind == "threads":
        raise HTTPException(
            status_code=422,
            detail="Chưa lấy được bài Threads, dán nội dung vào ô chat",
        )

    # 2. Kiểm tra Ollama
    default_m = "qwen2.5:3b-instruct"
    model_name = os.environ.get(
        "CHATTING_MODEL", getattr(state.settings, "chatting_model", default_m)
    )
    client = OllamaClient(model=model_name)
    status = client.check_status()

    is_fake_llm = os.environ.get("CHATTING_FAKE_LLM") == "1"
    if not is_fake_llm and not status["ollama_running"]:
        raise HTTPException(
            status_code=503,
            detail="Chưa thấy Ollama. Mở Ollama rồi thử lại.",
        )

    # 3. Gửi job vào hàng đợi
    job = state.jobs.submit_chatting_auto(
        raw_input=raw_input,
        platform=body.platform,
        background_name=body.background,
    )

    return {
        "slug": job.slug,
        "job_id": job.id,
    }


@router.get("/chatting/{slug}")
def get_chatting_project(slug: str, state: State) -> dict[str, Any]:
    """Lấy dữ liệu chat.json, source.json và danh sách renders của dự án."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    try:
        doc = load_chat(state.settings.workspace_dir, slug)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=404, detail=f"Không tìm thấy chat.json trong {slug}"
        ) from err
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dữ liệu chat.json không hợp lệ: {e}") from e

    source = load_source(state.settings.workspace_dir, slug)

    # Danh sách renders
    renders_dir = project_dir / "renders"
    renders_list: list[dict[str, Any]] = []
    if renders_dir.is_dir():
        for f in sorted(renders_dir.glob("render_*.json"), reverse=True):
            try:
                meta = json.loads(f.read_text(encoding="utf-8"))
                renders_list.append(meta)
            except Exception:
                pass

    preview_file = project_dir / "preview.mp4"
    has_preview = preview_file.is_file()

    return {
        "slug": slug,
        "doc": doc.model_dump(by_alias=True),
        "source": source,
        "renders": renders_list,
        "preview_url": f"/api/chatting/{slug}/preview.mp4" if has_preview else None,
    }


@router.put("/chatting/{slug}")
def update_chatting_project(slug: str, doc: ChatDoc, state: State) -> dict[str, Any]:
    """Cập nhật nội dung chat.json (kiểm tra đầy đủ quy tắc §3)."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    save_chat(state.settings.workspace_dir, slug, doc)
    return {"ok": True, "doc": doc.model_dump(by_alias=True)}


@router.post("/chatting/{slug}/avatar/{char_id}")
async def upload_chat_avatar(
    slug: str,
    char_id: str,
    state: State,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Tải ảnh avatar cho nhân vật (cắt vuông 256x256 px)."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    try:
        doc = load_chat(state.settings.workspace_dir, slug)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Lỗi đọc chat.json: {e}") from e

    # Tìm nhân vật
    char = next((c for c in doc.characters if c.id == char_id), None)
    if not char:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy nhân vật {char_id}")

    content = await file.read()
    try:
        rel_path = save_avatar(state.settings.workspace_dir, slug, char_id, content)
        char.avatar = rel_path
        save_chat(state.settings.workspace_dir, slug, doc)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Lỗi xử lý ảnh avatar: {e}") from e

    return {
        "ok": True,
        "char_id": char_id,
        "avatar": rel_path,
        "avatar_url": f"/api/chatting/{slug}/{rel_path}",
    }


@router.post("/chatting/{slug}/regen")
def regen_chatting_project(slug: str, state: State) -> dict[str, Any]:
    """Viết lại kịch bản bằng Ollama từ source.json gốc."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    source = load_source(state.settings.workspace_dir, slug)
    if not source:
        raise HTTPException(
            status_code=422,
            detail="Dự án không có thông tin bài viết gốc (source.json)",
        )

    doc = load_chat(state.settings.workspace_dir, slug)
    default_m = "qwen2.5:3b-instruct"
    model_name = os.environ.get(
        "CHATTING_MODEL", getattr(state.settings, "chatting_model", default_m)
    )
    client = OllamaClient(model=model_name)

    is_fake_llm = os.environ.get("CHATTING_FAKE_LLM") == "1"
    if not is_fake_llm:
        st = client.check_status()
        if not st["ollama_running"]:
            raise HTTPException(status_code=503, detail="Chưa thấy Ollama. Mở Ollama rồi thử lại.")

    try:
        chat_raw, llm_timings = client.generate_chat(
            title=source.get("title", doc.title),
            body=source.get("body", ""),
            comments=source.get("comments"),
            platform=doc.platform,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi sinh kịch bản Ollama: {e}") from e

    # Cập nhật messages và title
    messages: list[Message] = []
    for m in chat_raw.get("messages", []):
        messages.append(Message(from_=m["from"], text=m["text"], sticker=m.get("sticker")))

    doc.title = chat_raw.get("title", doc.title)
    doc.messages = messages
    save_chat(state.settings.workspace_dir, slug, doc)

    # Cập nhật timings
    timings = source.get("timings", {})
    timings.update(llm_timings)
    source["timings"] = timings
    save_source(state.settings.workspace_dir, slug, source)

    return {
        "ok": True,
        "doc": doc.model_dump(by_alias=True),
        "timings": timings,
    }


@router.post("/chatting/{slug}/render")
def render_chatting_project_api(slug: str, body: RenderChatBody, state: State) -> dict[str, Any]:
    """Gửi yêu cầu dựng video (xem nhanh hoặc bản đẹp)."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    try:
        job = state.jobs.submit_chatting_render(slug=slug, preview=body.preview)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Không thể bắt đầu dựng: {e}") from e

    return {
        "job_id": job.id,
        "slug": slug,
        "preview": body.preview,
    }


@router.delete("/chatting/{slug}")
def delete_chatting_project_api(slug: str, state: State) -> dict[str, Any]:
    """Xoá toàn bộ thư mục dự án Chatting."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    delete_project(state.settings.workspace_dir, slug)
    return {"ok": True, "slug": slug}


@router.get("/chatting/{slug}/renders/{filename}")
def serve_chatting_render(slug: str, filename: str, state: State):
    """Phục vụ file video đã dựng."""
    video_path = get_project_dir(state.settings.workspace_dir, slug) / "renders" / filename
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="File video không tồn tại")
    return FileResponse(str(video_path), media_type="video/mp4")


@router.get("/chatting/{slug}/avatars/{filename}")
def serve_chatting_avatar(slug: str, filename: str, state: State):
    """Phục vụ file avatar."""
    av_path = get_project_dir(state.settings.workspace_dir, slug) / "avatars" / filename
    if not av_path.is_file():
        raise HTTPException(status_code=404, detail="File avatar không tồn tại")
    return FileResponse(str(av_path), media_type="image/png")


@router.get("/chatting/{slug}/preview.mp4")
def serve_chatting_preview(slug: str, state: State):
    """Phục vụ file preview.mp4 mặc định."""
    p_path = get_project_dir(state.settings.workspace_dir, slug) / "preview.mp4"
    if not p_path.is_file():
        raise HTTPException(status_code=404, detail="Chưa có video xem nhanh")
    return FileResponse(str(p_path), media_type="video/mp4")
