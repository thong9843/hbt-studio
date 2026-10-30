"""PostV: tách chữ dán, kiểm tra kịch bản, danh sách từ che (IMPLEMENT-POSTV.md mục 5)."""

from __future__ import annotations

import io
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Response
from PIL import Image
from pydantic import BaseModel, Field

from hbt.api.deps import State
from hbt.backups import create_backup, list_backups, read_backup, write_project_bytes
from hbt.config import BRAND_DIR
from hbt.models import Publish, Thumbnail
from hbt.pipeline.thumbnail import LOGO_FILE, render_cover
from hbt.postv.auto_script import load_script_styles
from hbt.postv.captions import BAND, render_state, style_for
from hbt.postv.card import composite_preview, load_template, render_project_card
from hbt.postv.censor import compile_censor
from hbt.postv.models import PostvHook, PostvProject, PostvSegment
from hbt.postv.parse import MAX_TEXT, ParseResult, parse_threads_text
from hbt.postv.script import check_script
from hbt.sensitive import SensitiveWords
from hbt.storage import BadRequest, Conflict, NotFound, StorageError, Unprocessable

router = APIRouter(tags=["postv"])


class ParseBody(BaseModel):
    text: str = Field(max_length=MAX_TEXT)


@router.post("/postv/parse", response_model=ParseResult)
def parse(body: ParseBody):
    """Hàm thuần: tách bài + bình luận từ chữ dán. Không ghi gì, không truy cập mạng."""
    if not body.text.strip():
        raise Unprocessable("Chưa có chữ để tách")
    return parse_threads_text(body.text)


@router.post("/projects/{slug}/postv/script/check")
def script_check(slug: str, state: State):
    """Ước thời lượng và nhắc từ nhạy cảm của dự án PostV (chỉ nhắc, không chặn)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    if state.jobs.is_busy(slug):
        raise Conflict("Dự án đang được dựng, hãy đợi xong rồi kiểm tra")
    hbt_words = state.sensitive.load()
    censor = compile_censor(hbt_words, state.postv_words.load())
    return check_script(project, censor, hbt_words)


@router.get("/settings/postv-words", response_model=SensitiveWords)
def get_postv_words(state: State):
    return state.postv_words.load()


@router.put("/settings/postv-words", response_model=SensitiveWords)
def put_postv_words(body: SensitiveWords, state: State):
    return state.postv_words.save(body)


def _preview_background(
    project: PostvProject, state: State, t: float | None = None
) -> Image.Image | None:
    """Khung nền để xem thẻ: clip đầu của dự án, không có thì của thư viện, không có thì None.

    Nếu `t` được truyền (giây t): trích khung bằng ffmpeg từ clip;
    nếu không có clip hoặc lỗi thì dùng thumb.
    """
    ids = project.background.clip_ids or [e.id for e in state.backgrounds.list()]
    for clip_id in ids:
        entry = state.backgrounds.get(clip_id)
        if entry is not None and t is not None and t >= 0:
            clip_path = state.backgrounds.root / entry.file
            if clip_path.is_file():
                cmd = [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    f"{t:.3f}",
                    "-i",
                    str(clip_path),
                    "-vframes",
                    "1",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "png",
                    "-",
                ]
                try:
                    res = subprocess.run(cmd, capture_output=True, check=True)
                    if res.stdout:
                        return Image.open(io.BytesIO(res.stdout)).copy()
                except Exception:
                    pass
        try:
            return Image.open(state.backgrounds.thumb_path(clip_id)).copy()
        except (StorageError, OSError):
            continue
    return None


@router.get("/projects/{slug}/postv/card.png")
def card_png(
    slug: str,
    state: State,
    kind: Literal["hook", "post", "comment"] = "post",
    ref: str | None = None,
    w: int | None = Query(default=None, ge=16, le=1080, description="chiều rộng thu nhỏ (px)"),
    layer: bool = Query(default=False, description="true: lớp thẻ trong suốt 1080×1920"),
) -> Response:
    """Thẻ bài vẽ bằng Pillow theo dữ liệu đã lưu: tiêu đề, bài gốc hoặc một bình luận (`ref`)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    cfg = project.settings.censor
    censor = (
        compile_censor(state.sensitive.load(), state.postv_words.load())
        if cfg.enabled and cfg.blur_card
        else None
    )
    tpl = load_template(project.template if project.template == "story_cards" else "story_cards")
    if kind == "comment":
        if ref is None:
            raise Unprocessable("Cần `ref` (id bình luận) cho thẻ bình luận")
        if not any(c.id == ref for c in project.comments):
            raise NotFound(f"Không có bình luận '{ref}'")
    image = render_project_card(project, kind, ref, tpl, censor, cfg.text)
    out = image if layer else composite_preview(image, _preview_background(project, state))
    if w and w < out.width:
        out = out.resize((w, round(out.height * w / out.width)), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})


