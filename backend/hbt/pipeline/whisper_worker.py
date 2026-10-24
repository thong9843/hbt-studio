"""Tiến trình con chạy Whisper: `python -m hbt.pipeline.whisper_worker <request.json>`.

Chạy ở tiến trình riêng để (a) kill được khi hết giờ hoặc huỷ job, (b) model và VRAM tự giải phóng
khi tiến trình thoát (IMPLEMENT.md 5.2). Kết quả ghi vào file `out` trong request:
  {"ok": true, "syllables": [[âm tiết, bắt đầu, kết thúc], ...]}
  {"ok": false, "stage": "load" | "run", "error": "..."}
`faster_whisper` chỉ được import ở đây, khi thật sự chạy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .text import norm


def syllables_of(segments, on_segment=None) -> list[list]:
    """Mỗi từ Whisper nghe được → các âm tiết đã chuẩn hoá, chia đều thời gian của từ.

    `on_segment(seg)` được gọi sau mỗi đoạn (để báo tiến độ)."""
    out: list[list] = []
    for seg in segments:
        if on_segment is not None:
            on_segment(seg)
        for w in seg.words or []:
            parts = [p for p in (norm(x) for x in w.word.split()) if p]
            if not parts:
                continue
            step = (w.end - w.start) / len(parts)
            for i, p in enumerate(parts):
                out.append([p, w.start + i * step, w.start + (i + 1) * step])
    return out


def progress_reporter(path, duration):
    """Mỗi đoạn nhận dạng xong thì thêm một dòng "phần giọng đã nghe" (0…1) vào file tiến độ."""
    if not path or not duration:
        return None

    def report(seg) -> None:
        frac = max(0.0, min(1.0, float(seg.end) / float(duration)))
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{frac:.4f}\n")

    return report


def run(req: dict) -> list[list]:
    stage = "load"
    try:
        from faster_whisper import WhisperModel  # import muộn: không bắt buộc cài

        model = WhisperModel(
            req["model"],
            device=req["device"],
            compute_type=req["compute_type"],
            download_root=req["models_dir"],
            local_files_only=req["local_only"],
        )
        stage = "run"
        segments, info = model.transcribe(
            req["wav"],
            language="vi",
            word_timestamps=True,
            beam_size=5,
            initial_prompt=req["prompt"][:220] or None,  # rỗng: không dùng prompt (5.2)
            condition_on_previous_text=False,
        )
        return syllables_of(segments, progress_reporter(req.get("progress"), info.duration))
    except Exception as e:
        e.stage = stage  # type: ignore[attr-defined]
        raise


def main(argv: list[str]) -> int:
    req = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out = Path(req["out"])
    try:
        result = {"ok": True, "syllables": run(req)}
        code = 0
    except Exception as e:  # noqa: BLE001 — mọi lỗi (kể cả thiếu gói) đều báo lại cho tiến trình cha
        stage = getattr(e, "stage", "load")
        result = {"ok": False, "stage": stage, "error": f"{e.__class__.__name__}: {e}"}
        code = 1
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
