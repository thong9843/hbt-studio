"""Tích hợp Gemini Flash API cho HBT Core V2 (1-Click Prompt), dùng nền tảng `hbt.shared.llm`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from hbt.core.models import HbtCoreScript
from hbt.shared.llm.gemini import (
    AVAILABLE_GEMINI_MODELS,
    BACKEND_DIR,
    GEMINI_BASE_URL,
    GEMINI_ENDPOINT,
    GEMINI_MODEL,
    MODELS,
    PLACEHOLDER_KEYS,
    REPO_ROOT,
    GeminiClientError,
    _clean_key_value,
    _extract_json_text,
    _safe_print_config,
    build_gemini_headers,
    build_gemini_url,
    generate_structured_json,
    is_valid_gemini_api_key,
    load_gemini_api_key,
    normalize_model_name,
    resolve_candidate_env_paths,
)
from hbt.shared.llm.gemini import (
    build_gemini_payload as _shared_build_gemini_payload,
)

__all__ = [
    "AVAILABLE_GEMINI_MODELS",
    "BACKEND_DIR",
    "GEMINI_BASE_URL",
    "GEMINI_ENDPOINT",
    "GEMINI_MODEL",
    "MODELS",
    "PLACEHOLDER_KEYS",
    "REPO_ROOT",
    "SYSTEM_PROMPT",
    "GeminiClientError",
    "_clean_key_value",
    "_extract_json_text",
    "_safe_print_config",
    "build_gemini_headers",
    "build_gemini_payload",
    "build_gemini_url",
    "generate_script_from_prompt",
    "is_valid_gemini_api_key",
    "load_gemini_api_key",
    "normalize_model_name",
    "resolve_candidate_env_paths",
]

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là biên kịch chuyên viết kịch bản video ngắn kiến thức chuẩn kênh 'Hay Biết Tuốt'.\n"
    "Hãy trả về DUY NHẤT một đối tượng JSON thuần 100% (KHÔNG bọc trong markdown ```json),\n"
    "tuân thủ nghiêm ngặt cấu trúc Schema kèm ví dụ Few-shot sau:\n\n"
    "{\n"
    '  "topic": "Tên chủ đề",\n'
    '  "total_segments": 8,\n'
    '  "segments": [\n'
    "    {\n"
    '      "id": 1,\n'
    '      "title": "TIÊU ĐỀ THẺ KEM NGẮN",\n'
    '      "text": "Câu thoại thuyết minh tiếng Việt tự nhiên, lôi cuốn...",\n'
    '      "sticker": "shock",\n'
    '      "image_prompt": "Cinematic shot of ancient Roman Colosseum under dramatic golden '
    "hour sunlight, ultra realistic, highly detailed historical atmosphere, "
    '9:16 vertical framing"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "YÊU CẦU KỊCH BẢN & PHONG CÁCH 'HAY BIẾT TUỐT':\n"
    "1. Mỗi video gồm 6 đến 8 phân đoạn (id đánh số liên tiếp từ 1..N, khớp với total_segments).\n"
    "2. KHÔNG GIỚI HẠN SỐ TỪ (hệ thống dùng VieNeu-TTS cục bộ không giới hạn): viết tự nhiên,\n"
    "   đầy đủ chiều sâu, không cần cắt gọt gượng ép theo mốc 750 từ.\n"
    "3. Nhịp điệu kể chuyện chuẩn Hay Biết Tuốt:\n"
    "   - Đoạn 1: Hook mở đầu giật gân, đặt nghịch lý hoặc câu hỏi khơi gợi tò mò.\n"
    '   - Các đoạn thân (2..N-1): Giải thích cơ chế, lật lại các lầm tưởng ("Nhưng khoan đã...").\n'
    "   - Đoạn cuối (N): Đặt câu hỏi kích thích bình luận + kết đúng câu chốt:\n"
    '     "Theo dõi Hay Biết Tuốt trên TikTok và YouTube nhé".\n'
    '4. Trường "title": Tiêu đề thẻ kem ngắn gọn, súc tích IN HOA (3-7 từ) nổi bật trên video.\n'
    '5. Trường "sticker": Chọn loại biểu cảm phù hợp: '
    "question | shock | laugh | think | check | warning.\n"
    '6. Trường "image_prompt": Câu mô tả sinh ảnh BẰNG TIẾNG ANH chi tiết, phong cách điện ảnh\n'
    "   chân thực (cinematic, photorealistic, dramatic lighting, 9:16 vertical framing) dành\n"
    "   riêng cho ComfyUI / Stable Diffusion / Flux."
)


def build_gemini_payload(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> dict[str, Any]:
    """Tạo payload chuẩn cho v1beta models/{model_name}:generateContent."""
    return _shared_build_gemini_payload(user_prompt, system_prompt, temperature=0.7)


def generate_script_from_prompt(
    user_prompt: str,
    *,
    topic_hint: str | None = None,
    model_name: str | None = None,
    api_key: str | None = None,
    env_file: Path | None = None,
    models: list[str] | None = None,
    timeout_s: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> HbtCoreScript:
    """Gọi Gemini Flash API sinh kịch bản JSON chuẩn V1 từ 1 câu prompt của người dùng."""
    prompt_clean = (user_prompt or "").strip()
    if not prompt_clean:
        raise GeminiClientError(
            "Câu nhắc (prompt) không được để trống.",
            reason="invalid_prompt",
            fallback_v1=False,
        )

    full_user_prompt = prompt_clean
    if topic_hint and topic_hint.strip():
        full_user_prompt = f"{prompt_clean}\n(Chủ đề ưu tiên: {topic_hint.strip()})"

    resolved_key = api_key if api_key is not None else load_gemini_api_key(env_file=env_file)
    parsed, _timings = generate_structured_json(
        SYSTEM_PROMPT,
        full_user_prompt,
        model=model_name,
        models=models,
        api_key=resolved_key,
        env_file=env_file,
        temperature=0.7,
        timeout=timeout_s,
        transport=transport,
    )
    try:
        if topic_hint and not parsed.get("topic"):
            parsed["topic"] = topic_hint
        return HbtCoreScript.model_validate(parsed)
    except Exception as exc:
        logger.warning("Phản hồi Gemini không đúng định dạng JSON V1: %s", exc)
        raise GeminiClientError(
            f"Dữ liệu trả về từ Gemini không đúng cấu trúc JSON kịch bản ({exc}). "
            "Đã tự động chuyển sang Chế độ V1.",
            reason="invalid_response",
            fallback_v1=True,
        ) from exc
