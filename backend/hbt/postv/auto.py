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
import math
import random
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

from hbt.pipeline.cancel import RenderCancelled
from hbt.pipeline.render import RenderOptions
from hbt.postv.audio import pick_default_bgm
from hbt.postv.auto_script import clean_voice_text
from hbt.postv.backgrounds import BackgroundLibrary
from hbt.postv.models import PostvComment, PostvPost, PostvProject, PostvSegment
from hbt.postv.parse import parse_threads_text
from hbt.postv.threads import (
    ThreadsFetchError,
    download_post_media,
    extract_threads_post,
    is_threads_url,
)
from hbt.postv.timeline import (
    DEFAULT_MEME_CUTIN_SEC,
    compute_time_budget,
    estimate_meme_pause_slots,
    estimate_tts_seconds,
)
from hbt.postv.voice import VoiceUnavailable, build_plan, synthesize_plan
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
            logger.setLevel(logging.DEBUG)
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
    extra: dict[str, Any] | None = None,
) -> None:
    """Phát sự kiện tiến trình SSE {stage, step, status, progress, message, [data]}."""
    pct = round(progress, 1)
    with job._lock:
        if hasattr(job, "last_heartbeat"):
            import time as _time

            job.last_heartbeat = _time.time()
        job.progress = pct
        job.step = stage
        payload: dict[str, Any] = {
            "stage": stage,
            "step": stage,
            "status": status,
            "progress": pct,
            "message": message,
        }
        if extra:
            payload.update(extra)
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
    finally:
        _set_jm_lock(job_manager, job.slug, voice=False, render=False)
        if not getattr(job, "finished", True):
            job._finish("failed", error="Tác vụ tự động kết thúc bất thường, đã mở khoá dự án.")


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
                msg = (
                    "[404] Bài viết Threads không tồn tại hoặc đã bị xoá. "
                    "Gợi ý: Dán chữ bài vào khung."
                )
            elif any(
                k in err_str.lower()
                for k in ["kết nối", "máy chủ", "timeout", "connect", "network"]
            ):
                msg = "[502] Không thể kết nối tới Threads. Gợi ý: Dán chữ bài vào khung."
            else:
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
                "[422] Không trích xuất được bài viết từ nội dung dán. "
                "Gợi ý: Dán chữ bài vào khung."
            )

    project = job_manager.storage.load_any(job.slug)
    if not isinstance(project, PostvProject):
        raise RuntimeError(f"'{job.slug}' không phải dự án PostV")

    pdir = job_manager.storage.project_dir(job.slug)
    media_dir = pdir / "media"
    raw_media_urls = list(
        getattr(parsed, "media_urls", []) or getattr(parsed.post, "media_urls", []) or []
    )
    saved_media_rel: list[str] = []
    if raw_media_urls:
        saved_files = download_post_media(raw_media_urls, media_dir, timeout=15.0, prefix="post")
        saved_media_rel = [f"media/{p.name}" for p in saved_files]

    project.source.url = parsed.source_url or (clean_input if is_threads_url(clean_input) else "")
    project.post = PostvPost(
        handle=parsed.post.handle,
        age=parsed.post.age,
        text=parsed.post.text,
        media=saved_media_rel,
        media_urls=raw_media_urls,
    )
    built_comments: list[PostvComment] = []
    for c in parsed.comments:
        c_urls = list(getattr(c, "media_urls", []) or [])
        c_media: list[str] = []
        if c_urls:
            c_files = download_post_media(c_urls, media_dir, timeout=15.0, prefix=c.id)
            c_media = [f"media/{p.name}" for p in c_files]
        built_comments.append(
            PostvComment(
                id=c.id,
                handle=c.handle,
                age=c.age,
                text=c.text,
                parent=c.parent,
                picked=True,
                likes=getattr(c, "likes", None),
                replies=getattr(c, "replies", None),
                media=c_media,
                media_urls=c_urls,
            )
        )
    project.comments = built_comments
    job_manager.storage.save_any(job.slug, project)

    fetch_msg = f"Đã tải bài viết của @{project.post.handle}"
    low_warn = None
    if not project.comments:
        low_warn = (
            "Bài viết gốc chưa cào được bình luận nào (< 10). "
            "Gợi ý: Copy cả trang bài (Ctrl+A) rồi dán vào đây để thêm bình luận."
        )
        fetch_msg += (
            " (chưa có bình luận. Gợi ý: Copy cả trang bài (Ctrl+A) "
            "rồi dán vào đây để thêm bình luận)"
        )
    else:
        fetch_msg += f" ({len(project.comments)} bình luận)"
        if len(project.comments) < LOW_COMMENTS_THRESHOLD:
            low_warn = (
                f"Bài viết gốc chỉ có {len(project.comments)} bình luận "
                f"(< {LOW_COMMENTS_THRESHOLD}), video có thể ngắn hơn mục tiêu."
            )

    debug_fetch = (
        f"[DEBUG] Fetch @{project.post.handle}: cào={len(project.comments)} "
        f"(cha={sum(1 for c in project.comments if not c.parent)}, "
        f"reply_con={sum(1 for c in project.comments if c.parent)})"
    )
    log.debug(debug_fetch)
    logger.info(debug_fetch)

    emit_stage_event(
        job,
        stage=STAGE_FETCH,
        status="done",
        progress=STAGE_PROGRESS[STAGE_FETCH],
        message=fetch_msg,
        data={"total_comments": len(project.comments), "low_comments_warning": low_warn},
        logger=logger,
    )


