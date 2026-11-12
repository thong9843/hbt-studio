"""Tích hợp Gemini Flash API cho Chế độ V2 (1-Click Prompt) của HBT Core.

- Đọc GEMINI_API_KEY qua cơ chế dò tìm file cấu hình đa tầng (Multi-path Resolver):
  + Path(REPO_ROOT) / ".env"
  + Path(BACKEND_DIR) / ".env"
  + Path(REPO_ROOT) / ".env.example"
- Gọi endpoint v1beta models/{model_name}:generateContent với danh sách fallback:
  MODELS = ["gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-2.0-flash-exp"]
- Payload chuẩn chống lỗi 400:
  {
    "contents": [{"role": "user", "parts": [{"text": system_prompt + "\\n\\n" + user_prompt}]}],
    "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}
  }
- System prompt ép model trả về đúng định dạng JSON tương thích 100% với cấu trúc đầu vào của V1.
- Nếu gặp lỗi API (hết quota / lỗi mạng / thiếu key / 404 tất cả model), ném GeminiClientError
  kèm cờ fallback_v1=True để giao diện thông báo rõ ràng và tự động chuyển hướng sang chế độ V1.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from hbt.core.models import HbtCoreScript

logger = logging.getLogger(__name__)

# Xác định đường dẫn tuyệt đối của thư mục gốc project và backend thông qua Path(__file__).resolve()
# __file__ = <REPO_ROOT>/backend/hbt/core/gemini_client.py
BACKEND_DIR: Path = Path(__file__).resolve().parents[2]
REPO_ROOT: Path = Path(__file__).resolve().parents[3]

PLACEHOLDER_KEYS = {
    "",
    "aizasy_your_gemini_api_key_here",
    "your_gemini_api_key_here",
    "your_api_key_here",
}

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODELS: list[str] = [
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-2.0-flash-exp",
]
GEMINI_MODEL = MODELS[0]
GEMINI_ENDPOINT = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = (
    "Bạn là biên kịch chuyên viết kịch bản video ngắn kiến thức 'Vì Sao' (HBT Core) tiếng Việt.\n"
    "Nhiệm vụ của bạn là sinh kịch bản JSON chuẩn xác theo cấu trúc đầu vào của Chế độ V1:\n"
    "{\n"
    '  "title": "Tiêu đề video hấp dẫn",\n'
    '  "topic": "history | fun | science | mystery",\n'
    '  "segments": [\n'
    "    {\n"
    '      "order": 1,\n'
    '      "text": "Lời thoại tiếng Việt tự nhiên, súc tích, dễ hiểu cho phân đoạn 1...",\n'
    '      "image": "scene-01.png",\n'
    '      "sfx": "whoosh"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. Chỉ trả về DUY NHẤT một đối tượng JSON hợp lệ, không bọc trong markdown ```json.\n"
    '2. Trường "topic" chỉ được nhận 1 trong 4 giá trị: "history", "fun", "science", "mystery".\n'
    '3. Danh sách "segments" gồm từ 4 đến 8 phân đoạn (order đánh số liên tiếp từ 1).\n'
    '4. Trường "text" ở mỗi phân đoạn là lời đọc tiếng Việt thuần túy (18 đến 40 từ mỗi đoạn).\n'
    '5. Trường "image" đặt tên gợi ý ảnh minh họa (ví dụ: "scene-01.png", "scene-02.png"...).\n'
    '6. Trường "sfx" chọn hiệu ứng chuyển cảnh: "whoosh" hoặc "pop".'
)


class GeminiClientError(RuntimeError):
    """Lỗi khi gọi Gemini API; luôn kèm `fallback_v1 = True` để chuyển hướng sang chế độ V1."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reason: str = "api_error",
        fallback_v1: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason = reason
        self.fallback_v1 = fallback_v1


def normalize_model_name(model_name: str) -> str:
    """Chuẩn hóa tên model, loại bỏ tiền tố 'models/' thừa để không bị lặp 'models/models/...'."""
    clean = (model_name or "").strip()
    while clean.startswith("models/"):
        clean = clean[len("models/") :].strip()
    return clean or MODELS[0]


def build_gemini_url(model_name: str, api_key: str) -> str:
    """Tạo URL chuẩn v1beta cho model Gemini, đảm bảo không bao giờ lặp 'models/models/...'."""
    clean_model = normalize_model_name(model_name)
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{clean_model}:generateContent?key={api_key}"
    )


