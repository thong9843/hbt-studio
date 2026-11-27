"""Công cụ đo tài nguyên (Wall-clock, RSS RAM, CPU, tệp tạm) khi dựng video StickV thật.

Cách dùng:
  backend\\.venv\\Scripts\\python scripts/benchmark_render_resources.py \\
    --project bi-mat-dang-sau-thap-nghieng-pisa --reuse-wavs --cold-whisper \\
    --disable-beat-cache --out workspace/stickv/_checks/perf_after.json \\
    --compare workspace/stickv/_checks/perf_baseline.json
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import platform
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Hằng số Win32 cho Toolhelp32 + GetProcessMemoryInfo + GetProcessTimes
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


def _ft_to_sec(ft: _FILETIME) -> float:
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 10_000_000.0


def _sample_process_tree(root_pid: int) -> dict[int, tuple[str, float, float]]:
    """Trả về `{pid: (exe_name, rss_mb, total_cpu_sec)}` cho `root_pid` và mọi tiến trình con."""
    if os.name != "nt":
        return {}
    k32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == ctypes.c_void_p(-1).value:
        return {}
    children: dict[int, list[int]] = {}
    names: dict[int, str] = {}
    try:
        pe = _PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            pid = int(pe.th32ProcessID)
            ppid = int(pe.th32ParentProcessID)
            names[pid] = str(pe.szExeFile)
            children.setdefault(ppid, []).append(pid)
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)

    tree_pids: list[int] = []
    stack = [root_pid]
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        tree_pids.append(cur)
        stack.extend(children.get(cur, []))

    out: dict[int, tuple[str, float, float]] = {}
    for pid in tree_pids:
        h = k32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not h:
            h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            continue
        try:
            pmc = _PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            rss_mb = 0.0
            if psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                rss_mb = pmc.WorkingSetSize / (1024.0 * 1024.0)
            ct, et, kt, ut = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
            cpu_s = 0.0
            if k32.GetProcessTimes(
                h,
                ctypes.byref(ct),
                ctypes.byref(et),
                ctypes.byref(kt),
                ctypes.byref(ut),
            ):
                cpu_s = _ft_to_sec(kt) + _ft_to_sec(ut)
            out[pid] = (names.get(pid, f"pid-{pid}"), rss_mb, cpu_s)
        finally:
            k32.CloseHandle(h)
    return out


class ResourceMonitor:
    """Lấy mẫu CPU/RAM toàn cây tiến trình & số tệp tạm mỗi 0.25s khi render."""

    def __init__(self, build_dir: Path, interval_sec: float = 0.25) -> None:
        self.build_dir = build_dir
        self.interval_sec = interval_sec
        self.logical_cpus = max(1, os.cpu_count() or 1)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.cur_phase: str = "init"
        self.cur_pct: float = 0.0
        self.phases: list[dict[str, Any]] = []
        self._t0 = time.monotonic()

        self.rss_samples: list[float] = []
        self.cpu_machine_samples: list[float] = []
        self.cpu_multi_samples: list[float] = []
        self.peak_rss_mb = 0.0
        self.peak_rss_context: dict[str, Any] = {}
        self.peak_by_exe: dict[str, float] = {}
        self.max_temp_files = 0
        self.max_temp_pngs = 0
        self._prev_cpu: dict[int, float] = {}
        self._prev_t = 0.0

    def record_phase(self, pct: float, msg: str) -> None:
        now = round(time.monotonic() - self._t0, 2)
        with self._lock:
            if msg == self.cur_phase:
                return
            if self.phases:
                self.phases[-1]["dur_sec"] = round(
                    now - self.phases[-1]["start_sec"], 2
                )
            self.cur_phase = msg
            self.cur_pct = pct
            self.phases.append(
                {
                    "pct": pct,
                    "stage": msg,
                    "start_sec": now,
                    "dur_sec": 0.0,
                    "peak_rss_mb": 0.0,
                    "_cpu": [],
                }
            )

    def _tick(self) -> None:
        now_t = time.monotonic()
        tree = _sample_process_tree(os.getpid())
        total_rss = sum(v[1] for v in tree.values())
        dt = now_t - self._prev_t if self._prev_t > 0 else 0.0
        multi_pct = 0.0
        if dt > 0.05:
            delta_cpu = 0.0
            for pid, (_exe, _r, cpu_s) in tree.items():
                prev = self._prev_cpu.get(pid)
                if prev is not None and cpu_s >= prev:
                    delta_cpu += cpu_s - prev
            multi_pct = min(self.logical_cpus * 100.0, (delta_cpu / dt) * 100.0)
        machine_pct = multi_pct / self.logical_cpus
        self._prev_cpu = {pid: v[2] for pid, v in tree.items()}
        self._prev_t = now_t

        n_files = n_pngs = 0
        if self.build_dir.is_dir():
            try:
                for p in self.build_dir.rglob("*"):
                    if p.is_file() and "beat_cache" not in p.parts:
                        n_files += 1
                        if p.suffix.lower() == ".png":
                            n_pngs += 1
            except OSError:
                pass

        with self._lock:
            self.rss_samples.append(total_rss)
            if dt > 0.05:
                self.cpu_multi_samples.append(multi_pct)
                self.cpu_machine_samples.append(machine_pct)
            self.max_temp_files = max(self.max_temp_files, n_files)
            self.max_temp_pngs = max(self.max_temp_pngs, n_pngs)
            for pid, (exe, rss, _) in tree.items():
                self.peak_by_exe[exe] = max(
                    self.peak_by_exe.get(exe, 0.0), round(rss, 1)
                )
            if total_rss > self.peak_rss_mb:
                self.peak_rss_mb = total_rss
                self.peak_rss_context = {
                    "phase": self.cur_phase,
                    "processes_mb": {
                        f"{exe}({pid})": round(rss, 1)
                        for pid, (exe, rss, _) in sorted(tree.items())
                    },
                }
            if self.phases:
                self.phases[-1]["peak_rss_mb"] = max(
                    self.phases[-1]["peak_rss_mb"], round(total_rss, 1)
                )
                if dt > 0.05:
                    self.phases[-1]["_cpu"].append(machine_pct)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_sec):
            self._tick()

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._tick()
        self._thread = threading.Thread(target=self._run, name="res-mon", daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        wall = round(time.monotonic() - self._t0, 2)
        with self._lock:
            if self.phases:
                self.phases[-1]["dur_sec"] = round(
                    wall - self.phases[-1]["start_sec"], 2
                )
            cleaned_phases = []
            for ph in self.phases:
                cpus = ph.pop("_cpu", [])
                ph["avg_cpu_pct"] = round(sum(cpus) / len(cpus), 1) if cpus else 0.0
                cleaned_phases.append(ph)
            return {
                "metrics": {
                    "wall_clock_sec": wall,
                    "peak_rss_mb": round(self.peak_rss_mb, 1),
                    "avg_rss_mb": (
                        round(sum(self.rss_samples) / len(self.rss_samples), 1)
                        if self.rss_samples
                        else 0.0
                    ),
                    "peak_cpu_pct_machine": (
                        round(max(self.cpu_machine_samples), 1)
                        if self.cpu_machine_samples
                        else 0.0
                    ),
                    "avg_cpu_pct_machine": (
                        round(
                            sum(self.cpu_machine_samples)
                            / len(self.cpu_machine_samples),
                            1,
                        )
                        if self.cpu_machine_samples
                        else 0.0
                    ),
                    "peak_cpu_pct_multicore": (
                        round(max(self.cpu_multi_samples), 1)
                        if self.cpu_multi_samples
                        else 0.0
                    ),
                    "avg_cpu_pct_multicore": (
                        round(
                            sum(self.cpu_multi_samples) / len(self.cpu_multi_samples), 1
                        )
                        if self.cpu_multi_samples
                        else 0.0
                    ),
                    "max_temp_files_in_build": self.max_temp_files,
                    "max_temp_pngs_in_build": self.max_temp_pngs,
                    "sample_count": len(self.rss_samples),
                    "sample_interval_sec": self.interval_sec,
                },
                "peak_rss_context": self.peak_rss_context,
                "peak_single_process_mb_by_exe": self.peak_by_exe,
                "phases": cleaned_phases,
            }


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo CPU/RAM & thời gian render StickV")
    parser.add_argument("--project", default="bi-mat-dang-sau-thap-nghieng-pisa")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("workspace/stickv/_checks/perf_after.json"),
    )
    parser.add_argument("--compare", type=Path, default=None)
    parser.add_argument("--reuse-wavs", action="store_true")
    parser.add_argument("--cold-whisper", action="store_true")
    parser.add_argument("--disable-beat-cache", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    if args.disable_beat_cache:
        os.environ["STICKV_DISABLE_BEAT_CACHE"] = "1"
    else:
        os.environ.pop("STICKV_DISABLE_BEAT_CACHE", None)

    from hbt.app_settings import AppSettingsStore
    from hbt.config import BRAND_DIR, load_settings
    from hbt.shared.ffmpeg_utils import measure_audio_duration
    from hbt.stickv import render as sv_render
    from hbt.stickv.storage import load_stickv_project

    settings = load_settings()
    project_dir = settings.workspace_dir / "stickv" / args.project
    project = load_stickv_project(settings.workspace_dir, args.project)
    if args.cold_whisper:
        (project_dir / "build" / "stickv_timing.json").unlink(missing_ok=True)
    if args.disable_beat_cache:
        import shutil

        shutil.rmtree(project_dir / "build" / "beat_cache", ignore_errors=True)

    orig_synth = sv_render.synth_stickv_beats_audio
    if args.reuse_wavs:
        audio_dir = project_dir / "audio"

        def _reuse_synth(
            beats: list[Any], *_a: Any, **kw: Any
        ) -> list[tuple[Path, float]]:
            out_wavs: list[tuple[Path, float]] = []
            for b in beats:
                wp = audio_dir / f"{b.id}.wav"
                if not wp.is_file() or wp.stat().st_size <= 44:
                    return orig_synth(beats, *_a, **kw)
                dur = round(max(1.2, measure_audio_duration(wp)), 3)
                b.duration_sec = dur
                out_wavs.append((wp, dur))
            return out_wavs

        sv_render.synth_stickv_beats_audio = _reuse_synth  # type: ignore[assignment]

    wm = AppSettingsStore(settings.workspace_dir).load().watermark
    mon = ResourceMonitor(project_dir / "build")
    mon.start()
    render_res: dict[str, Any] = {}
    try:
        render_res = sv_render.render_stickv(
            project,
            project_dir,
            library_dir=settings.library_dir,
            assets_dir=settings.assets_dir,
            brand_dir=BRAND_DIR,
            watermark=wm,
            preview=args.preview,
            on_progress=mon.record_phase,
        )
    finally:
        sv_render.synth_stickv_beats_audio = orig_synth
        report = mon.stop()

    report["project_slug"] = args.project
    report["mode"] = (
        f"{'30fps_preview' if args.preview else '60fps_final'}"
        f"{'_reuse_wavs' if args.reuse_wavs else ''}"
        f"{'_cold_whisper' if args.cold_whisper else ''}"
        f"{'_nocache' if args.disable_beat_cache else '_cached'}"
    )
    report["machine"] = {
        "platform": platform.platform(),
        "logical_cpus": mon.logical_cpus,
    }
    report["render_output"] = render_res

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    m = report["metrics"]
    print(
        f"[BENCH] wall={m['wall_clock_sec']}s | peak_rss={m['peak_rss_mb']}MB | "
        f"avg_rss={m['avg_rss_mb']}MB | peak_cpu={m['peak_cpu_pct_machine']}% | "
        f"avg_cpu={m['avg_cpu_pct_machine']}% | temp_files={m['max_temp_files_in_build']}"
    )
    if args.compare and args.compare.is_file():
        base = json.loads(args.compare.read_text(encoding="utf-8")).get("metrics", {})
        print("[COMPARE vs baseline]")
        for k in (
            "wall_clock_sec",
            "peak_rss_mb",
            "avg_rss_mb",
            "peak_cpu_pct_machine",
            "avg_cpu_pct_machine",
            "max_temp_files_in_build",
        ):
            bv = base.get(k, 0)
            nv = m.get(k, 0)
            delta = round(nv - bv, 2) if isinstance(bv, (int, float)) else 0
            print(f"  {k}: {bv} -> {nv} (delta={delta:+})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
