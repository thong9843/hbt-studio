"""GET/PUT /api/settings/app: cài đặt chung (fps mặc định, màu chủ đề mặc định, Whisper)."""

from __future__ import annotations

from fastapi import APIRouter

from hbt.api.deps import State
from hbt.app_settings import AppSettings

router = APIRouter(tags=["settings"])


@router.get("/settings/app", response_model=AppSettings)
def get_app_settings(state: State):
    return state.app_settings.load()


@router.put("/settings/app", response_model=AppSettings)
def put_app_settings(body: AppSettings, state: State):
    from hbt.api.asset_hub import clear_online_search_cache

    saved = state.app_settings.save(body)
    clear_online_search_cache()
    return saved
