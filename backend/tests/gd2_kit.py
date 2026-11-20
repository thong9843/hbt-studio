"""Mẫu JSON nháp `hbt_draft: 1` dùng chung cho test GĐ2 (file `data/hbt-draft.sample.json`,
khớp docs/gd2/IMPLEMENT-GD2.md mục 2.2). E2e đọc cùng file."""

from __future__ import annotations

import copy
import json
from pathlib import Path

DATA = Path(__file__).parent / "data" / "hbt-draft.sample.json"

SAMPLE = json.loads(DATA.read_text(encoding="utf-8"))


def sample(**changes):
    """Bản sao của mẫu; `changes` ghi đè khoá gốc."""
    d = copy.deepcopy(SAMPLE)
    d.update(changes)
    return d


def codes(items):
    return [i["code"] for i in items]
