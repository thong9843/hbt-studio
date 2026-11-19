"""AudioDirector: siết thở <=120ms, Silence Drop 320ms, J/L-cut 160ms, Foley & -14 LUFS."""

from __future__ import annotations

import math
import os
import re
import subprocess
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from hbt.cinema.hardware import (
    HardwareProfile,
    detect_hardware,
    resolve_filter_complex_script_flag,
)
from hbt.cinema.schema import BeatSpec, TimelineSpec
from hbt.core.audio import build_topic_bgm_playlist, render_smart_bgm_wav
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP, measure_audio_duration

FOLEY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "whoosh": ("swoosh", "whoosh", "swipe", "transition"),
    "pop": ("pop", "bubble", "click"),
    "vine_boom": ("bass-drop", "boom", "drop", "hit", "punch", "slam"),
    "ding": ("ding", "bell", "chime", "ping", "retrieve"),
    "paper_slide": ("paper", "page", "slide", "card", "swoosh", "whoosh"),
}

_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def _atomic_write_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _atomic_write_pcm_wav(dest: Path, pcm: np.ndarray, *, sr: int, ch: int = 1) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    arr = np.asarray(pcm, dtype=np.int16)
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(ch)
            wf.setsampwidth(2)
            wf.setframerate(int(sr))
            wf.writeframes(arr.tobytes())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def tighten_breaths_wav(
    in_wav: Path,
    out_wav: Path,
    *,
    max_breath_ms: int = 120,
    silence_thresh: float = 0.015,
    crossfade_ms: int = 8,
) -> dict[str, Any]:
    """Siết mọi khoảng lặng > `max_breath_ms` xuống <= `max_breath_ms` bằng NumPy + crossfade."""
    src = Path(in_wav)
    with wave.open(str(src), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    if sw != 2 or not raw:
        _atomic_write_pcm_wav(out_wav, np.zeros(0, dtype=np.int16), sr=max(8000, sr), ch=ch)
        return {
            "file_path": str(out_wav),
            "original_ms": 0.0,
            "tightened_ms": 0.0,
            "removed_ms": 0.0,
        }

    pcm = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:
        pcm = pcm.reshape(-1, ch)
        mono = pcm.astype(np.float32).mean(axis=1) / 32768.0
    else:
        mono = pcm.astype(np.float32) / 32768.0

    n_samples = len(mono)
    orig_ms = round((n_samples / max(1, sr)) * 1000.0, 2)
    win = max(1, int(round(sr * 0.010)))  # 10ms RMS window
    max_keep = max(1, int(round(sr * max(10, int(max_breath_ms)) / 1000.0)))
    xfade = max(0, int(round(sr * max(0, int(crossfade_ms)) / 1000.0)))

    # Tính mặt nạ im lặng theo block 10ms
    is_silent = np.zeros(n_samples, dtype=bool)
    for start in range(0, n_samples, win):
        end = min(n_samples, start + win)
        rms = float(np.sqrt(np.mean(mono[start:end] ** 2)))
        if rms < silence_thresh:
            is_silent[start:end] = True

    # Tách đoạn liên tiếp (speech vs silence) và chỉ nén các đoạn lặng vượt max_keep
    pieces: list[np.ndarray] = []
    idx = 0
    while idx < n_samples:
        cur_state = bool(is_silent[idx])
        nxt = idx + 1
        while nxt < n_samples and bool(is_silent[nxt]) == cur_state:
            nxt += 1

        seg_len = nxt - idx
        if not cur_state or seg_len <= max_keep:
            pieces.append(pcm[idx:nxt].astype(np.float32))
        else:
            half_a = max_keep // 2
            half_b = max_keep - half_a
            head = pcm[idx : idx + half_a].astype(np.float32)
            tail = pcm[nxt - half_b : nxt].astype(np.float32)
            if xfade > 2 and len(head) >= xfade and len(tail) >= xfade:
                fade_out = np.linspace(1.0, 0.0, xfade, dtype=np.float32)
                fade_in = np.linspace(0.0, 1.0, xfade, dtype=np.float32)
                if ch > 1:
                    fade_out = fade_out[:, None]
                    fade_in = fade_in[:, None]
                head[-xfade:] *= fade_out
                tail[:xfade] *= fade_in
            pieces.append(head)
            pieces.append(tail)
        idx = nxt

    merged = np.concatenate(pieces, axis=0) if pieces else np.zeros((0,), dtype=np.float32)
    out_pcm = np.clip(np.round(merged), -32768, 32767).astype(np.int16)
    _atomic_write_pcm_wav(out_wav, out_pcm, sr=sr, ch=ch)
    tight_ms = round((len(out_pcm) / max(1, sr)) * 1000.0, 2)
    return {
        "file_path": str(out_wav),
        "original_ms": orig_ms,
        "tightened_ms": tight_ms,
        "removed_ms": round(max(0.0, orig_ms - tight_ms), 2),
    }


def compute_jl_cut_schedule(
    beats: Sequence[BeatSpec],
    *,
    jl_cut_ms: int = 160,
) -> list[dict[str, Any]]:
    """Tính mốc cắt âm thanh sớm (J-cut) / gối đuôi (L-cut) trên trục thời gian video."""
    schedule: list[dict[str, Any]] = []
    cur_t = 0.0
    default_shift = max(0, int(jl_cut_ms))

    for idx, beat in enumerate(beats):
        dur = max(0.25, float(beat.duration_sec))
        vis_start = cur_t
        vis_end = cur_t + dur

        j_lead_ms = 0
        l_trail_ms = 0
        for cue in beat.audio_cues:
            if cue.kind == "j_cut":
                j_lead_ms = max(j_lead_ms, abs(int(cue.offset_ms)) or default_shift)
            elif cue.kind == "l_cut":
                l_trail_ms = max(l_trail_ms, abs(int(cue.offset_ms)) or default_shift)

        if idx > 0 and j_lead_ms == 0 and beat.transition_in != "editorial_cut":
            j_lead_ms = default_shift

        aud_start = max(0.0, vis_start - j_lead_ms / 1000.0)
        aud_end = vis_end + l_trail_ms / 1000.0
        schedule.append(
            {
                "beat_id": beat.id,
                "visual_start_s": round(vis_start, 4),
                "visual_end_s": round(vis_end, 4),
                "audio_start_s": round(aud_start, 4),
                "audio_end_s": round(aud_end, 4),
                "delay_ms": int(round(aud_start * 1000.0)),
                "j_cut_ms": j_lead_ms,
                "l_cut_ms": l_trail_ms,
            }
        )
        cur_t = vis_end
    return schedule


def compute_silence_drops(
    beats: Sequence[BeatSpec],
    *,
    silence_drop_ms: int = 320,
) -> list[tuple[float, float]]:
    """Xác định các cửa sổ tắt nhạc nền đột ngột `silence_drop_ms` trước câu nhấn (`punch`)."""
    drops: list[tuple[float, float]] = []
    cur_t = 0.0
    default_drop_s = max(0.05, float(silence_drop_ms) / 1000.0)

    for idx, beat in enumerate(beats):
        dur = max(0.25, float(beat.duration_sec))
        drop_cue = next((c for c in beat.audio_cues if c.kind == "silence_drop"), None)
        if beat.punch or drop_cue is not None:
            drop_s = (
                max(0.05, float(drop_cue.duration_ms) / 1000.0)
                if (drop_cue is not None and drop_cue.duration_ms > 0)
                else default_drop_s
            )
            if idx == 0 and cur_t < drop_s:
                st = 0.0
                et = min(dur, drop_s)
            else:
                st = max(0.0, cur_t - drop_s)
                et = max(st + 0.05, cur_t)
            drops.append((round(st, 3), round(et, 3)))
        cur_t += dur
    return drops


def _synthesize_procedural_foley(tag: str, dest_wav: Path) -> Path:
    """Sinh SFX thủ tục bằng NumPy khi thiếu file binary trong `library/` (chống lỗi Ubuntu CI)."""
    sr = 48000
    low = (tag or "whoosh").strip().lower()
    rng = np.random.default_rng(seed=42)

    if low in ("pop",):
        dur = 0.12
        t = np.linspace(0.0, dur, int(sr * dur), endpoint=False)
        freq = 540.0 * np.exp(-t * 14.0) + 180.0
        sig = np.sin(2.0 * math.pi * freq * t) * np.exp(-t * 28.0) * 0.45
    elif low in ("vine_boom", "impact"):
        dur = 0.45
        t = np.linspace(0.0, dur, int(sr * dur), endpoint=False)
        freq = 92.0 * np.exp(-t * 4.5) + 34.0
        sig = np.sin(2.0 * math.pi * freq * t) * np.exp(-t * 6.5) * 0.65
    elif low in ("ding",):
        dur = 0.36
        t = np.linspace(0.0, dur, int(sr * dur), endpoint=False)
        sig = (
            0.40 * np.sin(2.0 * math.pi * 1320.0 * t) + 0.20 * np.sin(2.0 * math.pi * 2640.0 * t)
        ) * np.exp(-t * 9.0)
    else:  # whoosh / paper_slide
        dur = 0.24
        n = int(sr * dur)
        t = np.linspace(0.0, dur, n, endpoint=False)
        noise = rng.normal(0.0, 0.28, size=n)
        kernel = np.ones(16, dtype=np.float32) / 16.0
        smooth = np.convolve(noise, kernel, mode="same")
        env = np.sin(math.pi * (t / dur)) ** 1.4
        sig = smooth * env

    pcm = np.clip(np.round(sig * 32767.0), -32768, 32767).astype(np.int16)
    _atomic_write_pcm_wav(dest_wav, pcm, sr=sr, ch=1)
    return dest_wav


def resolve_foley_sfx(
    tag: str,
    library_dir: Path,
    assets_dir: Path | None = None,
    *,
    fallback_dir: Path | None = None,
) -> Path | None:
    """Tìm SFX local theo `tag`; nếu thiếu trên đĩa thì tự sinh Foley thủ tục sạch sẽ."""
    clean = (tag or "none").strip().lower()
    if not clean or clean == "none":
        return None

    keywords = FOLEY_KEYWORDS.get(clean, (clean,))
    dirs: list[Path] = []
    if assets_dir is not None:
        dirs.append(Path(assets_dir) / "sfx")
    dirs.append(Path(library_dir) / "sfx")

    for d in dirs:
        if not d.is_dir():
            continue
        files = sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in _AUDIO_EXTS)
        for kw in keywords:
            for f in files:
                if kw in f.stem.lower():
                    return f

    safe_tag = re.sub(r"[^a-z0-9_-]+", "_", clean) or "whoosh"
    fb_root = (
        Path(fallback_dir) if fallback_dir is not None else (Path(library_dir) / ".foley_cache")
    )
    target = fb_root / f"foley_{safe_tag}.wav"
    if target.is_file() and target.stat().st_size > 44:
        return target
    return _synthesize_procedural_foley(clean, target)


