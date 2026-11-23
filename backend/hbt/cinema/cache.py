"""Beat-Level Content-Addressed Cache (SHA-256) & ghép nối không lệch tiếng (`concat -c copy`)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from hbt.cinema.hardware import HardwareProfile, detect_hardware
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP

BEAT_VIDEO_TIMESCALE = 90000
BEAT_AUDIO_RATE = 48000
BEAT_AUDIO_CHANNELS = 2
BEAT_PIX_FMT = "yuv420p"

_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def build_normalized_beat_flags(
    fps: int,
    hw: HardwareProfile | None = None,
) -> list[str]:
    """Cờ FFmpeg khóa `fps`, `timescale=90000`, `yuv420p`, `48000Hz stereo` cho từng beat."""
    profile = hw or detect_hardware()
    enc_flags = list(profile.encode_flags)
    if profile.video_encoder == "libx264":
        profile_flags = ["-profile:v", "high", "-level", "4.1"]
    else:
        profile_flags = []
    return [
        *enc_flags,
        "-pix_fmt",
        BEAT_PIX_FMT,
        *profile_flags,
        "-r",
        str(max(15, int(fps))),
        "-fps_mode",
        "cfr",
        "-video_track_timescale",
        str(BEAT_VIDEO_TIMESCALE),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        str(BEAT_AUDIO_RATE),
        "-ac",
        str(BEAT_AUDIO_CHANNELS),
        "-movflags",
        "+faststart",
    ]


def _atomic_write_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _escape_concat_path(path: Path) -> str:
    posix = path.resolve().as_posix()
    return posix.replace("'", r"'\''")


class BeatCache:
    """Bộ đệm beat MP4 theo SHA-256: chỉ render beat đổi nội dung rồi ghép `concat -c copy`."""

    def __init__(self, cache_dir: Path, *, max_disk_mb: int = 1024) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_disk_bytes = max(16 * 1024 * 1024, int(max_disk_mb) * 1024 * 1024)

    def _validate_key(self, key: str) -> str:
        clean = (key or "").strip()
        if not _SAFE_KEY_RE.match(clean):
            raise ValueError(f"Khóa BeatCache không hợp lệ: {key!r}")
        return clean

    def path_for(self, key: str) -> Path:
        safe = self._validate_key(key)
        return self.cache_dir / f"{safe}.mp4"

    def lookup(self, key: str) -> Path | None:
        target = self.path_for(key)
        if not target.is_file():
            return None
        try:
            if target.stat().st_size <= 512:
                return None
            os.utime(target, None)
        except OSError:
            return None
        return target

    def store_from_file(self, key: str, src_mp4: Path) -> Path:
        """Lưu bản sao nguyên tử từ `src_mp4` vào BeatCache bằng `.tmp.mp4` + `os.replace`."""
        src = Path(src_mp4)
        if not src.is_file() or src.stat().st_size <= 512:
            raise ValueError(f"Tệp nguồn beat không hợp lệ: {src}")
        target = self.path_for(key)
        tmp = target.with_name(f"{target.stem}.tmp.mp4")
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        self._prune_if_needed(keep=target)
        return target

    def _prune_if_needed(self, *, keep: Path | None = None) -> None:
        items = sorted(
            (
                p
                for p in self.cache_dir.glob("*.mp4")
                if p.is_file() and not p.name.endswith(".tmp.mp4")
            ),
            key=lambda p: p.stat().st_mtime,
        )
        total = sum(p.stat().st_size for p in items)
        for p in items:
            if total <= self.max_disk_bytes:
                break
            if keep is not None and p.resolve() == keep.resolve():
                continue
            try:
                sz = p.stat().st_size
                p.unlink(missing_ok=True)
                total -= sz
            except OSError:
                continue

    def concat_cached_beats(
        self,
        beat_paths: Sequence[Path],
        out_mp4: Path,
        *,
        work_dir: Path | None = None,
        hw: HardwareProfile | None = None,
    ) -> Path:
        """Ghép các đoạn beat đã chuẩn hóa cùng luồng bằng `concat -c copy` + ghi nguyên tử."""
        if not beat_paths:
            raise ValueError("Danh sách beat cần ghép đang rỗng")

        out_path = Path(out_mp4)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        list_dir = Path(work_dir) if work_dir is not None else out_path.parent
        concat_txt = list_dir / "beat_concat.txt"
        lines = [f"file '{_escape_concat_path(Path(p))}'" for p in beat_paths]
        _atomic_write_text(concat_txt, "\n".join(lines) + "\n")

        tmp_out = out_path.with_name(f"{out_path.stem}.tmp.mp4")
        clamp = list(hw.ffmpeg_resource_clamp) if hw is not None else list(FFMPEG_RESOURCE_CLAMP)
        cmd = [
            ffmpeg_exe(),
            "-hide_banner",
            "-v",
            "error",
            "-y",
            *clamp,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(tmp_out),
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        stderr_b = b""
        try:
            _, stderr_b = proc.communicate(timeout=180.0)
            if proc.returncode != 0:
                raise FFmpegError(
                    f"concat BeatCache thất bại (mã {proc.returncode}): "
                    f"{stderr_b.decode('utf-8', errors='replace')[-400:]}"
                )
            os.replace(tmp_out, out_path)
            return out_path
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
            if tmp_out.exists():
                tmp_out.unlink(missing_ok=True)
