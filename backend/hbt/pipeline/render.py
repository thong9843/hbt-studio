"""Điều phối dựng video (IMPLEMENT.md mục 4, 4b–4d).

Tham số chuyển động / mã hoá lấy từ `reference/pipeline/render50_reference.py` (đã chạy thật):
phóng ảnh nội bộ ×3, easing smoothstep / easeOutCubic, chuyển cảnh trượt có nhoè chuyển động
ghép bằng numpy (không dùng `xfade`), clip cảnh `crf 12`, bản cuối `crf 16`.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import time
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from hbt.config import ALLOWED_FPS, BRAND_DIR, load_settings
from hbt.models import load_project
from hbt.sensitive import SensitiveWords

from . import align as _align
from . import audio, cache, cancel
from . import captions as _captions
from . import scene_align as _scene_align
from . import text as _text
from . import visual as _visual
from . import whisper as _whisper
from . import whisper_worker as _whisper_worker
from .align import match_script
from .audio import TailTrimNeedsConfirmation
from .cancel import CancelToken, RenderCancelled
from .captions import build_phrases, caption_y_for, render_states, write_ffconcat, write_srt
from .ffutil import ffmpeg_exe, measure_lufs, media_duration, probe, run_ffmpeg
from .lint import describe_issue, lint_project
from .publish import build_publish_text
from .scene_align import AlignError, align_scenes
from .text import parse_voice
from .thumbnail import LOGO_FILE, render_cover, save_covers
from .visual import build_scene_layers
from .whisper import WhisperConfig, WhisperFailed, run_whisper

X = 0.4  # thời lượng chuyển cảnh (giây)
SUBSAMPLES = 6  # mẫu con mỗi khung trong nửa chu kỳ khung (màn trập 180°)
INTERNAL_SCALE = (3240, 5760)  # ảnh phóng nội bộ gấp 3 lần 1080×1920
# Xem nhanh phóng ×2 như reference 30 fps: zoompan làm tròn vị trí cắt về pixel nguyên của ảnh
# nguồn, không phóng thì hình rung (chốt 26/10/2026 theo số đo rung).
PREVIEW_INTERNAL_SCALE = (2160, 3840)
CARD_FADE = 0.35
OUTRO_FILE = "outro_4s_50fps.mp4"
OUTRO_FILE_60 = "outro_4s_60fps.mp4"  # dựng sẵn cho 60 fps: đổi 50→60 bằng `fps=` sẽ lặp khung


def outro_clip_for(fps: int, brand_dir: Path) -> Path:
    """Clip outro theo fps xuất: 60 fps dùng clip 60 (nếu có); 30 và 50 fps dùng clip 50."""
    if fps == 60 and (brand_dir / "outro" / OUTRO_FILE_60).is_file():
        return brand_dir / "outro" / OUTRO_FILE_60
    return brand_dir / "outro" / OUTRO_FILE


# Hash mã nguồn pipeline: đổi thuật toán thì mọi khoá cache trong build/ tự đổi theo.
PIPELINE_VERSION = cache.code_digest(
    _text,
    _align,
    _scene_align,
    audio,
    _captions,
    _visual,
    cache,
    _whisper,
    _whisper_worker,
    sys.modules[__name__],
)
ALIGN_START, ALIGN_END = 6.0, 20.0  # khung tiến độ của bước 3 (Căn chữ) trong mục 4
MAX_PARALLEL_CLIPS = 3
MAX_PREVIEW_SECONDS = 60  # giới hạn trên của `preview_seconds`

ProgressFn = Callable[[float, str, str], None]


def _sec(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


class RenderError(RuntimeError):
    """Lỗi dựng video có thông báo dành cho người dùng."""


@dataclass(frozen=True)
class Quality:
    preview: bool
    fps: int
    width: int
    height: int
    clip_preset: str
    clip_crf: int
    final_preset: str
    final_crf: int
    audio_bitrate: str


def quality_for(preview: bool, fps: int) -> Quality:
    if preview:  # Xem nhanh: 540×960, 30 fps
        return Quality(True, 30, 540, 960, "ultrafast", 23, "veryfast", 30, "96k")
    return Quality(False, fps, 1080, 1920, "veryfast", 12, "veryfast", 16, "192k")


@dataclass
class RenderOptions:
    preview: bool = False
    fps: int | None = None  # None → settings.fps của project
    outro: bool | None = None  # None → settings.outro của project
    allow_long_trim: bool = False  # cho phép cắt đuôi giọng > 8 s (đã được chủ dự án xác nhận)
    # Xem nhanh chỉ dựng chừng này giây đầu (căn chữ, điểm nhạc vẫn tính trên cả video).
    # None = cả video.
    preview_seconds: float | None = None
    sensitive_words: SensitiveWords | None = None  # None → không kiểm từ nhạy cảm
    library_dir: Path | None = None
    brand_dir: Path | None = None
    whisper_model: str | None = None  # model chọn trong Cài đặt (auto → .env → phần cứng)
    whisper_timeout: int | None = None  # giây; None → mặc định
    job_id: str | None = None  # tên thư mục renders/<job_id>; None → thời điểm dựng


@dataclass
class RenderResult:
    job_dir: Path
    video: Path
    srt: Path | None
    publish: Path
    log: Path
    fps: int
    width: int
    height: int
    duration: float
    lufs: float | None  # None ở bản Xem nhanh 10 s đầu (không đo)
    aligner: str
    seconds: float
    warnings: list[str] = field(default_factory=list)
    preview_seconds: float | None = None  # có giá trị khi chỉ dựng đoạn đầu
    cover: Path | None = None  # cover_9x16.jpg; None nếu không có khối thumbnail hoặc vẽ lỗi
    youtube_cover: Path | None = None  # youtube_3x2.jpg
    trimmed_tail: Path | None = (
        None  # trimmed_tail.wav: phần giọng đã cắt (4d.4); None nếu không cắt
    )
    trimmed_tail_seconds: float | None = None
    aligner_info: dict = field(default_factory=dict)  # model/thiết bị/tỉ lệ khớp/lý do rơi bậc


# ---------------------------------------------------------------- toán học chuyển động
def smoothstep(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def ease_in_out_cubic(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 4 * p * p * p if p < 0.5 else 1 - pow(-2 * p + 2, 3) / 2


def _smooth_expr(p: str) -> str:
    return f"(({p})*({p})*(3-2*({p})))"


def zoom_expr(index1: int, n: int, fps: int, punch: bool) -> tuple[str, float]:
    """Biểu thức `z` của zoompan và thời điểm thẻ chữ bắt đầu hiện. `index1`: số cảnh từ 1."""
    p = f"(on/{n})"
    if punch:  # cú lật: 1.18 → 1.00 trong 0,45 s (easeOutCubic) rồi 1.00 → 1.05 (smoothstep)
        k = int(0.45 * fps)
        q = f"(on/{k})"
        p2 = f"((on-{k})/{n - k})"
        return f"if(lt(on,{k}),1.18-0.18*(1-pow(1-{q},3)),1+0.05*{_smooth_expr(p2)})", 0.15
    if index1 % 2:  # cảnh lẻ phóng vào, cảnh chẵn lùi ra
        return f"1+0.08*{_smooth_expr(p)}", 0.3
    return f"1.08-0.08*{_smooth_expr(p)}", 0.3


def compute_offsets(first_start: list[float], last_end: list[float]) -> list[float]:
    """Mốc bắt đầu trượt của cảnh 2..n (bước 4): cut_k = giữa khoảng nghỉ giữa hai đoạn lời,
    offset = cut − X/2."""
    return [(last_end[k - 1] + first_start[k]) / 2 - X / 2 for k in range(1, len(first_start))]


def scene_offsets(times: list, scene_of: list[int], n_scenes: int) -> list[float]:
    """Mốc bắt đầu trượt của cảnh 2..n từ mốc thời gian từng token."""
    first_start, last_end = [0.0] * n_scenes, [0.0] * n_scenes
    for si in range(n_scenes):
        idx = [i for i, s in enumerate(scene_of) if s == si]
        first_start[si], last_end[si] = times[idx[0]][0], times[idx[-1]][1]
    return compute_offsets(first_start, last_end)


def offsets_valid(offsets: list[float]) -> bool:
    return (
        bool(offsets)
        and offsets[0] > 0
        and all(b > a for a, b in zip(offsets, offsets[1:], strict=False))
    )


def transition_frames(fps: int) -> int:
    """Số khung của một lần chuyển cảnh (0,4 s → 20 khung ở 50 fps)."""
    return int(round(X * fps))


def clip_durations(offsets: list[float], total: float) -> list[float]:
    o = offsets
    return [o[0] + X] + [o[k] - o[k - 1] + X for k in range(1, len(o))] + [total - o[-1]]


# ---------------------------------------------------------------- clip từng cảnh
def scene_clip(
    base_png: Path,
    card_png: Path,
    dur: float,
    index1: int,
    q: Quality,
    punch: bool,
    out: Path,
    keep_frames: int | None = None,
) -> int:
    """Một cảnh: ảnh nền phóng/thu chậm (zoompan) + thẻ chữ hiện dần. Trả về số khung.

    Luồng thẻ chữ được ép chạy cùng fps (`-framerate`); mặc định 25 fps làm `overlay=shortest=1`
    cắt mất khung cuối (clip 1,0 s ở 50 fps chỉ ra 49 khung).

    `keep_frames`: chỉ giữ chừng này khung đầu (bản Xem nhanh 10 s); chuyển động vẫn tính trên
    độ dài đầy đủ của cảnh nên các khung đầu giống hệt bản dựng cả video."""
    n = int(round(dur * q.fps))
    z, card_start = zoom_expr(index1, n, q.fps, punch)
    pan = (
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={n}:s={q.width}x{q.height}:fps={q.fps}"
    )
    fade = f"format=rgba,fade=in:st={card_start}:d={CARD_FADE}:alpha=1"
    sw, sh = PREVIEW_INTERNAL_SCALE if q.preview else INTERNAL_SCALE
    fc = f"[0]scale={sw}:{sh}:flags=lanczos,{pan}[bg];"
    fc += f"[1]scale={q.width}:{q.height},{fade}[t];" if q.preview else f"[1]{fade}[t];"
    fc += "[bg][t]overlay=shortest=1,format=yuv420p[out]"
    tmp = out.with_name(out.stem + ".tmp.mp4")
    run_ffmpeg([
        "-i", base_png, "-framerate", str(q.fps), "-loop", "1", "-t", f"{dur:.3f}", "-i", card_png,
        "-filter_complex", fc, "-map", "[out]", "-frames:v", str(keep_frames or n),
        "-r", str(q.fps),
        "-c:v", "libx264", "-preset", q.clip_preset, "-crf", str(q.clip_crf), tmp,
    ])  # fmt: skip
    cache.publish_atomic(tmp, out)
    return n


# ---------------------------------------------------------------- ghép bằng numpy
class FrameReader:
    """Đọc tuần tự các khung rgb24 từ một file video (qua ffmpeg)."""

    def __init__(self, path: Path, width: int, height: int, vf: str | None = None):
        self.fs = width * height * 3
        self.shape = (height, width, 3)
        cmd = [ffmpeg_exe(), "-v", "error", "-i", str(path)]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.fs * 2
        )
        self.token = cancel.current()
        if self.token is not None:
            self.token.track(self.proc)
        self.idx = -1
        self.frame: np.ndarray | None = None
        self.done = False

    def get(self, i: int) -> np.ndarray:
        while self.idx < i and not self.done:
            data = self.proc.stdout.read(self.fs)
            if len(data) < self.fs:
                self.done = True
                break
            self.frame = np.frombuffer(data, np.uint8).reshape(self.shape)
            self.idx += 1
        if self.done and self.token is not None:
            self.token.check()  # đọc cụt vì tiến trình bị kill do huỷ
        if self.frame is None:
            raise RenderError("Clip trung gian không có khung hình nào")
        return self.frame

    def close(self) -> None:
        if self.token is not None:
            self.token.untrack(self.proc)
        self.proc.stdout.close()
        self.proc.kill()
        self.proc.wait()


PARTIAL_UNLINK_TRIES = 5
PARTIAL_UNLINK_DELAY = 0.1  # giây giữa các lần thử


def _remove_partial(partial: Path) -> None:
    """Xoá file dở sau khi bộ mã hoá đã dừng. Trên Windows file có thể còn bị giữ một lúc
    (antivirus…): thử lại vài lần; vẫn lỗi thì chỉ cảnh báo, không che exception đang bay."""
    for attempt in range(PARTIAL_UNLINK_TRIES):
        try:
            partial.unlink(missing_ok=True)
            return
        except OSError as e:
            if attempt + 1 == PARTIAL_UNLINK_TRIES:
                print(f"CẢNH BÁO: không xoá được {partial.name}: {e}", file=sys.stderr)
            else:
                time.sleep(PARTIAL_UNLINK_DELAY)


def slide_frame(a: np.ndarray, b: np.ndarray, lb: int, tn: int) -> np.ndarray:
    """Khung chuyển cảnh `lb` (0..tn−1): A trượt sang trái, B vào từ phải, easeInOutCubic.

    Mỗi khung lấy SUBSAMPLES mẫu con trong nửa chu kỳ khung (màn trập 180°) rồi trung bình."""
    h, w, _ = a.shape
    acc = np.zeros(a.shape, np.float32)
    for s in range(SUBSAMPLES):
        sh = int(round(ease_in_out_cubic((lb + 0.5 * (s + 0.5) / SUBSAMPLES) / tn) * w))
        comp = np.empty_like(a)
        comp[:, : w - sh] = a[:, sh:]
        comp[:, w - sh :] = b[:, :sh]
        acc += comp
    return (acc / SUBSAMPLES).astype(np.uint8)


def compose(
    clips: list[Path],
    offsets: list[float],
    total: float,
    out_total: float,
    q: Quality,
    outro_clip: Path | None,
    captions_concat: Path,
    audio_wav: Path,
    out: Path,
    progress: Callable[[float], None] | None = None,
) -> None:
    """Ghép các clip cảnh (trượt + nhoè), nối outro bằng hoà trộn 0,5 s, phủ phụ đề, gắn tiếng."""
    w, h, fps = q.width, q.height, q.fps
    starts = [0.0, *offsets]
    n_frames = int(round(out_total * fps))
    tn = transition_frames(fps)
    overlap_start = total - audio.OUTRO_CROSSFADE
    readers: dict[int, FrameReader] = {}

    def reader(k: int) -> FrameReader:
        if k not in readers:
            readers[k] = FrameReader(clips[k], w, h)
        return readers[k]

    outro_reader = None
    if outro_clip is not None:
        vf = f"fps={fps},scale={w}:{h}:flags=lanczos"
        outro_reader = FrameReader(outro_clip, w, h, vf)

    def body(t: float) -> np.ndarray:
        j = bisect_right(starts, t + 1e-9) - 1
        if j >= 1 and t < starts[j] + X - 1e-9:
            a = reader(j - 1).get(int(round((t - starts[j - 1]) * fps)))
            lb = int(round((t - starts[j]) * fps))
            return slide_frame(a, reader(j).get(lb), lb, tn)
        if j >= 1 and (j - 1) in readers:
            readers.pop(j - 1).close()
        return reader(j).get(int(round((t - starts[j]) * fps)))

    partial = out.with_name(out.stem + ".part.mp4")  # chỉ đổi tên thành `out` khi mã hoá xong
    cap_fc = f"[1:v]fps={fps},"
    cap_fc += f"scale={w}:{h}," if w != 1080 else ""
    cap_fc += "format=rgba[cap];[0:v][cap]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]"
    cmd = [
        ffmpeg_exe(), "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-f", "concat", "-safe", "0", "-i", str(captions_concat), "-i", str(audio_wav),
        "-filter_complex", cap_fc, "-map", "[v]", "-map", "2:a", "-r", str(fps),
        "-c:v", "libx264", "-preset", q.final_preset, "-crf", str(q.final_crf),
        "-profile:v", "high", "-g", str(2 * fps),
        "-c:a", "aac", "-b:a", q.audio_bitrate,
        "-shortest", "-movflags", "+faststart", str(partial),
    ]  # fmt: skip
    err = tempfile.TemporaryFile()
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
    token = cancel.current()
    if token is not None:
        token.track(enc)
    finished = False
    try:
        for f in range(n_frames):
            cancel.check_current()
            t = f / fps
            if outro_reader is not None and t >= overlap_start - 1e-9:
                o = outro_reader.get(int(round((t - overlap_start) * fps)))
                if t < total - 1e-9:  # hoà trộn hình 0,5 s
                    alpha = (t - overlap_start) / audio.OUTRO_CROSSFADE
                    frame = (body(t).astype(np.float32) * (1 - alpha) + o * alpha).astype(np.uint8)
                else:
                    frame = o
            else:
                frame = body(t)
            enc.stdin.write(memoryview(np.ascontiguousarray(frame)))
            if progress and f % fps == 0:
                progress(f / n_frames)
        enc.stdin.close()
        finished = True
    except (BrokenPipeError, OSError):
        finished = True  # bộ mã hoá đã dừng; lỗi thật nằm ở stderr bên dưới
    finally:
        for r in readers.values():
            r.close()
        if outro_reader is not None:
            outro_reader.close()
        if not finished:  # bị huỷ hoặc lỗi giữa chừng: không để bộ mã hoá treo chờ dữ liệu
            enc.kill()
        # Luôn wait() để thu dọn tiến trình, kể cả khi nó bị kill lúc đang ghi (BrokenPipeError):
        # bỏ sót thì trên Linux nó thành zombie `[ffmpeg] <defunct>`.
        enc.wait()
        if token is not None:
            token.untrack(enc)
        if not finished:  # huỷ (check_current ném trong vòng ghi) hoặc lỗi giữa chừng
            _remove_partial(partial)
    try:
        cancel.check_current()  # bộ mã hoá chết vì bị huỷ thì không phải lỗi mã hoá
        code = enc.returncode
        if code != 0:
            err.seek(0)
            detail = err.read().decode("utf-8", errors="replace").strip()[-800:]
            raise RenderError(f"Bộ mã hoá lỗi (mã {code}):\n{detail}")
        cache.publish_atomic(partial, out)
    except BaseException:
        partial.unlink(missing_ok=True)  # không để lại video dang dở
        raise


# ---------------------------------------------------------------- ảnh bìa
def make_covers(project, project_dir: Path, out_dir: Path, brand_dir: Path) -> tuple[Path, Path]:
    """Vẽ `cover_9x16.jpg` và `youtube_3x2.jpg` từ `project.thumbnail` (mục 4e)."""
    thumb = project.thumbnail
    bg = project_dir / project.scenes[thumb.scene - 1].image
    image = render_cover(
        bg, thumb.lines, thumb.series or project.series, thumb.accent, brand_dir / LOGO_FILE
    )
    return save_covers(image, out_dir)


# ---------------------------------------------------------------- căn chữ
@dataclass
class Alignment:
    times: list
    aligner: str  # "whisper" | "silence"
    dropped: int  # số đoạn cuối bị bỏ (chỉ khoảng lặng)
    warning: str | None
    info: dict  # chi tiết ghi vào timing.json / meta.json (model, thiết bị, tỉ lệ khớp, lý do rơi)


def tokens_of(project) -> tuple[list, list[int]]:
    """Token của toàn bộ lời đọc và chỉ số cảnh của từng token."""
    tokens, scene_of = [], []
    for si, scene in enumerate(project.scenes):
        ts = parse_voice(scene.voice)
        tokens += ts
        scene_of += [si] * len(ts)
    return tokens, scene_of


def whisper_alignment(
    tokens, scene_of, wav, cfg: WhisperConfig, log, on_progress=None
) -> Alignment:
    """Căn bằng Whisper (tiến trình con). Lỗi thì ném WhisperFailed / RuntimeError."""
    # Không dùng initial_prompt (điểm lệch tham số reference đã duyệt 24/10/2026, IMPLEMENT 5.2):
    # đo trên "muỗi", prompt làm Whisper bỏ sót nửa đầu ở cả small, medium và large-v3.
    run = run_whisper(wav, "", cfg, log, on_progress=on_progress)
    m = match_script(tokens, run.syllables)
    n_scenes = max(scene_of) + 1 if scene_of else 0
    if n_scenes > 1 and not offsets_valid(scene_offsets(m.times, scene_of, n_scenes)):
        # Không phải ngưỡng chất lượng: mốc cảnh không dựng được thì dùng khoảng lặng thay vì lỗi
        raise WhisperFailed(
            f"mốc chuyển cảnh từ Whisper không hợp lệ (khớp {m.matched_ratio:.1%} âm tiết)".replace(
                ".", ","
            )
        )
    info = {
        **run.info(),
        "match_ratio": round(m.matched_ratio, 3),
        "last_token_matched": m.last_token_matched,
        "last_matched_end": m.last_matched_end,
        "heard_end": round(m.heard_end, 3),
    }
    log(
        f"Căn phụ đề bằng Whisper {run.step.label}: khớp {m.matched_ratio:.1%} âm tiết, "
        f"{run.seconds:.1f} giây".replace(".", ",")
    )
    return Alignment(m.times, "whisper", 0, None, info)


def run_alignment(
    tokens, scene_of, wav, total, method, cfg: WhisperConfig, log, on_progress=None
) -> Alignment:
    """Whisper (nếu method auto/whisper), lỗi hoặc quá giờ thì rơi về khoảng lặng kèm log lý do."""
    info: dict = {}
    if method in ("auto", "whisper"):
        try:
            return whisper_alignment(tokens, scene_of, wav, cfg, log, on_progress)
        except (WhisperFailed, RuntimeError, ImportError) as e:
            if method == "whisper":
                raise RenderError(f"Whisper không chạy được: {e}") from e
            info["whisper_error"] = str(e)
            log(f"Không dùng được Whisper ({e}), chuyển sang căn theo khoảng lặng")
    try:
        res = align_scenes(tokens, scene_of, wav, total)
    except AlignError as e:
        raise RenderError(str(e)) from e
    if res.refined_scenes:
        log("Hạ ngưỡng khoảng lặng ở cảnh " + ", ".join(str(k + 1) for k in res.refined_scenes))
    return Alignment(res.times, "silence", res.dropped, res.warning, info)


# ---------------------------------------------------------------- điều phối
class _Reporter:
    def __init__(self, log_path: Path, progress: ProgressFn | None):
        self.log_path = log_path
        self.progress = progress
        self.pct = 0.0
        self.step = ""
        self.t0 = time.time()
        self.lines: list[str] = []

    def at(self, pct: float, step: str) -> None:
        cancel.check_current()
        self.pct, self.step = pct, step
        self.say(f"== {step}", emit=False)
        if self.progress:
            self.progress(pct, step, "")

    def tick(self, pct: float) -> None:
        self.pct = pct
        if self.progress:
            self.progress(pct, self.step, "")

    def say(self, msg: str, emit: bool = True) -> None:
        line = f"[{time.time() - self.t0:7.1f}s] {msg}"
        self.lines.append(line)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if emit and self.progress:
            self.progress(self.pct, self.step, msg)


def render_project(
    project_dir: str | Path,
    options: RenderOptions | None = None,
    progress: ProgressFn | None = None,
    cancel_token: CancelToken | None = None,
) -> RenderResult:
    """Dựng video. `cancel_token.cancel()` (từ luồng khác) kill ffmpeg con, ném RenderCancelled."""
    with cancel.use_token(cancel_token):
        return _render_project(project_dir, options, progress)


def _render_project(
    project_dir: str | Path,
    options: RenderOptions | None,
    progress: ProgressFn | None,
) -> RenderResult:
    opts = options or RenderOptions()
    t_start = time.time()
    project_dir = Path(project_dir).resolve()
    settings = load_settings()
    library_dir = opts.library_dir or settings.library_dir
    brand_dir = opts.brand_dir or BRAND_DIR
    whisper_cfg = WhisperConfig(
        model=_whisper.effective_model(opts.whisper_model or "auto", settings.whisper_model),
        device=settings.whisper_device,
        timeout=opts.whisper_timeout or _whisper.DEFAULT_TIMEOUT,
        models_dir=settings.models_dir,
    )

    project = load_project(project_dir)  # lỗi đường dẫn/JSON thì dừng trước khi tạo thư mục nào
    job_id = opts.job_id or time.strftime("%Y%m%d-%H%M%S") + ("-preview" if opts.preview else "")
    job_dir = project_dir / "renders" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    rep = _Reporter(job_dir / "log.txt", progress)
    warnings: list[str] = []

    def warn(msg: str) -> None:
        warnings.append(msg)
        rep.say("CẢNH BÁO: " + msg)

    # ---- 1. Kiểm tra (0–3)
    rep.at(0, "Kiểm tra")
    fps = opts.fps or project.settings.fps
    if fps not in ALLOWED_FPS:
        raise RenderError(f"fps phải là một trong {ALLOWED_FPS}, nhận {fps}")
    q = quality_for(opts.preview, fps)
    use_outro = project.settings.outro if opts.outro is None else opts.outro
    if opts.preview and opts.fps:
        rep.say("Chế độ Xem nhanh luôn dùng 30 fps, bỏ qua --fps")
    if opts.preview_seconds is not None:
        if not opts.preview:
            raise RenderError("preview_seconds chỉ dùng với chế độ Xem nhanh")
        if not 0 < opts.preview_seconds <= MAX_PREVIEW_SECONDS:
            raise RenderError(f"preview_seconds phải trong (0, {MAX_PREVIEW_SECONDS}] giây")

    problems = project.render_problems()
    if problems:
        listing = "\n  - ".join(problems)
        raise RenderError(f"Project chưa đủ để dựng:\n  - {listing}")
    voice_src = project_dir / project.voice.file
    needed = [voice_src, *(project_dir / sc.image for sc in project.scenes)]
    music_src = None
    if project.music and project.music.file:
        music_src = project_dir / project.music.file
        needed.append(music_src)
    missing = [str(p) for p in needed if not p.is_file()]
    if missing:
        listing = "\n  ".join(missing)
        raise RenderError(f"Thiếu file:\n  {listing}")
    issues = lint_project(project, opts.sensitive_words)
    blocked = [describe_issue(i) for i in issues if i.level == "block"]
    if blocked:
        raise RenderError("Chặn xuất: " + "; ".join(blocked))
    for issue in issues:
        warn(issue.message) if issue.level == "warn" else rep.say(issue.message)
    build = project_dir / "build"
    for sub in ("layers", "clips", "captions"):
        (build / sub).mkdir(parents=True, exist_ok=True)
    rep.say(
        f"Dựng {'Xem nhanh' if opts.preview else 'bản đẹp'}: {q.width}x{q.height} @ {q.fps} fps, "
        f"{len(project.scenes)} cảnh, outro {'có' if use_outro else 'không'}"
    )

    # ---- 2. Chuẩn hoá giọng (3–6)
    rep.at(3, "Chuẩn hoá giọng")
    voice_wav = build / "voice.wav"
    key = cache.digest("prep", voice_src, PIPELINE_VERSION)
    if cache.is_fresh(voice_wav, key):
        rep.say("voice.wav: dùng bản đã có")
    else:
        audio.prep_voice(voice_src, voice_wav)
        cache.mark(voice_wav, key)
    prepped_total = media_duration(voice_wav)

    # voice.trim_end: người dùng tự chọn điểm cắt (giây của file gốc); cắt TRƯỚC khi căn chữ để
    # đoạn thừa không làm lệch căn (IMPLEMENT.md 4d.3)
    manual_trim = project.voice.trim_end
    voice_align = voice_wav
    manual_cut: tuple[float, float] | None = None
    if manual_trim is not None:
        voice_end = manual_trim + audio.VOICE_DELAY
        content_end = prepped_total - audio.TAIL
        if voice_end >= content_end:
            raise RenderError(
                f"voice.trim_end = {_sec(manual_trim)} giây nằm sau hết file giọng "
                f"({_sec(content_end - audio.VOICE_DELAY)} giây)"
            )
        manual_cut = (voice_end, content_end)
        voice_align = build / "voice_cut.wav"
        key = cache.digest("cut", voice_wav, round(voice_end, 3), PIPELINE_VERSION)
        if not cache.is_fresh(voice_align, key):
            audio.trim_voice_tail(voice_wav, voice_align, voice_end)
            cache.mark(voice_align, key)
        rep.say(
            f"Cắt đuôi giọng theo voice.trim_end = {_sec(manual_trim)} giây "
            f"(bỏ {_sec(content_end - voice_end)} giây)"
        )
        prepped_total = media_duration(voice_align)

    # ---- 3. Căn chữ (6–20)
    rep.at(6, "Căn chữ")
    tokens, scene_of = tokens_of(project)
    timing_path = build / "timing.json"
    key = cache.digest(
        "timing", voice_align, [t["disp"] for t in tokens], project.settings.aligner,
        whisper_cfg.key_parts(), PIPELINE_VERSION,
    )  # fmt: skip
    if cache.is_fresh(timing_path, key):
        data = json.loads(timing_path.read_text(encoding="utf-8"))
        alignment = Alignment(
            [tuple(x) for x in data["times"]],
            data["aligner"], data["dropped"], data["warning"], data["info"],
        )  # fmt: skip
        rep.say(f"Mốc thời gian chữ: dùng bản đã có (aligner: {alignment.aligner})")
    else:
        alignment = run_alignment(
            tokens, scene_of, str(voice_align), prepped_total, project.settings.aligner,
            whisper_cfg, rep.say, lambda f: rep.tick(ALIGN_START + (ALIGN_END - ALIGN_START) * f),
        )  # fmt: skip
        timing_path.write_text(
            json.dumps(
                {
                    "aligner": alignment.aligner,
                    "dropped": alignment.dropped,
                    "warning": alignment.warning,
                    "info": alignment.info,
                    "times": alignment.times,
                }  # fmt: skip
            ),
            encoding="utf-8",
        )
        cache.mark(timing_path, key)
    times, aligner, dropped = alignment.times, alignment.aligner, alignment.dropped
    if alignment.warning:
        warn(alignment.warning)
    rep.say(f"Aligner đã dùng: {aligner}" + (f" (bỏ {dropped} đoạn cuối)" if dropped else ""))

    # cắt đuôi giọng thừa (4d); đã cắt tay bằng voice.trim_end thì thôi
    trim, cut_span = None, manual_cut
    cut_path = job_dir / audio.CUT_PART_NAME
    try:
        if manual_trim is not None:
            voice_final = voice_align
        elif aligner == "whisper":
            voice_final, trim = audio.trim_tail_whisper(
                voice_wav, times[-1][1], alignment.info, build / "voice_trimmed.wav", rep.say,
                warn, allow_long=opts.allow_long_trim,
            )  # fmt: skip
        else:
            voice_final, trim = audio.trim_tail_if_needed(
                voice_wav, times[-1][1], build / "voice_trimmed.wav", rep.say,
                allow_long=opts.allow_long_trim,
            )  # fmt: skip
    except TailTrimNeedsConfirmation as e:
        if e.voice_end is not None and e.content_end is not None:
            e.cut_file = audio.save_cut_part(voice_wav, e.voice_end, e.content_end, cut_path)
        raise
    if trim is not None:
        cut_span = (trim.voice_end, trim.voice_end + trim.cut_seconds)
    trimmed_tail = None
    if cut_span is not None:  # lưu phần đã cắt để nghe lại (4d.4)
        trimmed_tail = audio.save_cut_part(voice_wav, cut_span[0], cut_span[1], cut_path)
    total = media_duration(voice_final)
    rep.say(f"Phần có lời dài {total:.2f} giây")

    # ---- 4. Mốc chuyển cảnh (20)
    rep.at(20, "Mốc chuyển cảnh")
    n_scenes = len(project.scenes)
    offsets = scene_offsets(times, scene_of, n_scenes)
    if not offsets_valid(offsets):
        raise RenderError("Mốc chuyển cảnh không hợp lệ: có cảnh quá ngắn so với lời đọc")
    durs = clip_durations(offsets, total)
    # Xem nhanh 10 s đầu: video ngắn hơn giới hạn thì dựng cả video như thường (có outro nếu bật)
    partial = (
        opts.preview_seconds if opts.preview_seconds and opts.preview_seconds < total else None
    )
    if partial:
        use_outro = False
    if min(durs) <= X:
        raise RenderError(f"Cảnh {durs.index(min(durs)) + 1} quá ngắn ({min(durs):.2f} giây)")
    rep.say("Mốc bắt đầu trượt: " + ", ".join(f"{o:.2f}" for o in offsets))
    starts = [0.0, *offsets]
    n_build = bisect_left(starts, partial) if partial else n_scenes  # cảnh bắt đầu trước giây T
    if partial:
        rep.say(f"Xem nhanh {partial:g} s đầu: dựng {n_build}/{n_scenes} cảnh, không outro")

    # ---- 5. Lớp hình (20–25)
    rep.at(20, "Lớp hình")
    theme = project.theme.model_dump()
    bottoms: list[int | None] = []
    for si, scene in enumerate(project.scenes):
        i = si + 1
        meta = build / "layers" / f"m{i}.json"
        key = cache.digest(
            "layers", project_dir / scene.image,
            scene.model_dump(exclude={"voice", "punch", "caption_y"}), theme, PIPELINE_VERSION,
        )  # fmt: skip
        b_png, t_png = build / "layers" / f"b{i}.png", build / "layers" / f"t{i}.png"
        if cache.is_fresh(meta, key) and b_png.exists() and t_png.exists():
            bottoms.append(json.loads(meta.read_text(encoding="utf-8"))["bottom"])
        else:
            _, bottom = build_scene_layers(
                scene.model_dump(), project_dir / scene.image, b_png, t_png, theme
            )
            meta.write_text(json.dumps({"bottom": bottom}), encoding="utf-8")
            cache.mark(meta, key)
            bottoms.append(bottom)
        rep.tick(20 + 5 * i / n_scenes)

    # ---- 6. Clip từng cảnh (25–70)
    rep.at(25, "Clip từng cảnh")
    clips: list[Path] = []
    todo: list[tuple[int, Path]] = []
    keep: dict[int, int | None] = {}
    for si, scene in enumerate(project.scenes[:n_build]):
        i = si + 1
        keep[si] = None
        if partial and si == n_build - 1:  # cảnh cuối của đoạn: chỉ giữ các khung trước giây T
            frames = int(math.ceil((partial - starts[si]) * q.fps)) + 2
            keep[si] = frames if frames < int(round(durs[si] * q.fps)) else None
        key = cache.digest(
            "clip", build / "layers" / f"b{i}.png", build / "layers" / f"t{i}.png",
            round(durs[si], 3), i % 2, scene.punch, q, PIPELINE_VERSION,
            *([keep[si]] if keep[si] else []),
        )  # fmt: skip
        clip = build / "clips" / f"c{i}-{key[:10]}.mp4"
        clips.append(clip)
        if clip.exists():
            continue
        todo.append((si, clip))
    if len(todo) < n_build:
        rep.say(f"Dùng lại {n_build - len(todo)} clip đã có")
    workers = max(1, min(MAX_PARALLEL_CLIPS, (os.cpu_count() or 2) // 2))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                scene_clip,
                build / "layers" / f"b{si + 1}.png",
                build / "layers" / f"t{si + 1}.png",
                durs[si], si + 1, q, project.scenes[si].punch, clip, keep[si],
            ): si
            for si, clip in todo
        }  # fmt: skip
        for fut in as_completed(futures):
            fut.result()
            done += 1
            rep.say(f"Cảnh {futures[fut] + 1} xong ({done}/{len(todo)})", emit=False)
            rep.tick(25 + 45 * done / max(len(todo), 1))

    # ---- 7. Âm thanh (70–75)
    rep.at(70, "Âm thanh")
    music_start = 0.0
    music_start_source = None  # "manual" | "auto"; ghi vào meta.json cho tab Âm thanh
    if music_src is not None:
        if project.music.start is not None:
            music_start, music_start_source = project.music.start, "manual"
            rep.say(f"Nhạc bắt đầu từ {music_start:.1f} s (đặt tay)")
        else:
            music_start = audio.pick_music_start(music_src, total)
            music_start_source = "auto"
            rep.say(f"Nhạc bắt đầu từ {music_start:.1f} s (tự chọn; chỉnh music.start nếu muốn)")
        music_len = media_duration(music_src)
        if music_start + total > music_len:
            warn(
                f"Nhạc ngắn hơn video: từ giây {music_start:.1f} chỉ còn "
                f"{max(music_len - music_start, 0.0):.1f} s, video cần {total:.1f} s"
            )
    sfx = []
    if project.settings.sfx_on_punch and any(s.punch for s in project.scenes):
        whoosh = build / "whoosh.wav"
        if not whoosh.exists():
            audio.synth_whoosh(whoosh)
        for si, scene in enumerate(project.scenes):
            if scene.punch:
                sfx.append((whoosh, 0.0 if si == 0 else offsets[si - 1], audio.WHOOSH_VOL))
    mix = build / "mix.wav"
    sfx_key = [(round(at, 3), vol) for _, at, vol in sfx]
    key = cache.digest(
        "mix", voice_final, music_src, music_start, round(total, 3), sfx_key, PIPELINE_VERSION
    )
    if not cache.is_fresh(mix, key):
        audio.mix_audio(voice_final, music_src, music_start, total, mix, build, sfx)
        cache.mark(mix, key)
    final_audio, out_total, outro_clip = mix, total, None
    if partial:  # giữ T giây đầu của bản trộn cả video, fade ra ngắn
        out_total = partial
        final_audio = build / "preview_audio.wav"
        audio.trim_with_fade(mix, partial, final_audio)
    elif use_outro:
        outro_clip = outro_clip_for(fps, brand_dir)
        if not outro_clip.is_file():
            raise RenderError(f"Thiếu clip outro: {outro_clip}")
        outro_voice = library_dir / "outro" / "voice.wav"
        if not outro_voice.is_file():
            warn(f"Không có {outro_voice}; outro chỉ có tiếng ting")
            outro_voice = None
        outro_audio = build / "outro_audio.wav"
        key = cache.digest("outro", outro_voice, PIPELINE_VERSION)
        if not cache.is_fresh(outro_audio, key):
            measured = audio.build_outro_audio(outro_voice, outro_audio, build)
            if measured is not None:
                rep.say(f"Outro: độ lớn thô {measured:.1f} LUFS → chỉnh về −14,0 LUFS")
            cache.mark(outro_audio, key)
        final_audio = build / "final_audio.wav"
        out_total = audio.join_audio(mix, outro_audio, final_audio)

    # ---- 8. Phụ đề (75–80)
    rep.at(75, "Phụ đề")
    caption_ys = [
        caption_y_for(sc.caption_y, bottom)
        for sc, bottom in zip(project.scenes, bottoms, strict=True)
    ]
    phrases = build_phrases(tokens, times, scene_of) if project.settings.captions else []
    timeline = render_states(phrases, caption_ys, build / "captions", out_total + 1.0)
    concat = build / "captions.ffconcat"
    write_ffconcat(timeline, concat)
    srt = None
    if phrases and not partial:  # bản 10 s đầu không kèm phụ đề .srt
        srt = job_dir / "captions.srt"
        write_srt(phrases, srt)
    rep.say(f"{len(phrases)} cụm phụ đề, {len(timeline)} trạng thái")

    # ---- 9. Ghép cuối (80–98)
    rep.at(80, "Ghép cuối")
    video = job_dir / "video.mp4"
    compose(
        clips, offsets, total, out_total, q, outro_clip, concat, final_audio, video,
        progress=lambda frac: rep.tick(80 + 18 * frac),
    )  # fmt: skip

    # ---- 10. Kiểm tra đầu ra (98–100)
    rep.at(98, "Kiểm tra đầu ra")
    info = probe(video)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    duration = float(info["format"]["duration"])
    if (int(vs["width"]), int(vs["height"])) != (q.width, q.height):
        raise RenderError(f"Kích thước đầu ra sai: {vs['width']}x{vs['height']}")
    if vs["r_frame_rate"] != f"{q.fps}/1":
        raise RenderError(f"fps đầu ra sai: {vs['r_frame_rate']} (cần {q.fps})")
    if not has_audio:
        raise RenderError("Video đầu ra không có tiếng")
    if abs(duration - out_total) > 0.25:
        raise RenderError(f"Độ dài đầu ra {duration:.2f} s lệch dự kiến {out_total:.2f} s")
    lufs = None  # bản 10 s đầu không đo độ lớn (đoạn cắt không đại diện cho cả video)
    if not partial:
        lufs = measure_lufs(video)
        if not -15.0 <= lufs <= -13.0:
            warn(f"Độ lớn tổng {lufs:.1f} LUFS nằm ngoài khoảng −15…−13")
    cover = youtube_cover = None
    if project.thumbnail and not partial:  # ảnh bìa đi cùng video (4e); bản 10 s đầu thì bỏ
        try:
            cover, youtube_cover = make_covers(project, project_dir, job_dir, brand_dir)
            rep.say(f"Ảnh bìa: {cover.name}, {youtube_cover.name}")
        except RenderCancelled:
            raise
        except Exception as e:  # noqa: BLE001 — lỗi vẽ bìa không làm hỏng video
            warn(f"Không vẽ được ảnh bìa: {e}")
    publish = job_dir / "publish.txt"
    publish.write_text(build_publish_text(project), encoding="utf-8")
    meta = {
        "job_id": job_id,
        "preview": q.preview,
        "fps": q.fps,
        "width": q.width,
        "height": q.height,
        "duration": round(duration, 3),
        "lufs": round(lufs, 2) if lufs is not None else None,
        "aligner": aligner,
        "aligner_info": alignment.info,
        "trimmed_tail": trimmed_tail.name if trimmed_tail else None,
        "trimmed_tail_seconds": round(cut_span[1] - cut_span[0], 3) if trimmed_tail else None,
        "music_start": round(music_start, 3) if music_src is not None else None,
        "music_start_source": music_start_source,
        "preview_seconds": partial,
        "cover_9x16": cover.name if cover else None,
        "youtube_3x2": youtube_cover.name if youtube_cover else None,
        "music_sha256": cache.sha256_file(music_src) if music_src is not None else None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    rep.at(100, "Xong")
    rep.say(
        f"Xong: {video} — {duration:.2f} s, {q.fps} fps, "
        f"{f'{lufs:.1f} LUFS, ' if lufs is not None else ''}"
        f"{video.stat().st_size / 1e6:.1f} MB, aligner {aligner}"
    )
    return RenderResult(
        job_dir=job_dir, video=video, srt=srt, publish=publish, log=job_dir / "log.txt",
        fps=q.fps, width=q.width, height=q.height, duration=duration, lufs=lufs,
        aligner=aligner, aligner_info=alignment.info, seconds=time.time() - t_start,
        warnings=warnings,
        preview_seconds=partial, cover=cover, youtube_cover=youtube_cover,
        trimmed_tail=trimmed_tail,
        trimmed_tail_seconds=(cut_span[1] - cut_span[0]) if trimmed_tail else None,
    )  # fmt: skip


__all__ = [
    "CancelToken",
    "Quality",
    "RenderCancelled",
    "RenderError",
    "RenderOptions",
    "RenderResult",
    "render_project",
]