def build_mix_filtergraph_script(
    *,
    voice_entries: Sequence[tuple[Path, int]],
    foley_entries: Sequence[tuple[Path, int, float]],
    bgm_wav: Path | None,
    total_duration_s: float,
    silence_drops: Sequence[tuple[float, float]] = (),
    target_lufs: float = -14.0,
) -> tuple[list[Path], str]:
    """Sinh danh sách input và nội dung UTF-8 `filtergraph.txt` (chống tràn lệnh 32KB Windows)."""
    inputs: list[Path] = []
    lines: list[str] = []
    speech_labels: list[str] = []
    foley_labels: list[str] = []
    dur_s = max(0.5, float(total_duration_s))

    for idx, (vp, delay_ms) in enumerate(voice_entries):
        in_idx = len(inputs)
        inputs.append(Path(vp))
        lbl = f"v{idx}"
        d_ms = max(0, int(delay_ms))
        delay_part = f",adelay={d_ms}|{d_ms}" if d_ms > 0 else ""
        lines.append(
            f"[{in_idx}:a]aresample=48000,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo{delay_part}[{lbl}]"
        )
        speech_labels.append(f"[{lbl}]")

    if not speech_labels:
        # Không có file thoại -> tạo nhánh im lặng chuẩn 48kHz stereo để pipeline luôn chạy
        lines.append(
            f"anullsrc=r=48000:cl=stereo:d={dur_s:.3f},"
            "aformat=sample_fmts=fltp:channel_layouts=stereo[speech]"
        )
    elif len(speech_labels) == 1:
        src = speech_labels[0]
        lines.append(f"{src}apad=whole_dur={dur_s:.3f},atrim=0:{dur_s:.3f}[speech]")
    else:
        joined = "".join(speech_labels)
        lines.append(
            f"{joined}amix=inputs={len(speech_labels)}:duration=longest:"
            f"dropout_transition=0:normalize=0,apad=whole_dur={dur_s:.3f},atrim=0:{dur_s:.3f}[speech]"
        )

    for idx, (fp, delay_ms, gain_db) in enumerate(foley_entries):
        in_idx = len(inputs)
        inputs.append(Path(fp))
        lbl = f"fx{idx}"
        d_ms = max(0, int(delay_ms))
        delay_part = f",adelay={d_ms}|{d_ms}" if d_ms > 0 else ""
        vol_db = float(gain_db) - 6.0
        lines.append(
            f"[{in_idx}:a]aresample=48000,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={vol_db:.1f}dB{delay_part}[{lbl}]"
        )
        foley_labels.append(f"[{lbl}]")

    mix_branches: list[str] = []
    if bgm_wav is not None and Path(bgm_wav).is_file():
        bgm_idx = len(inputs)
        inputs.append(Path(bgm_wav))
        drop_filters = "".join(
            f",volume=enable='between(t,{st:.3f},{et:.3f})':volume=0.001"
            for st, et in silence_drops
            if et > st
        )
        lines.append(
            f"[{bgm_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"apad=whole_dur={dur_s:.3f},atrim=0:{dur_s:.3f},asetpts=PTS-STARTPTS,"
            f"volume=0.18{drop_filters}[bgm_raw]"
        )
        lines.append("[speech]asplit=2[sp_mix][sp_sc]")
        lines.append(
            "[bgm_raw][sp_sc]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=220[bgm_duck]"
        )
        mix_branches.extend(["[sp_mix]", "[bgm_duck]"])
    else:
        mix_branches.append("[speech]")

    if len(foley_labels) == 1:
        mix_branches.append(foley_labels[0])
    elif len(foley_labels) > 1:
        lines.append(
            f"{''.join(foley_labels)}amix=inputs={len(foley_labels)}:duration=longest:"
            f"dropout_transition=0:normalize=0[foley_mix]"
        )
        mix_branches.append("[foley_mix]")

    if len(mix_branches) == 1:
        pre_norm = mix_branches[0]
    else:
        lines.append(
            f"{''.join(mix_branches)}amix=inputs={len(mix_branches)}:duration=first:"
            f"dropout_transition=0:normalize=0[pre_norm]"
        )
        pre_norm = "[pre_norm]"

    lines.append(
        f"{pre_norm}loudnorm=I={float(target_lufs):.1f}:TP=-1.5:LRA=11,atrim=0:{dur_s:.3f}[aout]"
    )
    return inputs, ";\n".join(lines) + "\n"


