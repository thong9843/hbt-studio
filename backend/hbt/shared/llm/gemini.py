"""Nền tảng Gemini API dùng chung cho toàn hệ thống (không phụ thuộc ngược vào `core/`)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# __file__ = <REPO_ROOT>/backend/hbt/shared/llm/gemini.py
BACKEND_DIR: Path = Path(__file__).resolve().parents[3]
REPO_ROOT: Path = Path(__file__).resolve().parents[4]

PLACEHOLDER_KEYS = {
    "",
    "aizasy_your_gemini_api_key_here",
    "your_gemini_api_key_here",
    "your_api_key_here",
}

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
AVAILABLE_GEMINI_MODELS: list[dict[str, str]] = [
    {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash Lite (Mặc định / 500 RPD)"},
    {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash Lite (Nhẹ / Tiết kiệm)"},
    {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash"},
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash (Nhanh)"},
]
MODELS: list[str] = [item["id"] for item in AVAILABLE_GEMINI_MODELS]
GEMINI_MODEL = MODELS[0]
GEMINI_ENDPOINT = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent"


class GeminiClientError(RuntimeError):
    """Lỗi khi gọi Gemini API; luôn kèm `fallback_v1 = True` để chuyển hướng khi cần."""

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
    """Chuẩn hóa tên model, loại bỏ tiền tố 'models/' thừa."""
    clean = (model_name or "").strip()
    while clean.startswith("models/"):
        clean = clean[len("models/") :].strip()
    return clean or MODELS[0]


def build_gemini_url(model_name: str, api_key: str | None = None) -> str:
    """Tạo URL endpoint sạch v1beta cho model Gemini."""
    _ = api_key
    clean_model = normalize_model_name(model_name)
    return f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"


def build_gemini_headers(api_key: str) -> dict[str, str]:
    """Tạo Header chuẩn Google AI Studio với `x-goog-api-key`."""
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key.strip(),
    }


def _clean_key_value(raw: str | None) -> str:
    """Chuẩn hóa chuỗi GEMINI_API_KEY và loại bỏ placeholder."""
    key = (raw or "").strip().strip('"').strip("'").strip()
    if key.lower() in PLACEHOLDER_KEYS:
        return ""
    return key


def is_valid_gemini_api_key(api_key: str | None) -> bool:
    """Kiểm tra tính hợp lệ của Key trước khi gọi (AIzaSy... hoặc AQ...., >= 30 ký tự)."""
    if not api_key:
        return False
    k = _clean_key_value(api_key)
    return (k.startswith("AIzaSy") or k.startswith("AQ.")) and len(k) >= 30


def resolve_candidate_env_paths(env_file: Path | None = None) -> list[Path]:
    """Trả về danh sách đường dẫn file `.env` đa tầng."""
    candidate_paths: list[Path] = []
    if env_file is not None:
        candidate_paths.append(Path(env_file).resolve())
    candidate_paths.extend(
        [
            Path(REPO_ROOT) / ".env",
            Path(BACKEND_DIR) / ".env",
        ]
    )
    return candidate_paths


def _safe_print_config(msg: str) -> None:
    """In log an toàn ra stdout, chống lỗi UnicodeEncodeError (cp1252) trên Windows."""
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
    """Dò tìm `.env` đa tầng và nạp `GEMINI_API_KEY` mới nhất."""
    candidate_paths = [Path(env_file)] if env_file is not None else resolve_candidate_env_paths()
    for env_path in candidate_paths:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
            loaded = _clean_key_value(os.getenv("GEMINI_API_KEY"))
            if loaded:
                break
            os.environ.pop("GEMINI_API_KEY", None)

    key = _clean_key_value(os.getenv("GEMINI_API_KEY", ""))
    _safe_print_config(
        f"[GEMINI_CONFIG] Đã tìm thấy GEMINI_API_KEY: {bool(key)} "
        f"(Độ dài: {len(key)}, Bắt đầu bằng AIzaSy: {key.startswith('AIzaSy')})"
    )
    return key


def build_gemini_payload(
    user_prompt: str,
    system_prompt: str,
    *,
    temperature: float = 0.7,
    response_schema: dict[str, Any] | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Tạo payload JSON chuẩn cho v1beta models/{model_name}:generateContent."""
    gen_cfg: dict[str, Any] = {
        "temperature": temperature,
        "responseMimeType": "application/json",
    }
    if response_schema is not None:
        gen_cfg["responseSchema"] = response_schema
    if max_output_tokens is not None and max_output_tokens > 0:
        gen_cfg["maxOutputTokens"] = int(max_output_tokens)
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt.strip()}"}],
            }
        ],
        "generationConfig": gen_cfg,
    }


