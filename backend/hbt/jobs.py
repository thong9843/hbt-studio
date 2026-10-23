"""Hàng đợi job dựng video: 1 luồng, tiến độ, sự kiện cho SSE, huỷ (IMPLEMENT.md mục 9).

Job nằm trong bộ nhớ (mất khi khởi động lại server); file đã xuất vẫn còn ở `renders/<job_id>/`.
"""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hbt.config import ALLOWED_FPS
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.cancel import CancelToken, RenderCancelled
from hbt.pipeline.ffutil import INSTALL_HINT
from hbt.pipeline.lint import describe_issue, lint_project
from hbt.pipeline.render import MAX_PREVIEW_SECONDS, RenderOptions, render_project
from hbt.sensitive import SensitiveStore
from hbt.storage import Conflict, NotFound, ServiceUnavailable, Storage, Unprocessable

MAX_JOBS = 200  # giữ tối đa chừng này job (bỏ job đã xong cũ nhất)
LOG_TAIL = 20
CANCEL_WAIT = 5.0  # giây chờ job đang chạy dừng hẳn sau khi huỷ

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
FINISHED = (DONE, FAILED, CANCELLED)


@dataclass
class Job:
    id: str
    slug: str
    preview: bool
    fps: int | None
    outro: bool | None
    allow_long_trim: bool
    preview_seconds: float | None = None
    status: str = QUEUED
    progress: float = 0.0
    step: str = ""
    error: str | None = None
    needs_confirmation: bool = False
    output: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    token: CancelToken = field(default_factory=CancelToken)
    _log: deque = field(default_factory=lambda: deque(maxlen=200))
    _events: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _done: threading.Event = field(default_factory=threading.Event)

    @property
    def finished(self) -> bool:
        return self.status in FINISHED

    def log_tail(self, n: int = LOG_TAIL) -> list[str]:
        with self._lock:
            return list(self._log)[-n:]

    def events_since(self, index: int) -> list[tuple[str, dict]]:
        with self._lock:
            return list(self._events[index:])

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    def _emit(self, kind: str, data: dict) -> None:
        with self._lock:
            self._events.append((kind, data))

    def _progress(self, pct: float, step: str, message: str) -> None:
        with self._lock:
            self.progress, self.step = pct, step
            if message:
                self._log.append(message)
            self._events.append(
                ("progress", {"progress": round(pct, 1), "step": step, "message": message})
            )

    def _finish_locked(self, status: str, **extra: Any) -> None:
        if self.status in FINISHED:  # chỉ kết thúc một lần
            return
        self.status = status
        self.finished_at = time.time()
        for k, v in extra.items():
            setattr(self, k, v)
        payload = {"status": status, "error": self.error, "output": self.output}
        self._events.append(("end", payload))
        self._done.set()

    def _finish(self, status: str, **extra: Any) -> None:
        with self._lock:
            self._finish_locked(status, **extra)

    def _cancel_if_queued(self) -> bool:
        """Nguyên tử: job còn xếp hàng thì chuyển luôn sang cancelled (`_run` sẽ bỏ qua)."""
        with self._lock:
            if self.status != QUEUED:
                return False
            self._finish_locked(CANCELLED)
            return True


def check_render_tools() -> None:
    """Đủ FFmpeg (và ffprobe) để dựng chưa? Thiếu thì ServiceUnavailable kèm lời nhắn cài."""
    from hbt.api.health import check_ffmpeg

    missing = check_ffmpeg()
    if missing is None or shutil.which("ffprobe") is None:
        what = "FFmpeg" if missing is None else "ffprobe"
        raise ServiceUnavailable(
            f"Không tìm thấy {what} trên PATH nên chưa dựng được. {INSTALL_HINT}"
        )
    if missing:
        raise ServiceUnavailable(f"FFmpeg trên máy thiếu: {', '.join(missing)}. {INSTALL_HINT}")


