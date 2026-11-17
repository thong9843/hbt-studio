"""Lưu trữ dự án StickV tại `workspace/stickv/<slug>/project.json`."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

from hbt.stickv.models import StickvBeat, StickvProject, now_iso
from hbt.storage import BadRequest, NotFound

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9-]+")


def slugify_stickv(title: str) -> str:
    s = (title or "stickv").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = _SLUG_CLEAN_RE.sub("-", s).strip("-")
    return (s[:48] or "stickv").strip("-")


def stickv_root(workspace_dir: Path) -> Path:
    root = Path(workspace_dir) / "stickv"
    root.mkdir(parents=True, exist_ok=True)
    return root


def stickv_project_dir(workspace_dir: Path, slug: str) -> Path:
    clean = (slug or "").strip()
    if not clean or "/" in clean or "\\" in clean or ".." in clean:
        raise BadRequest("Slug dự án StickV không hợp lệ")
    return stickv_root(workspace_dir) / clean


def _unique_slug(workspace_dir: Path, base_title: str) -> str:
    base = slugify_stickv(base_title)
    root = stickv_root(workspace_dir)
    if not (root / base).exists():
        return base
    idx = 2
    while (root / f"{base}-{idx}").exists():
        idx += 1
    return f"{base}-{idx}"


def save_stickv_project(workspace_dir: Path, project: StickvProject) -> StickvProject:
    pdir = stickv_project_dir(workspace_dir, project.slug)
    pdir.mkdir(parents=True, exist_ok=True)
    updated = project.model_copy(update={"updated_at": now_iso()})
    target = pdir / "project.json"
    tmp = pdir / "project.json.tmp"
    tmp.write_text(
        json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(target)
    return updated


def load_stickv_project(workspace_dir: Path, slug: str) -> StickvProject:
    pdir = stickv_project_dir(workspace_dir, slug)
    target = pdir / "project.json"
    if not target.is_file():
        raise NotFound(f"Không tìm thấy dự án StickV '{slug}'")
    raw = json.loads(target.read_text(encoding="utf-8"))
    return StickvProject.model_validate(raw)


def list_stickv_projects(workspace_dir: Path) -> list[StickvProject]:
    root = stickv_root(workspace_dir)
    projects: list[StickvProject] = []
    for child in root.iterdir():
        pfile = child / "project.json"
        if not child.is_dir() or not pfile.is_file():
            continue
        try:
            projects.append(StickvProject.model_validate_json(pfile.read_text(encoding="utf-8")))
        except Exception:
            continue
    projects.sort(key=lambda p: p.updated_at, reverse=True)
    return projects


def create_stickv_project(
    workspace_dir: Path,
    *,
    title: str,
    topic: str = "science",
    aspect: str = "9:16",
    theme: str = "cream",
    target_minutes: float = 1.0,
    gemini_model: str = "",
    beats: list[StickvBeat] | None = None,
) -> StickvProject:
    slug = _unique_slug(workspace_dir, title)
    proj = StickvProject(
        slug=slug,
        title=title.strip() or "Video StickV mới",
        topic=topic,
        aspect=aspect,  # type: ignore[arg-type]
        theme=theme,  # type: ignore[arg-type]
        music_mood=topic,
        gemini_model=gemini_model,
        target_minutes=target_minutes,
        beats=beats or [],
    )
    return save_stickv_project(workspace_dir, proj)


def delete_stickv_project(workspace_dir: Path, slug: str) -> None:
    pdir = stickv_project_dir(workspace_dir, slug)
    if not pdir.is_dir():
        raise NotFound(f"Không tìm thấy dự án StickV '{slug}'")
    shutil.rmtree(pdir)
