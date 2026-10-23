"""Dòng lệnh dựng video: `python -m cli render <project_dir> [--preview] [--fps 30|50|60]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from hbt.config import ALLOWED_FPS
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.ffutil import FFmpegError
from hbt.pipeline.render import RenderError, RenderOptions, render_project
from hbt.sensitive import SensitiveStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli", description="HBT Studio — dòng lệnh")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("render", help="Dựng video từ một thư mục project")
    r.add_argument("project_dir", type=Path, help="thư mục chứa project.json")
    r.add_argument("--preview", action="store_true", help="Xem nhanh: 540×960, 30 fps")
    r.add_argument(
        "--fps", type=int, choices=ALLOWED_FPS, help="ghi đè settings.fps (mặc định theo project)"
    )
    r.add_argument("--no-outro", action="store_true", help="không thêm outro")
    r.add_argument(
        "--allow-long-trim",
        action="store_true",
        help="cho phép cắt đuôi file giọng dài hơn 8 giây (chỉ dùng sau khi đã nghe và xác nhận)",
    )
    return parser


def _progress_printer():
    state = {"step": None}

    def show(pct: float, step: str, message: str) -> None:
        if step != state["step"]:
            state["step"] = step
            print(f"[{pct:5.1f}%] {step}", flush=True)
        if message:
            print(f"         {message}", flush=True)

    return show


def current_sensitive_words(project_dir: Path):
    """Danh sách từ nhạy cảm hiện hành: bản riêng `workspace/settings/` nếu có, không thì bản
    mặc định. Thư mục project nằm ngoài `workspace/projects/` thì dùng bản mặc định."""
    parent = project_dir.resolve().parent
    workspace = parent.parent if parent.name == "projects" else parent
    return SensitiveStore(workspace).load()


def _describe(err: ValidationError) -> str:
    return "\n".join(
        f"  {'.'.join(str(p) for p in e['loc']) or '(gốc)'}: {e['msg']}" for e in err.errors()
    )


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # console Windows mặc định không in được tiếng Việt
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

    options = RenderOptions(
        preview=args.preview,
        fps=args.fps,
        outro=False if args.no_outro else None,
        allow_long_trim=args.allow_long_trim,
    )
    try:
        options.sensitive_words = current_sensitive_words(args.project_dir)
        result = render_project(args.project_dir, options, progress=_progress_printer())
    except TailTrimNeedsConfirmation as e:
        print(
            f"\nDỪNG: {e}\nChạy lại với --allow-long-trim nếu đúng là phần cần cắt.",
            file=sys.stderr,
        )
        return 2
    except ValidationError as e:
        print(f"\nproject.json không hợp lệ:\n{_describe(e)}", file=sys.stderr)
        return 1
    except (RenderError, FFmpegError, FileNotFoundError, ValueError) as e:
        print(f"\nLỖI: {e}", file=sys.stderr)
        return 1

    print(
        f"\nXong trong {result.seconds:.0f} giây\n"
        f"  video   : {result.video}\n"
        f"  kích cỡ : {result.width}x{result.height} @ {result.fps} fps, "
        f"{result.duration:.2f} giây\n"
        f"  độ lớn  : {result.lufs:.1f} LUFS\n"
        f"  aligner : {result.aligner}\n"
        f"  phụ đề  : {result.srt or '(tắt)'}\n"
        f"  đăng bài: {result.publish}\n"
        f"  nhật ký : {result.log}"
    )
    for w in result.warnings:
        print(f"  CẢNH BÁO: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
