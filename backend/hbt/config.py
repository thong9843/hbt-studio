"""Đọc cấu hình từ `.env` ở gốc repo (biến môi trường thật được ưu tiên)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAND_DIR = REPO_ROOT / "brand"
ALLOWED_FPS = (30, 50, 60)
DEFAULT_FPS = 50


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    workspace_dir: Path
    library_dir: Path
    whisper_model: str
    whisper_device: str
    default_fps: int
    chatting_model: str = "gemini-3.1-flash-lite"
    models_dir: Path = REPO_ROOT / "models"  # model Whisper tải về đây (đã ignore)
    assets_dir: Path = (
        REPO_ROOT / "assets"
    )  # kho tài nguyên Asset Hub (stickers, memes, backgrounds, renders)
    freesound_api_key: str = ""
    voicemod_tuna_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-2-klein-4b"


WHISPER_MODELS = ("auto", "small", "medium", "large-v3")


def load_settings(env_file: Path | None = None) -> Settings:
    env = _read_env_file(env_file or REPO_ROOT / ".env")
    env.update({k: v for k, v in os.environ.items() if k in _KEYS})

    def path(key: str, default: str) -> Path:
        p = Path(env.get(key, default))
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    fps = int(env.get("DEFAULT_FPS", str(DEFAULT_FPS)))
    if fps not in ALLOWED_FPS:
        raise ValueError(f"DEFAULT_FPS phải là 30, 50 hoặc 60, nhận {fps}")
    device = env.get("WHISPER_DEVICE", "auto")
    if device not in ("auto", "cuda", "cpu"):
        raise ValueError(f"WHISPER_DEVICE phải là auto|cuda|cpu, nhận {device}")

    model = env.get("WHISPER_MODEL", "auto")
    if model not in WHISPER_MODELS:
        raise ValueError(f"WHISPER_MODEL phải là {'|'.join(WHISPER_MODELS)}, nhận {model}")

    return Settings(
        workspace_dir=path("WORKSPACE_DIR", "./workspace"),
        library_dir=path("LIBRARY_DIR", "./library"),
        whisper_model=model,
        whisper_device=device,
        default_fps=fps,
        chatting_model=env.get("CHATTING_MODEL", "gemini-3.1-flash-lite"),
        models_dir=path("MODELS_DIR", "./models"),
        assets_dir=path("ASSETS_DIR", "./assets"),
        freesound_api_key=env.get("FREESOUND_API_KEY", ""),
        voicemod_tuna_api_key=env.get("VOICEMOD_TUNA_API_KEY", ""),
        cloudflare_account_id=env.get("CLOUDFLARE_ACCOUNT_ID", ""),
        cloudflare_api_token=env.get("CLOUDFLARE_API_TOKEN", ""),
        cloudflare_image_model=env.get(
            "CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b"
        ),
    )


_KEYS = (
    "WORKSPACE_DIR",
    "LIBRARY_DIR",
    "WHISPER_MODEL",
    "WHISPER_DEVICE",
    "DEFAULT_FPS",
    "MODELS_DIR",
    "ASSETS_DIR",
    "CHATTING_MODEL",
    "FREESOUND_API_KEY",
    "VOICEMOD_TUNA_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_IMAGE_MODEL",
)
