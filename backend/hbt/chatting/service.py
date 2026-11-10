"""Dịch vụ tự động hoá Chatting và điều phối job (chatting_auto, chatting_render)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hbt.chatting.llm import OllamaClient, sanitize_chat_raw
from hbt.chatting.models import Character, ChatDoc, Message
from hbt.chatting.render import render_chat_video
from hbt.chatting.sources import (
    fetch_reddit,
    fetch_threads,
    parse_direct_script,
    parse_link,
)
from hbt.chatting.store import (
    get_project_dir,
    save_chat,
    save_job,
    save_source,
)
from hbt.postv.voice import VoiceProvider

logger = logging.getLogger(__name__)

ProgressEmit = Callable[[str, dict[str, Any]], None]


def run_chatting_auto_job(
    workspace_dir: Path,
    library_dir: Path,
    brand_dir: Path,
    voice_provider: VoiceProvider,
    chatting_model: str,
    raw_input: str,
    platform: str = "messenger",
    background_name: str = "minecraft4-1080p60",
    slug_override: str | None = None,
    direct_script: bool = False,
    target_duration_s: float | None = None,
    emit_event: ProgressEmit | None = None,
) -> tuple[str, Path]:
    """Chạy toàn bộ quy trình 4 pha của Chatting:
    1. Lấy bài (fetch)
    2. Viết chat (llm hoặc parse kịch bản trực tiếp)
    3. Giọng đọc (voice)
    4. Xem nhanh (preview)
    """
    slug = slug_override or f"chat-{int(time.time()) % 10000:04d}"

    def emit(phase: str, data: dict[str, Any]) -> None:
        save_job(
            workspace_dir,
            slug,
            {
                "slug": slug,
                "status": "done" if phase == "done" else "running",
                "phase": data.get("phase", phase),
                "percent": data.get("percent", 0),
                "text": data.get("text", ""),
                "timings": data.get("timings"),
                "video": data.get("video"),
                "updated_at": time.time(),
            },
        )
        if emit_event:
            emit_event(phase, data)

    timings: dict[str, Any] = {
        "fetch_s": 0.0,
        "llm_s": 0.0,
        "llm_tokens": 0,
        "llm_retry": 0,
        "model": chatting_model,
    }

    # Pha 1: Lấy bài
    emit("progress", {"phase": "fetch", "percent": 10, "text": "Đang lấy nội dung bài viết..."})
    t0_fetch = time.perf_counter()

    if direct_script:
        kind, link_url = "direct", None
        first_line = raw_input.strip().splitlines()[0] if raw_input.strip() else "Kịch bản"
        title = first_line[:40].strip()
        source_data = {
            "title": title,
            "body": raw_input,
            "comments": [],
            "source_url": None,
        }
    else:
        kind, link_url = parse_link(raw_input)
        if kind == "threads" and link_url:
            try:
                source_data = fetch_threads(link_url)
            except Exception as e:
                logger.warning("Không thể tải Threads trực tiếp: %s, dùng text dán", e)
                lines = [line.strip() for line in raw_input.strip().splitlines() if line.strip()]
                title = lines[0][:60] if lines else "Đoạn chat vui"
                body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0] if lines else "Nội dung"
                source_data = {
                    "title": title,
                    "body": body,
                    "comments": [],
                    "source_url": link_url,
                }
        elif kind == "reddit" and link_url:
            source_data = fetch_reddit(link_url)
        else:
            # Dán chữ
            lines = [line.strip() for line in raw_input.strip().splitlines() if line.strip()]
            title = lines[0][:60] if lines else "Đoạn chat vui"
            body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0] if lines else "Nội dung"
            source_data = {
                "title": title,
                "body": body,
                "comments": [],
                "source_url": None,
            }

    timings["fetch_s"] = round(time.perf_counter() - t0_fetch, 3)
    emit(
        "progress",
        {
            "phase": "fetch_done",
            "percent": 25,
            "text": f"Đã lấy xong bài ({timings['fetch_s']}s)",
            "timings": timings,
        },
    )

    # Đảm bảo thư mục dự án
    project_dir = get_project_dir(workspace_dir, slug)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Pha 2: Viết chat (hoặc phân tích kịch bản trực tiếp)
    if direct_script:
        emit(
            "progress",
            {
                "phase": "llm",
                "percent": 30,
                "text": "Đang phân tích kịch bản trực tiếp...",
                "timings": timings,
            },
        )
        chat_raw = parse_direct_script(raw_input)
        chat_raw = sanitize_chat_raw(chat_raw)
        timings["llm_s"] = 0.0
        timings["llm_tokens"] = 0
    else:
        emit(
            "progress",
            {
                "phase": "llm",
                "percent": 30,
                "text": "Ollama đang viết kịch bản chat...",
                "timings": timings,
            },
        )
        llm_client = OllamaClient(model=chatting_model)
        chat_raw, llm_timings = llm_client.generate_chat(
            title=source_data["title"],
            body=source_data["body"],
            comments=source_data.get("comments"),
            platform=platform,
            target_duration_s=target_duration_s,
        )
        timings.update(llm_timings)
        chat_raw = sanitize_chat_raw(chat_raw)

    # Khởi tạo ChatDoc (phân giọng khác nhau cho từng nhân vật trong Group Chat)
    default_voices = ["Adam bựa", "Trúc Ly", "Thiện Minh", "Mai Anh", "Hải Đăng"]
    characters: list[Character] = []
    for idx, c in enumerate(chat_raw.get("characters", [])):
        default_v = (
            "Adam bựa"
            if c["side"] == "right"
            else default_voices[(idx + 1) % len(default_voices)]
        )
        characters.append(
            Character(
                id=c["id"],
                name=c["name"],
                side=c["side"],
                voice=c.get("voice") or default_v,
                avatar=None,
            )
        )

    messages: list[Message] = []
    for m in chat_raw.get("messages", []):
        messages.append(
            Message(
                from_=m["from"],
                text=m["text"],
                display_text=m.get("display_text"),
                spoken_text=m.get("spoken_text"),
                sticker=m.get("sticker"),
            )
        )

    doc = ChatDoc(
        hbt_chat=1,
        title=chat_raw.get("title", source_data["title"]),
        platform=platform,
        source={"kind": kind, "url": link_url},
        background={"name": background_name, "seed": 7},
        target_duration_s=target_duration_s,
        characters=characters,
        messages=messages,
        warnings=chat_raw.get("warnings", []),
    )

    # Lưu chat.json và source.json
    save_chat(workspace_dir, slug, doc)
    source_record = {
        **source_data,
        "timings": timings,
    }
    save_source(workspace_dir, slug, source_record)

    emit(
        "progress",
        {
            "phase": "llm_done",
            "percent": 50,
            "text": f"Viết xong kịch bản ({timings['llm_s']}s, {timings['llm_tokens']} tokens)",
            "timings": timings,
            "slug": slug,
            "doc": doc.model_dump(by_alias=True),
        },
    )

    # Pha 3 & 4: Giọng đọc và Dựng xem nhanh
    def on_render_progress(pct: int, msg: str) -> None:
        scaled_pct = 50 + int(pct * 0.5)
        phase_name = "voice" if pct < 35 else "render"
        emit(
            "progress",
            {
                "phase": phase_name,
                "percent": scaled_pct,
                "text": msg,
                "timings": timings,
                "slug": slug,
            },
        )

    video_path = render_chat_video(
        workspace_dir=workspace_dir,
        slug=slug,
        doc=doc,
        voice_provider=voice_provider,
        library_dir=library_dir,
        brand_dir=brand_dir,
        preview=True,
        progress=on_render_progress,
    )

    emit(
        "done",
        {
            "phase": "done",
            "percent": 100,
            "text": "Hoàn tất! Video xem nhanh đã sẵn sàng.",
            "slug": slug,
            "video": f"/api/chatting/{slug}/renders/{video_path.name}",
            "timings": timings,
        },
    )

    return slug, video_path