MIN_COMMENT_LENGTH = 8
MAX_AUTO_COMMENTS = 200
LOW_COMMENTS_THRESHOLD = 10
SPAM_COMMENT_RE = re.compile(
    r"(?:^|\b)(?:check\s+bio|link\s+(?:ở|trong|dưới)?\s*bio|ib\s+zalo|"
    r"tương\s+tác\s+chéo|follow\s+chéo|fl\s+chéo|mua\s+ngay\s+tại|shopee\.vn|lazada\.vn)(?:\b|$)"
    r"|^https?://\S+$"
    r"|^(?:@[A-Za-z0-9._]+\s*)+$",
    re.IGNORECASE,
)
HUMOR_CUE_RE = re.compile(
    r"(?:haha|hihi|kaka|huhu|cười|chết\s*cười|vãi|vcl|vl|ảo\s*thật|lú\s*luôn|"
    r"ét\s*ô\s*ét|chịu\s*luôn|toang|😂|🤣|💀|😭|🤡|🤯|🤬|😡|😱)",
    re.IGNORECASE,
)


def _is_spam_comment(text: str) -> bool:
    return bool(SPAM_COMMENT_RE.search(text.strip()))


def score_comment(comment: PostvComment, child_count: int = 0) -> float:
    """Chấm điểm bình luận theo tương tác (like/reply), độ dài có nghĩa và độ hài hước/cao trào."""
    likes = float(comment.likes or 0)
    replies = float(comment.replies or 0) + float(child_count)
    text = comment.text.strip()
    clean_len = len(re.sub(r"\s+", " ", text))

    # Tương tác cao luôn là tín hiệu hàng đầu nhưng không áp đảo hoàn toàn comment dài/hài hước
    like_score = math.log1p(max(likes, 0.0)) * 12.0 + min(likes, 5000.0) * 0.02
    reply_score = replies * 8.0
    length_bonus = min(max(clean_len - 12, 0), 220) * 0.08
    humor_hits = len(HUMOR_CUE_RE.findall(text))
    humor_bonus = min(humor_hits, 3) * 6.0
    punct_bonus = 2.0 if ("!" in text or "?" in text) else 0.0
    return like_score + reply_score + length_bonus + humor_bonus + punct_bonus


def inspect_comment_filter(
    comment: PostvComment,
    seen: set[str],
    censor_matchers: list[Any] | None = None,
) -> str | None:
    """Trả về lý do không đạt ('ngắn', 'trùng', 'từ nhạy cảm', 'rác'), None nếu hợp lệ."""
    raw = comment.text.strip()
    if len(raw) < MIN_COMMENT_LENGTH or not any(ch.isalnum() for ch in raw):
        return "ngắn"
    if _is_spam_comment(raw):
        return "rác"
    norm = re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw).casefold()).strip()
    if norm in seen:
        return "trùng"
    if censor_matchers:
        from hbt.postv.censor import find_censor_hits

        if find_censor_hits(raw, censor_matchers):
            return "từ nhạy cảm"
    seen.add(norm)
    return None


