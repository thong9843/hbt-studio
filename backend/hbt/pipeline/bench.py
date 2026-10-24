"""`python -m cli bench-align`: đo Whisper trên một project (IMPLEMENT.md 5.2).

Ba chỉ số cho mỗi model: thời gian chạy, tỉ lệ âm tiết kịch bản khớp với âm tiết nghe được, và
độ lệch mốc cắt cảnh so với căn theo khoảng lặng. Không so với bản đã đăng (việc của golden test)
và không đặt ngưỡng đạt/rớt: chỉ báo số đo để chủ dự án chốt model mặc định theo từng máy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from hbt.models import load_project

from . import audio, cache
from .align import match_script
from .ffutil import media_duration
from .render import PIPELINE_VERSION, compute_offsets, tokens_of
from .scene_align import AlignError, align_scenes
from .whisper import WhisperConfig, WhisperFailed, plan_steps, run_whisper
from .whisper import detect_cuda as _detect_cuda


@dataclass
class BenchRow:
    model: str  # model được yêu cầu
    used: str | None = None  # bậc thật sự chạy (model, thiết bị)
    seconds: float | None = None
    match_ratio: float | None = None
    mean_offset_ms: float | None = None  # trung bình |mốc cắt cảnh Whisper − khoảng lặng|
    max_offset_ms: float | None = None
    error: str | None = None


def scene_offsets(times: list, scene_of: list[int], n_scenes: int) -> list[float]:
    """Mốc bắt đầu chuyển cảnh (như bước 4 của render) từ mốc thời gian từng token."""
    first, last = [0.0] * n_scenes, [0.0] * n_scenes
    for si in range(n_scenes):
        idx = [i for i, s in enumerate(scene_of) if s == si]
        first[si], last[si] = times[idx[0]][0], times[idx[-1]][1]
    return compute_offsets(first, last)


def prepared_voice(project_dir: Path, project) -> Path:
    """`build/voice.wav` (bước 2 của render, dùng chung cache)."""
    build = project_dir / "build"
    build.mkdir(parents=True, exist_ok=True)
    src, wav = project_dir / project.voice.file, build / "voice.wav"
    key = cache.digest("prep", src, PIPELINE_VERSION)
    if not cache.is_fresh(wav, key):
        audio.prep_voice(src, wav)
        cache.mark(wav, key)
    return wav


def bench_align(
    project_dir: str | Path,
    models: list[str],
    cfg: WhisperConfig,
    log: Callable[[str], None] = print,
) -> list[BenchRow]:
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir)
    problems = project.render_problems()
    if problems:
        raise ValueError("Project chưa đủ để đo: " + "; ".join(problems))
    wav = prepared_voice(project_dir, project)
    tokens, scene_of = tokens_of(project)
    n = len(project.scenes)
    prompt = " ".join(t["disp"] for t in tokens)

    reference: list[float] | None = None
    try:
        sil = align_scenes(tokens, scene_of, str(wav), media_duration(wav))
        reference = scene_offsets(sil.times, scene_of, n)
    except AlignError as e:
        log(f"Không có mốc khoảng lặng để so sánh: {e}")

    rows = []
    for model in models:
        row = BenchRow(model)
        rows.append(row)
        one = replace(cfg, model=model)
        steps = plan_steps(model, cfg.device, _detect_cuda())
        t0 = time.monotonic()
        try:
            run = run_whisper(wav, prompt, one, log, steps=steps)
            m = match_script(tokens, run.syllables)
        except (WhisperFailed, RuntimeError) as e:
            row.seconds, row.error = time.monotonic() - t0, str(e)
            continue
        row.seconds = run.seconds
        row.used = f"{run.step.model} ({run.step.device}, {run.step.compute_type})"
        row.match_ratio = m.matched_ratio
        if reference is not None:
            diffs = [
                abs(a - b) * 1000
                for a, b in zip(scene_offsets(m.times, scene_of, n), reference, strict=True)
            ]
            if diffs:
                row.mean_offset_ms, row.max_offset_ms = sum(diffs) / len(diffs), max(diffs)
    return rows


def format_rows(rows: list[BenchRow]) -> str:
    head = (
        f"{'model':<10}{'chạy bằng':<28}{'thời gian':>11}{'khớp':>8}{'lệch TB':>10}{'lệch max':>10}"
    )
    lines = [head, "-" * len(head)]
    for r in rows:
        if r.error:
            secs = f"{r.seconds:.1f}".replace(".", ",")
            lines.append(f"{r.model:<10}LỖI sau {secs} s: {r.error}")
            continue
        mean = f"{r.mean_offset_ms:.0f} ms" if r.mean_offset_ms is not None else "—"
        peak = f"{r.max_offset_ms:.0f} ms" if r.max_offset_ms is not None else "—"
        lines.append(
            f"{r.model:<10}{r.used or '—':<28}{r.seconds:>9.1f} s"
            f"{r.match_ratio:>8.1%}{mean:>10}{peak:>10}".replace(".", ",")
        )
    return "\n".join(lines)
