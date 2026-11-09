"""Lưu trữ dự án Chatting (workspace/chatting/<slug>/) theo §1 (CH-D3) và §3."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from hbt.chatting.models import ChatDoc


def to_slug(text: str) -> str:
    """Tạo slug an toàn từ tiêu đề tiếng Việt."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[-\s]+", "-", s)
    return s[:40] or "chat"


def get_chatting_root(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / "chatting"


def get_project_dir(workspace_dir: Path, slug: str) -> Path:
    return get_chatting_root(workspace_dir) / slug


def load_chat(workspace_dir: Path, slug: str) -> ChatDoc:
    project_dir = get_project_dir(workspace_dir, slug)
    chat_file = project_dir / "chat.json"
    if not chat_file.is_file():
        raise FileNotFoundError(f"Dự án chatting '{slug}' không có file chat.json")
    data = json.loads(chat_file.read_text(encoding="utf-8"))
    return ChatDoc.model_validate(data)


def save_chat(workspace_dir: Path, slug: str, doc: ChatDoc) -> None:
    project_dir = get_project_dir(workspace_dir, slug)
    project_dir.mkdir(parents=True, exist_ok=True)
    chat_file = project_dir / "chat.json"
    tmp_file = chat_file.with_name(chat_file.name + ".tmp")
    payload = doc.model_dump(by_alias=True)
    tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_file, chat_file)


def load_source(workspace_dir: Path, slug: str) -> dict[str, Any]:
    project_dir = get_project_dir(workspace_dir, slug)
    source_file = project_dir / "source.json"
    if not source_file.is_file():
        return {}
    try:
        return json.loads(source_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_source(workspace_dir: Path, slug: str, data: dict[str, Any]) -> None:
    project_dir = get_project_dir(workspace_dir, slug)
    project_dir.mkdir(parents=True, exist_ok=True)
    source_file = project_dir / "source.json"
    tmp_file = source_file.with_name(source_file.name + ".tmp")
    tmp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_file, source_file)


def save_avatar(workspace_dir: Path, slug: str, char_id: str, image_bytes: bytes) -> str:
    """Cắt vuông và lưu avatar 256x256 px."""
    project_dir = get_project_dir(workspace_dir, slug)
    avatars_dir = project_dir / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    img_cropped = img.crop((left, top, left + min_dim, top + min_dim))
    img_resized = img_cropped.resize((256, 256), Image.Resampling.LANCZOS)

    filename = f"{char_id}.png"
    dest_path = avatars_dir / filename
    img_resized.save(dest_path, format="PNG")

    rel_path = f"avatars/{filename}"
    return rel_path


def list_projects(workspace_dir: Path) -> list[dict[str, Any]]:
    """Liệt kê các dự án Chatting."""
    root = get_chatting_root(workspace_dir)
    if not root.is_dir():
        return []

    projects = []
    subdirs = [p for p in root.iterdir() if p.is_dir()]
    for d in sorted(subdirs, key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        chat_file = d / "chat.json"
        if not chat_file.is_file():
            continue
        try:
            doc = ChatDoc.model_validate(json.loads(chat_file.read_text(encoding="utf-8")))
            source = load_source(workspace_dir, d.name)
            renders_dir = d / "renders"
            has_render = renders_dir.is_dir() and any(renders_dir.glob("*.mp4"))

            projects.append(
                {
                    "slug": d.name,
                    "title": doc.title,
                    "platform": doc.platform,
                    "updated_at": datetime.fromtimestamp(
                        chat_file.stat().st_mtime, tz=UTC
                    ).isoformat(),
                    "characters_count": len(doc.characters),
                    "messages_count": len(doc.messages),
                    "has_render": has_render,
                    "timings": source.get("timings", {}),
                }
            )
        except Exception:
            continue

    return projects


def delete_project(workspace_dir: Path, slug: str) -> None:
    project_dir = get_project_dir(workspace_dir, slug)
    if not project_dir.is_dir():
        return
    for attempt in range(5):
        try:
            shutil.rmtree(project_dir)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.1)
