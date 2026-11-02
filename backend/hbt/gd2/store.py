"""`draft.json` cạnh `project.json` (IMPLEMENT-GD2 mục 2.4)."""

from __future__ import annotations

import json
from pathlib import Path

from hbt.gd2.draft import DraftSplit
from hbt.storage import BadRequest, NotFound, _write_json_atomic

DRAFT_FILE = "draft.json"


def build_draft_doc(split: DraftSplit, prompt_ok: list[bool]) -> dict:
    return {
        "draft": 1,
        "topic": split.topic,
        "series_hint": split.series_hint,
        "music_mood": split.music_mood,
        "sources": split.sources,
        "scenes": [
            {"image_prompt": (p.strip() if isinstance(p, str) else ""), "image_prompt_ok": ok}
            for p, ok in zip(split.prompts, prompt_ok, strict=True)
        ],
        "images_approved": False,
    }


def write_draft(folder: Path, doc: dict) -> None:
    _write_json_atomic(folder / DRAFT_FILE, doc)


def read_draft(folder: Path) -> dict:
    path = folder / DRAFT_FILE
    if not path.is_file():
        raise NotFound("Dự án này không có bản nháp (draft.json)")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BadRequest(f"draft.json không hợp lệ: {e}") from e
