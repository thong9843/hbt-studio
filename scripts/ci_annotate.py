"""Đọc báo cáo JUnit của pytest và in các test lỗi thành chú thích GitHub (`::error`).

Nhật ký của job CI chỉ người có quyền admin mới tải được; chú thích thì đọc được qua API công khai
(`/check-runs/<id>/annotations`), nên in lỗi ra đây để chẩn đoán CI đỏ mà không cần mở nhật ký.
Chạy: python scripts/ci_annotate.py pytest-report.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

MAX_ANNOTATIONS = 10  # GitHub chỉ hiển thị một số chú thích mỗi bước
MAX_MESSAGE = 1800


def escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def failures(root: ET.Element) -> list[tuple[str, str]]:
    found = []
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            for el in case.findall(kind):
                name = f"{case.get('classname', '')}.{case.get('name', '')}"
                detail = f"{el.get('message') or ''}\n{el.text or ''}".strip()
                found.append((name, detail))
    return found


def main(path: str) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        print(f"::error title=pytest::Không đọc được báo cáo {path}: {escape_data(str(e))}")
        return 1
    bad = failures(root)
    for name, detail in bad[:MAX_ANNOTATIONS]:
        print(f"::error title={escape_property(name)}::{escape_data(detail[:MAX_MESSAGE])}")
    if len(bad) > MAX_ANNOTATIONS:
        print(f"::warning title=pytest::Còn {len(bad) - MAX_ANNOTATIONS} test lỗi nữa chưa liệt kê")
    print(f"::notice title=pytest::{len(bad)} test lỗi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "pytest-report.xml"))
