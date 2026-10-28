"""Khối JSON kịch bản (IMPLEMENT.md 13.B4): đọc, gộp vào project và kiểm K1–K12.

Module này không ghi file nào: `check_script` trả kết quả kiểm cùng bản project sau gộp, việc ghi
(sao lưu, `base_hash`) do `api/script.py` làm. Đo chữ thẻ dùng lại `SIZES`, `font`, `_wrap` của
`pipeline/visual.py` (chỉ đọc, không sửa).
"""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image, ImageDraw
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
)

from hbt.models import (
    MAX_SCENES,
    MIN_SCENES,
    Card,
    CardLine,
    Label,
    Project,
    Publish,
    Scene,
    Thumbnail,
)
from hbt.pipeline.lint import lint_project
from hbt.pipeline.visual import SIZES, _wrap, font
from hbt.sensitive import SensitiveWords

TEXT_W = 960 - 2 * 36  # rộng chữ tối đa trong thẻ (draw_card: maxw 960, pad 36)
LINE_CHAR_LIMIT = {"xl": 10, "l": 15, "m": 22, "s": 26}  # K5
MAX_CARD_LINES = 3  # K7
Extra = Literal["add", "trim"]

# Trường project không đổi được qua JSON (K4). Ở cấp cảnh, `voice` là lời đọc nên được phép.
FORBIDDEN_FIELDS = frozenset(
    {"image", "voice", "music", "settings", "title", "slug", "series", "theme", "version"}
)

_UNION_TAG = re.compile(r"^(literal\[.*|int|str|float|bool|none)$")
_ERROR_TEXT = {
    "missing": "Thiếu trường này",
    "string_type": "Phải là chuỗi chữ",
    "bool_type": "Phải là true hoặc false",
    "int_type": "Phải là số nguyên",
    "list_type": "Phải là danh sách",
    "model_type": "Phải là một khối {…}",
    "dict_type": "Phải là một khối {…}",
    "literal_error": "Giá trị không nằm trong các giá trị cho phép",
    "too_short": "Có quá ít phần tử",
    "too_long": "Có quá nhiều phần tử",
}


# ---------------------------------------------------------------------------- mô hình đầu vào
# Bản chặt (extra="forbid") của các khối trong models.py để bắt trường lạ (K4); kiểu và giá trị
# hợp lệ vẫn lấy từ chính các lớp đó (K3). `models.py` giữ extra="ignore".
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScriptLine(CardLine):
    model_config = ConfigDict(extra="forbid")


class ScriptCard(Card):
    model_config = ConfigDict(extra="forbid")
    lines: list[ScriptLine] = Field(default_factory=list)


class ScriptLabel(Label):
    model_config = ConfigDict(extra="forbid")


class ScriptPublish(Publish):
    model_config = ConfigDict(extra="forbid")


class ScriptThumbnail(Thumbnail):
    model_config = ConfigDict(extra="forbid")


class ScriptScene(_Strict):
    voice: StrictStr = ""
    card: ScriptCard = Field(default_factory=ScriptCard)
    labels: list[ScriptLabel] = Field(default_factory=list)
    punch: StrictBool = False
    caption_y: StrictInt | None = None


class ScriptIn(_Strict):
    hbt_script: Literal[1] = 1
    scenes: list[ScriptScene] = Field(default_factory=list)
    publish: ScriptPublish = Field(default_factory=ScriptPublish)
    thumbnail: ScriptThumbnail = None  # type: ignore[assignment]  # null không hợp lệ


# ---------------------------------------------------------------------------- kết quả
def _issue(
    code: str, field_: str, message: str, scene_index: int | None = None, level: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "code": code,
        "scene_index": scene_index,
        "field": field_,
        "message": message,
    }
    if level is not None:
        out["level"] = level
    return out