def _extract_json_text(raw_text: str) -> str:
    """Làm sạch khối JSON (cắt bỏ ```json ... ```)."""
    s = (raw_text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    models: list[str] | None = None,
    api_key: str | None = None,
    env_file: Path | None = None,
    temperature: float = 0.8,
    timeout: float = 60.0,
    response_schema: dict[str, Any] | None = None,
    max_output_tokens: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gọi Gemini API (Structured JSON Output + model fallback) và trả `(parsed_dict, timings)`."""
    if api_key is not None:
        key = _clean_key_value(api_key)
    else:
        key = load_gemini_api_key(env_file=env_file)

    if not is_valid_gemini_api_key(key):
        raise GeminiClientError(
            "Chưa cấu hình hoặc GEMINI_API_KEY không hợp lệ trong .env "
            "(yêu cầu bắt đầu bằng 'AIzaSy' hoặc 'AQ.').",
            status_code=401,
            reason="invalid_or_missing_api_key",
            fallback_v1=True,
        )

    base_models = [normalize_model_name(m) for m in (models or MODELS) if m and m.strip()]
    if not base_models:
        base_models = list(MODELS)
    if model and model.strip():
        preferred = normalize_model_name(model)
        candidates = [preferred] + [m for m in base_models if m != preferred]
    else:
        candidates = base_models

    payload = build_gemini_payload(
        user_prompt,
        system_prompt,
        temperature=temperature,
        response_schema=response_schema,
        max_output_tokens=max_output_tokens,
    )
    headers = build_gemini_headers(key)

    t0 = time.perf_counter()
    response: httpx.Response | None = None
    last_error_detail = ""
    last_timeout_exc: httpx.TimeoutException | None = None
    last_req_exc: httpx.RequestError | None = None
    chosen_model = candidates[0]
    chosen_idx = 0

    with httpx.Client(timeout=timeout, transport=transport) as client:
        for idx, cand_model in enumerate(candidates):
            chosen_model = cand_model
            chosen_idx = idx
            url = build_gemini_url(cand_model)
            try:
                resp = client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                last_timeout_exc = exc
                logger.warning("Model Gemini '%s' quá thời gian chờ (%s)", cand_model, exc)
                continue
            except httpx.RequestError as exc:
                last_req_exc = exc
                logger.warning("Lỗi kết nối model Gemini '%s' (%s)", cand_model, exc)
                continue

            response = resp
            if resp.status_code >= 400:
                try:
                    last_error_detail = resp.json().get("error", {}).get("message", "")
                except Exception:
                    last_error_detail = resp.text[:200]
                logger.warning(
                    "Model Gemini '%s' trả HTTP %s (%s)",
                    cand_model,
                    resp.status_code,
                    last_error_detail,
                )
                if idx + 1 < len(candidates):
                    continue
            break

    if response is None:
        if last_timeout_exc is not None:
            raise GeminiClientError(
                "Kết nối tới Gemini Flash API bị quá thời gian chờ (timeout).",
                reason="network_timeout",
                fallback_v1=True,
            ) from last_timeout_exc
        if last_req_exc is not None:
            raise GeminiClientError(
                f"Lỗi kết nối mạng khi gọi Gemini Flash API ({last_req_exc.__class__.__name__}).",
                reason="network_error",
                fallback_v1=True,
            ) from last_req_exc
        raise GeminiClientError(
            "Không thể khởi tạo yêu cầu tới Gemini API.",
            reason="api_error",
            fallback_v1=True,
        )

    if response.status_code == 429:
        raise GeminiClientError(
            "Gemini API đã hết hạn mức (Quota 429).",
            status_code=429,
            reason="quota_exceeded",
            fallback_v1=True,
        )

    if response.status_code >= 400:
        detail = last_error_detail or response.text[:200]
        suffix = f": {detail}" if detail else ""
        raise GeminiClientError(
            f"Gemini API trả về lỗi HTTP {response.status_code}{suffix}.",
            status_code=response.status_code,
            reason="http_error",
            fallback_v1=True,
        )

    try:
        data = response.json()
        candidates_out = data.get("candidates") or []
        parts = candidates_out[0].get("content", {}).get("parts", [])
        raw_text = "".join(str(p.get("text", "")) for p in parts).strip()
        if not raw_text:
            raise ValueError("Phản hồi từ Gemini không có nội dung văn bản")
        clean_json = _extract_json_text(raw_text)
        parsed = json.loads(clean_json)
        if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            raise ValueError("Gemini không trả về JSON object")
        usage = data.get("usageMetadata") or {}
        timings = {
            "llm_s": round(time.perf_counter() - t0, 3),
            "llm_tokens": int(usage.get("candidatesTokenCount") or 0),
            "llm_retry": chosen_idx,
            "model": chosen_model,
        }
        return parsed, timings
    except Exception as exc:
        raise GeminiClientError(
            f"Dữ liệu trả về từ Gemini không đúng định dạng JSON ({exc}).",
            reason="invalid_response",
            fallback_v1=True,
        ) from exc
