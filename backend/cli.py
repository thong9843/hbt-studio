"""Dòng lệnh: `python -m cli render <project_dir> [--preview] [--fps 30|50|60]` dựng video;
`python -m cli bench-align <project_dir> [--models small,medium,large-v3]` đo Whisper."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from hbt.config import ALLOWED_FPS, WHISPER_MODELS, load_settings
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.bench import bench_align, format_rows
from hbt.pipeline.ffutil import FFmpegError, media_duration
from hbt.pipeline.golden import GoldenError, import_file
from hbt.pipeline.render import RenderError, RenderOptions, render_project
from hbt.pipeline.whisper import DEFAULT_TIMEOUT, WhisperConfig
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
    r.add_argument(
        "--seconds",
        type=float,
        metavar="N",
        help="với --preview: chỉ dựng N giây đầu (căn chữ và điểm nhạc vẫn tính trên cả video)",
    )
    r.add_argument("--no-outro", action="store_true", help="không thêm outro")
    r.add_argument(
        "--allow-long-trim",
        action="store_true",
        help="cho phép cắt đuôi file giọng dài hơn 8 giây (chỉ dùng sau khi đã nghe và xác nhận)",
    )
    b = sub.add_parser(
        "bench-align", help="Đo Whisper: thời gian, tỉ lệ khớp âm tiết, lệch mốc cắt cảnh"
    )
    b.add_argument("project_dir", type=Path, help="thư mục chứa project.json")
    b.add_argument(
        "--models",
        default="auto",
        help="danh sách cách nhau bằng dấu phẩy: auto,small,medium,large-v3 (mặc định auto)",
    )
    b.add_argument(
        "--prompt",
        choices=("on", "off", "both"),
        default="off",
        help="đo không có initial_prompt (off, như đường dựng; mặc định), có (on), hoặc cả hai "
        "(both); chỉ để so sánh",
    )
    b.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"giới hạn thời gian mỗi model, giây (mặc định {DEFAULT_TIMEOUT})",
    )
    g = sub.add_parser(
        "golden-import", help="Nhập mốc đánh tay (nhãn Audacity) vào golden_marks.json của tập mẫu"
    )
    g.add_argument("sample_dir", type=Path, help="thư mục tập mẫu, ví dụ workspace/samples/muoi")
    g.add_argument(
        "--labels", type=Path, help="file nhãn Audacity (mặc định labels.txt trong thư mục mẫu)"
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


def _golden_import(args) -> int:
    try:
        duration = media_duration(args.sample_dir / "voice.mp3")
        path, n = import_file(args.sample_dir, args.labels, duration)
    except (GoldenError, ValidationError, FileNotFoundError, FFmpegError) as e:
        print(f"\nLỖI: {e}\nChưa ghi gì vào golden_marks.json.", file=sys.stderr)
        return 1
    print(f"Đã ghi {n} mốc vào {path}")
    return 0


def _bench_align(args, parser: argparse.ArgumentParser) -> int:
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in models if m not in WHISPER_MODELS]
    if not models or unknown:
        parser.error(f"--models: không hợp lệ {', '.join(unknown) or '(trống)'}")
    settings = load_settings()
    cfg = WhisperConfig(
        device=settings.whisper_device, timeout=args.timeout, models_dir=settings.models_dir
    )
    try:
        rows = bench_align(
            args.project_dir,
            models,
            cfg,
            log=lambda m: print(f"  {m}", flush=True),
            prompts={"on": (True,), "off": (False,), "both": (True, False)}[args.prompt],
        )
    except (ValidationError, ValueError, FileNotFoundError, FFmpegError) as e:
        print(f"\nLỖI: {e}", file=sys.stderr)
        return 1
    print("\n" + format_rows(rows))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # console Windows mặc định không in được tiếng Việt
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "bench-align":
        return _bench_align(args, parser)
    if args.command == "golden-import":
        return _golden_import(args)

    options = RenderOptions(
        preview=args.preview,
        fps=args.fps,
        outro=False if args.no_outro else None,
        allow_long_trim=args.allow_long_trim,
        preview_seconds=args.seconds,
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

    loudness = f"{result.lufs:.1f} LUFS" if result.lufs is not None else "(không đo)"
    print(
        f"\nXong trong {result.seconds:.0f} giây\n"
        f"  video   : {result.video}\n"
        f"  kích cỡ : {result.width}x{result.height} @ {result.fps} fps, "
        f"{result.duration:.2f} giây\n"
        f"  độ lớn  : {loudness}\n"
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
