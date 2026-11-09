"""Mẫu JSON trong tài liệu GĐ2 phải khớp file mẫu dùng cho test và e2e."""

import json
import re
from pathlib import Path

import pytest

from tests.gd2_kit import SAMPLE

DOCS = Path(__file__).resolve().parents[2] / "docs" / "archive" / "gd2"
if not DOCS.exists():
    DOCS = Path(__file__).resolve().parents[2] / "docs" / "gd2"


def sample_block(path: Path, heading: str) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(re.escape(heading) + r".*?```json\n(.*?)\n```", text, re.S)
    assert m, f"{path.name}: không thấy khối json sau '{heading}'"
    return json.loads(m.group(1))


@pytest.mark.parametrize(
    ("name", "heading"),
    [("PROMPT-KICH-BAN.md", "## Mẫu JSON hợp lệ"), ("IMPLEMENT-GD2.md", "### 2.2 Mẫu hợp lệ")],
)
def test_doc_sample_matches_fixture(name, heading):
    assert sample_block(DOCS / name, heading) == SAMPLE
