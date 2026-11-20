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
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hbt.api.deps import State, file_url
from hbt.app_settings import resolve_cloudflare_config
from hbt.core.audio import scan_music_by_topic, scan_sfx_library
from hbt.core.gemini_client import (
    AVAILABLE_GEMINI_MODELS,
    MODELS,
    GeminiClientError,
    generate_script_from_prompt,
    is_valid_gemini_api_key,
    load_gemini_api_key,
)
from hbt.core.models import VALID_TOPICS, HbtCoreScript
from hbt.core.render import TOPIC_SERIES_LABELS, sync_script_to_project
from hbt.shared.image_gen.cloudflare_flux import (
    CloudflareImageError,
    derive_project_seed,
    generate_scene_image,
)
from hbt.storage import BadRequest, StorageError, Unprocessable

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hbt_core"])


def _fallback_error_response(
    *,
    error: str,
    message: str,
    reason: str = "internal_error",
    fallback_v1: bool = True,
    status_code: int = 200,
) -> JSONResponse:
    """Trả về phản hồi JSON có cấu trúc rõ ràng, tuyệt đối không để crash HTTP 500."""
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "success": False,
            "fallback_v1": fallback_v1,
            "error": error,
            "message": message,
            "detail": message,
            "reason": reason,
        },
    )


class CoreV1CheckBody(BaseModel):
    """Kiểm tra khối JSON kịch bản V1 (dạng chuỗi hoặc dict)."""

    script: str | dict[str, Any]


class CoreV1RenderBody(BaseModel):
    """Yêu cầu dựng video từ Chế độ V1 (Offline 100%, 0 token)."""

    script: str | dict[str, Any]
    slug: str | None = None
    voice_id: str | None = None
    fps: int = Field(default=60)
    preview: bool = False
    aspect_mode: Literal["fill", "fit"] = "fill"


class CoreV2PromptBody(BaseModel):
    """Yêu cầu Chế độ V2 (1-Click Prompt -> Gemini Flash -> Pipeline V1). Không giới hạn số từ."""

    prompt: str = Field(min_length=1)
    topic: str | None = Field(default=None)
    model_name: str | None = Field(default=None)
    selectedModel: str | None = Field(default=None)
    slug: str | None = None
    voice_id: str | None = None
    fps: int = Field(default=60)
    preview: bool = False
    aspect_mode: Literal["fill", "fit"] = "fill"
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