@dataclass
class ScriptCheck:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    diff: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {"json": 0, "project": 0, "after": 0})
    realign_scenes: list[int] = field(default_factory=list)
    merged: Project | None = None  # bản project sau gộp; chỉ có khi `ok`

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "diff": self.diff,
            "counts": self.counts,
            "realign_scenes": self.realign_scenes,
        }


# ---------------------------------------------------------------------------- đọc và chuẩn hoá
def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(v) for v in value]
    if isinstance(value, dict):
        return {k: _nfc(v) for k, v in value.items()}
    return value


def _path(loc: tuple) -> tuple[int | None, str]:
    """Đổi `loc` của Pydantic thành (chỉ số cảnh | None, đường dẫn dạng `card.lines[0].size`)."""
    parts = list(loc)
    while parts and isinstance(parts[-1], str) and _UNION_TAG.match(parts[-1]):
        parts.pop()
    scene_index = None
    if len(parts) >= 2 and parts[0] == "scenes" and isinstance(parts[1], int):
        scene_index = parts[1]
        parts = parts[2:]
    text = ""
    for p in parts:
        text += f"[{p}]" if isinstance(p, int) else (f".{p}" if text else str(p))
    return scene_index, text


def _validation_issues(err: ValidationError) -> list[dict]:
    issues, seen = [], set()
    for e in err.errors():
        scene_index, path = _path(e["loc"])
        if (scene_index, path) in seen:  # trường kiểu hợp (Union) báo nhiều lần cùng chỗ
            continue
        seen.add((scene_index, path))
        name = next((p for p in reversed(e["loc"]) if isinstance(p, str)), "")
        where = f"Cảnh {scene_index + 1}, " if scene_index is not None else ""
        if e["type"] == "extra_forbidden":
            if name in FORBIDDEN_FIELDS:
                msg = f"{where}trường “{name}” không đổi được qua JSON"
            else:
                msg = f"{where}trường lạ “{name}” (sai tên?)"
            issues.append(_issue("K4", path, msg, scene_index))
            continue
        union = (
            bool(e["loc"])
            and isinstance(e["loc"][-1], str)
            and bool(_UNION_TAG.match(e["loc"][-1]))
        )
        detail = (
            "Giá trị không hợp lệ"
            if union
            else _ERROR_TEXT.get(e["type"])
            or re.sub(r"^Value error, ", "", e["msg"])  # lỗi do validator của models.py
        )
        code = "K11" if path.startswith("thumbnail.lines") else "K3"
        issues.append(_issue(code, path, f"{where}{path or 'JSON'}: {detail}", scene_index))
    return issues


