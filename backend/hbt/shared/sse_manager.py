"""Bộ phát sự kiện tiến trình thời gian thực (SSE Manager) dùng chung cho các job."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


def format_sse_progress(pct: float, step: str, message: str, **extra: Any) -> dict[str, Any]:
    """Chuẩn hóa payload sự kiện SSE `progress`."""
    payload: dict[str, Any] = {
        "progress": round(float(pct), 1),
        "step": step,
        "message": message,
    }
    if extra:
        payload.update(extra)
    return payload


class SSEProgressEmitter:
    """Bộ phát tiến trình thread-safe cho từng phiên job độc lập."""

    def __init__(self, callback: Callable[..., None] | None = None) -> None:
        self._callback = callback
        self._lock = threading.Lock()

    def emit(self, pct: float, step: str, message: str, **extra: Any) -> dict[str, Any]:
        payload = format_sse_progress(pct, step, message, **extra)
        if self._callback is not None:
            with self._lock:
                try:
                    self._callback(pct, step, message, **extra)
                except TypeError:
                    self._callback(pct, step, message)
        return payload