class JobManager:
    def __init__(
        self,
        storage: Storage,
        library_dir: Path,
        brand_dir: Path | None = None,
        render_fn=render_project,
        tool_check=check_render_tools,
        sensitive: SensitiveStore | None = None,
    ):
        self.storage = storage
        self.library_dir = library_dir
        self.brand_dir = brand_dir
        self._render = render_fn
        self._tool_check = tool_check
        self.sensitive = sensitive
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="render")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- tra cứu
    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise NotFound(f"Không có job '{job_id}'")
        return job

    def is_busy(self, slug: str) -> bool:
        with self._lock:
            return any(j.slug == slug and not j.finished for j in self._jobs.values())

    # ---------------------------------------------------------------- tạo / huỷ
    def submit(
        self,
        slug: str,
        *,
        preview: bool = False,
        fps: int | None = None,
        outro: bool | None = None,
        allow_long_trim: bool = False,
        preview_seconds: float | None = None,
    ) -> Job:
        project = self.storage.load(slug)  # NotFound / BadRequest nếu project hỏng
        if fps is not None and fps not in ALLOWED_FPS:
            raise Unprocessable(f"fps phải là một trong {ALLOWED_FPS}")
        if preview_seconds is not None:
            if not preview:
                raise Unprocessable("preview_seconds chỉ dùng với chế độ Xem nhanh (preview=true)")
            if not 0 < preview_seconds <= MAX_PREVIEW_SECONDS:
                raise Unprocessable(f"preview_seconds phải trong (0, {MAX_PREVIEW_SECONDS}] giây")
        problems = project.render_problems()
        if problems:
            raise Unprocessable("Project chưa đủ để dựng: " + "; ".join(problems))
        if self.sensitive is not None:  # từ mức `block` chặn xuất, không tạo job (mục 7)
            blocked = [
                describe_issue(i)
                for i in lint_project(project, self.sensitive.load())
                if i.level == "block"
            ]
            if blocked:
                raise Unprocessable("Có từ bị chặn, sửa rồi dựng lại: " + "; ".join(blocked))
        if self._tool_check is not None:
            self._tool_check()
        job = Job(
            uuid.uuid4().hex[:12], slug, preview, fps, outro, allow_long_trim, preview_seconds
        )
        with self._lock:
            self._jobs[job.id] = job
            self._prune()
        self._pool.submit(self._run, job)
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.finished:
            raise Conflict(f"Job đã kết thúc ({job.status})")
        job.token.cancel()
        if not job._cancel_if_queued():
            job.wait(CANCEL_WAIT)  # đang chạy: chờ luồng dựng dừng hẳn
        return job

    def shutdown(self) -> None:
        with self._lock:
            jobs = [j for j in self._jobs.values() if not j.finished]
        for j in jobs:
            j.token.cancel()
        self._pool.shutdown(wait=True, cancel_futures=True)

    # ---------------------------------------------------------------- chạy
    def _prune(self) -> None:
        if len(self._jobs) <= MAX_JOBS:
            return
        done = sorted((j for j in self._jobs.values() if j.finished), key=lambda j: j.created_at)
        for j in done[: len(self._jobs) - MAX_JOBS]:
            del self._jobs[j.id]

    def _run(self, job: Job) -> None:
        with job._lock:
            if job.status != QUEUED:  # đã bị huỷ lúc còn xếp hàng
                return
            job.status = RUNNING
            job.started_at = time.time()
        folder = self.storage.project_dir(job.slug)
        opts = RenderOptions(
            preview=job.preview,
            fps=job.fps,
            outro=job.outro,
            allow_long_trim=job.allow_long_trim,
            preview_seconds=job.preview_seconds,
            sensitive_words=self.sensitive.load() if self.sensitive is not None else None,
            library_dir=self.library_dir,
            brand_dir=self.brand_dir,
            job_id=job.id,
        )
        try:
            result = self._render(folder, opts, progress=job._progress, cancel_token=job.token)
        except RenderCancelled:
            job._finish(CANCELLED)
        except TailTrimNeedsConfirmation as e:
            job._finish(FAILED, error=str(e), needs_confirmation=True)
        except Exception as e:  # noqa: BLE001
            job._finish(FAILED, error=str(e) or e.__class__.__name__)
        else:
            rel = self.storage.rel
            output = {
                "video": rel(result.video),
                "publish": rel(result.publish),
                "log": rel(result.log),
                "srt": rel(result.srt) if result.srt else None,
                "cover": rel(result.cover) if result.cover else None,
                "youtube_cover": rel(result.youtube_cover) if result.youtube_cover else None,
                "fps": result.fps,
                "width": result.width,
                "height": result.height,
                "duration": round(result.duration, 3),
                "lufs": round(result.lufs, 2) if result.lufs is not None else None,
                "preview_seconds": result.preview_seconds,
                "aligner": result.aligner,
                "seconds": round(result.seconds, 1),
                "warnings": result.warnings,
            }
            job._finish(DONE, output=output)