def _filter_comments(
    comments: list[PostvComment],
    censor_matchers: list[Any] | None = None,
) -> list[PostvComment]:
    """Lọc bình luận trước khi xếp hạng:
    - >= 8 ký tự (MIN_COMMENT_LENGTH)
    - không chỉ toàn emoji / ký hiệu (phải chứa ít nhất 1 chữ hoặc số)
    - không trùng lặp nội dung
    - không chứa từ mức chặn (censor block)
    """
    valid: list[PostvComment] = []
    seen: set[str] = set()

    for c in comments:
        reason = inspect_comment_filter(c, seen, censor_matchers)
        if reason is None:
            valid.append(c)

    return valid


def _has_meme_library(library_dir: Path | str | None) -> bool:
    if not isinstance(library_dir, (str, Path)):
        return False
    try:
        from hbt.postv.memes import MemeLibrary

        return bool(MemeLibrary(Path(library_dir)).scan_local())
    except Exception:
        return False


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

    target_seconds = float(options.get("target_seconds", 90))

    # Chuẩn bị bộ lọc từ mức chặn nếu có
    matchers = None
    if getattr(job_manager, "postv_words", None):
        try:
            from hbt.postv.censor import compile_censor

            words = job_manager.postv_words.load()
            if words:
                matchers = compile_censor(words, levels=("block",))
        except Exception:
            pass

    # Lọc bình luận theo quy tắc
    valid_comments = _filter_comments(project.comments, matchers)

    # Thuật toán Ngân sách thời gian: T_post + Sum(T_comments+T_replies) + Sum(T_memes)
    current_sec = estimate_tts_seconds(project.post.text)
    has_memes = _has_meme_library(getattr(job_manager, "library_dir", None))

    # Nhóm cấu trúc Threaded Tree: cha ở trên, reply con nổi bật bám ngay dưới cha
    valid_ids = {c.id for c in valid_comments}
    children_by_parent: dict[str, list[PostvComment]] = {}
    top_level: list[PostvComment] = []
    for c in valid_comments:
        if c.parent and c.parent in valid_ids:
            children_by_parent.setdefault(c.parent, []).append(c)
        else:
            top_level.append(c)

    for pid, kids in children_by_parent.items():
        children_by_parent[pid] = sorted(kids, key=lambda k: score_comment(k), reverse=True)

    sorted_roots = sorted(
        top_level,
        key=lambda c: (-score_comment(c, len(children_by_parent.get(c.id, []))), c.id),
    )

    picked_ordered: list[PostvComment] = []
    picked_ids: set[str] = set()
    explicit_max = options.get("max_comments")
    max_pick = int(explicit_max) if explicit_max is not None else MAX_AUTO_COMMENTS

    def _add_with_budget(item: PostvComment) -> None:
        nonlocal current_sec
        picked_ids.add(item.id)
        picked_ordered.append(item)
        current_sec += estimate_tts_seconds(item.text)
        # Ước tính phần cut-in meme (~3.0s) cho bình luận cao trào khi kho meme sẵn sàng
        if has_memes and item.parent is None and len(picked_ordered) % 3 == 1:
            current_sec += DEFAULT_MEME_CUTIN_SEC

    def _should_stop() -> bool:
        return len(picked_ids) >= max_pick or current_sec >= target_seconds

    for root in sorted_roots:
        if _should_stop():
            break
        _add_with_budget(root)

        # BẮT BUỘC bóc theo tối đa 2 reply con nổi bật lồng bên dưới comment cha đã chọn
        for kid in children_by_parent.get(root.id, [])[:2]:
            if len(picked_ids) >= max_pick:
                break
            _add_with_budget(kid)
            if current_sec >= target_seconds + 5.0:
                break

    pick_mode = options.get("pick_mode", "auto")
    if pick_mode == "auto" and picked_ordered:
        rest = [c for c in project.comments if c.id not in picked_ids]
        project.comments = picked_ordered + rest

    # Kiểm tra lý do lọc cho từng bình luận để UI hiển thị
    filter_seen: set[str] = set()
    all_comments_data = []
    for c in project.comments:
        reason = inspect_comment_filter(c, filter_seen, matchers)
        c.picked = c.id in picked_ids
        all_comments_data.append(
            {
                "id": c.id,
                "handle": c.handle,
                "age": c.age,
                "text": c.text,
                "likes": c.likes if c.likes is not None else 0,
                "replies": c.replies if c.replies is not None else 0,
                "parent": c.parent,
                "picked": c.picked,
                "filter_reason": reason,
            }
        )

    job_manager.storage.save_any(job.slug, project)

    est_meme_durs = [
        DEFAULT_MEME_CUTIN_SEC
        for idx, item in enumerate(picked_ordered, 1)
        if has_memes and item.parent is None and idx % 3 == 1
    ]
    budget = compute_time_budget(
        project.post.text,
        picked_ordered,
        est_meme_durs,
        target_seconds=target_seconds,
    )
    debug_pick = (
        f"[DEBUG] Pick ngân sách: cào={len(project.comments)} | "
        f"hợp_lệ={len(valid_comments)} | chọn={len(picked_ids)} | "
        f"T_post={budget.t_post:.2f}s | T_comments={budget.t_comments_replies:.2f}s | "
        f"T_memes={budget.t_memes:.2f}s | "
        f"tích_lũy={current_sec:.2f}s / mục_tiêu={target_seconds:.0f}s"
    )
    log.debug(debug_pick)
    logger.info(debug_pick)

    low_comments_warning = None
    if len(project.comments) < LOW_COMMENTS_THRESHOLD:
        low_comments_warning = (
            f"Bài viết gốc chỉ có {len(project.comments)} bình luận (< {LOW_COMMENTS_THRESHOLD}), "
            "video có thể ngắn hơn mục tiêu. "
            "Gợi ý: Trên Threads cuộn và bấm Xem thêm bình luận trước khi copy cả trang (Ctrl+A)."
        )

    data = {
        "handle": project.post.handle,
        "snippet": project.post.text[:120],
        "post_text": project.post.text,
        "comments": all_comments_data,
        "picked_count": len(picked_ids),
        "total_comments": len(project.comments),
        "target_seconds": target_seconds,
        "estimated_seconds": current_sec,
        "low_comments_warning": low_comments_warning,
    }

    if pick_mode == "manual":
        job._pick_event = threading.Event()
        job._waiting_pick_data = data
        with job._lock:
            job.status = "waiting_pick"
        emit_stage_event(
            job,
            stage=STAGE_PICK,
            status="waiting_pick",
            progress=STAGE_PROGRESS[STAGE_PICK],
            message="Đang chờ bạn chọn bình luận…",
            data=data,
            logger=logger,
        )
        # Chờ người dùng chọn bình luận và gửi POST /postv/auto/{job_id}/pick
        waited = job._pick_event.wait(timeout=1800.0)
        if job.token.cancelled:
            raise RenderCancelled()
        if not waited:
            raise RuntimeError("Hết thời gian chờ chọn bình luận (timeout 30 phút).")
        with job._lock:
            job.status = "running"
        project = job_manager.storage.load_any(job.slug)
    else:
        emit_stage_event(
            job,
            stage=STAGE_PICK,
            status="done",
            progress=STAGE_PROGRESS[STAGE_PICK],
            message=(
                f"Đã chọn {len(picked_ids)}/{len(project.comments)} "
                f"bình luận (ước tính ≈ {current_sec:.0f}s)"
            ),
            data=data,
            logger=logger,
        )


