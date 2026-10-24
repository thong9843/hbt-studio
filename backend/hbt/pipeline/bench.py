"""`python -m cli bench-align`: đo Whisper trên một project (IMPLEMENT.md 5.2).

Ba chỉ số cho mỗi model: thời gian chạy, tỉ lệ âm tiết kịch bản khớp với âm tiết nghe được, và
độ lệch mốc cắt cảnh so với căn theo khoảng lặng. Không so với bản đã đăng (việc của golden test)
và không đặt ngưỡng đạt/rớt: chỉ báo số đo để chủ dự án chốt model mặc định theo từng máy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from hbt.models import load_project

from . import audio, cache
from .align import match_script
from .ffutil import media_duration
from .render import PIPELINE_VERSION, scene_offsets, tokens_of
from .scene_align import AlignError, align_scenes
from .whisper import WhisperConfig, WhisperFailed, WhisperTimeout, plan_steps, run_whisper
from .whisper import detect_cuda as _detect_cuda


@dataclass
class BenchRow:
    model: str  # model được yêu cầu
    prompt: bool = True  # có dùng initial_prompt (lời đọc) hay không
    used: str | None = None  # bậc thật sự chạy (model, thiết bị)
    seconds: float | None = None
    match_ratio: float | None = None
    mean_offset_ms: float | None = None  # trung bình |mốc cắt cảnh Whisper − khoảng lặng|
    max_offset_ms: float | None = None
    offsets_ms: list[float] = field(default_factory=list)  # từng mốc cắt cảnh
    error: str | None = None
    timed_out: bool = False


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
    prompts: tuple[bool, ...] = (True,),
) -> list[BenchRow]:
    """Đo từng (model, có/không initial_prompt). Chỉ để đo: đường dựng luôn dùng prompt (5.2)."""
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
        for use_prompt in prompts:
            row = BenchRow(model, use_prompt)
            rows.append(row)
            one = replace(cfg, model=model)
            steps = plan_steps(model, cfg.device, _detect_cuda())
            t0 = time.monotonic()
            try:
                run = run_whisper(wav, prompt if use_prompt else "", one, log, steps=steps)
                m = match_script(tokens, run.syllables)
            except (WhisperFailed, RuntimeError) as e:
                row.seconds, row.error = time.monotonic() - t0, str(e)
                row.timed_out = isinstance(e, WhisperTimeout)
                continue
            row.seconds = run.seconds
            row.used = f"{run.step.model} ({run.step.device}, {run.step.compute_type})"
            row.match_ratio = m.matched_ratio
            if reference is not None:
                row.offsets_ms = [
                    abs(a - b) * 1000
                    for a, b in zip(scene_offsets(m.times, scene_of, n), reference, strict=True)
                ]
                if row.offsets_ms:
                    row.mean_offset_ms = sum(row.offsets_ms) / len(row.offsets_ms)
                    row.max_offset_ms = max(row.offsets_ms)
    return rows


def _vn(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def format_rows(rows: list[BenchRow]) -> str:
    head = (
        f"{'model':<10}{'prompt':<8}{'chạy bằng':<26}{'thời gian':>11}{'khớp':>8}"
        f"{'lệch TB':>10}{'lệch max':>10}"
    )
    lines = [head, "-" * len(head)]
    for r in rows:
        prompt = "có" if r.prompt else "không"
        if r.error:
            what = "QUÁ GIỚI HẠN THỜI GIAN" if r.timed_out else "LỖI"
            lines.append(f"{r.model:<10}{prompt:<8}{what} sau {_vn(r.seconds)} s: {r.error}")
            continue
        mean = f"{r.mean_offset_ms:.0f} ms" if r.mean_offset_ms is not None else "—"
        peak = f"{r.max_offset_ms:.0f} ms" if r.max_offset_ms is not None else "—"
        lines.append(
            f"{r.model:<10}{prompt:<8}{r.used or '—':<26}{_vn(r.seconds):>9} s"
            f"{_vn(r.match_ratio * 100):>7}%{mean:>10}{peak:>10}"
        )
        if r.offsets_ms:
            lines.append(f"{'':<18}từng mốc (ms): " + " ".join(f"{x:.0f}" for x in r.offsets_ms))
    return "\n".join(lines)