@router.get("/hbt/core/models")
@router.get("/hbt-core/models")
def get_hbt_core_models() -> Any:
    """Trả về danh sách các model Gemini thế hệ mới khả dụng cho Chế độ V2."""
    try:
        return {
            "models": AVAILABLE_GEMINI_MODELS,
            "default": MODELS[0],
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi không mong đợi tại GET /hbt/core/models: %s", exc)
        return {
            "models": [],
            "default": "gemini-3.8-flash",
            "error": str(exc),
        }


@router.get("/hbt-core/assets")
def get_hbt_core_assets(state: State, slug: str | None = None) -> Any:
    """Liệt kê SFX cục bộ (`library/sfx/`), nhạc theo chủ đề (`library/music/`),
    ảnh có sẵn của dự án và trạng thái cấu hình Gemini API key.
    """
    try:
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

        has_gemini_key = is_valid_gemini_api_key(load_gemini_api_key())
        cf_account, cf_token, cf_model = resolve_cloudflare_config(state.storage.workspace_dir)
        return {
            "topics": list(VALID_TOPICS),
            "sfx": sfx_items,
            "sfx_presets": ["whoosh", "pop", "impact", "none"],
            "topic_music": topic_music,
            "images": images,
            "gemini_configured": has_gemini_key,
            "gemini_models": AVAILABLE_GEMINI_MODELS,
            "cloudflare_configured": bool(cf_account and cf_token),
            "cloudflare_model": cf_model,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi không mong đợi tại GET /hbt-core/assets: %s", exc)
        return {
            "topics": list(VALID_TOPICS),
            "sfx": [],
            "sfx_presets": ["whoosh", "pop", "impact", "none"],
            "topic_music": {t: [] for t in VALID_TOPICS},
            "images": [],
            "gemini_configured": False,
            "gemini_models": AVAILABLE_GEMINI_MODELS,
            "cloudflare_configured": False,
            "error": str(exc),
        }


@router.post("/hbt-core/v1/check")
def check_v1_script(body: CoreV1CheckBody) -> Any:
    """Kiểm tra và chuẩn hóa khối JSON kịch bản ở Chế độ V1 (Offline 100%, 0 token)."""
    try:
        script = _parse_v1_script(body.script)
        return {
            "ok": True,
            "success": True,
            "script": script.model_dump(mode="json"),
            "segments_count": len(script.segments),
        }
    except StorageError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi không mong đợi tại POST /hbt-core/v1/check: %s", exc)
        return _fallback_error_response(
            error=str(exc),
            message=f"Không thể kiểm tra khối JSON kịch bản V1: {exc}",
            reason="v1_check_error",
            fallback_v1=True,
            status_code=422,
        )


@router.post("/hbt-core/v1/render", status_code=202)
def start_v1_render(body: CoreV1RenderBody, state: State) -> Any:
    """Chế độ V1: Lưu kịch bản JSON (0 token, offline) và kích hoạt chuỗi dựng tự động."""
    try:
        script = _parse_v1_script(body.script)
        slug, _ = _ensure_project_for_script(state, script, slug=body.slug)
        job = state.jobs.submit_hbt_core_auto(
            slug=slug,
            script=script,
            voice_id=body.voice_id,
            fps=body.fps,
            preview=body.preview,
            aspect_mode=body.aspect_mode,
        )
        return {
            "ok": True,
            "success": True,
            "mode": "v1",
            "slug": slug,
            "job_id": job.id,
            "script": script.model_dump(mode="json"),
        }
    except StorageError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi không mong đợi tại POST /hbt-core/v1/render: %s", exc)
        return _fallback_error_response(
            error=str(exc),
            message=f"Không thể khởi chạy chuỗi dựng video Chế độ V1: {exc}",
            reason="v1_render_error",
            fallback_v1=True,
            status_code=400,
        )


@router.post("/hbt-core/v2/prompt")
def run_v2_one_click_prompt(body: CoreV2PromptBody, state: State) -> Any:
    """Chế độ V2 (1-Click Prompt):
    Gọi Gemini 1.5 Flash sinh kịch bản JSON chuẩn V1 -> tự động nạp vào pipeline V1 để xuất video.
    Nếu gặp lỗi API (hết quota / lỗi mạng / thiếu key / lỗi bất ngờ), tuyệt đối không để crash 500;
    trả về JSON rõ ràng kèm `fallback_v1=True` để giao diện tự động chuyển hướng sang chế độ V1.
    """
    try:
        chosen_model = body.model_name or body.selectedModel
        script = generate_script_from_prompt(
            body.prompt,
            topic_hint=body.topic,
            model_name=chosen_model,
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
                aspect_mode=body.aspect_mode,
            )
            job_id = job.id

        return {
            "ok": True,
            "success": True,
            "fallback_v1": False,
            "mode": "v2",
            "slug": slug,
            "job_id": job_id,
            "script": script.model_dump(mode="json"),
        }
    except GeminiClientError as exc:
        logger.warning("Chế độ V2 chuyển hướng sang V1 do GeminiClientError: %s", exc)
        raw_code = exc.status_code if exc.status_code else 400
        status_code = raw_code if 400 <= raw_code < 500 else 503
        return _fallback_error_response(
            error=str(exc),
            message=exc.message,
            reason=exc.reason,
            fallback_v1=exc.fallback_v1,
            status_code=status_code,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi bất ngờ tại POST /hbt-core/v2/prompt: %s", exc)
        friendly_msg = (
            f"Hệ thống gặp sự cố khi tạo kịch bản tự động V2 ({exc}). "
            "Đã tự động chuyển sang Chế độ V1 (Phao cứu sinh) để bạn dán hoặc sửa JSON thủ công."
        )
        return _fallback_error_response(
            error=str(exc),
            message=friendly_msg,
            reason="internal_exception",
            fallback_v1=True,
            status_code=200,
        )


class CoreGenerateImagesBody(BaseModel):
    """Yêu cầu tự vẽ hàng loạt ảnh 2D cho HBT Core qua Cloudflare Workers AI."""

    overwrite: bool = False
    economy_mode: bool = False
    use_style_ref: bool = False
    script: str | dict[str, Any] | None = None


class CoreGenerateSceneImageBody(BaseModel):
    """Yêu cầu vẽ lại riêng 1 cảnh (0-based) cho HBT Core."""

    image_prompt: str | None = None
    economy_mode: bool = False
    use_style_ref: bool = False
    script: str | dict[str, Any] | None = None


class CorePrepareBody(BaseModel):
    """Yêu cầu 1 nút 'Chuẩn bị nội dung' 3 pha: Kịch bản -> Giọng VieNeu -> Ảnh 2D Cloudflare."""

    prompt: str = ""
    topic: str | None = None
    model_name: str | None = None
    selectedModel: str | None = None
    script: str | dict[str, Any] | None = None
    voice_id: str | None = None
    economy_mode: bool = False
    use_style_ref: bool = False
    overwrite_images: bool = False


def _missing_cloudflare_response() -> JSONResponse:
    msg = "Chưa cấu hình Cloudflare Account ID hoặc API Token. Vào Cài đặt để nhập khóa."
    return JSONResponse(
        status_code=400,
        content={"ok": False, "code": "missing_cloudflare_key", "detail": msg, "message": msg},
    )


@router.post("/hbt-core/{slug}/prepare", status_code=202)
def prepare_hbt_core(
    slug: str,
    state: State,
    body: CorePrepareBody | None = None,
) -> Any:
    """Chạy 1 job nền 3 pha: Kịch bản (0-25%) -> Giọng VieNeu (25-55%) -> Ảnh 2D (55-100%)."""
    body = body or CorePrepareBody()
    parsed_script: HbtCoreScript | None = None
    if body.script is not None:
        parsed_script = _parse_v1_script(body.script)
    elif not body.prompt.strip():
        raise BadRequest(
            "Cần nhập chủ đề (prompt) hoặc cung cấp kịch bản JSON để chuẩn bị nội dung"
        )

    target_slug = None if slug in ("_new", "new") else slug
    if parsed_script is not None:
        actual_slug, _ = _ensure_project_for_script(state, parsed_script, slug=target_slug)
    elif target_slug and state.storage.exists(target_slug):
        actual_slug = target_slug
    else:
        series_name = TOPIC_SERIES_LABELS.get((body.topic or "science").lower(), "Vì Sao")
        title_seed = body.prompt.strip()[:80] or "Video Hay Biết Tuốt"
        project = state.storage.create(title=title_seed, series=series_name, scene_count=3)
        actual_slug = project.slug

    chosen_model = body.model_name or body.selectedModel
    job = state.jobs.submit_hbt_core_prepare(
        actual_slug,
        prompt=body.prompt.strip(),
        topic=body.topic,
        model_name=chosen_model,
        script=parsed_script,
        voice_id=body.voice_id,
        economy_mode=body.economy_mode,
        overwrite_images=body.overwrite_images,
    )
    return {
        "ok": True,
        "slug": actual_slug,
        "job_id": job.id,
        "total": job.total_beats,
    }


@router.post("/hbt-core/{slug}/generate-images", status_code=202)
def generate_hbt_core_images(
    slug: str,
    state: State,
    body: CoreGenerateImagesBody | None = None,
) -> Any:
    """Chạy job nền sinh tuần tự ảnh 2D 1080x1920 cho toàn bộ cảnh HBT Core qua Cloudflare Flux."""
    body = body or CoreGenerateImagesBody()
    account_id, api_token, _ = resolve_cloudflare_config(state.storage.workspace_dir)
    if not account_id or not api_token:
        return _missing_cloudflare_response()

    actual_slug = slug
    existed = slug not in ("_new", "new") and state.storage.exists(slug)
    if body.script is not None:
        parsed = _parse_v1_script(body.script)
        target_slug = None if slug in ("_new", "new") else slug
        actual_slug, _ = _ensure_project_for_script(state, parsed, slug=target_slug)

    job = state.jobs.submit_hbt_core_images(
        actual_slug,
        overwrite=body.overwrite or (not existed),
        economy_mode=body.economy_mode,
    )
    return {
        "ok": True,
        "slug": actual_slug,
        "job_id": job.id,
        "total": job.total_beats,
    }


@router.post("/hbt-core/{slug}/scenes/{scene_index}/generate-image")
def generate_hbt_core_scene_image(
    slug: str,
    scene_index: int,
    state: State,
    body: CoreGenerateSceneImageBody | None = None,
) -> Any:
    """Vẽ lại riêng 1 cảnh (`scene_index` tính từ 0) và cập nhật `project.json`."""
    body = body or CoreGenerateSceneImageBody()
    account_id, api_token, model = resolve_cloudflare_config(state.storage.workspace_dir)
    if not account_id or not api_token:
        return _missing_cloudflare_response()

    actual_slug = slug
    if body.script is not None:
        parsed = _parse_v1_script(body.script)
        target_slug = None if slug in ("_new", "new") else slug
        actual_slug, _ = _ensure_project_for_script(state, parsed, slug=target_slug)

    project = state.storage.load(actual_slug)
    if scene_index < 0 or scene_index >= len(project.scenes):
        raise Unprocessable(
            f"Chỉ số cảnh {scene_index} không hợp lệ (dự án có {len(project.scenes)} cảnh)"
        )

    project_dir = state.storage.project_dir(actual_slug)
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    scene = project.scenes[scene_index]

    core_script_path = project_dir / "core_script.json"
    core_script_data: dict[str, Any] | None = None
    saved_prompt = ""
    if core_script_path.is_file():
        try:
            raw = json.loads(core_script_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("segments"), list):
                core_script_data = raw
                if scene_index < len(raw["segments"]) and isinstance(
                    raw["segments"][scene_index], dict
                ):
                    seg_raw = raw["segments"][scene_index]
                    saved_prompt = str(seg_raw.get("image_prompt") or "").strip()
        except Exception:  # noqa: BLE001
            core_script_data = None

    prompt_text = (body.image_prompt or "").strip() or saved_prompt
    card_text = " ".join(ln.text for ln in scene.card.lines).strip()
    fallback_ctx = f"{card_text}. {scene.voice}".strip(". ")

    rel_img = f"images/scene-{scene_index + 1:02d}.png"
    dest = images_dir / f"scene-{scene_index + 1:02d}.png"
    ref_candidates = []
    if scene_index > 0:
        if project.scenes and project.scenes[0].image:
            ref_candidates.append(project_dir / project.scenes[0].image)
        ref_candidates.append(images_dir / "scene-01.png")
    reference_image = next((p for p in ref_candidates if p.is_file()), None)

    try:
        generate_scene_image(
            prompt_text,
            dest,
            account_id=account_id,
            api_token=api_token,
            model=model,
            seed=derive_project_seed(actual_slug),
            reference_image=reference_image,
            use_style_ref=body.use_style_ref,
            economy_mode=body.economy_mode,
            fallback_context=fallback_ctx,
        )
    except CloudflareImageError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "code": exc.code, "detail": str(exc), "message": str(exc)},
        )

    project.scenes[scene_index].image = rel_img
    state.storage.save(actual_slug, project)
    reloaded = state.storage.load(actual_slug)
    actual_rel = reloaded.scenes[scene_index].image or rel_img
    if core_script_data is not None and scene_index < len(core_script_data["segments"]):
        seg = core_script_data["segments"][scene_index]
        if isinstance(seg, dict):
            seg["image"] = actual_rel
            if body.image_prompt is not None:
                seg["image_prompt"] = body.image_prompt.strip()
            core_script_path.write_text(
                json.dumps(core_script_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return {
        "ok": True,
        "slug": actual_slug,
        "scene_index": scene_index,
        "image": actual_rel,
        "url": file_url(f"projects/{actual_slug}/{actual_rel}"),
    }


@router.get("/projects/{slug}/core-script")
def get_project_core_script(slug: str, state: State) -> Any:
    """Đọc kịch bản HBT Core (`core_script.json`) của dự án, hoặc suy ra từ `project.json`."""
    try:
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
                "id": idx,
                "order": idx,
                "title": (
                    " ".join(ln.text for ln in sc.card.lines).strip()
                    if sc.card and sc.card.lines
                    else f"Phân đoạn {idx}"
                ),
                "text": sc.voice or f"Lời thoại phân đoạn {idx}",
                "sticker": "shock" if sc.punch else "question",
                "image_prompt": "",
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
    except StorageError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi bất ngờ tại GET /projects/%s/core-script: %s", slug, exc)
        return _fallback_error_response(
            error=str(exc),
            message=f"Không thể tải kịch bản HBT Core cho dự án '{slug}': {exc}",
            reason="core_script_load_error",
            fallback_v1=True,
            status_code=400,
        )
