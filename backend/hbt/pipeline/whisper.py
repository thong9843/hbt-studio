"""Chạy Whisper trong tiến trình con, chọn cấu hình theo phần cứng, rơi bậc khi lỗi (5.2).

Bậc rơi (mục 0): CUDA (lỗi lúc nạp hoặc lúc chạy) hoặc không có GPU → CPU `small` `int8` →
khoảng lặng. Module này lo hai bậc Whisper; bậc khoảng lặng do `render.run_alignment` lo khi nhận
`WhisperFailed`. Giới hạn thời gian là một ngân sách chung cho mọi bậc.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import cancel
from .cancel import RenderCancelled

DEFAULT_TIMEOUT = 900
POLL_SECONDS = 0.2
CUDA_MODEL, CUDA_COMPUTE = "large-v3", "int8_float16"
CPU_MODEL, CPU_COMPUTE = "small", "int8"
BACKEND_DIR = Path(__file__).resolve().parents[2]


class WhisperFailed(RuntimeError):
    """Whisper không cho được kết quả (mọi bậc đều lỗi, hết giờ, hoặc không nhận ra giọng)."""


class WhisperTimeout(WhisperFailed):
    pass


@dataclass(frozen=True)
class Step:
    device: str  # "cuda" | "cpu"
    compute_type: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.model} ({self.device}, {self.compute_type})"


@dataclass(frozen=True)
class WhisperConfig:
    model: str = "auto"  # auto | small | medium | large-v3
    device: str = "auto"  # auto | cuda | cpu
    timeout: int = DEFAULT_TIMEOUT
    models_dir: Path = Path("models")

    def key_parts(self) -> list:
        """Phần của khoá cache `timing.json` do cấu hình Whisper quyết định."""
        return [self.model, self.device, self.timeout, is_installed(), detect_cuda()]


@dataclass
class WhisperRun:
    syllables: list[tuple[str, float, float]]
    step: Step
    seconds: float
    skipped: list[str] = field(default_factory=list)  # lý do từng bậc đã bỏ qua

    def info(self) -> dict:
        return {
            "model": self.step.model,
            "device": self.step.device,
            "compute_type": self.step.compute_type,
            "whisper_seconds": round(self.seconds, 1),
            "skipped": self.skipped,
        }


def effective_model(app_model: str, env_model: str) -> str:
    """`app.json` (Cài đặt) ghi đè `.env`; `auto` thì xét `.env`; vẫn `auto` thì theo phần cứng."""
    return app_model if app_model != "auto" else env_model


def is_installed() -> bool:
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


def detect_cuda() -> bool:
    try:
        return importlib.import_module("ctranslate2").get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 — không có ctranslate2 hoặc driver lỗi: coi như không có GPU
        return False


def plan_steps(model: str, device: str, gpu: bool) -> list[Step]:
    """Các bậc Whisper theo thứ tự thử. `model=auto` chọn theo thiết bị của từng bậc."""
    cuda = Step("cuda", CUDA_COMPUTE, CUDA_MODEL if model == "auto" else model)
    cpu = Step("cpu", CPU_COMPUTE, CPU_MODEL if model == "auto" else model)
    if device == "cpu":
        return [cpu]
    if device == "cuda" or gpu:
        return [cuda, cpu]
    return [cpu]


def model_cached(models_dir: Path, name: str) -> bool:
    """Model đã có trong `models/` (cấu trúc cache Hugging Face) thì nạp thẳng, không tải lại."""
    snapshots = Path(models_dir) / f"models--Systran--faster-whisper-{name}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.glob("*/model.bin"))


def worker_command(request: Path) -> list[str]:
    return [sys.executable, "-m", "hbt.pipeline.whisper_worker", str(request)]


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    proc.wait()


def _read_progress(path: Path) -> float | None:
    """Dòng tiến độ cuối cùng của tiến trình con (phần giọng đã nghe, 0…1)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return float(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None  # chưa có file, hoặc đang ghi dở dòng cuối


def _run_step(
    step: Step,
    wav: str,
    prompt: str,
    cfg: WhisperConfig,
    deadline: float,
    work: Path,
    on_progress: Callable[[float], None] | None = None,
) -> list:
    """Chạy một bậc; trả về danh sách âm tiết hoặc ném WhisperFailed / WhisperTimeout."""
    req_path, out_path, err_path = work / "req.json", work / "out.json", work / "err.txt"
    progress_path = work / "progress.txt"
    out_path.unlink(missing_ok=True)
    progress_path.unlink(missing_ok=True)
    request = {
        **asdict(step),
        # tiến trình con chạy ở thư mục backend/: đường dẫn tương đối của người gọi sẽ sai
        "wav": str(Path(wav).resolve()),
        "prompt": prompt,
        "models_dir": str(Path(cfg.models_dir).resolve()),
        "local_only": model_cached(cfg.models_dir, step.model),
        "out": str(out_path),
        "progress": str(progress_path),
    }
    req_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    token = cancel.current()
    with err_path.open("wb") as err:
        proc = subprocess.Popen(
            worker_command(req_path), stdout=subprocess.DEVNULL, stderr=err, cwd=BACKEND_DIR
        )
        if token is not None:
            token.track(proc)
        try:
            last = 0.0
            while True:
                try:
                    proc.wait(timeout=POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
                cancel.check_current()
                if on_progress is not None:
                    frac = _read_progress(progress_path)
                    if frac is not None and frac > last:
                        last = frac
                        on_progress(frac)
                if time.monotonic() >= deadline:
                    raise WhisperTimeout(f"quá giới hạn {cfg.timeout} giây")
        finally:
            _kill(proc)  # hết giờ, huỷ job hay lỗi: không để tiến trình mồ côi
            if token is not None:
                token.untrack(proc)
    cancel.check_current()
    if out_path.is_file():
        data = json.loads(out_path.read_text(encoding="utf-8"))
        if data.get("ok"):
            return [(s, float(a), float(b)) for s, a, b in data["syllables"]]
        when = "lúc chạy" if data.get("stage") == "run" else "lúc nạp model"
        raise WhisperFailed(f"lỗi {when}: {data.get('error', '?')}")
    tail = err_path.read_text(encoding="utf-8", errors="replace").strip()[-300:]
    raise WhisperFailed(f"tiến trình Whisper thoát mã {proc.returncode} {tail}".strip())


def run_whisper(
    wav: str | Path,
    prompt: str,
    cfg: WhisperConfig,
    log: Callable[[str], None] = print,
    *,
    steps: list[Step] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> WhisperRun:
    """Thử lần lượt các bậc đến khi một bậc cho kết quả. Mọi bậc lỗi → WhisperFailed.

    `on_progress(f)`: phần giọng đã nghe (0…1, tăng dần trong mỗi bậc)."""
    steps = steps or plan_steps(cfg.model, cfg.device, detect_cuda())
    deadline = time.monotonic() + cfg.timeout
    skipped: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hbt-whisper-") as tmp:
        for i, step in enumerate(steps):
            log(f"Whisper {step.label}…")
            t0 = time.monotonic()
            try:
                syllables = _run_step(step, str(wav), prompt, cfg, deadline, Path(tmp), on_progress)
            except RenderCancelled:
                raise
            except WhisperTimeout as e:
                skipped.append(f"{step.label}: {e}")
                log(f"Whisper {step.label} {e}")
                raise WhisperTimeout("; ".join(skipped)) from e
            except WhisperFailed as e:
                skipped.append(f"{step.label}: {e}")
                more = "thử bậc kế" if i + 1 < len(steps) else "hết bậc"
                log(f"Whisper {step.label} {e}; {more}")
                continue
            if not syllables:
                skipped.append(f"{step.label}: không nhận ra giọng nói")
                log(f"Whisper {step.label} không nhận ra giọng nói")
                continue
            return WhisperRun(syllables, step, time.monotonic() - t0, skipped)
    raise WhisperFailed("; ".join(skipped))
