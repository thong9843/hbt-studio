"""Router API cho Chatting theo §11."""

from __future__ import annotations

import json
import os
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.chatting.llm import DEFAULT_MODEL, GeminiChatClient, sanitize_chat_raw
from hbt.chatting.models import ChatDoc, Message
from hbt.chatting.stickers import count_stickers_per_tag
from hbt.chatting.store import (
    delete_project,
    get_project_dir,
    list_projects,
    load_chat,
    load_job,
    load_source,
    save_avatar,
    save_chat,
    save_job,
    save_source,
)

router = APIRouter(tags=["chatting"])


class CreateChatBody(BaseModel):
    input: str = Field(min_length=1, max_length=20000)
    platform: Literal["messenger", "instagram", "zalo"] = "messenger"
    background: str = "minecraft4-1080p60"
    direct_script: bool = False
    target_duration_s: float | None = Field(default=None, ge=30.0, le=300.0)
    model: str | None = Field(default=None)
    auto_fetch_online: bool = True


class RegenChatBody(BaseModel):
    auto_fetch_online: bool | None = None


class RerollAssetBody(BaseModel):
    kind: Literal["meme", "sticker", "sfx"]
    auto_fetch_online: bool | None = None


class RenderChatBody(BaseModel):
    preview: bool = False
    aspect_mode: Literal["fill", "fit"] | None = None


