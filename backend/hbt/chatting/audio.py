"""Trộn âm thanh Playlist BGM nối tiếp (acrossfade) & duy trì -20dB dưới TTS cho Chatting."""

from __future__ import annotations

import logging
import random
import shutil
from pathlib import Path

from hbt.pipeline.ffutil import media_duration, run_ffmpeg

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def list_music_files(library_dir: Path) -> list[Path]:
    """Liệt kê toàn bộ file nhạc hợp lệ trong library/music/."""
    music_dir = Path(library_dir) / "music"
    if not music_dir.is_dir():
        return []
    tracks = [
        p
        for p in sorted(music_dir.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS
    ]
    return tracks


def pick_initial_music(library_dir: Path, music_name: str | None) -> Path | None:
    """Chọn bài BGM khởi đầu theo tên hoặc ngẫu nhiên từ kho."""
    tracks = list_music_files(library_dir)
    if not tracks:
        return None
    if music_name:
        for t in tracks:
            if t.stem == music_name or t.name == music_name:
                return t
    return random.choice(tracks)


def build_bgm_playlist(
    library_dir: Path,
    first_music: str | None,
    total_duration: float,
    crossfade_s: float = 2.0,
) -> list[tuple[Path, float]]:
    """Tạo danh sách phát BGM phủ kín 100% thời lượng video, không lặp lại bài khi chưa hết kho."""
    tracks = list_music_files(library_dir)
    if not tracks or total_duration <= 0:
        return []

    first = pick_initial_music(library_dir, first_music)
    if first is None:
        return []

    first_dur = media_duration(first) or 60.0
    playlist: list[tuple[Path, float]] = [(first, first_dur)]
    effective_dur = first_dur
    used_names: set[str] = {first.name}
    last_name = first.name

    # Tiếp tục nối bài ngẫu nhiên cho đến khi phủ kín hoàn toàn total_duration (+1s dự phòng)
    max_tracks = 20
    while effective_dur < (total_duration + 1.0) and len(playlist) < max_tracks:
        candidates = [t for t in tracks if t.name not in used_names]
        if not candidates:
            # Nếu đã dùng hết cả kho nhạc -> xoay vòng (tránh lặp trùng bài vừa phát ngay trước đó)
            used_names.clear()
            candidates = [t for t in tracks if t.name != last_name] or tracks

        nxt = random.choice(candidates)
        used_names.add(nxt.name)
        last_name = nxt.name
        nxt_dur = media_duration(nxt) or 60.0
        cf = min(crossfade_s, max(0.0, nxt_dur * 0.35), max(0.0, effective_dur * 0.35))
        effective_dur += max(1.0, nxt_dur - cf)
        playlist.append((nxt, nxt_dur))

    return playlist


def render_bgm_playlist_wav(
    playlist: list[tuple[Path, float]],
    total_duration: float,
    out_wav: Path,
    crossfade_s: float = 2.0,
    fade_out_s: float = 2.0,
    volume_db: float | None = -20.0,
) -> Path:
    """Nối các bài nhạc trong playlist bằng FFmpeg acrossfade=d=2.0 & chuẩn âm lượng."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if not playlist:
        raise ValueError("Playlist BGM trống")

    actual_fade_out = min(fade_out_s, max(0.2, total_duration * 0.4))
    fade_start = max(0.0, total_duration - actual_fade_out)
    vol_suffix = f",volume={volume_db:g}dB" if volume_db is not None else ""

    cmd: list[str] = ["-y", "-v", "error"]
    if len(playlist) == 1:
        track_path, track_dur = playlist[0]
        if track_dur < total_duration:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend(["-i", str(track_path)])
        af = (
            f"[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d=0.8,afade=t=out:st={fade_start:.3f}:d={actual_fade_out:.3f},"
            f"loudnorm=I=-14:TP=-2:LRA=11{vol_suffix}[bgm]"
        )
    else:
        filter_parts: list[str] = []
        for idx, (track_path, _dur) in enumerate(playlist):
            cmd.extend(["-i", str(track_path)])
            filter_parts.append(
                f"[{idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{idx}]"
            )

        prev_label = "a0"
        prev_dur = playlist[0][1]
        for idx in range(1, len(playlist)):
            cur_label = f"a{idx}"
            cur_dur = playlist[idx][1]
            cf = min(crossfade_s, max(0.2, prev_dur * 0.35), max(0.2, cur_dur * 0.35))
            next_label = f"cf{idx}"
            filter_parts.append(
                f"[{prev_label}][{cur_label}]acrossfade=d={cf:.2f}:c1=tri:c2=tri[{next_label}]"
            )
            prev_label = next_label
            prev_dur = max(1.0, prev_dur + cur_dur - cf)

        filter_parts.append(
            f"[{prev_label}]atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d=0.8,afade=t=out:st={fade_start:.3f}:d={actual_fade_out:.3f},"
            f"loudnorm=I=-14:TP=-2:LRA=11{vol_suffix}[bgm]"
        )
        af = ";".join(filter_parts)

    cmd.extend(["-filter_complex", af, "-map", "[bgm]", "-c:a", "pcm_s16le", str(out_wav)])
    run_ffmpeg(cmd)
    return out_wav


def mix_voice_and_bgm_playlist(
    voice_mix_wav: Path,
    library_dir: Path,
    music_name: str | None,
    total_duration: float,
    out_wav: Path,
    workdir: Path,
) -> Path:
    """Trộn track giọng (-14 LUFS) với Playlist BGM phủ 100% thời lượng ở mức -20dB dưới giọng."""
    playlist = build_bgm_playlist(library_dir, music_name, total_duration, crossfade_s=2.0)
    if not playlist:
        shutil.copyfile(voice_mix_wav, out_wav)
        return out_wav

    bgm_wav = Path(workdir) / "bgm_playlist.wav"
    try:
        render_bgm_playlist_wav(playlist, total_duration, bgm_wav, crossfade_s=2.0, fade_out_s=2.0)
        fc = (
            "[0:a]pan=stereo|c0=0.707*c0|c1=0.707*c0,loudnorm=I=-14:TP=-1.5:LRA=11[v];"
            "[1:a]aresample=44100[bgm];"
            f"[v][bgm]amix=inputs=2:duration=first:normalize=0,atrim=0:{total_duration:.3f}[outa]"
        )
        run_ffmpeg(
            [
                "-y",
                "-v",
                "error",
                "-i",
                str(voice_mix_wav),
                "-i",
                str(bgm_wav),
                "-filter_complex",
                fc,
                "-map",
                "[outa]",
                "-c:a",
                "pcm_s16le",
                str(out_wav),
            ]
        )
        return out_wav
    except Exception as e:
        logger.warning("Trộn Playlist BGM thất bại: %s, giữ nguyên track giọng thuần", e)
        shutil.copyfile(voice_mix_wav, out_wav)
        return out_wav
