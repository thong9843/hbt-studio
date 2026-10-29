"""FastAPI app. Chạy: uvicorn hbt.main:app --host 127.0.0.1 --port 8000"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hbt.api import assets, backgrounds, files, health, lint, music, postv, projects, script, voices
from hbt.api import render as render_api
from hbt.api import settings as settings_api
from hbt.app_settings import AppSettingsStore
from hbt.config import BRAND_DIR, Settings, load_settings
from hbt.jobs import JobManager
from hbt.library import MusicLibrary
from hbt.postv.backgrounds import BackgroundLibrary
from hbt.postv.censor import CensorStore
from hbt.postv.voice import VieNeuProvider, VoiceProvider
from hbt.sensitive import SensitiveStore
from hbt.state import AppState
from hbt.storage import (
    BadRequest,
    Conflict,
    NotFound,
    ServiceUnavailable,
    Storage,
    StorageError,
    Unprocessable,
)

STATUS_BY_ERROR = {
    NotFound: 404,
    Conflict: 409,
    BadRequest: 400,
    Unprocessable: 422,
    ServiceUnavailable: 503,
}


def make_voice_provider(settings: Settings) -> VoiceProvider:
    """VieNeu trong `backend/.venv-tts`, trọng số ở `models/hf_vieneu` (IMPLEMENT-POSTV 6c)."""
    cache = settings.workspace_dir / "cache" / "vieneu_voices.json"
    return VieNeuProvider(settings.models_dir, cache_file=cache)


def create_app(
    settings: Settings | None = None,
    brand_dir: Path | None = None,
    voice: VoiceProvider | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    brand_dir = brand_dir or BRAND_DIR
    voice = voice or make_voice_provider(settings)
    app_settings = AppSettingsStore(settings.workspace_dir, settings.default_fps)
    storage = Storage(settings.workspace_dir, settings.default_fps, app_settings)
    sensitive = SensitiveStore(settings.workspace_dir)
    postv_words = CensorStore(settings.workspace_dir)
    state = AppState(
        settings=settings,
        storage=storage,
        jobs=JobManager(
            storage,
            settings.library_dir,
            brand_dir,
            sensitive=sensitive,
            app_settings=app_settings,
            voice=voice,
            postv_words=postv_words,
        ),
        library=MusicLibrary(settings.library_dir),
        sensitive=sensitive,
        app_settings=app_settings,
        brand_dir=brand_dir,
        postv_words=postv_words,
        backgrounds=BackgroundLibrary(settings.library_dir),
        voice=voice,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        state.jobs.shutdown()  # huỷ việc đang dựng khi tắt server

    app = FastAPI(title="HBT Studio", version="0.3.0", lifespan=lifespan)
    app.state.hbt = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(StorageError)
    async def storage_error(_: Request, exc: StorageError) -> JSONResponse:
        code = next((c for t, c in STATUS_BY_ERROR.items() if isinstance(exc, t)), 400)
        return JSONResponse({"detail": exc.message}, status_code=code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Lỗi theo dạng {detail}: một chuỗi dễ đọc thay vì danh sách lồng nhau
        parts = [
            f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()
        ]
        return JSONResponse({"detail": "; ".join(parts) or "Dữ liệu không hợp lệ"}, status_code=422)

    for module in (
        health,
        projects,
        assets,
        lint,
        settings_api,
        render_api,
        music,
        files,
        script,
        postv,
        backgrounds,
        voices,
    ):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
