"""Đọc cấu hình từ `.env` ở gốc repo (biến môi trường thật được ưu tiên)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FPS = (30, 60)


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


def load_settings(env_file: Path | None = None) -> Settings:
    env = _read_env_file(env_file or REPO_ROOT / ".env")
    env.update({k: v for k, v in os.environ.items() if k in _KEYS})

    def path(key: str, default: str) -> Path:
        p = Path(env.get(key, default))
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    fps = int(env.get("DEFAULT_FPS", "60"))
    if fps not in ALLOWED_FPS:
        raise ValueError(f"DEFAULT_FPS phải là 30 hoặc 60, nhận {fps}")
    device = env.get("WHISPER_DEVICE", "auto")
    if device not in ("auto", "cuda", "cpu"):
        raise ValueError(f"WHISPER_DEVICE phải là auto|cuda|cpu, nhận {device}")

    return Settings(
        workspace_dir=path("WORKSPACE_DIR", "./workspace"),
        library_dir=path("LIBRARY_DIR", "./library"),
        whisper_model=env.get("WHISPER_MODEL", "large-v3"),
        whisper_device=device,
        default_fps=fps,
    )


_KEYS = ("WORKSPACE_DIR", "LIBRARY_DIR", "WHISPER_MODEL", "WHISPER_DEVICE", "DEFAULT_FPS")