@router.get("/chatting/status")
def get_chatting_status(state: State) -> dict[str, Any]:
    """Kiểm tra trạng thái Gemini API Key và thư viện sticker (không bao giờ trả về lỗi 500)."""
    model_name = os.environ.get(
        "CHATTING_MODEL", getattr(state.settings, "chatting_model", DEFAULT_MODEL)
    )
    client = GeminiChatClient(model=model_name)
    llm_info = client.check_status()
    sticker_counts = count_stickers_per_tag(state.settings.library_dir)

    return {
        **llm_info,
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

    # 1. Kiểm tra Gemini API Key nếu dùng chế độ viết AI
    if not body.direct_script:
        model_name = body.model or os.environ.get(
            "CHATTING_MODEL", getattr(state.settings, "chatting_model", DEFAULT_MODEL)
        )
        client = GeminiChatClient(model=model_name)
        status = client.check_status()

        is_fake_llm = os.environ.get("CHATTING_FAKE_LLM") == "1"
        if not is_fake_llm and not status["gemini_configured"]:
            raise HTTPException(
                status_code=503,
                detail="Chưa cấu hình GEMINI_API_KEY. Thêm khoá vào .env rồi thử lại.",
            )

    # 2. Khởi tạo slug và ghi job.json ban đầu
    slug = f"chat-{uuid.uuid4().hex[:6]}"
    save_job(
        state.settings.workspace_dir,
        slug,
        {
            "slug": slug,
            "status": "running",
            "phase": "fetch",
            "percent": 5,
            "text": "Bắt đầu khởi tạo dự án...",
        },
    )

    # 3. Gửi job vào hàng đợi
    job = state.jobs.submit_chatting_auto(
        raw_input=raw_input,
        platform=body.platform,
        background_name=body.background,
        slug=slug,
        direct_script=body.direct_script,
        target_duration_s=body.target_duration_s,
        auto_fetch_online=body.auto_fetch_online,
        model=body.model,
    )

    # Cập nhật job_id vào job.json
    save_job(
        state.settings.workspace_dir,
        slug,
        {
            "job_id": job.id,
            "slug": slug,
            "status": "running",
            "phase": "fetch",
            "percent": 5,
            "text": "Bắt đầu khởi tạo dự án...",
        },
    )

    return {
        "slug": slug,
        "job_id": job.id,
    }


@router.get("/chatting/{slug}/job")
def get_chatting_project_job(slug: str, state: State) -> dict[str, Any]:
    """Lấy trạng thái tiến trình từ workspace/chatting/<slug>/job.json."""
    job_data = load_job(state.settings.workspace_dir, slug)
    if not job_data:
        raise HTTPException(status_code=404, detail="Không có job nào cho dự án này")
    return job_data


@router.get("/chatting/{slug}")
def get_chatting_project(slug: str, state: State) -> dict[str, Any]:
    """Lấy dữ liệu chat.json, source.json và danh sách renders của dự án."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    job_data = load_job(state.settings.workspace_dir, slug)

    if not project_dir.is_dir():
        if job_data and job_data.get("status") == "running":
            return {
                "slug": slug,
                "doc": None,
                "source": None,
                "renders": [],
                "preview_url": None,
                "job": job_data,
            }
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    try:
        doc = load_chat(state.settings.workspace_dir, slug)
    except FileNotFoundError as err:
        if job_data and job_data.get("status") == "running":
            return {
                "slug": slug,
                "doc": None,
                "source": None,
                "renders": [],
                "preview_url": None,
                "job": job_data,
            }
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
def regen_chatting_project(
    slug: str,
    state: State,
    body: RegenChatBody | None = None,
) -> dict[str, Any]:
    """Viết lại kịch bản bằng Gemini từ source.json gốc và chạy Smart Asset Director."""
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
    model_name = os.environ.get(
        "CHATTING_MODEL", getattr(state.settings, "chatting_model", DEFAULT_MODEL)
    )
    client = GeminiChatClient(model=model_name)

    is_fake_llm = os.environ.get("CHATTING_FAKE_LLM") == "1"
    if not is_fake_llm:
        st = client.check_status()
        if not st["gemini_configured"]:
            raise HTTPException(
                status_code=503,
                detail="Chưa cấu hình GEMINI_API_KEY. Thêm khoá vào .env rồi thử lại.",
            )

    try:
        chat_raw, llm_timings = client.generate_chat(
            title=source.get("title", doc.title),
            body=source.get("body", ""),
            comments=source.get("comments"),
            platform=doc.platform,
        )
        chat_raw = sanitize_chat_raw(chat_raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi sinh kịch bản Gemini: {e}") from e

    # Cập nhật messages, warnings và title (khớp người gửi với doc.characters hiện tại)
    char_map: dict[str, str] = {}
    new_rights = [c["id"] for c in chat_raw.get("characters", []) if c.get("side") == "right"]
    new_lefts = [c["id"] for c in chat_raw.get("characters", []) if c.get("side") != "right"]
    old_rights = [c.id for c in doc.characters if c.side == "right"]
    old_lefts = [c.id for c in doc.characters if c.side != "right"]

    default_old_right = (
        old_rights[0] if old_rights else (doc.characters[0].id if doc.characters else "me")
    )
    default_old_left = (
        old_lefts[0] if old_lefts else (doc.characters[-1].id if doc.characters else "other")
    )

    for nr in new_rights:
        char_map[nr] = default_old_right
    for i, nl in enumerate(new_lefts):
        char_map[nl] = old_lefts[i] if i < len(old_lefts) else default_old_left

    messages: list[Message] = []
    for m in chat_raw.get("messages", []):
        sender = char_map.get(
            m["from"], default_old_right if m["from"] in new_rights else default_old_left
        )
        messages.append(
            Message(
                from_=sender,
                text=m["text"],
                sticker=m.get("sticker"),
                meme_id=m.get("meme_id"),
                beat_role=m.get("beat_role"),
                intensity=int(m.get("intensity", 2)),
                meme_query=m.get("meme_query"),
                sfx_query=m.get("sfx_query"),
                sfx_id=m.get("sfx_id"),
                asset_origin=m.get("asset_origin"),
            )
        )

    allow_online = (
        body.auto_fetch_online
        if (body is not None and body.auto_fetch_online is not None)
        else doc.auto_fetch_online
    )
    doc.title = chat_raw.get("title", doc.title)
    doc.auto_fetch_online = allow_online
    doc.messages = messages
    doc.warnings = chat_raw.get("warnings", [])

    from hbt.shared.asset_director import AssetDirector

    director = AssetDirector(
        state.settings.library_dir, state.settings.workspace_dir, engine="chatting"
    )
    doc, report = director.direct_chat_doc(doc, auto_fetch_online=allow_online)
    director_summary = {
        "memes_kept": report.memes_kept,
        "memes_stripped": report.memes_stripped,
        "sfx_kept": report.sfx_kept,
        "fetched_online_count": report.fetched_online_count,
    }
    save_chat(state.settings.workspace_dir, slug, doc)

    # Cập nhật timings
    timings = source.get("timings", {})
    timings.update(llm_timings)
    timings["director_summary"] = director_summary
    source["timings"] = timings
    source["director_summary"] = director_summary
    save_source(state.settings.workspace_dir, slug, source)

    return {
        "ok": True,
        "doc": doc.model_dump(by_alias=True),
        "timings": timings,
        "director_summary": director_summary,
    }


@router.post("/chatting/{slug}/messages/{msg_id}/reroll-asset")
def reroll_chatting_message_asset(
    slug: str,
    msg_id: int,
    body: RerollAssetBody,
    state: State,
) -> dict[str, Any]:
    """Đổi nhanh 1 chạm meme/sticker hoặc SFX cho 1 tin nhắn (không trùng trong video)."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    try:
        doc = load_chat(state.settings.workspace_dir, slug)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Không đọc được chat.json: {e}") from e

    if msg_id < 0 or msg_id >= len(doc.messages):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tin nhắn chỉ số {msg_id}")

    msg = doc.messages[msg_id]
    allow_online = (
        body.auto_fetch_online if body.auto_fetch_online is not None else doc.auto_fetch_online
    )

    exclude_ids: set[str] = set()
    for m in doc.messages:
        if body.kind == "sfx":
            if m.sfx_id:
                exclude_ids.add(m.sfx_id)
        else:
            if m.meme_id:
                exclude_ids.add(m.meme_id)

    from hbt.shared.asset_director import AssetDirector

    director = AssetDirector(
        state.settings.library_dir, state.settings.workspace_dir, engine="chatting"
    )
    query = (
        (msg.sfx_query or msg.text)
        if body.kind == "sfx"
        else (msg.meme_query or msg.sticker or msg.text)
    )
    resolved = director.reroll_asset(
        body.kind,
        query,
        exclude_ids=exclude_ids,
        auto_fetch_online=allow_online,
        prefer_greenmeme=(body.kind == "meme"),
    )
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail="Không còn tài nguyên mới phù hợp để đổi (hãy bật Tự tải online).",
        )

    if body.kind == "sfx":
        msg.sfx_id = resolved.asset_id
        msg.asset_origin = resolved.origin
    else:
        msg.meme_id = resolved.asset_id
        if not msg.sticker:
            msg.sticker = "soc"
        msg.asset_origin = resolved.origin

    save_chat(state.settings.workspace_dir, slug, doc)
    return {
        "ok": True,
        "msg_id": msg_id,
        "message": msg.model_dump(by_alias=True),
        "asset": resolved.model_dump(),
        "doc": doc.model_dump(by_alias=True),
    }