def generate_bleep_wav(
    seconds: float = 0.35,
    sr: int = 44100,
    vol: float = 0.35,
    freq: float = 1000.0,
    fade: float = 0.005,
) -> bytes:
    """Tổng hợp tiếng bíp 1 kHz stereo PCM 16-bit fade 5 ms ở mức quy định (PV6)."""
    total_samples = int(sr * seconds)
    fade_samples = max(int(sr * fade), 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(total_samples):
            env = 1.0
            if i < fade_samples:
                env = i / fade_samples
            elif i > total_samples - fade_samples:
                env = (total_samples - i) / fade_samples
            val = math.sin(2 * math.pi * freq * (i / sr)) * vol * env
            sample = int(max(min(val, 1.0), -1.0) * 32767)
            frames.extend(struct.pack("<hh", sample, sample))
        wf.writeframes(frames)
    return buf.getvalue()


@router.get("/postv/bleep.wav")
def bleep_wav(
    seconds: float = Query(default=0.35, ge=0.05, le=2.0, description="độ dài tiếng bíp (giây)"),
) -> Response:
    """Tiếng bíp 1 kHz chuẩn 0,35 để nghe thử trước khi xuất (PV6)."""
    wav_bytes = generate_bleep_wav(seconds=seconds, vol=0.35)
    return Response(
        wav_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/projects/{slug}/postv/preview.png")
def postv_preview_png(
    slug: str,
    state: State,
    t: float | None = Query(default=None, description="mốc thời gian"),
    kind: Literal["hook", "post", "comment"] | None = Query(default=None),
    ref: str | None = Query(default=None),
    w: int | None = Query(default=None, ge=16, le=1080),
) -> Response:
    """Xem trước tĩnh 9:16: nền gameplay + thẻ bài + dải phụ đề mẫu (PV6)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")

    cfg = project.settings.censor
    censor = (
        compile_censor(state.sensitive.load(), state.postv_words.load())
        if cfg.enabled and cfg.blur_card
        else None
    )
    tpl = load_template(project.template if project.template == "story_cards" else "story_cards")

    # Chọn loại thẻ
    actual_kind: Literal["hook", "post", "comment"]
    if kind is not None:
        actual_kind = kind
    elif project.hook.text.strip():
        actual_kind = "hook"
    else:
        actual_kind = "post"

    if actual_kind == "comment":
        if ref is None:
            if project.comments:
                ref = project.comments[0].id
            else:
                actual_kind = "post"
        elif not any(c.id == ref for c in project.comments):
            raise NotFound(f"Không có bình luận '{ref}'")

    card_img = render_project_card(project, actual_kind, ref, tpl, censor, cfg.text)
    bg = _preview_background(project, state, t=t)
    out = composite_preview(card_img, bg)

    # Phụ đề mẫu (nếu bật captions)
    if project.settings.captions:
        sample_words: list[str] = []
        for s in project.segments:
            words = s.voice.strip().split()
            if words:
                sample_words = words[:3]
                break
        if not sample_words:
            if project.hook.text.strip():
                sample_words = project.hook.text.strip().split()[:3]
            else:
                sample_words = ["Hay", "Biết", "Tuốt"]

        style = style_for(project.style.caption.preset, project.style.caption.highlight_color)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            render_state(
                words=sample_words,
                act=0,
                masked=[False] * len(sample_words),
                style=style,
                mode=cfg.text,
                path=tmp_path,
            )
            with Image.open(tmp_path) as band_img:
                out_rgba = out.convert("RGBA")
                out_rgba.alpha_composite(band_img, (0, style.y - BAND // 2))
                out = out_rgba.convert("RGB")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    if w and w < out.width:
        out = out.resize((w, round(out.height * w / out.width)), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})


class DraftThumbnail(BaseModel):
    thumbnail: Thumbnail | None = None


@router.post("/projects/{slug}/postv/thumbnail/preview.jpg")
def draft_postv_thumbnail_preview(
    slug: str,
    body: DraftThumbnail,
    state: State,
    w: int | None = Query(default=None, ge=16, le=1080),
) -> Response:
    """Xem trước ảnh bìa PostV (ảnh tải lên hoặc khung gameplay) (PV6)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")

    thumb = body.thumbnail or project.thumbnail
    if thumb is None:
        raise Unprocessable("Project chưa có khối thumbnail (ảnh bìa)")

    project_dir = state.storage.project_dir(slug)
    tmp_bg: Path | None = None

    if thumb.image:
        source = project_dir / thumb.image
        if not source.is_file():
            raise Unprocessable(f"Thiếu ảnh bìa {thumb.image}")
        fit = True
    else:
        fit = True
        clip_source: Path | None = None
        ids = project.background.clip_ids or [e.id for e in state.backgrounds.list()]
        for cid in ids:
            try:
                clip_source = state.backgrounds.thumb_path(cid)
                break
            except (StorageError, OSError):
                continue
        if clip_source and clip_source.is_file():
            source = clip_source
        else:
            tmp_dir = project_dir / "build"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_bg = tmp_dir / "gameplay_placeholder_cover.jpg"
            img = Image.new("RGB", (1080, 1920), (35, 42, 54))
            img.save(tmp_bg, format="JPEG", quality=90)
            source = tmp_bg

    logo = state.brand_dir / LOGO_FILE
    if not logo.is_file():
        logo = BRAND_DIR / LOGO_FILE

    try:
        cover = render_cover(
            source,
            thumb.lines,
            thumb.series or project.series,
            thumb.accent,
            logo,
            fit_background=fit,
        )
    except OSError as e:
        raise Unprocessable(f"Không vẽ được ảnh bìa: {e}") from e
    finally:
        if tmp_bg and tmp_bg.exists():
            try:
                tmp_bg.unlink()
            except OSError:
                pass

    if w and w < cover.width:
        cover = cover.resize((w, round(cover.height * w / cover.width)), Image.LANCZOS)
    buf = io.BytesIO()
    cover.save(buf, format="JPEG", quality=90)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


# ===================================================================== PVA (Tự động)
@router.get("/postv/styles")
def get_postv_styles(state: State):
    """Danh sách 5 phong cách kịch bản cho chip chọn (PVA)."""
    settings_dir = state.storage.workspace_dir / "settings" if state.storage.workspace_dir else None
    return [s.view() for s in load_script_styles(settings_dir)]


class AutoBody(BaseModel):
    style: str = "ke-chuyen"
    comments: int = Field(default=3, ge=2, le=5)
    voices: Literal["random", "manual"] = "random"
    seed: int | None = None


@router.post("/projects/{slug}/postv/auto", status_code=202)
def start_postv_auto(slug: str, body: AutoBody, state: State):
    """Bắt đầu chuỗi 7 pha tự động, dừng ở Xem nhanh 10 s (PVA)."""
    job = state.jobs.submit_postv_auto(
        slug,
        style=body.style,
        comments=body.comments,
        voices=body.voices,
        seed=body.seed,
    )
    return {"job_id": job.id}


class ScriptJsonCheckResult(BaseModel):
    ok: bool
    issues: list[str] = []
    warnings: list[str] = []
    segments_count: int = 0


def _validate_postv_script_json(
    body: dict, project: PostvProject, state: State
) -> tuple[list[str], list[str]]:
    """Kiểm tra tính hợp lệ của JSON kịch bản PostV (PVA)."""
    issues: list[str] = []
    warnings: list[str] = []

    if not isinstance(body, dict):
        return ["Dữ liệu phải là JSON object"], []

    if body.get("postv_script") != 1:
        issues.append("Trường `postv_script` phải có giá trị là 1")

    allowed_keys = {"postv_script", "style", "hook", "segments", "cast", "publish"}
    for k in body:
        if k not in allowed_keys:
            issues.append(f"Trường lạ không được phép: '{k}'")

    segments = body.get("segments")
    if not isinstance(segments, list) or len(segments) < 2 or len(segments) > 40:
        issues.append("Cần danh sách `segments` từ 2 đến 40 đoạn")
        return issues, warnings

    known_comments = {c.id for c in project.comments}
    allowed_speakers = {"narrator", "post", *known_comments}

    voices_known: set[str] = set()
    if state.voice is not None:
        try:
            voices_known = {v.id for v in state.voice.list_voices()}
        except Exception:
            pass

    for i, s in enumerate(segments, 1):
        if not isinstance(s, dict):
            issues.append(f"Đoạn {i} không hợp lệ")
            continue
        role = s.get("role")
        if role not in ("hook", "post", "comment", "commentary"):
            issues.append(f"Đoạn {i} có role không hợp lệ: '{role}'")
        if role == "comment":
            ref = s.get("ref")
            if not ref or ref not in known_comments:
                issues.append(f"Đoạn {i} trỏ tới bình luận không có trong bài: '{ref}'")
        speaker = s.get("speaker")
        if speaker and speaker not in allowed_speakers:
            issues.append(f"Đoạn {i} có người đọc không hợp lệ: '{speaker}'")
        voice_text = str(s.get("voice", ""))
        if any(ch in voice_text for ch in ("{", "}", "|")):
            warnings.append(f"Đoạn {i} chứa ký tự đặc biệt ({'{'}, {'}'}, |), PostV đọc nguyên văn")

    cast = body.get("cast")
    if isinstance(cast, dict):
        for who, vid in cast.items():
            if who not in allowed_speakers:
                issues.append(f"Gán giọng cho người không có: '{who}'")
            if voices_known and vid not in voices_known:
                issues.append(f"Giọng '{vid}' không có trong danh sách giọng")

    return issues, warnings


@router.post("/projects/{slug}/postv/script-json/check", response_model=ScriptJsonCheckResult)
def check_postv_script_json(slug: str, body: dict, state: State):
    """Kiểm tra JSON kịch bản trước khi áp (không ghi gì) (PVA)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    issues, warnings = _validate_postv_script_json(body, project, state)
    segments = body.get("segments") if isinstance(body, dict) else []
    return ScriptJsonCheckResult(
        ok=len(issues) == 0,
        issues=issues,
        warnings=warnings,
        segments_count=len(segments) if isinstance(segments, list) else 0,
    )


@router.post("/projects/{slug}/postv/script-json/apply")
def apply_postv_script_json(slug: str, body: dict, state: State):
    """Áp dụng JSON kịch bản: tự động sao lưu, giữ tối đa 10 bản (PVA)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    if state.jobs.is_busy(slug):
        raise Conflict("Dự án đang bận (đang dựng hoặc sinh giọng), hãy đợi hoặc huỷ job")

    issues, _ = _validate_postv_script_json(body, project, state)
    if issues:
        raise Unprocessable("; ".join(issues))

    pdir = state.storage.project_dir(slug)
    backup_id = create_backup(pdir, reason="apply")

    if "hook" in body and isinstance(body["hook"], dict):
        project.hook = PostvHook(**body["hook"])
    if "segments" in body and isinstance(body["segments"], list):
        project.segments = [PostvSegment(**s) for s in body["segments"]]
    if "cast" in body and isinstance(body["cast"], dict):
        project.voice.cast = {str(k): str(v) for k, v in body["cast"].items()}
    if "publish" in body and isinstance(body["publish"], dict):
        project.publish = Publish(**body["publish"])

    state.storage.save_any(slug, project)
    return {"ok": True, "backup_id": backup_id, "project": project.model_dump(mode="json")}


@router.get("/projects/{slug}/postv/backups")
def get_postv_backups(slug: str, state: State):
    """Danh sách các bản sao lưu kịch bản của dự án PostV."""
    pdir = state.storage.project_dir(slug)
    return list_backups(pdir)


@router.post("/projects/{slug}/postv/backups/{backup_id}/restore")
def restore_postv_backup(slug: str, backup_id: str, state: State):
    """Khôi phục bản sao lưu kịch bản PostV (tự động tạo bản sao lưu trước khi khôi phục)."""
    if state.jobs.is_busy(slug):
        raise Conflict("Dự án đang bận, hãy đợi hoặc huỷ job")
    pdir = state.storage.project_dir(slug)
    raw = read_backup(pdir, backup_id)
    create_backup(pdir, reason="restore")
    write_project_bytes(pdir, raw)
    restored = state.storage.load_any(slug)
    return {"ok": True, "restored_id": backup_id, "project": restored.model_dump(mode="json")}


# ===================================================================== Gỡ Voice / Music
@router.delete("/projects/{slug}/postv/assets/voice", status_code=204)
def delete_postv_voice_asset(slug: str, state: State) -> None:
    """Gỡ file giọng đã nạp/sinh (xoá file + bỏ tham chiếu) (PVA)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    if state.jobs.is_busy(slug):
        raise Conflict("Dự án đang bận, hãy đợi hoặc huỷ job")
    if project.voice.file:
        pdir = state.storage.project_dir(slug)
        fpath = pdir / project.voice.file
        try:
            if fpath.is_file():
                fpath.unlink()
        except OSError:
            pass
        project.voice.file = None
        project.voice.engine = "vieneu"
        project.voice.trim_end = None
        state.storage.save_any(slug, project)


@router.delete("/projects/{slug}/postv/assets/music", status_code=204)
def delete_postv_music_asset(slug: str, state: State) -> None:
    """Gỡ nhạc nền đã chọn/nạp (xoá file trong project nếu có + bỏ tham chiếu) (PVA)."""
    project = state.storage.load_any(slug)
    if not isinstance(project, PostvProject):
        raise BadRequest(f"'{slug}' không phải dự án PostV")
    if state.jobs.is_busy(slug):
        raise Conflict("Dự án đang bận, hãy đợi hoặc huỷ job")
    if project.music is not None:
        if project.music.file:
            pdir = state.storage.project_dir(slug)
            mf = pdir / project.music.file
            try:
                if mf.is_file():
                    mf.unlink()
            except OSError:
                pass
        project.music = None
        state.storage.save_any(slug, project)
