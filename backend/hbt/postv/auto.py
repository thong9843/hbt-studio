"""HBT Studio - Tự động hoá PostV: Dán link/chữ -> Video (PV9).

Chuỗi 6 bước tự động:
1. fetch: Bóc tách bài viết từ URL Threads (hoặc dán chữ)
2. pick: Chọn bình luận theo like & thời lượng mục tiêu
3. script: Soạn kịch bản segments (hook -> post -> comments)
4. voice: Sinh giọng đọc VieNeu (có cache)
5. render: Dựng video bản đẹp (render_postv)
6. done: Trả đường dẫn video, ảnh bìa, publish.txt
"""

from __future__ import annotations

import logging
import random
import re
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hbt.library import MusicLibrary
from hbt.models import Music
from hbt.pipeline.cancel import CancelToken, RenderCancelled
from hbt.pipeline.render import RenderOptions
from hbt.postv.backgrounds import BackgroundLibrary
from hbt.postv.models import PostvComment, PostvHook, PostvPost, PostvProject, PostvSegment
from hbt.postv.parse import parse_threads_text
from hbt.postv.script import estimate_seconds, voice_chars
from hbt.postv.threads import ThreadsFetchError, extract_threads_post, is_threads_url
from hbt.postv.voice import VoiceError, VoiceUnavailable, build_plan, synthesize_plan
from hbt.storage import Storage

log = logging.getLogger(__name__)

STAGE_FETCH = "fetch"
STAGE_PICK = "pick"
STAGE_SCRIPT = "script"
STAGE_VOICE = "voice"
STAGE_RENDER = "render"
STAGE_DONE = "done"

STAGES = [STAGE_FETCH, STAGE_PICK, STAGE_SCRIPT, STAGE_VOICE, STAGE_RENDER, STAGE_DONE]

STAGE_PROGRESS = {
    STAGE_FETCH: 15.0,
    STAGE_PICK: 30.0,
    STAGE_SCRIPT: 45.0,
    STAGE_VOICE: 65.0,
    STAGE_RENDER: 95.0,
    STAGE_DONE: 100.0,
}


def _setup_auto_logger(workspace_dir: Path | None) -> logging.Logger:
    logger = logging.getLogger("hbt.postv.auto")
    if workspace_dir:
        log_file = workspace_dir / "logs" / "postv-auto.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Avoid duplicate handlers
        has_file_handler = any(
            isinstance(h, logging.FileHandler) and Path(h.baseFilename) == log_file.resolve()
            for h in logger.handlers
        )
        if not has_file_handler:
            fh = logging.FileHandler(str(log_file), encoding="utf-8")
            fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
            logger.addHandler(fh)
            logger.setLevel(logging.INFO)
    return logger


def find_existing_url(storage: Storage, url: str) -> str | None:
    """Tìm slug dự án PostV đã từng sử dụng URL này."""
    clean = url.strip()
    if not clean:
        return None
    for item in storage.list_projects():
        slug = item["slug"] if isinstance(item, dict) else getattr(item, "slug", "")
        kind = item.get("kind") if isinstance(item, dict) else getattr(item, "kind", "")
        if kind == "postv":
            try:
                proj = storage.load_any(slug)
                if isinstance(proj, PostvProject):
                    if proj.source.url and proj.source.url.strip() == clean:
                        return proj.slug
            except Exception:
                continue
    return None


def get_hook_text(text: str, max_len: int = 160) -> str:
    """Lấy câu đầu tiên của bài viết làm hook, tối đa 160 ký tự."""
    cleaned = unicodedata.normalize("NFC", text).strip()
    if not cleaned:
        return ""
    # Cắt theo ngắt câu hoặc dòng đầu
    parts = re.split(r"(?<=[.!?\n])\s+", cleaned)
    first = parts[0].strip() if parts else cleaned
    if len(first) <= max_len:
        return first
    truncated = first[:max_len].rsplit(" ", 1)[0]
    return truncated.strip() or first[:max_len]


