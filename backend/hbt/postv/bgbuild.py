"""Nền gameplay của video PostV: chọn clip theo `seed`, cắt thẳng, nối đủ độ dài (mục 6, bước 5).

Nền chạy liền, không hiệu ứng (D6). Mỗi mảnh dài 7,5 s hoặc 15 s (đo từ video mẫu), cắt thẳng
không hoà trộn (K-17). Cả đoạn nền dựng bằng **một** lệnh ffmpeg ra `build/bg.mp4`; khoá cache chỉ
phụ thuộc vào nền (clip, seed, kích thước, fps) nên đổi thẻ hay phụ đề không dựng lại nền.
"""

from __future__ import annotations

import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.pipeline import cache
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.pipeline.render import PIPELINE_VERSION
from hbt.postv.backgrounds import BackgroundEntry

PIECE_SECONDS = (7.5, 15.0)  # mỗi clip được dùng 7,5 s hoặc 15 s
PAD = 0.5  # dựng dư để cắt lại đúng số khung
MIN_PIECE = 0.5

# Đổi cách chọn/nối thì khoá cache nền đổi theo (không phụ thuộc mã thẻ, phụ đề…)
BG_VERSION = cache.code_digest(sys.modules[__name__])


@dataclass(frozen=True)
class Piece:
    clip_id: str
    file: Path
    start: float
    seconds: float


def pick_pieces(
    clips: Sequence[BackgroundEntry],
    root: Path,
    total: float,
    seed: int,
    start_offset: float | None = None,
) -> list[Piece]:
    """Danh sách mảnh nền phủ `total` + PAD giây. Cùng `seed` cho cùng kết quả.

    Xáo các clip theo `seed`, dùng hết một lượt rồi xáo lượt mới (hai mảnh liền nhau không cùng
    clip nếu còn clip khác). `start_offset` chỉ áp cho mảnh đầu."""
    if not clips:
        raise ValueError("Không có clip nền")
    rng = random.Random(seed)
    target = total + PAD
    pieces: list[Piece] = []
    queue: list[BackgroundEntry] = []
    acc = 0.0
    while acc < target - 1e-6:
        if not queue:
            queue = rng.sample(list(clips), len(clips))
            if len(queue) > 1 and pieces and queue[0].id == pieces[-1].clip_id:
                queue.append(queue.pop(0))
        clip = queue.pop(0)
        seconds = min(rng.choice(PIECE_SECONDS), clip.duration, target - acc)
        seconds = round(max(seconds, min(MIN_PIECE, clip.duration)), 3)
        room = max(clip.duration - seconds, 0.0)
        start = rng.uniform(0, room)
        if start_offset is not None and not pieces:
            start = start_offset
        start = round(min(max(start, 0.0), room), 2)
        pieces.append(Piece(clip.id, root / clip.file, start, seconds))
        acc += seconds
    return pieces


def bg_key(
    pieces: Sequence[Piece], width: int, height: int, fps: int, preset: str, crf: int
) -> str:
    """Khoá cache `bg.mp4`: mảnh (kèm kích thước + giờ sửa file nguồn), kích thước, fps, mã hoá."""
    sources = []
    for p in pieces:
        st = p.file.stat()
        sources.append([p.clip_id, p.start, p.seconds, st.st_size, st.st_mtime_ns])
    return cache.digest(
        "pv-bg", sources, width, height, fps, preset, crf, BG_VERSION, PIPELINE_VERSION
    )


def build_background(
    pieces: Sequence[Piece],
    width: int,
    height: int,
    fps: int,
    preset: str,
    crf: int,
    out: Path,
) -> None:
    """Một lệnh ffmpeg: cắt từng mảnh, đưa về `width×height` `fps`, nối, không tiếng."""
    args: list[str | Path] = []
    chains = []
    for i, p in enumerate(pieces):
        args += ["-ss", f"{p.start:.2f}", "-t", f"{p.seconds:.3f}", "-i", p.file]
        chains.append(
            f"[{i}:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase:"
            f"flags=lanczos,crop={width}:{height},setsar=1,format=yuv420p[v{i}]"
        )
    labels = "".join(f"[v{i}]" for i in range(len(pieces)))
    fc = ";".join([*chains, f"{labels}concat=n={len(pieces)}:v=1:a=0[bg]"])
    partial = out.with_name(out.stem + ".part.mp4")
    run_ffmpeg([
        *args, "-filter_complex", fc, "-map", "[bg]", "-an", "-r", str(fps),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-g", str(2 * fps),
        "-pix_fmt", "yuv420p", partial,
    ])  # fmt: skip
    cache.publish_atomic(partial, out)
