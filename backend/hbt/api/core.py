"""Router API cho HBT Core (Chế độ V1 Bán tự động / JSON Thủ công & Chế độ V2 1-Click Prompt).

- Chế độ V1: Hoàn toàn không gọi API ngoài (0 token, offline 100%). Nhận khối JSON kịch bản
  (hoặc đối tượng đã chỉnh sửa trực tiếp), đồng bộ vào project và kích hoạt chuỗi:
  Sinh giọng VieNeu-TTS -> BGM acrossfade -> Chèn SFX -> Render FFmpeg kẹp luồng.
- Chế độ V2: Gọi Gemini 1.5 Flash sinh kịch bản JSON chuẩn V1 rồi tự động nạp vào pipeline V1.
  Nếu gặp lỗi API (hết quota / lỗi mạng / thiếu key), trả về thông báo rõ ràng kèm
  `fallback_v1=True` để giao diện tự động chuyển hướng sang chế độ V1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.core.audio import scan_music_by_topic, scan_sfx_library
from hbt.core.gemini_client import (
    GeminiClientError,
    generate_script_from_prompt,
    load_gemini_api_key,
)
from hbt.core.models import VALID_TOPICS, HbtCoreScript
from hbt.core.render import TOPIC_SERIES_LABELS, sync_script_to_project
from hbt.storage import BadRequest, Unprocessable

router = APIRouter(tags=["hbt_core"])


class CoreV1CheckBody(BaseModel):
    """Kiểm tra khối JSON kịch bản V1 (dạng chuỗi hoặc dict)."""

    script: str | dict[str, Any]


class CoreV1RenderBody(BaseModel):
    """Yêu cầu dựng video từ Chế độ V1 (Offline 100%, 0 token)."""

    script: str | dict[str, Any]
    slug: str | None = None
    voice_id: str | None = None
    fps: int = Field(default=30)
    preview: bool = False


class CoreV2PromptBody(BaseModel):
    """Yêu cầu Chế độ V2 (1-Click Prompt -> Gemini Flash -> Pipeline V1)."""

    prompt: str = Field(min_length=1, max_length=4000)
    topic: str | None = Field(default=None)
    slug: str | None = None
    voice_id: str | None = None
    fps: int = Field(default=30)
    preview: bool = False
    auto_render: bool = True


def _parse_v1_script(raw: str | dict[str, Any]) -> HbtCoreScript:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise BadRequest("Khối JSON kịch bản không được để trống")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise Unprocessable(
                f"JSON không hợp lệ (dòng {exc.lineno}, cột {exc.colno}): {exc.msg}"
            ) from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise BadRequest("Dữ liệu kịch bản phải là chuỗi JSON hoặc đối tượng JSON")

    if not isinstance(data, dict):
        raise Unprocessable("Kịch bản JSON phải là một đối tượng `{ title, topic, segments }`")
    try:
        return HbtCoreScript.model_validate(data)
    except Exception as exc:
        raise Unprocessable(f"Cấu trúc kịch bản chưa hợp lệ: {exc}") from exc


def _ensure_project_for_script(
    state: State,
    script: HbtCoreScript,
    slug: str | None = None,
) -> tuple[str, Path]:
    if slug and state.storage.exists(slug):
        project = state.storage.load(slug)
        project_dir = state.storage.project_dir(slug)
    else:
        series_name = TOPIC_SERIES_LABELS.get(script.topic, "Vì Sao")
        scene_count = max(3, min(12, len(script.segments)))
        project = state.storage.create(
            title=script.title,
            series=series_name,
            scene_count=scene_count,
        )
        slug = project.slug
        project_dir = state.storage.project_dir(slug)

    project = sync_script_to_project(project, project_dir, script)
    state.storage.save(slug, project)
    return slug, project_dir


@router.get("/hbt-core/assets")
def get_hbt_core_assets(state: State, slug: str | None = None) -> dict[str, Any]:
    """Liệt kê SFX cục bộ (`library/sfx/`), nhạc theo chủ đề (`library/music/`),
    ảnh có sẵn của dự án và trạng thái cấu hình Gemini API key.
    """
    lib_dir = state.settings.library_dir
    sfx_items = [
        {"id": item["id"], "name": item["name"], "category": item["category"]}
        for item in scan_sfx_library(lib_dir)
    ]
    topic_music: dict[str, list[str]] = {}
    for t in VALID_TOPICS:
        topic_music[t] = [p.name for p in scan_music_by_topic(lib_dir, topic=t, seed=t)[:4]]

    images: list[str] = []
    if slug and state.storage.exists(slug):
        img_dir = state.storage.project_dir(slug) / "images"
        if img_dir.is_dir():
            images = sorted(
                f"images/{p.name}"
                for p in img_dir.iterdir()
                if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
            )

    has_gemini_key = bool(load_gemini_api_key())
    return {
        "topics": list(VALID_TOPICS),
        "sfx": sfx_items,
        "sfx_presets": ["whoosh", "pop", "impact", "none"],
        "topic_music": topic_music,
        "images": images,
        "gemini_configured": has_gemini_key,
    }


@router.post("/hbt-core/v1/check")
def check_v1_script(body: CoreV1CheckBody) -> dict[str, Any]:
    """Kiểm tra và chuẩn hóa khối JSON kịch bản ở Chế độ V1 (Offline 100%, 0 token)."""
    script = _parse_v1_script(body.script)
    return {
        "ok": True,
        "script": script.model_dump(mode="json"),
        "segments_count": len(script.segments),
    }


@router.post("/hbt-core/v1/render", status_code=202)
def start_v1_render(body: CoreV1RenderBody, state: State) -> dict[str, Any]:
    """Chế độ V1: Lưu kịch bản JSON (0 token, offline) và kích hoạt chuỗi dựng tự động."""
    script = _parse_v1_script(body.script)
    slug, _ = _ensure_project_for_script(state, script, slug=body.slug)
    job = state.jobs.submit_hbt_core_auto(
        slug=slug,
        script=script,
        voice_id=body.voice_id,
        fps=body.fps,
        preview=body.preview,
    )
    return {
        "ok": True,
        "mode": "v1",
        "slug": slug,
        "job_id": job.id,
        "script": script.model_dump(mode="json"),
    }


@router.post("/hbt-core/v2/prompt")
def run_v2_one_click_prompt(body: CoreV2PromptBody, state: State):
    """Chế độ V2 (1-Click Prompt):
    Gọi Gemini 1.5 Flash sinh kịch bản JSON chuẩn V1 -> tự động nạp vào pipeline V1 để xuất video.
    Nếu gặp lỗi API (hết quota / lỗi mạng / thiếu key), trả về mã lỗi kèm `fallback_v1=True`
    để giao diện thông báo rõ ràng và tự động chuyển hướng sang chế độ V1.
    """
    try:
        script = generate_script_from_prompt(
            body.prompt,
            topic_hint=body.topic,
        )
    except GeminiClientError as exc:
        status_code = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": exc.message,
                "reason": exc.reason,
                "fallback_v1": exc.fallback_v1,
            },
        )

    slug, _ = _ensure_project_for_script(state, script, slug=body.slug)
    job_id: str | None = None
    if body.auto_render:
        job = state.jobs.submit_hbt_core_auto(
            slug=slug,
            script=script,
            voice_id=body.voice_id,
            fps=body.fps,
            preview=body.preview,
        )
        job_id = job.id

    return {
        "ok": True,
        "mode": "v2",
        "slug": slug,
        "job_id": job_id,
        "script": script.model_dump(mode="json"),
    }


@router.get("/projects/{slug}/core-script")
def get_project_core_script(slug: str, state: State) -> dict[str, Any]:
    """Đọc kịch bản HBT Core (`core_script.json`) của dự án, hoặc suy ra từ `project.json`."""
    project = state.storage.load(slug)
    project_dir = state.storage.project_dir(slug)
    core_path = project_dir / "core_script.json"
    if core_path.is_file():
        try:
            raw = json.loads(core_path.read_text(encoding="utf-8"))
            script = HbtCoreScript.model_validate(raw)
            return {"slug": slug, "script": script.model_dump(mode="json")}
        except Exception:
            pass

    segments = [
        {
            "order": idx,
            "text": sc.voice or f"Lời thoại phân đoạn {idx}",
            "image": sc.image or f"scene-{idx:02d}.png",
            "sfx": "impact" if sc.punch else "whoosh",
        }
        for idx, sc in enumerate(project.scenes, start=1)
    ]
    fallback_script = HbtCoreScript(
        title=project.title,
        topic="science",
        segments=segments,
    )
    return {"slug": slug, "script": fallback_script.model_dump(mode="json")}
