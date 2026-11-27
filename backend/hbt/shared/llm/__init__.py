"""Shared LLM clients (Gemini API)."""

from __future__ import annotations

from hbt.shared.llm.gemini import (
    AVAILABLE_GEMINI_MODELS,
    GEMINI_BASE_URL,
    GEMINI_ENDPOINT,
    GEMINI_MODEL,
    MODELS,
    PLACEHOLDER_KEYS,
    GeminiClientError,
    _clean_key_value,
    _extract_json_text,
    _safe_print_config,
    build_gemini_headers,
    build_gemini_payload,
    build_gemini_url,
    generate_structured_json,
    is_valid_gemini_api_key,
    load_gemini_api_key,
    normalize_model_name,
    resolve_candidate_env_paths,
)

__all__ = [
    "AVAILABLE_GEMINI_MODELS",
    "GEMINI_BASE_URL",
    "GEMINI_ENDPOINT",
    "GEMINI_MODEL",
    "MODELS",
    "PLACEHOLDER_KEYS",
    "GeminiClientError",
    "_clean_key_value",
    "_extract_json_text",
    "_safe_print_config",
    "build_gemini_headers",
    "build_gemini_payload",
    "build_gemini_url",
    "generate_structured_json",
    "is_valid_gemini_api_key",
    "load_gemini_api_key",
    "normalize_model_name",
    "resolve_candidate_env_paths",
]