def mix_cinema_audio(
    spec: TimelineSpec,
    beat_wavs: dict[str, Path],
    out_wav: Path,
    *,
    library_dir: Path,
    assets_dir: Path | None = None,
    work_dir: Path,
    tighten_breaths: bool = True,
    hw: HardwareProfile | None = None,
) -> dict[str, Any]:
    """Trộn giọng (đã siết thở), Foley SFX, J/L-cut, Silence Drop & BGM chuẩn -14 LUFS."""
    profile = hw or detect_hardware()
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    tight_dir = work / "tight_voice"
    sfx_fb_dir = work / "sfx_fallback"

    jl_schedule = compute_jl_cut_schedule(spec.beats, jl_cut_ms=spec.audio.jl_cut_ms)
    silence_drops = compute_silence_drops(spec.beats, silence_drop_ms=spec.audio.silence_drop_ms)

    voice_entries: list[tuple[Path, int]] = []
    foley_entries: list[tuple[Path, int, float]] = []
    breath_saved_ms = 0.0

    for idx, (beat, sched) in enumerate(zip(spec.beats, jl_schedule, strict=True)):
        raw_wav = beat_wavs.get(beat.id)
        if raw_wav is not None and Path(raw_wav).is_file():
            use_wav = Path(raw_wav)
            if tighten_breaths and spec.audio.max_breath_ms > 0:
                tight_out = tight_dir / f"{beat.id}_tight.wav"
                t_stats = tighten_breaths_wav(
                    use_wav,
                    tight_out,
                    max_breath_ms=spec.audio.max_breath_ms,
                )
                breath_saved_ms += float(t_stats.get("removed_ms", 0.0))
                use_wav = tight_out
            voice_entries.append((use_wav, int(sched["delay_ms"])))

        # Foley mặc định từ transition hoặc AudioCue
        cue_tags = [
            (c.tag, int(round(sched["visual_start_s"] * 1000.0)) + int(c.offset_ms), c.gain_db)
            for c in beat.audio_cues
            if c.kind in ("foley", "sfx") and c.tag and c.tag != "none"
        ]
        if not cue_tags and beat.sfx_tag and beat.sfx_tag != "none":
            cue_tags.append((beat.sfx_tag, int(round(sched["visual_start_s"] * 1000.0)), 0.0))
        elif idx > 0 and not cue_tags and beat.transition_in == "paper_slide":
            cue_tags.append(("paper_slide", int(round(sched["visual_start_s"] * 1000.0)), -2.0))

        for tag, delay_ms, gain_db in cue_tags:
            sfx_p = resolve_foley_sfx(
                tag, library_dir, assets_dir=assets_dir, fallback_dir=sfx_fb_dir
            )
            if sfx_p is not None and sfx_p.is_file():
                foley_entries.append((sfx_p, max(0, delay_ms), gain_db))

    total_dur = max(1.0, spec.total_duration_sec)
    bgm_wav: Path | None = None
    playlist = build_topic_bgm_playlist(
        Path(library_dir),
        total_dur,
        topic=spec.topic,
        seed=spec.slug,
    )
    if playlist:
        cand_bgm = work / "bgm_acrossfade.wav"
        try:
            bgm_wav = render_smart_bgm_wav(playlist, total_dur, cand_bgm)
        except Exception:
            bgm_wav = None

    inputs, fc_script = build_mix_filtergraph_script(
        voice_entries=voice_entries,
        foley_entries=foley_entries,
        bgm_wav=bgm_wav,
        total_duration_s=total_dur,
        silence_drops=silence_drops,
        target_lufs=spec.audio.target_lufs,
    )

    script_path = work / "filtergraph.txt"
    _atomic_write_text(script_path, fc_script)

    out_path = Path(out_wav)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_wav = out_path.with_name(f"{out_path.stem}.tmp.wav")

    in_args: list[str] = []
    for p in inputs:
        in_args.extend(["-i", str(p)])

    clamp = (
        list(profile.ffmpeg_resource_clamp)
        if profile.ffmpeg_resource_clamp
        else list(FFMPEG_RESOURCE_CLAMP)
    )
    script_flag = resolve_filter_complex_script_flag()
    cmd = [
        ffmpeg_exe(),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        *clamp,
        *in_args,
        script_flag,
        str(script_path),
        "-map",
        "[aout]",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(tmp_wav),
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _, err_b = proc.communicate(timeout=180.0)
        if proc.returncode != 0:
            raise FFmpegError(
                f"AudioDirector FFmpeg lỗi ({proc.returncode}): "
                f"{err_b.decode('utf-8', errors='replace')[-400:]}"
            )
        os.replace(tmp_wav, out_path)
    finally:
        if proc.stderr is not None:
            try:
                proc.stderr.close()
            except OSError:
                pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass
        if tmp_wav.exists():
            tmp_wav.unlink(missing_ok=True)

    return {
        "file_path": str(out_path),
        "filtergraph_path": str(script_path),
        "script_flag": script_flag,
        "duration_sec": measure_audio_duration(out_path) or total_dur,
        "breath_saved_ms": round(breath_saved_ms, 2),
        "silence_drops": silence_drops,
        "jl_cuts": len([s for s in jl_schedule if s["j_cut_ms"] > 0 or s["l_cut_ms"] > 0]),
        "foley_count": len(foley_entries),
        "bgm_used": bgm_wav is not None,
    }
