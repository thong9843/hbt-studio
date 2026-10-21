"""Âm thanh: chuẩn hoá giọng, cắt đuôi thừa, chọn đoạn nhạc, trộn nhạc/ducking/whoosh, tiếng outro.

Tham số lấy từ `reference/pipeline/render_reference.py` (đã chạy thật) và IMPLEMENT.md mục 4c–4d, 6.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .align import speech_segments
from .ffutil import FFmpegError, ffmpeg_exe, measure_lufs, media_duration, run_ffmpeg

VOICE_DELAY = 0.2  # giây trễ đầu giọng
TAIL = 1.6  # giữ hình sau câu cuối
TARGET_LUFS = -14.0

# Cắt đuôi file giọng (4d)
VOICE_END_MARGIN = 0.35
TAIL_FADE = 0.08
MAX_TRIM_SECONDS = 8.0

# Outro (4c)
OUTRO_DURATION = 4.0
OUTRO_VOICE_DELAY = 0.5
OUTRO_TINGS = ((0.15, 0.22), (1.15, 0.18))  # (giây, âm lượng)
OUTRO_FADE_OUT = 0.3
OUTRO_CROSSFADE = 0.5
OUTRO_LIMITER = "alimiter=limit=0.89:level=0"  # level=0: không tự nâng mức lên −13 LUFS

# Whoosh (6.3)
WHOOSH_VOL = 0.30

SR = 44100
MUSIC_SR = 22050


# ---------------------------------------------------------------- giọng đọc
def prep_voice(src: str | Path, dst: str | Path) -> None:
    """highpass 70 Hz, trễ 0,2 s, đệm 1,6 s, loudnorm −14 LUFS, mono 44,1 kHz (bước 2)."""
    # `all=1`: cùng độ trễ cho mọi kênh (file Vbee có thể là stereo); với mono thì y như reference.
    af = (
        f"highpass=f=70,adelay={int(VOICE_DELAY * 1000)}:all=1,apad=pad_dur={TAIL},"
        "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100"
    )
    run_ffmpeg(["-i", src, "-af", af, "-ac", "1", dst])


class TailTrimNeedsConfirmation(RuntimeError):
    """Đuôi thừa quá dài (> 8 s): dừng lại, hỏi chủ dự án trước khi cắt (4d.3)."""


@dataclass(frozen=True)
class TailTrim:
    voice_end: float  # giây trên mốc thời gian của voice.wav
    cut_seconds: float  # độ dài âm thanh bị cắt
    segments_cut: int  # số đoạn tiếng nói nằm trong phần bị cắt


def plan_tail_trim(
    last_token_end: float,
    speech_segs: Sequence[tuple[float, float]],
    content_end: float,
    *,
    allow_long: bool = False,
) -> TailTrim | None:
    """Có đoạn tiếng nói nào *sau* chữ cuối của kịch bản không? Có thì trả kế hoạch cắt.

    `content_end` = hết phần giọng thật (trước đoạn đệm TAIL). Không có đoạn thừa → None."""
    voice_end = last_token_end + VOICE_END_MARGIN
    extra = [s for s in speech_segs if s[0] >= voice_end]
    if not extra:
        return None
    cut = content_end - voice_end
    if cut <= 0:
        return None
    if cut > MAX_TRIM_SECONDS and not allow_long:
        raise TailTrimNeedsConfirmation(
            f"Đuôi thừa dài {cut:.2f} giây (> {MAX_TRIM_SECONDS:.0f} giây) "
            "sau chữ cuối của kịch bản. "
            "Hãy nghe lại file giọng; nếu đúng là phần cần cắt thì chạy lại với xác nhận."
        )
    return TailTrim(voice_end=voice_end, cut_seconds=cut, segments_cut=len(extra))


def trim_voice_tail(src: str | Path, dst: str | Path, voice_end: float) -> None:
    """Cắt đuôi tại voice_end, fade ra 80 ms, đệm lại TAIL, chuẩn hoá lại −14 LUFS.

    Chuẩn hoá lại sau khi cắt để độ lớn (và ducking) chỉ tính trên phần giọng giữ lại (4d.4)."""
    fade_start = max(voice_end - TAIL_FADE, 0)
    af = (
        f"atrim=end={voice_end:.3f},afade=t=out:st={fade_start:.3f}:d={TAIL_FADE},"
        f"apad=pad_dur={TAIL},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100"
    )
    run_ffmpeg(["-i", src, "-af", af, "-ac", "1", dst])


def trim_tail_if_needed(
    voice_wav: str | Path,
    last_token_end: float,
    dst: str | Path,
    log=print,
    *,
    allow_long: bool = False,
) -> tuple[Path, TailTrim | None]:
    """Cắt đoạn tiếng nói thừa sau chữ cuối của kịch bản (4d).

    Trả về (file giọng dùng để dựng, kế hoạch cắt).

    Không có đoạn thừa → trả lại đúng `voice_wav`, không ghi gì."""
    total = media_duration(voice_wav)
    segs = speech_segments(str(voice_wav), total)
    plan = plan_tail_trim(last_token_end, segs, total - TAIL, allow_long=allow_long)
    if plan is None:
        return Path(voice_wav), None
    trim_voice_tail(voice_wav, dst, plan.voice_end)
    log(
        f"Đã cắt {plan.segments_cut} đoạn thừa ở cuối file giọng "
        f"({plan.cut_seconds:.2f} giây)".replace(".", ",")
    )
    return Path(dst), plan


# ---------------------------------------------------------------- nhạc nền
def pick_music_start(music_src: str | Path, video_total: float) -> float:
    """Tự chọn điểm bắt đầu nhạc (6.1): đo độ lớn theo cửa sổ 1 s, bỏ 2 s đầu, lấy cửa sổ đầu tiên
    có độ lớn ≥ (trung vị − 3 dB); nếu phần còn lại ngắn hơn video thì lùi điểm bắt đầu."""
    cmd = [
        ffmpeg_exe(), "-v", "error", "-i", str(music_src),
        "-vn", "-ac", "1", "-ar", str(MUSIC_SR), "-f", "s16le", "-",
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise FFmpegError(
            f"Không đọc được nhạc {music_src}:\n{result.stderr.decode(errors='replace')}"
        )
    samples = np.frombuffer(result.stdout, dtype="<i2").astype(np.float64) / 32768.0
    duration = len(samples) / MUSIC_SR
    windows = len(samples) // MUSIC_SR
    if windows <= 2:
        return 0.0
    frames = samples[: windows * MUSIC_SR].reshape(windows, MUSIC_SR)
    db = 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9)
    threshold = float(np.median(db[2:])) - 3.0
    start = next((i for i in range(2, windows) if db[i] >= threshold), 2)
    if duration - start < video_total:
        start = max(0.0, duration - video_total)
    return float(start)


# ---------------------------------------------------------------- hiệu ứng tổng hợp
def synth_whoosh(out: str | Path) -> None:
    """Tiếng 'vút' tổng hợp bằng FFmpeg (như reference), không dùng file ngoài."""
    run_ffmpeg([
        "-f", "lavfi", "-i", "anoisesrc=d=0.7:c=pink:a=0.6",
        "-af", "highpass=f=300,lowpass=f=6000,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.35",
        "-ar", str(SR), "-ac", "2", out,
    ])  # fmt: skip


def synth_ting(out: str | Path) -> None:
    """Tiếng 'ting' nhẹ cho outro: ba hài 1318 / 1976 / 2637 Hz tắt dần exp(−5t), dài 0,9 s,
    stereo 44,1 kHz (thông số của bản đã chạy thật, IMPLEMENT.md 6.5)."""
    expr = "0.35*(sin(2*PI*1318*t)+0.6*sin(2*PI*1976*t)+0.4*sin(2*PI*2637*t))*exp(-5*t)"
    run_ffmpeg([
        "-f", "lavfi", "-i", f"aevalsrc='{expr}':d=0.9:s={SR}",
        "-ar", str(SR), "-ac", "2", out,
    ])  # fmt: skip


# ---------------------------------------------------------------- trộn âm thanh phần có lời
def mix_audio(
    voice_wav: str | Path,
    music_src: str | Path | None,
    music_start: float,
    total: float,
    out: str | Path,
    workdir: str | Path,
    sfx: Sequence[tuple[str | Path, float, float]] = (),
) -> None:
    """Giọng + nhạc (hạ nhỏ khi có giọng) + hiệu ứng → stereo, tổng −14 LUFS.

    `sfx`: (file, giây, âm lượng). Không có nhạc (6.4): bỏ cắt nhạc và ducking."""
    inputs: list[str | Path] = ["-i", voice_wav]
    if music_src is not None:
        music_cut = Path(workdir) / "music_cut.wav"
        run_ffmpeg([
            "-ss", f"{music_start:.3f}", "-t", f"{total:.3f}", "-i", music_src, "-af",
            f"aresample=44100,afade=t=in:d=0.8,afade=t=out:st={total - 2.5:.3f}:d=2.5,"
            "loudnorm=I=-27:TP=-6:LRA=11",
            "-ac", "2", music_cut,
        ])  # fmt: skip
        inputs += ["-i", music_cut]
        fc = (
            "[0:a]pan=stereo|c0=0.707*c0|c1=0.707*c0,asplit=2[v][sc];"
            "[1:a][sc]sidechaincompress=threshold=0.03:ratio=3:attack=40:release=350[md];"
        )
        labels = "[v][md]"
    else:
        fc = "[0:a]pan=stereo|c0=0.707*c0|c1=0.707*c0[v];"
        labels = "[v]"
    first_sfx = 2 if music_src is not None else 1
    for i, (path, at, vol) in enumerate(sfx):
        inputs += ["-i", path]
        ms = int(at * 1000)
        fc += f"[{first_sfx + i}:a]volume={vol},adelay={ms}|{ms}[s{i}];"
        labels += f"[s{i}]"
    n = labels.count("[")
    mixed = f"{labels}amix=inputs={n}:normalize=0," if n > 1 else labels
    fc += f"{mixed}atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100"
    run_ffmpeg([*inputs, "-filter_complex", fc, "-c:a", "pcm_s16le", out])


# ---------------------------------------------------------------- outro
def build_outro_audio(
    outro_voice: str | Path | None,
    out: str | Path,
    workdir: str | Path,
) -> float | None:
    """Âm thanh outro 4,0 s (4c): lời trễ 0,5 s + hai tiếng ting, đo ebur128, gain về −14,0 LUFS,
    giới hạn đỉnh, mờ ra 0,3 s. Thiếu `outro_voice` thì chỉ có tiếng ting (giữ mức gốc, không
    kéo lên −14 LUFS vì hai tiếng ting thưa sẽ bị khuếch đại quá to).

    Trả về độ lớn đo được trước khi chỉnh gain (None nếu không có lời)."""
    workdir = Path(workdir)
    ting = workdir / "ting.wav"
    synth_ting(ting)
    inputs: list[str | Path] = []
    fc = ""
    labels = ""
    idx = 0
    if outro_voice is not None:
        inputs += ["-i", outro_voice]
        ms = int(OUTRO_VOICE_DELAY * 1000)
        fc += f"[0:a]pan=stereo|c0=c0|c1=c0,adelay={ms}:all=1[ov];"
        labels += "[ov]"
        idx = 1
    for i, (at, vol) in enumerate(OUTRO_TINGS):
        inputs += ["-i", ting]
        ms = int(at * 1000)
        fc += f"[{idx + i}:a]volume={vol},adelay={ms}:all=1[t{i}];"
        labels += f"[t{i}]"
    n = labels.count("[")
    fc += (
        f"{labels}amix=inputs={n}:normalize=0,aresample={SR},"
        f"apad=whole_dur={OUTRO_DURATION},atrim=0:{OUTRO_DURATION}"
    )
    raw = workdir / "outro_raw.wav"
    run_ffmpeg([*inputs, "-filter_complex", fc, "-c:a", "pcm_s16le", raw])

    measured = None
    gain = 0.0
    if outro_voice is not None:
        measured = measure_lufs(raw)
        gain = TARGET_LUFS - measured
    fade_start = OUTRO_DURATION - OUTRO_FADE_OUT
    af = f"volume={gain:.3f}dB,{OUTRO_LIMITER},afade=t=out:st={fade_start}:d={OUTRO_FADE_OUT}"
    run_ffmpeg(["-i", raw, "-af", af, "-c:a", "pcm_s16le", out])
    return measured


def join_audio(body: str | Path, outro: str | Path, out: str | Path) -> float:
    """Nối tiếng outro sau phần có lời bằng acrossfade 0,5 s. Trả về độ dài kết quả."""
    run_ffmpeg([
        "-i", body, "-i", outro, "-filter_complex",
        f"[0:a][1:a]acrossfade=d={OUTRO_CROSSFADE}:c1=tri:c2=tri,aresample={SR}",
        "-c:a", "pcm_s16le", out,
    ])  # fmt: skip
    return media_duration(out)
