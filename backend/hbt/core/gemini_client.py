"""Tích hợp Gemini Flash API cho Chế độ V2 (1-Click Prompt) của HBT Core.

- Đọc GEMINI_API_KEY từ file .env hoặc biến môi trường.
- Gọi endpoint v1beta models/gemini-1.5-flash với payload chuẩn chống lỗi 400:
  {
    "contents": [{"role": "user", "parts": [{"text": system_prompt + "\\n\\n" + user_prompt}]}],
    "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}
  }
- System prompt ép model trả về đúng định dạng JSON tương thích 100% với cấu trúc đầu vào của V1.
- Nếu gặp lỗi API (hết quota / lỗi mạng / thiếu key), ném GeminiClientError kèm cờ fallback_v1=True
  để giao diện thông báo rõ ràng và tự động chuyển hướng sang chế độ V1.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

from hbt.config import REPO_ROOT
from hbt.core.models import HbtCoreScript

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

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


def load_gemini_api_key(env_file: Path | None = None) -> str:
    """Đọc GEMINI_API_KEY từ biến môi trường hoặc file .env ở thư mục gốc dự án."""
    env_val = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_val:
        return env_val

    candidates: list[Path] = []
    if env_file is not None:
        candidates.append(Path(env_file))
    candidates.extend([REPO_ROOT / ".env", Path.cwd() / ".env"])

    for path in candidates:
        if not path.is_file():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "GEMINI_API_KEY":
                    cleaned = v.strip().strip('"').strip("'").strip()
                    if cleaned:
                        return cleaned
        except OSError:
            continue

    return ""


def build_gemini_payload(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> dict[str, Any]:
    """Tạo payload chuẩn chống lỗi 400 cho v1beta models/gemini-1.5-flash."""
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
    timeout_s: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> HbtCoreScript:
    """Gọi Gemini 1.5 Flash sinh kịch bản JSON chuẩn V1 từ 1 câu prompt của người dùng."""
    prompt_clean = (user_prompt or "").strip()
    if not prompt_clean:
        raise GeminiClientError(
            "Câu nhắc (prompt) không được để trống.",
            reason="invalid_prompt",
            fallback_v1=False,
        )

    key = (api_key if api_key is not None else load_gemini_api_key(env_file=env_file)).strip()
    if not key:
        raise GeminiClientError(
            "Chưa cấu hình GEMINI_API_KEY trong file .env. "
            "Đã tự động chuyển sang Chế độ V1 (Dán JSON thủ công).",
            status_code=401,
            reason="missing_api_key",
            fallback_v1=True,
        )

    full_user_prompt = prompt_clean
    if topic_hint and topic_hint.strip():
        full_user_prompt = f"{prompt_clean}\n(Chủ đề ưu tiên: {topic_hint.strip()})"

    payload = build_gemini_payload(full_user_prompt, system_prompt=SYSTEM_PROMPT)
    url = f"{GEMINI_ENDPOINT}?key={key}"

    try:
        with httpx.Client(timeout=timeout_s, transport=transport) as client:
            response = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
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
