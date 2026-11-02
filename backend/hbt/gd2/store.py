"""`draft.json` cạnh `project.json` (IMPLEMENT-GD2 mục 2.4)."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from hbt.gd2.checks import FORBIDDEN, full_prompt
from hbt.gd2.draft import DraftSplit
from hbt.storage import BadRequest, NotFound, Unprocessable, _write_json_atomic

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
        "approved_marks": [],
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


def effective_draft(doc: dict, images: list[str]) -> dict:
    """Bản nháp để trả ra API (không ghi). `images`: `scene.image` hiện tại của từng cảnh.

    Duyệt ảnh lưu dấu ảnh từng cảnh lúc duyệt (`approved_marks`); cảnh có ảnh khác dấu, hoặc
    chưa có ảnh, là chưa duyệt. `images_approved` chỉ đúng khi cả bộ cảnh còn khớp dấu."""
    out = json.loads(json.dumps(doc))
    marks = out.get("approved_marks") or []
    scenes = out.get("scenes") or []
    flag = bool(out.get("images_approved")) and len(marks) == len(scenes) > 0
    all_ok = flag
    for i, scene in enumerate(scenes):
        image = images[i] if i < len(images) else ""
        ok = flag and bool(image) and i < len(marks) and marks[i] == image
        scene["image_approved"] = ok
        scene["full_prompt"] = (
            full_prompt(scene["image_prompt"])
            if scene.get("image_prompt_ok") and scene.get("image_prompt")
            else ""
        )
        scene["forbidden"] = list(
            dict.fromkeys(
                m.group(1).lower() for m in FORBIDDEN.finditer(scene.get("image_prompt") or "")
            )
        )
        all_ok = all_ok and ok
    out["images_approved"] = all_ok
    return out


def set_approved(folder: Path, approved: bool, images: list[str]) -> dict:
    """Duyệt (lưu dấu ảnh từng cảnh; thiếu ảnh → 422) hoặc bỏ duyệt (xoá dấu)."""
    doc = read_draft(folder)
    if approved:
        missing = [i + 1 for i, img in enumerate(images) if not img]
        if missing:
            raise Unprocessable("Chưa có ảnh ở cảnh " + ", ".join(str(n) for n in missing))
        doc["images_approved"] = True
        doc["approved_marks"] = list(images)
    else:
        doc["images_approved"] = False
        doc["approved_marks"] = []
    write_draft(folder, doc)
    return doc


def set_prompt(folder: Path, index: int, prompt: str) -> dict:
    """Đặt `image_prompt` cho cảnh `index` (từ 0). Không đụng dấu duyệt ảnh."""
    doc = read_draft(folder)
    scenes = doc.get("scenes") or []
    if not 0 <= index < len(scenes):
        raise NotFound(f"Không có cảnh {index + 1} trong bản nháp")
    text = unicodedata.normalize("NFC", prompt).strip()
    scenes[index]["image_prompt"] = text
    scenes[index]["image_prompt_ok"] = bool(text)
    write_draft(folder, doc)
    return doc
