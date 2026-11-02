"""Dòng lệnh: `python -m cli render <project_dir> [--preview] [--fps 30|50|60]` dựng video;
`python -m cli bench-align <project_dir> [--models small,medium,large-v3]` đo Whisper;
`python -m cli pack-media` / `unpack-media` chuyển media giữa hai máy (zip + sha256)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from pydantic import ValidationError

from hbt import transfer
from hbt.config import ALLOWED_FPS, REPO_ROOT, WHISPER_MODELS, load_settings
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.bench import bench_align, format_rows
from hbt.pipeline.ffutil import FFmpegError
from hbt.pipeline.render import RenderError, RenderOptions, render_project
from hbt.pipeline.whisper import DEFAULT_TIMEOUT, WhisperConfig
from hbt.postv.censor import CensorStore
from hbt.postv.models import project_kind
from hbt.postv.render import render_postv
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
    groups_help = (
        f"nhóm media, cách nhau bằng dấu phẩy (mặc định tất cả: {','.join(transfer.GROUPS)})"
    )
    pk = sub.add_parser(
        "pack-media", help="Gói media (nền, nhạc, giọng VieNeu, dự án mẫu) thành zip + manifest"
    )
    pk.add_argument("--out", type=Path, default=REPO_ROOT / "workspace" / "transfer")
    pk.add_argument("--groups", help=groups_help)
    pk.add_argument("--dry-run", action="store_true", help="chỉ đếm file và dung lượng")
    up = sub.add_parser(
        "unpack-media", help="Giải gói vào repo, kiểm sha256, không ghi đè file git theo dõi"
    )
    up.add_argument("src", type=Path, nargs="?", default=REPO_ROOT / "workspace" / "transfer")
    up.add_argument("--groups", help=groups_help)
    up.add_argument(
        "--with-index", action="store_true", help="cho phép ghi đè index.json của thư viện"
    )
    up.add_argument("--force", action="store_true", help="ghi đè file có sẵn nhưng khác nội dung")
    return parser


def _git_tracked(root: Path) -> set[str]:
    """File git đang theo dõi (posix, tương đối). Không chạy được git thì chỉ coi các `index.json`
    của thư viện là đang theo dõi (an toàn hơn là ghi đè)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True, timeout=60
        ).stdout
        return {p for p in out.decode("utf-8").split("\0") if p}
    except (OSError, subprocess.SubprocessError):
        return {"library/backgrounds/index.json", "library/music/index.json"}


def _split(value: str | None) -> list[str] | None:
    return [g.strip() for g in value.split(",") if g.strip()] if value else None


def _media(args) -> int:
    def log(m: str) -> None:
        print(f"  {m}", flush=True)

    try:
        if args.command == "pack-media":
            if args.dry_run:
                for group, files in transfer.plan_pack(REPO_ROOT, _split(args.groups)).items():
                    size = sum(p.stat().st_size for p in files)
                    print(f"  {group}: {len(files)} file, {size / 1e6:.1f} MB")
                return 0
            transfer.pack(REPO_ROOT, args.out, _split(args.groups), log)
            print(f"\nĐã ghi vào {args.out}")
            return 0
        report = transfer.unpack(
            REPO_ROOT,
            args.src,
            tracked=_git_tracked(REPO_ROOT),
            with_index=args.with_index,
            force=args.force,
            groups=_split(args.groups),
            log=log,
        )
    except (transfer.TransferError, OSError, zipfile.BadZipFile) as e:
        print(f"\nLỖI: {e}", file=sys.stderr)
        return 1
    print(
        f"\nGhi {len(report.written)} · đã có {len(report.same)} · "
        f"giữ nguyên file git theo dõi {len(report.protected)} · khác nội dung bỏ qua "
        f"{len(report.differs)}"
    )
    for rel in report.differs:
        print(f"  KHÁC: {rel} (thêm --force để ghi đè)")
    return 0


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


def project_workspace(project_dir: Path) -> Path:
    parent = project_dir.resolve().parent
    return parent.parent if parent.name == "projects" else parent


def _is_postv(project_dir: Path) -> bool:
    try:
        data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False  # để đường dựng HBT báo lỗi đọc project như cũ
    return project_kind(data) == "postv"


def _describe(err: ValidationError) -> str:
    return "\n".join(
        f"  {'.'.join(str(p) for p in e['loc']) or '(gốc)'}: {e['msg']}" for e in err.errors()
    )


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
    if args.command in ("pack-media", "unpack-media"):
        return _media(args)

    options = RenderOptions(
        preview=args.preview,
        fps=args.fps,
        outro=False if args.no_outro else None,
        allow_long_trim=args.allow_long_trim,
        preview_seconds=args.seconds,
    )
    try:
        options.sensitive_words = current_sensitive_words(args.project_dir)
        if _is_postv(args.project_dir):  # dự án PostV: bộ dựng riêng, cùng cách báo kết quả
            words = CensorStore(project_workspace(args.project_dir)).load()
            result = render_postv(
                args.project_dir, options, progress=_progress_printer(), censor_words=words
            )
        else:
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
