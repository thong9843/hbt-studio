"""Mốc đánh tay cho golden test phụ đề (IMPLEMENT.md 10b):
`workspace/samples/<tên>/golden_marks.json`.

File dùng số thứ tự người dùng thấy (cụm và cảnh đều từ 1). Nội bộ code giữ chỉ số từ 0 và chỉ
đổi khi đọc/ghi file. `start` là giây trên file giọng GỐC, tại lúc bắt đầu chữ đầu tiên của cụm.
"""

from __future__ import annotations

import json
from pathlib import Path

from hbt.models import load_project

from .captions import split_phrases
from .text import parse_voice

MARKS_FILE = "golden_marks.json"
TOLERANCE_SEC = 0.2
NOTES = [
    "Số thứ tự cụm (index) và cảnh (scene) đều tính từ 1, như người dùng thấy.",
    "Điền 'start' (giây) trên file voice.mp3 GỐC, tại lúc bắt đầu chữ đầu tiên của cụm.",
    "Khi so sánh, app phải cộng VOICE_DELAY = 0,2 s (audio.py, bước chuẩn hoá giọng) vào 'start'.",
    "Cụm chia đúng theo captions.split_phrases.",
]


class GoldenError(ValueError):
    """Lỗi nhập mốc: thông báo tiếng Việt, không ghi file."""


def build_marks(project) -> dict:
    tokens, scene_of = [], []
    for si, scene in enumerate(project.scenes):
        ts = parse_voice(scene.voice)
        tokens += ts
        scene_of += [si] * len(ts)
    marks = [
        {
            "index": k + 1,
            "scene": scene_of[ids[0]] + 1,
            "text": " ".join(tokens[i]["disp"] for i in ids),
            "start": None,
        }
        for k, ids in enumerate(split_phrases(tokens, scene_of))
    ]
    return {"_notes": NOTES, "tolerance_sec": TOLERANCE_SEC, "marks": marks}


def parse_labels(text: str) -> tuple[list[tuple[float, str]], list[str]]:
    """Nhãn Audacity "start<TAB>end<TAB>tên" → [(start, tên)].
    Bỏ dòng trống và dòng bắt đầu bằng `\\`."""
    out: list[tuple[float, str]] = []
    errors: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("\\"):
            continue
        parts = line.split("\t")
        try:
            start = round(float(parts[0].strip().replace(",", ".")), 3)
        except ValueError:
            errors.append(f"Dòng {n}: '{parts[0].strip()}' không phải là số giây.")
            continue
        out.append((start, parts[2].strip() if len(parts) > 2 else ""))
    return out, errors


def import_labels(data: dict, labels_text: str, duration: float) -> dict:
    """Ghi `start` vào bản sao của `data["marks"]`; sai thì ném `GoldenError` (liệt kê mọi lỗi)."""
    labels, errors = parse_labels(labels_text)
    marks = data["marks"]
    total = len(marks)
    if len(labels) < total:
        errors.append(f"Thiếu {total - len(labels)} nhãn: có {len(labels)}, cần {total}.")
    elif len(labels) > total:
        errors.append(f"Thừa {len(labels) - total} nhãn: có {len(labels)}, cần {total}.")
    prev = None
    for k, (start, name) in enumerate(labels, 1):
        if start < 0 or start >= duration:
            errors.append(f"Nhãn {k}: {start} s nằm ngoài file giọng (0 đến {duration:.3f} s).")
        if prev is not None and start <= prev:
            errors.append(f"Nhãn {k}: {start} s không lớn hơn nhãn trước ({prev} s).")
        prev = start
        if name.isdigit() and int(name) != k:
            errors.append(f"Nhãn {k}: tên là số {name}, phải bằng thứ tự {k}.")
    if errors:
        raise GoldenError("\n".join(errors))
    return {**data, "marks": [{**m, "start": s} for m, (s, _) in zip(marks, labels, strict=True)]}


def import_file(sample_dir: Path, labels_path: Path | None, duration: float) -> tuple[Path, int]:
    """Đọc nhãn (mặc định `labels.txt` trong thư mục mẫu), ghi `golden_marks.json`.
    Chưa có `golden_marks.json` thì tạo từ project trước khi điền."""
    labels_path = labels_path or sample_dir / "labels.txt"
    if not labels_path.is_file():
        raise GoldenError(f"Không thấy file nhãn: {labels_path}")
    marks_path = sample_dir / MARKS_FILE
    if marks_path.is_file():
        data = json.loads(marks_path.read_text(encoding="utf-8"))
    else:
        data = build_marks(load_project(sample_dir))
    new = import_labels(data, labels_path.read_text(encoding="utf-8-sig"), duration)
    marks_path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    return marks_path, len(new["marks"])