def parse_script(raw: Any) -> tuple[ScriptIn | None, list[dict]]:
    """`raw`: chuỗi JSON (K1: báo dòng:cột) hoặc giá trị đã đọc; gốc là mảng thì coi là `scenes`."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw.lstrip("﻿"))
        except json.JSONDecodeError as e:
            return None, [
                _issue("K1", "", f"JSON không đọc được: dòng {e.lineno}, cột {e.colno}: {e.msg}")
            ]
    if isinstance(raw, list):
        raw = {"scenes": raw}
    if not isinstance(raw, dict):
        return None, [_issue("K3", "", "Gốc JSON phải là một khối {…} hoặc một danh sách […]")]
    try:
        return ScriptIn.model_validate(_nfc(raw)), []
    except ValidationError as e:
        return None, _validation_issues(e)


def _clean_hashtags(tags: list[str]) -> list[str]:
    cleaned = (t.strip().lstrip("#").strip() for t in tags)
    return [t for t in cleaned if t]


# ---------------------------------------------------------------------------- kiểm thẻ chữ
def _card_issues(i: int, card: dict) -> tuple[list[dict], list[dict]]:
    """K5–K8 cho thẻ của cảnh `i`. Trả về (lỗi, cảnh báo)."""
    errors: list[dict] = []
    warns: list[dict] = []
    lines = [ln for ln in card["lines"] if ln["text"]]
    n = i + 1
    if not lines:
        warns.append(_issue("K7", "card.lines", f"Cảnh {n}: thẻ chữ không có dòng nào", i))
    if len(lines) > MAX_CARD_LINES:
        warns.append(_issue("K7", "card.lines", f"Cảnh {n}: thẻ có {len(lines)} dòng (nên ≤ 3)", i))
    if sum(1 for ln in lines if ln["color"] == "accent") > 1:
        warns.append(_issue("K7", "card.lines", f"Cảnh {n}: có hơn 1 dòng màu accent", i))
    draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    for j, ln in enumerate(lines):
        text, where = ln["text"], f"card.lines[{j}]"
        limit = LINE_CHAR_LIMIT[ln["size"]]
        if len(text) > limit:
            warns.append(
                _issue(
                    "K5",
                    where,
                    f"Cảnh {n}, dòng {j + 1}: {len(text)} ký tự, cỡ {ln['size']} nên ≤ {limit}",
                    i,
                )
            )
        if any(c in text for c in "|{}"):
            warns.append(
                _issue("K8", where, f"Cảnh {n}, dòng {j + 1}: chữ thẻ có ký tự |, {{ hoặc }}", i)
            )
        px = SIZES[ln["size"]]
        f = font("ExtraBold" if px >= 70 else "Bold", px)
        wide = [w for w in text.split() if draw.textlength(w, font=f) > TEXT_W]
        if wide:
            errors.append(
                _issue(
                    "K6",
                    where,
                    f"Cảnh {n}, dòng {j + 1}: từ “{wide[0]}” rộng hơn {TEXT_W} px, bị tràn thẻ",
                    i,
                )
            )
        parts = _wrap(draw, text, f, TEXT_W)
        if len(parts) > 1:
            warns.append(
                _issue(
                    "K6b", where, f"Cảnh {n}, dòng {j + 1} tự xuống hàng thành {len(parts)} dòng", i
                )
            )
    return errors, warns


# ---------------------------------------------------------------------------- kiểm và gộp
def check_script(
    project: Project,
    raw: Any,
    words: SensitiveWords | None = None,
    extra: Extra | None = None,
) -> ScriptCheck:
    """Kiểm khối JSON `raw` và gộp vào bản sao của `project` (không ghi gì)."""
    res = ScriptCheck()
    n_proj = len(project.scenes)
    res.counts = {"json": 0, "project": n_proj, "after": n_proj}
    script, issues = parse_script(raw)
    if script is None:
        res.errors = issues
        data = raw.get("scenes") if isinstance(raw, dict) else raw
        res.counts["json"] = len(data) if isinstance(data, list) else 0
        return res

    current = project.model_dump(mode="json")
    scenes: list[dict] = current["scenes"]
    defaults = Scene().model_dump(mode="json")
    touched: dict[int, set[str]] = {}  # chỉ số cảnh → các trường JSON ghi đè
    added: set[int] = set()

    # --- số cảnh (K2, 13.B4.5)
    apply_n = 0
    if "scenes" in script.model_fields_set:
        n_json = len(script.scenes)
        res.counts["json"] = n_json
        apply_n = min(n_json, n_proj)
        if n_json < n_proj:
            res.warnings.append(
                _issue(
                    "K2",
                    "scenes",
                    f"JSON có {n_json} cảnh, project có {n_proj}: chỉ áp cho cảnh 1…{n_json}",
                )
            )
        elif n_json > n_proj:
            surplus = n_json - n_proj
            if extra == "add":
                added = set(range(n_proj, n_json))
                scenes += [deepcopy(defaults) for _ in added]
                apply_n = n_json
            elif extra == "trim":
                res.warnings.append(
                    _issue("K2", "scenes", f"Bỏ {surplus} cảnh thừa của JSON (cảnh {n_proj + 1}…)")
                )
            else:
                res.errors.append(
                    _issue(
                        "K2",
                        "scenes",
                        f"JSON có {n_json} cảnh, project chỉ có {n_proj}: "
                        "chọn Thêm cảnh hoặc Bỏ phần thừa",
                    )
                )
        if not MIN_SCENES <= len(scenes) <= MAX_SCENES:
            res.errors.append(
                _issue(
                    "K2",
                    "scenes",
                    f"Sau khi gộp có {len(scenes)} cảnh, cần từ {MIN_SCENES} đến {MAX_SCENES}",
                )
            )
    res.counts["after"] = len(scenes)

    # --- gộp từng cảnh (trường vắng giữ nguyên, trường có mặt ghi đè cả trường)
    for i in range(apply_n):
        given = script.scenes[i]
        values = given.model_dump(mode="json")
        before = scenes[i]
        changed = {}
        touched[i] = set(given.model_fields_set)
        for name in given.model_fields_set:
            old = before.get(name, defaults[name])
            if values[name] != old:
                changed[name] = (old, values[name])
            before[name] = values[name]
        if i in added:
            res.diff.append(
                {
                    "scene_index": i,
                    "field": "scene",
                    "before": None,
                    "after": {k: values[k] for k in given.model_fields_set},
                }
            )
        else:
            res.diff += [
                {"scene_index": i, "field": k, "before": old, "after": new}
                for k, (old, new) in changed.items()
            ]
        if "voice" in changed:
            res.realign_scenes.append(i)

    # --- khối publish, thumbnail
    if "publish" in script.model_fields_set:
        pub = script.publish.model_dump(mode="json")
        pub["hashtags"] = _clean_hashtags(pub["hashtags"])
        if pub != current["publish"]:
            before = current["publish"]
            res.diff.append(
                {"scene_index": None, "field": "publish", "before": before, "after": pub}
            )
        current["publish"] = pub
    if "thumbnail" in script.model_fields_set:
        thumb = script.thumbnail.model_dump(mode="json")
        if thumb != current["thumbnail"]:
            res.diff.append(
                {
                    "scene_index": None,
                    "field": "thumbnail",
                    "before": current["thumbnail"],
                    "after": thumb,
                }
            )
        current["thumbnail"] = thumb
        if thumb["scene"] > len(scenes):
            res.errors.append(
                _issue(
                    "K11",
                    "thumbnail.scene",
                    f"Ảnh bìa lấy cảnh {thumb['scene']} nhưng chỉ có {len(scenes)} cảnh",
                )
            )

    # --- thẻ chữ và lời đọc của các cảnh được ghi (K5–K9)
    for i, names in sorted(touched.items()):
        if "card" in names:
            errs, warns = _card_issues(i, scenes[i]["card"])
            res.errors += errs
            res.warnings += warns
        if ("voice" in names or i in added) and not re.sub(r"[|{}\s]", "", scenes[i]["voice"]):
            res.warnings.append(_issue("K9", "voice", f"Cảnh {i + 1}: lời đọc đang trống", i))

    # --- K12: toàn bộ project sau gộp
    try:
        merged = Project.model_validate(current)
    except ValidationError as e:
        covered = {"scenes": any(x["code"] == "K2" for x in res.errors)}
        covered["thumbnail"] = any(x["code"] == "K11" for x in res.errors)
        for item in _validation_issues(e):
            if item["field"] == "scenes" and covered["scenes"]:
                continue
            if "thumbnail.scene" in item["message"] and covered["thumbnail"]:
                continue
            item["code"] = "K12"
            res.errors.append(item)
        return res

    # --- K9 (tổng lời đọc) và K10 (từ nhạy cảm) trên bản đã gộp
    for it in lint_project(merged, words):
        if it.category == "voice_length":
            res.warnings.append(_issue("K9", it.field, it.message, it.scene_index))
        elif it.category != "number_reading":
            note = " — sẽ chặn xuất" if it.level == "block" else ""
            res.warnings.append(
                _issue("K10", it.field, it.message + note, it.scene_index, level=it.level)
            )
    if res.ok:
        res.merged = merged
    return res
