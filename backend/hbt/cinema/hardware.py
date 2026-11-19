"""Tự dò phần cứng thực tế (CPU i5-10400 clamp vs GPU RTX 2060S NVENC 1-frame probe)."""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable

from pydantic import BaseModel, Field

from hbt.shared.ffmpeg_utils import FFMPEG_ENCODE_CLAMP, FFMPEG_RESOURCE_CLAMP
from hbt.stickv.render import STICKV_MP4_COMPAT_FLAGS

CPU_LAYER_CACHE_MB = 256
GPU_LAYER_CACHE_MB = 512


class HardwareProfile(BaseModel):
    """Hồ sơ cấu hình phần cứng đang chạy để khóa ngân sách RAM và bộ mã hóa FFmpeg."""

    mode: str = "cpu"
    video_encoder: str = "libx264"
    gpu_name: str | None = None
    nvenc_probed: bool = False
    nvenc_probe_error: str | None = None
    layer_cache_mb: int = CPU_LAYER_CACHE_MB
    ffmpeg_threads: int = 2
    ffmpeg_resource_clamp: list[str] = Field(
        default_factory=lambda: list(FFMPEG_RESOURCE_CLAMP),
    )
    encode_flags: list[str] = Field(
        default_factory=lambda: list(FFMPEG_ENCODE_CLAMP),
    )
    compat_flags: list[str] = Field(
        default_factory=lambda: list(STICKV_MP4_COMPAT_FLAGS),
    )


_CACHE_LOCK = threading.Lock()
_CACHED_PROFILE: HardwareProfile | None = None
_CACHED_SCRIPT_FLAG: str | None = None


def _run_popen_quiet(cmd: list[str], timeout: float) -> tuple[int, str]:
    """Chạy tiến trình con có timeout và luôn đóng pipe + wait() trong try...finally."""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return -1, (stderr or "timeout")
        return proc.returncode, (stderr or stdout or "").strip()
    finally:
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass


def _detect_nvidia_gpu_name() -> str | None:
    """Lấy tên GPU NVIDIA qua `nvidia-smi` nếu có trên máy (không lỗi khi thiếu)."""
    smi = shutil.which("nvidia-smi")
    if smi is None:
        return None
    try:
        rc, out = _run_popen_quiet(
            [smi, "--query-gpu=name", "--format=csv,noheader"],
            timeout=3.0,
        )
    except OSError:
        return None
    if rc == 0 and out:
        return out.splitlines()[0].strip()
    return None


def probe_nvenc_one_frame(
    ffmpeg_bin: str | None = None,
    *,
    timeout: float = 5.0,
) -> tuple[bool, str | None]:
    """Thử encode thật 1 frame bằng `h264_nvenc` để xác nhận GPU & driver sẵn sàng."""
    exe = ffmpeg_bin or shutil.which("ffmpeg")
    if exe is None:
        return False, "ffmpeg not found on PATH"

    cmd = [
        exe,
        "-hide_banner",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=128x128:r=30:d=0.05",
        "-frames:v",
        "1",
        "-c:v",
        "h264_nvenc",
        "-pix_fmt",
        "yuv420p",
        "-f",
        "null",
        "-",
    ]
    try:
        rc, msg = _run_popen_quiet(cmd, timeout=timeout)
    except OSError as exc:
        return False, str(exc)

    if rc == 0:
        return True, None
    return False, (msg or f"h264_nvenc probe failed with exit code {rc}")[-300:]


def _build_profile(nvenc_ok: bool, probe_err: str | None, gpu_name: str | None) -> HardwareProfile:
    if nvenc_ok:
        return HardwareProfile(
            mode="gpu",
            video_encoder="h264_nvenc",
            gpu_name=gpu_name or "NVIDIA NVENC",
            nvenc_probed=True,
            nvenc_probe_error=None,
            layer_cache_mb=GPU_LAYER_CACHE_MB,
            ffmpeg_threads=0,
            ffmpeg_resource_clamp=[],
            encode_flags=["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21", "-rc", "vbr"],
            compat_flags=list(STICKV_MP4_COMPAT_FLAGS),
        )
    return HardwareProfile(
        mode="cpu",
        video_encoder="libx264",
        gpu_name=gpu_name,
        nvenc_probed=True,
        nvenc_probe_error=probe_err,
        layer_cache_mb=CPU_LAYER_CACHE_MB,
        ffmpeg_threads=2,
        ffmpeg_resource_clamp=list(FFMPEG_RESOURCE_CLAMP),
        encode_flags=list(FFMPEG_ENCODE_CLAMP),
        compat_flags=list(STICKV_MP4_COMPAT_FLAGS),
    )


def detect_hardware(
    *,
    force_refresh: bool = False,
    probe_fn: Callable[[], tuple[bool, str | None]] | None = None,
) -> HardwareProfile:
    """Dò phần cứng có cache luồng-an-toàn; lỗi probe tự động rơi về `libx264` + kẹp CPU."""
    global _CACHED_PROFILE

    if probe_fn is not None:
        ok, err = probe_fn()
        gpu_name = "Simulated NVENC GPU" if ok else None
        return _build_profile(ok, err, gpu_name)

    with _CACHE_LOCK:
        if _CACHED_PROFILE is not None and not force_refresh:
            return _CACHED_PROFILE
        gpu_name = _detect_nvidia_gpu_name()
        ok, err = probe_nvenc_one_frame()
        _CACHED_PROFILE = _build_profile(ok, err, gpu_name)
        return _CACHED_PROFILE


def resolve_filter_complex_script_flag(
    *,
    ffmpeg_bin: str | None = None,
    help_output: str | None = None,
) -> str:
    """Chọn cờ filtergraph theo FFmpeg (`-/filter_complex` 7+ vs `-filter_complex_script` 6)."""
    global _CACHED_SCRIPT_FLAG

    if help_output is not None:
        return (
            "-filter_complex_script"
            if "-filter_complex_script" in help_output
            else "-/filter_complex"
        )

    if ffmpeg_bin is None:
        with _CACHE_LOCK:
            if _CACHED_SCRIPT_FLAG is not None:
                return _CACHED_SCRIPT_FLAG

    exe = ffmpeg_bin or shutil.which("ffmpeg")
    if exe is None:
        return "-filter_complex_script"

    try:
        rc, out = _run_popen_quiet([exe, "-hide_banner", "-h", "long"], timeout=5.0)
    except OSError:
        return "-filter_complex_script"

    flag = (
        "-filter_complex_script"
        if (rc == 0 and "-filter_complex_script" in out)
        else "-/filter_complex"
    )
    if ffmpeg_bin is None:
        with _CACHE_LOCK:
            _CACHED_SCRIPT_FLAG = flag
    return flag


def reset_hardware_cache() -> None:
    """Xóa cache phần cứng (chủ yếu dùng trong unit test)."""
    global _CACHED_PROFILE, _CACHED_SCRIPT_FLAG
    with _CACHE_LOCK:
        _CACHED_PROFILE = None
        _CACHED_SCRIPT_FLAG = None
