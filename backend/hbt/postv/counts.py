"""Đọc số liệu kiểu mạng xã hội (`27.6K`, `1,5K`, `2M`, `1.200`) thành số nguyên.

Dùng chung bộ ca `shared/count_cases.json` với giao diện (`frontend/src/utils/count.ts`).
"""

from __future__ import annotations

import re

_SUFFIX = {"": 1, "k": 1_000, "m": 1_000_000}
_WITH_SUFFIX = re.compile(r"^(\d+(?:[.,]\d+)?)([km])$")
_GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_PLAIN = re.compile(r"^\d+$")


def parse_count(raw: str | None) -> int | None:
    """`None` nếu không đọc được. Có hậu tố K/M: dấu `.` hoặc `,` là dấu thập phân; không có
    hậu tố: nhóm 3 chữ số là hàng nghìn (`1.200` → 1200); `1,5` (không hậu tố) không đọc được."""
    s = (raw or "").strip().lower().replace(" ", "")
    if not s:
        return None
    if _PLAIN.match(s):
        return int(s)
    if _GROUPED.match(s):
        return int(re.sub(r"[.,]", "", s))
    m = _WITH_SUFFIX.match(s)
    if m:
        number = float(m.group(1).replace(",", "."))
        return round(number * _SUFFIX[m.group(2)])
    return None
