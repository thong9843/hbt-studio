"""Huỷ một lần dựng: ngắt giữa các bước và kill các tiến trình ffmpeg con (IMPLEMENT.md mục 9).

Chỉ có một lần dựng chạy tại một thời điểm (`jobs.py` dùng 1 luồng), nên token đang dùng được giữ ở
biến module `_current`; mọi chỗ gọi ffmpeg (kể cả trong luồng phụ) tự nhận ra nó.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager


class RenderCancelled(Exception):
    """Lần dựng bị người dùng huỷ."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen] = set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise RenderCancelled

    def cancel(self) -> None:
        """Đặt cờ huỷ và kill mọi tiến trình đang được theo dõi."""
        with self._lock:
            self._event.set()
            procs = list(self._procs)
        for p in procs:
            _kill(p)

    def track(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.add(proc)
            already = self._event.is_set()
        if already:  # huỷ xảy ra giữa lúc bắt đầu tiến trình
            _kill(proc)

    def untrack(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)


def _kill(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except OSError:
        pass  # đã tự kết thúc


_current: CancelToken | None = None


def current() -> CancelToken | None:
    return _current


def check_current() -> None:
    if _current is not None:
        _current.check()


@contextmanager
def use_token(token: CancelToken | None) -> Iterator[None]:
    global _current
    previous, _current = _current, token
    try:
        yield
    finally:
        _current = previous