def _infer_meme_tag(text: str) -> str | None:
    low = text.lower()
    if any(k in low for k in ("haha", "hihi", "cười", "chết cười", "hài", "vãi", "vl", "vcl")):
        return "cuoi"
    if any(k in low for k in ("sốc", "ảo", "lú", "wtf", "ủa", "trời ơi", "thật sự", "!")):
        return "soc"
    if any(k in low for k in ("tức", "bực", "điên", "ghét", "cay", "phẫn nộ")):
        return "gian"
    if any(k in low for k in ("khóc", "huhu", "buồn", "thương", "tội")):
        return "khoc"
    if any(k in low for k in ("bất lực", "chịu", "toang", "hết cứu", "bó tay")):
        return "bat_luc"
    return None


def _assign_climax_memes(
    segments: list[PostvSegment],
    comments_by_id: dict[str, PostvComment],
    library_dir: Path | str | None,
) -> None:
    """Nạp toàn bộ kho meme cục bộ (library/memes/) vào vòng xoay tua Round-Robin Shuffle."""
    if not isinstance(library_dir, (str, Path)):
        return
    try:
        from hbt.postv.memes import RoundRobinMemePool
    except Exception:
        return

    pool = RoundRobinMemePool(library_dir)
    if pool.size == 0:
        return

    comment_segs = [(i, s) for i, s in enumerate(segments) if s.role == "comment" and s.ref]
    if not comment_segs:
        return

    # Ưu tiên các bình luận điểm cao / cao trào, cách nhau ít nhất 1 đoạn, xoay vòng toàn kho cục bộ
    ranked = sorted(
        comment_segs,
        key=lambda pair: (
            score_comment(comments_by_id[pair[1].ref]) if pair[1].ref in comments_by_id else 0.0
        ),
        reverse=True,
    )
    max_memes = max(1, min(12, (len(comment_segs) + 2) // 3))
    assigned_indices: set[int] = set()

    for seg_idx, seg in ranked:
        if len(assigned_indices) >= max_memes:
            break
        # Tránh gắn 2 meme liền kề nhau liên tiếp
        if (seg_idx - 1) in assigned_indices or (seg_idx + 1) in assigned_indices:
            continue
        comment = comments_by_id.get(seg.ref or "")
        text = comment.text if comment else seg.voice
        tag = _infer_meme_tag(text)
        chosen_path = pool.next_meme(preferred_emojis_text=text, preferred_tag=tag)
        if chosen_path is not None and chosen_path.is_file():
            seg.meme_id = chosen_path.name
            seg.meme_pos = "center"
            assigned_indices.add(seg_idx)


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
    project.publish.hook = hook_text
    project.hook.text = ""  # Không dùng màn hình Tiêu đề rời

    # Mở đầu video là Thẻ Bài Gốc hoàn chỉnh & TTS đọc thẳng nội dung bài gốc ngay từ giây 0
    post_voice = clean_voice_text(project.post.text) or project.post.text
    segments: list[PostvSegment] = [
        PostvSegment(role="post", card="post", voice=post_voice, speaker="post"),
    ]

    picked_comments = [c for c in project.comments if c.picked]
    for c in picked_comments:
        c_voice = clean_voice_text(c.text) or c.text
        segments.append(
            PostvSegment(role="comment", card="comment", voice=c_voice, ref=c.id, speaker=c.id)
        )

    comments_by_id = {c.id: c for c in picked_comments}
    _assign_climax_memes(segments, comments_by_id, getattr(job_manager, "library_dir", None))

    project.segments = segments

    # Giọng đọc: tuỳ chọn voice_id hoặc giọng nhớ gần nhất
    ws_dir = (
        job_manager.storage.workspace_dir
        if hasattr(job_manager.storage, "workspace_dir") and job_manager.storage.workspace_dir
        else None
    )
    chosen_voice = options.get("voice_id")
    if not chosen_voice and ws_dir:
        try:
            from hbt.postv.prefs import PostvPrefs

            chosen_voice = PostvPrefs(ws_dir).voice_id()
        except Exception:
            pass

    if not chosen_voice and ws_dir:
        try:
            from hbt.gd2.prefs import Gd2Prefs

            chosen_voice = Gd2Prefs(ws_dir).voice_id()
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
        if ws_dir:
            try:
                from hbt.postv.prefs import PostvPrefs

                PostvPrefs(ws_dir).set_voice_id(chosen_voice)
            except Exception:
                pass
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

    # Nhạc nền BGM: luôn ưu tiên quét từ library/music/ và chọn mặc định nếu chưa chọn tay
    music_opt = options.get("music", "auto")
    preferred_music = options.get("music_id")
    if music_opt == "none":
        project.music = None
    elif project.music is None or preferred_music:
        track = pick_default_bgm(
            getattr(job_manager, "library_dir", None),
            preferred_id=preferred_music if isinstance(preferred_music, str) else None,
        )
        if track and track.path.is_file():
            # Chép file BGM đầu vào thư mục project nếu có, giữ nguyên credit
            attached_file = track.file
            try:
                pdir = job_manager.storage.project_dir(job.slug)
                if pdir.is_dir():
                    import shutil

                    dst_name = f"music{track.path.suffix.lower()}"
                    shutil.copyfile(track.path, pdir / dst_name)
                    attached_file = dst_name
            except Exception:
                pass
            project.music = track.to_music(file_override=attached_file)

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


def _set_jm_lock(
    job_manager: Any, slug: str, *, voice: bool | None = None, render: bool | None = None
) -> None:
    lock = getattr(job_manager, "_lock", None)
    vmap = getattr(job_manager, "is_generating_voice", None)
    rmap = getattr(job_manager, "is_rendering", None)
    if not isinstance(vmap, dict) or not isinstance(rmap, dict):
        return
    if lock is not None:
        with lock:
            if voice is not None:
                vmap[slug] = voice
            if render is not None:
                rmap[slug] = render
    else:
        if voice is not None:
            vmap[slug] = voice
        if render is not None:
            rmap[slug] = render


def _step_voice(
    job_manager: Any, job: Any, options: dict[str, Any], logger: logging.Logger
) -> None:
    emit_stage_event(
        job,
        stage=STAGE_VOICE,
        status="running",
        progress=45.0,
        message="Đang chuẩn bị sinh giọng đọc VieNeu…",
        data={"step": "voice", "current": 0, "total": 1, "percent": 0},
        extra={"current": 0, "total": 1, "percent": 0},
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
    total_items = len(plan)

    def on_voice_detail(detail: dict[str, Any]) -> None:
        cur = int(detail.get("current", 0))
        tot = int(detail.get("total", max(total_items, 1)))
        vpct = int(detail.get("percent", 0))
        vmsg = str(detail.get("message") or f"Đang sinh giọng bình luận {cur}/{tot}...")
        emit_stage_event(
            job,
            stage=STAGE_VOICE,
            status="running",
            progress=45.0 + (vpct * 0.20),
            message=vmsg,
            data={"step": "voice", "current": cur, "total": tot, "percent": vpct, "message": vmsg},
            extra={"current": cur, "total": tot, "percent": vpct},
            logger=logger,
        )

    post_gaps = estimate_meme_pause_slots(
        [s for s in project.segments if s.voice.strip()],
        getattr(job_manager, "library_dir", None),
    )
    _set_jm_lock(job_manager, job.slug, voice=True)
    try:
        synthesize_plan(
            plan,
            pdir,
            job_manager.voice,
            cast,
            None,
            post_gaps=post_gaps,
            on_detail=on_voice_detail,
        )
    finally:
        _set_jm_lock(job_manager, job.slug, voice=False)

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
        message=f"Đã sinh xong {total_items}/{total_items} đoạn giọng đọc",
        data={
            "step": "voice",
            "current": total_items,
            "total": total_items,
            "percent": 100,
            "message": f"Đã sinh xong {total_items}/{total_items} đoạn giọng đọc",
        },
        extra={"current": total_items, "total": total_items, "percent": 100},
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

    picked_cnt = len([c for c in project.comments if c.picked])
    total_cnt = len(project.comments)
    target_sec = float(options.get("target_seconds", 90))
    duration_rounded = round(res.duration, 1)

    warning_msg = None
    if duration_rounded < target_sec - 5.0:
        warning_msg = (
            f"Thời lượng video ({duration_rounded:g}s) ngắn hơn mục tiêu "
            f"({target_sec:g}s) do bài viết có ít bình luận phù hợp. "
            "Gợi ý: Trên Threads cuộn và bấm Xem thêm bình luận trước khi copy cả trang."
        )
    elif total_cnt < LOW_COMMENTS_THRESHOLD:
        warning_msg = (
            f"Bài viết gốc chỉ có {total_cnt} bình luận (< {LOW_COMMENTS_THRESHOLD}). "
            "Gợi ý: Trên Threads cuộn và bấm Xem thêm bình luận trước khi copy cả trang."
        )

    output = {
        "video": _safe_rel(job_manager.storage, res.video),
        "cover": _safe_rel(job_manager.storage, res.cover),
        "youtube_cover": _safe_rel(job_manager.storage, res.youtube_cover),
        "publish": _safe_rel(job_manager.storage, res.publish),
        "log": _safe_rel(job_manager.storage, res.log),
        "duration": duration_rounded,
        "fps": res.fps,
        "project_slug": job.slug,
        "picked_comments": picked_cnt,
        "total_comments": total_cnt,
        "target_seconds": target_sec,
        "warning": warning_msg,
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
