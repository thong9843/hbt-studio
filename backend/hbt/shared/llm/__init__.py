"""Shared LLM clients (Gemini API)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from hbt.core.gemini_client import (
    AVAILABLE_GEMINI_MODELS,
    GEMINI_MODEL,
    MODELS,
    GeminiClientError,
    _extract_json_text,
    build_gemini_headers,
    build_gemini_url,
    is_valid_gemini_api_key,
    load_gemini_api_key,
    normalize_model_name,
)

__all__ = [
    "AVAILABLE_GEMINI_MODELS",
    "GEMINI_MODEL",
    "MODELS",
    "GeminiClientError",
    "build_gemini_headers",
    "build_gemini_url",
    "generate_structured_json",
    "is_valid_gemini_api_key",
    "load_gemini_api_key",
    "normalize_model_name",
]


def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.8,
    timeout: float = 60.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gọi Gemini API (Structured JSON Output) và trả về (parsed_dict, timings)."""
    api_key = load_gemini_api_key()
    if not is_valid_gemini_api_key(api_key):
        raise GeminiClientError(
            "Chưa cấu hình GEMINI_API_KEY hợp lệ trong .env.",
            fallback_v1=True,
        )

    chosen = normalize_model_name(model or GEMINI_MODEL)
    candidates = [chosen] + [m for m in MODELS if m != chosen]

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    headers = build_gemini_headers(api_key)

    t0 = time.perf_counter()
    last_err: Exception | None = None
    for idx, m in enumerate(candidates):
        url = build_gemini_url(m)
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    last_err = GeminiClientError(
                        f"Gemini HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    continue
                data = resp.json()
                raw_text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                clean_json = _extract_json_text(raw_text)
                parsed = json.loads(clean_json)
                if not isinstance(parsed, dict):
                    raise ValueError("Gemini không trả về JSON object")
                usage = data.get("usageMetadata") or {}
                tokens = int(usage.get("candidatesTokenCount") or 0)
                timings = {
                    "llm_s": round(time.perf_counter() - t0, 3),
                    "llm_tokens": tokens,
                    "llm_retry": idx,
                    "model": m,
                }
                return parsed, timings
        except Exception as exc:
            last_err = exc
            continue

    raise GeminiClientError(
        f"Không thể gọi Gemini API: {last_err}",
        fallback_v1=True,
    )
