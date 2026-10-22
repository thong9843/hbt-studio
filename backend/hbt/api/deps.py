"""Truy cập trạng thái dùng chung của app (kho project, hàng đợi job, thư viện…)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from hbt.state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.hbt


State = Annotated[AppState, Depends(get_state)]

FILES_PREFIX = "/api/files/"


def file_url(rel: str | None) -> str | None:
    """Đường dẫn tương đối so với workspace → URL của GET /api/files/{path}."""
    return None if rel is None else FILES_PREFIX + rel
