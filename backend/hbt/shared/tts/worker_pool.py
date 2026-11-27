"""Warm Resident VieNeu-TTS Pool (giữ worker sống qua nhiều beat, tự giải phóng khi rảnh)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hbt.postv.voice import BACKEND_DIR, WEIGHTS_REPO, venv_python
from hbt.shared.audio_utils import write_fallback_speech_wav_atomic

RESIDENT_WORKER = Path(__file__).with_name("resident_worker.py")
DEFAULT_IDLE_TTL_SEC = 600.0
FALLBACK_SAMPLE_RATE = 24000


def _write_fallback_wav_atomic(dest: Path, text: str) -> Path:
    """Tạo file WAV 24kHz mono 16-bit dự phòng khi chạy trên CI không có VieNeu/weights."""
    return write_fallback_speech_wav_atomic(
        dest, text, sample_rate=FALLBACK_SAMPLE_RATE, audible=False
    )


def _close_proc_safely(proc: subprocess.Popen[str]) -> None:
    """Đóng toàn bộ pipe của tiến trình con và đợi thoát hẳn trong khối try...finally."""
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            try:
                proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                proc.stdin.flush()
            except OSError:
                pass
            try:
                proc.stdin.close()
            except OSError:
                pass
    finally:
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None and not pipe.closed:
                try:
                    pipe.close()
                except OSError:
                    pass
        try:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)
            else:
                proc.wait(timeout=1.0)
        except Exception:
            pass


class WarmTTSPool:
    """Quản lý tiến trình VieNeu-TTS thường trú (`idle_ttl_sec=600s`) + fallback CI an toàn."""

    def __init__(
        self,
        models_dir: Path,
        *,
        venv_dir: Path | None = None,
        idle_ttl_sec: float = DEFAULT_IDLE_TTL_SEC,
        reaper_interval_sec: float = 0.25,
        worker_cmd: Sequence[str] | None = None,
    ) -> None:
        self.models_dir = Path(models_dir)
        self.hf_home = self.models_dir / "hf_vieneu"
        self.venv_dir = Path(venv_dir) if venv_dir is not None else BACKEND_DIR / ".venv-tts"
        self.idle_ttl_sec = max(0.05, float(idle_ttl_sec))
        self.reaper_interval_sec = max(
            0.02, min(float(reaper_interval_sec), self.idle_ttl_sec / 2.0)
        )
        self._custom_worker_cmd = list(worker_cmd) if worker_cmd is not None else None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._proc: subprocess.Popen[str] | None = None
        self._last_used_at: float = 0.0
        self._worker_pid: int | None = None
        self._spawn_count: int = 0
        self._reaper_thread: threading.Thread | None = None

    def is_available(self) -> bool:
        """Kiểm tra có tiến trình worker cấu hình riêng hoặc đủ `.venv-tts` + trọng số local."""
        if self._custom_worker_cmd is not None:
            return True
        py = venv_python(self.venv_dir)
        site = [*self.venv_dir.glob("Lib/site-packages/vieneu")]
        site += [*self.venv_dir.glob("lib/*/site-packages/vieneu")]
        if not py.is_file() or not site:
            return False
        snapshots = self.hf_home / "hub" / WEIGHTS_REPO / "snapshots"
        return next(snapshots.glob("*"), None) is not None

    @property
    def is_warm(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def worker_pid(self) -> int | None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._worker_pid
            return None

    @property
    def spawn_count(self) -> int:
        with self._lock:
            return self._spawn_count

    def _ensure_reaper_locked(self) -> None:
        if self._reaper_thread is not None and self._reaper_thread.is_alive():
            return
        self._stop_event.clear()
        self._reaper_thread = threading.Thread(
            target=self._reap_loop,
            name="warm-tts-reaper",
            daemon=True,
        )
        self._reaper_thread.start()

    def _reap_loop(self) -> None:
        while not self._stop_event.wait(self.reaper_interval_sec):
            stale_proc: subprocess.Popen[str] | None = None
            with self._lock:
                if (
                    self._proc is not None
                    and self._proc.poll() is None
                    and self._last_used_at > 0.0
                    and (time.monotonic() - self._last_used_at) >= self.idle_ttl_sec
                ):
                    stale_proc = self._proc
                    self._proc = None
                    self._worker_pid = None
            if stale_proc is not None:
                _close_proc_safely(stale_proc)

    def _spawn_locked(self) -> subprocess.Popen[str]:
        if self._custom_worker_cmd is not None:
            cmd = list(self._custom_worker_cmd)
            env = dict(os.environ)
        else:
            cmd = [
                str(venv_python(self.venv_dir)),
                "-I",
                "-X",
                "utf8",
                str(RESIDENT_WORKER),
                str(self.hf_home.resolve()),
            ]
            env = {
                **os.environ,
                "HF_HOME": str(self.hf_home.resolve()),
                "HF_HUB_OFFLINE": "1",
            }

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(BACKEND_DIR),
        )
        try:
            assert proc.stdout is not None
            boot_line = proc.stdout.readline()
            if not boot_line:
                err_txt = proc.stderr.read() if proc.stderr is not None else ""
                raise RuntimeError(f"WarmTTS worker thoát sớm lúc khởi động: {err_txt[-300:]}")
            boot_data = json.loads(boot_line)
            if not boot_data.get("ok"):
                raise RuntimeError(str(boot_data.get("error") or "WarmTTS worker load thất bại"))
            self._proc = proc
            self._worker_pid = int(boot_data.get("pid") or proc.pid)
            self._spawn_count += 1
            self._last_used_at = time.monotonic()
            self._ensure_reaper_locked()
            return proc
        except Exception:
            _close_proc_safely(proc)
            raise

    def _send_command(self, payload: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                if self._proc is not None:
                    _close_proc_safely(self._proc)
                    self._proc = None
                    self._worker_pid = None
                proc = self._spawn_locked()
            else:
                proc = self._proc

            assert proc.stdin is not None
            assert proc.stdout is not None

            result_box: dict[str, Any] = {}
            err_box: list[BaseException] = []

            def _rpc() -> None:
                try:
                    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    proc.stdin.flush()
                    line = proc.stdout.readline()
                    if not line:
                        raise RuntimeError("WarmTTS worker đóng stdout bất ngờ")
                    result_box["data"] = json.loads(line)
                except BaseException as exc:  # noqa: BLE001
                    err_box.append(exc)

            worker_io = threading.Thread(target=_rpc, daemon=True)
            worker_io.start()
            worker_io.join(timeout=timeout)
            if worker_io.is_alive() or err_box:
                self._proc = None
                self._worker_pid = None
                _close_proc_safely(proc)
                if err_box:
                    err = err_box[0]
                    raise RuntimeError(f"Lỗi giao tiếp WarmTTS worker: {err}") from err
                raise TimeoutError(f"WarmTTS worker quá hạn {timeout:.1f}s")

            self._last_used_at = time.monotonic()
            return result_box["data"]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        out_wav: Path,
        *,
        timeout: float = 60.0,
    ) -> Path:
        """Sinh file WAV qua worker thường trú; tự động rơi về WAV dự phòng khi thiếu VieNeu."""
        target = Path(out_wav)
        if not self.is_available():
            return _write_fallback_wav_atomic(target, text)

        target.parent.mkdir(parents=True, exist_ok=True)
        resp = self._send_command(
            {"cmd": "synth", "text": text, "voice": voice_id, "out": str(target)},
            timeout=timeout,
        )
        if not resp.get("ok") or not target.is_file() or target.stat().st_size <= 44:
            if self._custom_worker_cmd is not None:
                raise RuntimeError(str(resp.get("error") or "Worker không tạo được file WAV"))
            return _write_fallback_wav_atomic(target, text)
        return target

    def shutdown(self) -> None:
        """Tắt hẳn worker thường trú & giải phóng RAM ngay lập tức."""
        self._stop_event.set()
        proc: subprocess.Popen[str] | None = None
        with self._lock:
            proc = self._proc
            self._proc = None
            self._worker_pid = None
            reaper = self._reaper_thread
            self._reaper_thread = None
        if proc is not None:
            _close_proc_safely(proc)
        if reaper is not None and reaper.is_alive():
            reaper.join(timeout=1.5)

    def __enter__(self) -> WarmTTSPool:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()
