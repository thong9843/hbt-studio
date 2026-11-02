"""Kiểm JSON nháp: K1–K12 (bộ kiểm M5, không đổi) + K13–K18 (IMPLEMENT-GD2 mục 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hbt.gd2.checks import check_prompts, check_sources_for_numbers
from hbt.gd2.draft import DraftSplit, split_draft
from hbt.gd2.music_pick import MusicPick, pick_music
from hbt.models import MAX_SCENES, MIN_SCENES, Project, Scene
from hbt.script import ScriptCheck, _issue, check_script
from hbt.sensitive import SensitiveWords


@dataclass
class DraftCheck:
    split: DraftSplit
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    script_check: ScriptCheck | None = None
    prompt_ok: list[bool] = field(default_factory=list)
    music: MusicPick = field(default_factory=MusicPick)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        sc = self.script_check
        entry = self.music.entry
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "topic": self.split.topic,
            "series_hint": self.split.series_hint,
            "scenes": self.split.scene_count,
            "counts": sc.counts if sc else None,
            "music_match": {"id": entry.id, "title": entry.title} if entry else None,
        }


def _blank_project(n: int) -> Project:
    return Project(slug="gd2-check", title="gd2-check", scenes=[Scene() for _ in range(n)])


def check_draft(
    raw: Any, words: SensitiveWords | None, library_dir: Path | None = None
) -> DraftCheck:
    """Chỉ kiểm, không ghi gì. `library_dir` là `library/` (chứa `music/`); None = bỏ qua nhạc."""
    split = split_draft(raw)
    res = DraftCheck(split=split, errors=list(split.errors))
    if split.script is None:  # K1 hoặc gốc không phải khối
        return res

    n = split.scene_count
    if MIN_SCENES <= n <= MAX_SCENES:
        sc = check_script(_blank_project(n), split.script, words)
        res.script_check = sc
        res.errors += sc.errors
        res.warnings += sc.warnings
    else:
        res.errors.append(
            _issue("K2", "scenes", f"Bản nháp có {n} cảnh, cần từ {MIN_SCENES} đến {MAX_SCENES}")
        )

    voices = [
        s.get("voice", "") if isinstance(s, dict) and isinstance(s.get("voice", ""), str) else ""
        for s in split.script.get("scenes", [])
    ]
    res.warnings += check_sources_for_numbers(voices, split.sources)
    prompt_warns, res.prompt_ok = check_prompts(split.prompts)
    res.warnings += prompt_warns

    if library_dir is not None and split.music_mood:
        res.music = pick_music(Path(library_dir) / "music", split.music_mood)
        if res.music.warning:
            res.warnings.append(_issue("MUSIC", "music_mood", res.music.warning))
    return res