def _safe_rel(storage: Any, path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return storage.rel(path)
    except Exception:
        return str(path)


def emit_stage_event(
    job: Any,
    stage: str,
    status: str,
    progress: float,
    message: str,
    data: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> None:
    """Phát sự kiện tiến trình SSE {stage, status, progress, message, [data]}."""
    pct = round(progress, 1)
    with job._lock:
        job.progress = pct
        job.step = stage
        payload: dict[str, Any] = {
            "stage": stage,
            "status": status,
            "progress": pct,
            "message": message,
        }
        if data:
            payload["data"] = data
        job._events.append(("progress", payload))
        if message:
            job._log.append(f"[{stage}] {message}")

    if logger:
        logger.info(f"[{job.id}] [{stage}] [{status}] ({pct}%) {message}")


def run_auto_job(job_manager: Any, job: Any) -> None:
    """Điều phối toàn bộ chuỗi 6 bước tự động của PostV (PV9)."""
    ws_dir = (
        job_manager.storage.workspace_dir if hasattr(job_manager.storage, "workspace_dir") else None
    )
    logger = _setup_auto_logger(ws_dir)
    logger.info(f"[{job.id}] Bắt đầu chuỗi tự động cho dự án '{job.slug}'")

    start_stage = getattr(job, "start_stage", STAGE_FETCH) or STAGE_FETCH
    options = getattr(job, "auto_options", {}) or {}
    raw_input = getattr(job, "auto_input", "") or ""

    start_idx = STAGES.index(start_stage) if start_stage in STAGES else 0

    try:
        # Bước 1: Fetch
        if start_idx <= STAGES.index(STAGE_FETCH):
            job.last_stage = STAGE_FETCH
            if job.token.cancelled:
                raise RenderCancelled()
            _step_fetch(job_manager, job, raw_input, logger)

        # Bước 2: Pick
        if start_idx <= STAGES.index(STAGE_PICK):
            job.last_stage = STAGE_PICK
            if job.token.cancelled:
                raise RenderCancelled()
            _step_pick(job_manager, job, options, logger)

        # Bước 3: Script
        if start_idx <= STAGES.index(STAGE_SCRIPT):
            job.last_stage = STAGE_SCRIPT
            if job.token.cancelled:
                raise RenderCancelled()
            _step_script(job_manager, job, options, logger)

        # Bước 4: Voice
        if start_idx <= STAGES.index(STAGE_VOICE):
            job.last_stage = STAGE_VOICE
            if job.token.cancelled:
                raise RenderCancelled()
            _step_voice(job_manager, job, options, logger)

        # Bước 5: Render
        if start_idx <= STAGES.index(STAGE_RENDER):
            job.last_stage = STAGE_RENDER
            if job.token.cancelled:
                raise RenderCancelled()
            output = _step_render(job_manager, job, options, logger)

        # Bước 6: Done
        job.last_stage = STAGE_DONE
        emit_stage_event(
            job,
            stage=STAGE_DONE,
            status="done",
            progress=100.0,
            message="Video đã hoàn thành!",
            data=output,
            logger=logger,
        )
        job._finish("done", output=output)
        logger.info(f"[{job.id}] Hoàn thành chuỗi tự động thành công cho '{job.slug}'")

    except RenderCancelled:
        logger.warning(f"[{job.id}] Job bị huỷ giữa chừng")
        job._finish("cancelled")
    except Exception as e:
        err_msg = str(e) or e.__class__.__name__
        logger.error(f"[{job.id}] Lỗi ở bước '{getattr(job, 'last_stage', 'unknown')}': {err_msg}")
        emit_stage_event(
            job,
            stage=getattr(job, "last_stage", "unknown"),
            status="failed",
            progress=job.progress,
            message=err_msg,
            logger=logger,
        )
        job._finish("failed", error=err_msg)


def _step_fetch(job_manager: Any, job: Any, raw_input: str, logger: logging.Logger) -> None:
    emit_stage_event(
        job,
        stage=STAGE_FETCH,
        status="running",
        progress=5.0,
        message="Đang tải dữ liệu bài viết…",
        logger=logger,
    )

    clean_input = raw_input.strip()
    if is_threads_url(clean_input):
        try:
            parsed = extract_threads_post(clean_input, timeout=15.0)
        except ThreadsFetchError as e:
            err_str = str(e)
            if "404" in err_str:
                code = 404
                msg = "[404] Bài viết Threads không tồn tại hoặc đã bị xoá. Gợi ý: Dán chữ bài vào khung."
            elif any(
                k in err_str.lower()
                for k in ["kết nối", "máy chủ", "timeout", "connect", "network"]
            ):
                code = 502
                msg = "[502] Không thể kết nối tới Threads. Gợi ý: Dán chữ bài vào khung."
            else:
                code = 422
                msg = f"[422] {err_str}. Gợi ý: Dán chữ bài vào khung."
            raise RuntimeError(msg) from e
        except Exception as e:
            raise RuntimeError(
                f"[502] Lỗi mạng khi kết nối Threads: {e}. Gợi ý: Dán chữ bài vào khung."
            ) from e
    else:
        parsed = parse_threads_text(clean_input)
        if not parsed.post or not parsed.post.text.strip():
            raise RuntimeError(
                "[422] Không trích xuất được bài viết từ nội dung dán. Gợi ý: Dán chữ bài vào khung."
            )

    project = job_manager.storage.load_any(job.slug)
    if not isinstance(project, PostvProject):
        raise RuntimeError(f"'{job.slug}' không phải dự án PostV")

    project.source.url = parsed.source_url or (clean_input if is_threads_url(clean_input) else "")
    project.post = PostvPost(
        handle=parsed.post.handle,
        age=parsed.post.age,
        text=parsed.post.text,
    )
    project.comments = [
        PostvComment(
            id=c.id,
            handle=c.handle,
            age=c.age,
            text=c.text,
            parent=c.parent,
            picked=True,
            likes=None,
        )
        for c in parsed.comments
    ]
    job_manager.storage.save_any(job.slug, project)
    emit_stage_event(
        job,
        stage=STAGE_FETCH,
        status="done",
        progress=STAGE_PROGRESS[STAGE_FETCH],
        message=f"Đã tải bài viết của @{project.post.handle}",
        logger=logger,
    )


def _step_pick(job_manager: Any, job: Any, options: dict[str, Any], logger: logging.Logger) -> None:
    emit_stage_event(
        job,
        stage=STAGE_PICK,
        status="running",
        progress=20.0,
        message="Đang chọn bình luận hay nhất…",
        logger=logger,
    )

    project = job_manager.storage.load_any(job.slug)
    if not isinstance(project, PostvProject):
        raise RuntimeError(f"'{job.slug}' không phải dự án PostV")

    target_seconds = float(options.get("target_seconds", 75))
    max_comments = int(options.get("max_comments", 5))

    hook_text = get_hook_text(project.post.text, max_len=160)
    current_chars = voice_chars(hook_text) + voice_chars(project.post.text)
    current_sec = estimate_seconds(current_chars)

    # Sắp xếp bình luận: nhiều like nhất, không có like thì theo thứ tự gốc
    indexed_comments = list(enumerate(project.comments))
    sorted_comments = sorted(
        indexed_comments,
        key=lambda pair: (-(pair[1].likes if pair[1].likes is not None else -1), pair[0]),
    )

    picked_ids: set[str] = set()
    for _, comment in sorted_comments:
        if len(picked_ids) >= max_comments:
            break
        picked_ids.add(comment.id)
        current_chars += voice_chars(comment.text)
        current_sec = estimate_seconds(current_chars)
        if current_sec >= target_seconds:
            break

    # Nếu chưa có bình luận nào được chọn nhưng có comments, lấy tối thiểu comment đầu
    if not picked_ids and project.comments:
        for c in project.comments[:max_comments]:
            picked_ids.add(c.id)
            current_chars += voice_chars(c.text)
        current_sec = estimate_seconds(current_chars)

    for c in project.comments:
        c.picked = c.id in picked_ids

    job_manager.storage.save_any(job.slug, project)

    data = {
        "handle": project.post.handle,
        "snippet": project.post.text[:120],
        "picked_count": len(picked_ids),
        "total_comments": len(project.comments),
        "target_seconds": target_seconds,
        "estimated_seconds": current_sec,
    }
    emit_stage_event(
        job,
        stage=STAGE_PICK,
        status="done",
        progress=STAGE_PROGRESS[STAGE_PICK],
        message=f"Đã chọn {len(picked_ids)} bình luận (ước tính ≈ {current_sec:.0f}s)",
        data=data,
        logger=logger,
    )


def _step_script(
    job_manager: Any, job: Any, options: dict[str, Any], logger: logging.Logger
) -> None:
    emit_stage_event(
        job,
        stage=STAGE_SCRIPT,
        status="running",
        progress=35.0,
        message="Đang tạo kịch bản và phân đoạn…",
        logger=logger,
    )

    project = job_manager.storage.load_any(job.slug)
    if not isinstance(project, PostvProject):
        raise RuntimeError(f"'{job.slug}' không phải dự án PostV")

    hook_text = get_hook_text(project.post.text, max_len=160)
    project.hook.text = hook_text

    segments: list[PostvSegment] = [
        PostvSegment(role="hook", card="hook", voice=hook_text, speaker="narrator"),
        PostvSegment(role="post", card="post", voice=project.post.text, speaker="post"),
    ]

    picked_comments = [c for c in project.comments if c.picked]
    for c in picked_comments:
        segments.append(
            PostvSegment(role="comment", card="comment", voice=c.text, ref=c.id, speaker=c.id)
        )

    project.segments = segments

    # Giọng đọc: tuỳ chọn voice_id hoặc giọng nhớ gần nhất
    chosen_voice = options.get("voice_id")
    if not chosen_voice:
        try:
            from hbt.api.gd2 import Gd2Prefs

            settings_dir = (
                job_manager.storage.workspace_dir / "settings"
                if hasattr(job_manager.storage, "workspace_dir")
                and job_manager.storage.workspace_dir
                else None
            )
            if settings_dir:
                chosen_voice = Gd2Prefs(settings_dir).voice_id()
        except Exception:
            pass

    if not chosen_voice and job_manager.voice is not None:
        try:
            voices = job_manager.voice.list_voices()
            if voices:
                chosen_voice = voices[0].id
        except Exception:
            pass

    if chosen_voice:
        project.voice.voice_id = chosen_voice
        all_speakers = ["narrator", "post", *[c.id for c in picked_comments]]
        project.voice.cast = {s: chosen_voice for s in all_speakers}

    # Clip nền: chế độ auto
    bg_mode = options.get("background", "auto")
    if bg_mode == "auto" and not project.background.clip_ids:
        bg_lib = BackgroundLibrary(job_manager.library_dir)
        bg_list = bg_lib.list()
        if bg_list:
            ids = [b.id for b in bg_list]
            random.shuffle(ids)
            project.background.clip_ids = ids[: min(3, len(ids))]

    # Nhạc nền: auto | none
    music_opt = options.get("music", "auto")
    if music_opt == "none":
        project.music = None
    elif music_opt == "auto" and project.music is None:
        music_lib = MusicLibrary(job_manager.library_dir)
        musics = music_lib.list()
        if musics:
            picked_m = random.choice(musics)
            project.music = Music(id=picked_m.id, file=picked_m.file, title=picked_m.title)

    # FPS và outro
    fps_val = options.get("fps", 60)
    if fps_val in (30, 50, 60):
        project.settings.fps = fps_val
    project.settings.outro = bool(options.get("outro", True))
    project.publish.hook = hook_text

    job_manager.storage.save_any(job.slug, project)

    emit_stage_event(
        job,
        stage=STAGE_SCRIPT,
        status="done",
        progress=STAGE_PROGRESS[STAGE_SCRIPT],
        message=f"Kịch bản gồm {len(segments)} đoạn",
        logger=logger,
    )


def _step_voice(
    job_manager: Any, job: Any, options: dict[str, Any], logger: logging.Logger
) -> None:
    emit_stage_event(
        job,
        stage=STAGE_VOICE,
        status="running",
        progress=50.0,
        message="Đang sinh giọng đọc VieNeu…",
        logger=logger,
    )

    if job_manager.voice is None:
        raise VoiceUnavailable("Chưa cấu hình bộ sinh giọng VieNeu")
    status = job_manager.voice.status()
    if not status.ok:
        raise VoiceUnavailable(f"VieNeu chưa sẵn sàng: {status.note}")

    project = job_manager.storage.load_any(job.slug)
    pdir = job_manager.storage.project_dir(job.slug)

    plan, cast = build_plan(project, job_manager.voice.list_voices())

    def on_voice_progress(pct: float, step: str, msg: str) -> None:
        emit_stage_event(
            job,
            stage=STAGE_VOICE,
            status="running",
            progress=45.0 + pct * 0.20,
            message=f"Sinh giọng: {msg}",
            logger=logger,
        )

    synthesize_plan(plan, pdir, job_manager.voice, cast, on_voice_progress)

    latest = job_manager.storage.load_any(job.slug)
    latest.voice = latest.voice.model_copy(
        update={"engine": "vieneu", "file": "voice.wav", "trim_end": None}
    )
    job_manager.storage.save_any(job.slug, latest)

    emit_stage_event(
        job,
        stage=STAGE_VOICE,
        status="done",
        progress=STAGE_PROGRESS[STAGE_VOICE],
        message="Đã sinh xong toàn bộ giọng đọc",
        logger=logger,
    )


def _step_render(
    job_manager: Any, job: Any, options: dict[str, Any], logger: logging.Logger
) -> dict[str, Any]:
    emit_stage_event(
        job,
        stage=STAGE_RENDER,
        status="running",
        progress=70.0,
        message="Đang căn chữ và dựng video bản đẹp…",
        logger=logger,
    )

    project = job_manager.storage.load_any(job.slug)
    pdir = job_manager.storage.project_dir(job.slug)

    cfg = job_manager.app_settings.load() if job_manager.app_settings else None
    opts = RenderOptions(
        preview=False,
        fps=project.settings.fps or 60,
        outro=project.settings.outro,
        library_dir=job_manager.library_dir,
        brand_dir=job_manager.brand_dir,
        whisper_model=cfg.whisper_model if cfg else None,
        whisper_timeout=cfg.whisper_timeout_seconds if cfg else None,
        job_id=job.id,
    )

    words = job_manager.postv_words.load() if job_manager.postv_words else None

    def on_render_progress(pct: float, step: str, msg: str) -> None:
        emit_stage_event(
            job,
            stage=STAGE_RENDER,
            status="running",
            progress=65.0 + pct * 0.30,
            message=f"Dựng video: {msg}",
            logger=logger,
        )

    res = job_manager._render_postv(
        pdir,
        opts,
        progress=on_render_progress,
        cancel_token=job.token,
        censor_words=words,
    )

    output = {
        "video": _safe_rel(job_manager.storage, res.video),
        "cover": _safe_rel(job_manager.storage, res.cover),
        "youtube_cover": _safe_rel(job_manager.storage, res.youtube_cover),
        "publish": _safe_rel(job_manager.storage, res.publish),
        "log": _safe_rel(job_manager.storage, res.log),
        "duration": round(res.duration, 3),
        "fps": res.fps,
        "project_slug": job.slug,
    }

    emit_stage_event(
        job,
        stage=STAGE_RENDER,
        status="done",
        progress=STAGE_PROGRESS[STAGE_RENDER],
        message="Đã dựng xong video!",
        data=output,
        logger=logger,
    )
    return output