def _clean_key_value(raw: str | None) -> str:
    """Chuẩn hóa chuỗi GEMINI_API_KEY:
    - Cắt khoảng trắng, dấu nháy kép/đơn và loại bỏ placeholder.
    - Tự động sửa lỗi ghép thừa tiền tố 'AIzaSy' vào đầu key định dạng mới 'AQ....' của AI Studio
      (ví dụ 'AIzaSyAQ.Ab8...' -> 'AQ.Ab8...').
    """
    key = (raw or "").strip().strip('"').strip("'").strip()
    if key.lower() in PLACEHOLDER_KEYS:
        return ""
    if key.startswith("AIzaSyAQ."):
        key = key[len("AIzaSy") :]
    return key


def resolve_candidate_env_paths(env_file: Path | None = None) -> list[Path]:
    """Trả về danh sách đường dẫn file cấu hình đa tầng (Multi-path Resolver)."""
    candidate_paths: list[Path] = []
    if env_file is not None:
        candidate_paths.append(Path(env_file).resolve())
    candidate_paths.extend(
        [
            Path(REPO_ROOT) / ".env",
            Path(BACKEND_DIR) / ".env",
            Path(REPO_ROOT) / ".env.example",
        ]
    )
    return candidate_paths


def _safe_print_config(msg: str) -> None:
    """In log chẩn đoán an toàn ra stdout, chống lỗi UnicodeEncodeError (cp1252) trên Windows."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            import sys

            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_msg = msg.encode(enc, errors="replace").decode(enc, errors="replace")
            print(safe_msg, flush=True)
        except Exception:
            pass
    logger.info(msg)


def load_gemini_api_key(env_file: Path | None = None) -> str:
    """Dò tìm file cấu hình đa tầng bằng `load_dotenv(dotenv_path=env_path, override=True)`
    và chuẩn hóa chuỗi `GEMINI_API_KEY`. Luôn ưu tiên đọc lại `.env` nếu tồn tại để cập nhật
    ngay khi người dùng sửa key mà không cần khởi động lại server.
    """
    if env_file is not None:
        candidate_paths = [Path(env_file)]
    else:
        candidate_paths = resolve_candidate_env_paths()

    loaded_from_file = False
    for env_path in candidate_paths:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
            loaded = _clean_key_value(os.getenv("GEMINI_API_KEY"))
            if loaded:
                loaded_from_file = True
                break
            # Nếu là giá trị mẫu placeholder thì xoá khỏi os.environ để tiếp tục dò
            os.environ.pop("GEMINI_API_KEY", None)

    key = _clean_key_value(os.getenv("GEMINI_API_KEY", ""))
    _ = loaded_from_file

    _safe_print_config(
        f"[GEMINI_CONFIG] Đã tìm thấy GEMINI_API_KEY: {bool(key)} "
        f"(Độ dài: {len(key)}, Bắt đầu bằng AIzaSy: {key.startswith('AIzaSy')}, "
        f"Bắt đầu bằng AQ.: {key.startswith('AQ.')})"
    )
    return key


def build_gemini_payload(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> dict[str, Any]:
    """Tạo payload chuẩn chống lỗi 400 cho v1beta models/{model_name}:generateContent."""
    prompt_clean = user_prompt.strip()
    combined_text = system_prompt + "\n\n" + prompt_clean
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": combined_text}],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }


def _extract_json_text(raw_text: str) -> str:
    """Làm sạch khối JSON nếu model vô tình bọc trong ```json ... ```."""
    s = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


def generate_script_from_prompt(
    user_prompt: str,
    *,
    topic_hint: str | None = None,
    api_key: str | None = None,
    env_file: Path | None = None,
    models: list[str] | None = None,
    timeout_s: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> HbtCoreScript:
    """Gọi Gemini Flash API sinh kịch bản JSON chuẩn V1 từ 1 câu prompt của người dùng.

    Tự động thử lần lượt các model trong `MODELS = ["gemini-1.5-flash-latest",
    "gemini-1.5-flash", "gemini-2.0-flash-exp"]` nếu gặp lỗi HTTP 404.
    """
    prompt_clean = (user_prompt or "").strip()
    if not prompt_clean:
        raise GeminiClientError(
            "Câu nhắc (prompt) không được để trống.",
            reason="invalid_prompt",
            fallback_v1=False,
        )

    if api_key is not None:
        key = _clean_key_value(api_key)
        _safe_print_config(
            f"[GEMINI_CONFIG] Đã tìm thấy GEMINI_API_KEY: {bool(key)} "
            f"(Độ dài: {len(key)}, Bắt đầu bằng AIzaSy: {key.startswith('AIzaSy')})"
        )
    else:
        key = load_gemini_api_key(env_file=env_file)

    if not key:
        logger.warning(
            "[GEMINI_CONFIG] GEMINI_API_KEY rỗng hoặc không hợp lệ -> Kích hoạt fallback_v1=True."
        )
        raise GeminiClientError(
            "Chưa cấu hình hoặc GEMINI_API_KEY không hợp lệ trong file .env. "
            "Đã tự động chuyển sang Chế độ V1 (Dán JSON thủ công).",
            status_code=401,
            reason="missing_api_key",
            fallback_v1=True,
        )

    full_user_prompt = prompt_clean
    if topic_hint and topic_hint.strip():
        full_user_prompt = f"{prompt_clean}\n(Chủ đề ưu tiên: {topic_hint.strip()})"

    payload = build_gemini_payload(full_user_prompt, system_prompt=SYSTEM_PROMPT)
    candidate_models = [normalize_model_name(m) for m in (models or MODELS) if m and m.strip()]
    if not candidate_models:
        candidate_models = list(MODELS)

    response: httpx.Response | None = None
    last_404_detail = ""

    try:
        with httpx.Client(timeout=timeout_s, transport=transport) as client:
            for idx, model_name in enumerate(candidate_models):
                url = build_gemini_url(model_name, key)
                response = client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": key,
                    },
                )
                if response.status_code == 404:
                    try:
                        err_body = response.json()
                        last_404_detail = err_body.get("error", {}).get("message", "")
                    except Exception:
                        last_404_detail = response.text[:200]
                    logger.warning(
                        "Model Gemini '%s' trả về 404 (%s)%s",
                        model_name,
                        last_404_detail,
                        f", thử tiếp '{candidate_models[idx + 1]}'"
                        if idx + 1 < len(candidate_models)
                        else ", đã hết danh sách fallback",
                    )
                    continue
                break
    except httpx.TimeoutException as exc:
        logger.warning("Gemini API quá thời gian chờ: %s", exc)
        raise GeminiClientError(
            "Kết nối tới Gemini Flash API bị quá thời gian chờ (timeout). "
            "Đã chuyển sang Chế độ V1 để bạn dán JSON thủ công.",
            reason="network_timeout",
            fallback_v1=True,
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("Lỗi mạng khi gọi Gemini API: %s", exc)
        raise GeminiClientError(
            f"Lỗi kết nối mạng khi gọi Gemini Flash API ({exc.__class__.__name__}). "
            "Đã chuyển sang Chế độ V1 để không gián đoạn công việc.",
            reason="network_error",
            fallback_v1=True,
        ) from exc

    if response is None:
        raise GeminiClientError(
            "Không thể khởi tạo yêu cầu tới Gemini API. Đã tự động chuyển sang Chế độ V1.",
            reason="api_error",
            fallback_v1=True,
        )

    if response.status_code == 429:
        raise GeminiClientError(
            "Gemini API đã hết hạn mức (Quota 429). "
            "Đã tự động chuyển sang Chế độ V1 (Bán tự động / JSON Thủ công).",
            status_code=429,
            reason="quota_exceeded",
            fallback_v1=True,
        )

    if response.status_code >= 400:
        detail = ""
        try:
            err_body = response.json()
            detail = err_body.get("error", {}).get("message", "")
        except Exception:
            detail = response.text[:200]
        if not detail and response.status_code == 404:
            detail = last_404_detail
        suffix = f": {detail}" if detail else ""
        raise GeminiClientError(
            f"Gemini API trả về lỗi HTTP {response.status_code}{suffix}. "
            "Đã tự động chuyển sang Chế độ V1.",
            status_code=response.status_code,
            reason="http_error",
            fallback_v1=True,
        )

    try:
        body = response.json()
        candidates = body.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(str(p.get("text", "")) for p in parts).strip()
        if not raw_text:
            raise ValueError("Phản hồi từ Gemini không có nội dung văn bản")
        cleaned_json = _extract_json_text(raw_text)
        parsed = json.loads(cleaned_json)
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
