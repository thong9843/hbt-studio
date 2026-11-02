"""Đọc và tách JSON nháp `hbt_draft: 1` (IMPLEMENT-GD2 mục 2, K13–K15).

Trường nháp (`topic`, `series_hint`, `music_mood`, `sources`, `scenes[].image_prompt`) đi vào
`draft.json`; phần còn lại, bỏ `hbt_draft`, thêm `hbt_script: 1`, là khối `hbt_script` của M5."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from hbt.script import _issue, _nfc

DRAFT_KEYS = ("topic", "series_hint", "music_mood", "sources")


@dataclass
class DraftSplit:
    errors: list[dict] = field(default_factory=list)
    topic: str = ""
    series_hint: str = ""
    music_mood: str = ""
    sources: list[dict] = field(default_factory=list)
    prompts: list[Any] = field(default_factory=list)  # image_prompt từng cảnh (None = vắng)
    script: dict | None = None  # khối hbt_script; None khi JSON không đọc được

    @property
    def scene_count(self) -> int:
        return len(self.prompts)


def _is_one(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v == 1


def _check_sources(raw: Any) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    if raw is None:
        return [], errors
    if not isinstance(raw, list):
        return [], [_issue("K14", "sources", "sources phải là một danh sách các nguồn")]
    out: list[dict] = []
    seen: set[str] = set()
    for n, item in enumerate(raw, 1):
        where = f"sources[{n - 1}]"
        if not isinstance(item, dict):
            errors.append(_issue("K14", where, f"Nguồn {n} phải là một khối {{id, claim, url}}"))
            continue
        for key in ("id", "claim", "url"):
            v = item.get(key)
            if not isinstance(v, str) or not v.strip():
                errors.append(_issue("K14", f"{where}.{key}", f"Nguồn {n} thiếu hoặc rỗng '{key}'"))
        sid = item.get("id")
        if isinstance(sid, str) and sid.strip():
            if sid in seen:
                errors.append(_issue("K14", f"{where}.id", f"Nguồn {n}: id '{sid}' bị trùng"))
            seen.add(sid)
        out.append(
            {k: item[k].strip() for k in ("id", "claim", "url") if isinstance(item.get(k), str)}
        )
    return out, errors


def split_draft(raw: Any) -> DraftSplit:
    """`raw`: chuỗi JSON (K1: báo dòng:cột) hoặc giá trị đã đọc."""
    res = DraftSplit()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw.lstrip("﻿"))
        except json.JSONDecodeError as e:
            res.errors.append(
                _issue("K1", "", f"JSON không đọc được: dòng {e.lineno}, cột {e.colno}: {e.msg}")
            )
            return res
    if not isinstance(raw, dict):
        res.errors.append(_issue("K13", "", "Gốc JSON nháp phải là một khối {…}"))
        return res
    raw = _nfc(raw)

    if not _is_one(raw.get("hbt_draft")):
        res.errors.append(_issue("K13", "hbt_draft", "hbt_draft phải bằng 1"))
    topic = raw.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        res.errors.append(_issue("K13", "topic", "Thiếu hoặc rỗng 'topic'"))
    else:
        res.topic = topic.strip()

    hint = raw.get("series_hint", "")
    if isinstance(hint, str):
        res.series_hint = hint.strip()
    else:
        res.errors.append(_issue("K15", "series_hint", "series_hint phải là chuỗi"))
    mood = raw.get("music_mood", "")
    if isinstance(mood, str):
        res.music_mood = mood.strip()
    else:
        res.errors.append(_issue("K15", "music_mood", "music_mood phải là chuỗi"))

    res.sources, errs = _check_sources(raw.get("sources"))
    res.errors += errs

    script = {k: v for k, v in raw.items() if k != "hbt_draft" and k not in DRAFT_KEYS}
    script["hbt_script"] = 1
    scenes = raw.get("scenes")
    if isinstance(scenes, list):
        cleaned = []
        for i, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                cleaned.append(scene)  # để ScriptIn báo lỗi
                res.prompts.append(None)
                continue
            scene = dict(scene)
            prompt = scene.pop("image_prompt", None)
            if prompt is not None and not isinstance(prompt, str):
                res.errors.append(
                    _issue(
                        "K15",
                        f"scenes[{i}].image_prompt",
                        f"Cảnh {i + 1}: image_prompt phải là chuỗi",
                        i,
                    )
                )
                prompt = None
            res.prompts.append(prompt)
            cleaned.append(scene)
        script["scenes"] = cleaned
    res.script = script
    return res