@router.post("/chatting/{slug}/render")
def render_chatting_project_api(slug: str, body: RenderChatBody, state: State) -> dict[str, Any]:
    """Gửi yêu cầu dựng video (xem nhanh hoặc bản đẹp)."""
    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    try:
        job = state.jobs.submit_chatting_render(
            slug=slug, preview=body.preview, aspect_mode=body.aspect_mode
        )
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


@router.post("/chatting/{slug}/media")
async def upload_chatting_media(
    slug: str,
    file: Annotated[UploadFile, File()],
    state: State,
) -> dict[str, Any]:
    """Tải ảnh hoặc video minh họa vào workspace/chatting/<slug>/media/."""
    from pathlib import Path

    project_dir = get_project_dir(state.settings.workspace_dir, slug)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án {slug}")

    ext = Path(file.filename or "media.png").suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        media_type = "image"
    elif ext in (".mp4", ".mov", ".gif"):
        media_type = "video"
    else:
        raise HTTPException(status_code=422, detail=f"Định dạng media không hỗ trợ: {ext}")

    media_dir = project_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{uuid.uuid4().hex[:8]}{ext}"
    target_path = media_dir / target_name
    content = await file.read()
    target_path.write_bytes(content)

    return {
        "media_type": media_type,
        "media_path": f"media/{target_name}",
    }
