"""Pipeline dựng video tự động cho HBT Core (Chế độ V1 & V2).

Đảm bảo thực thi đầy đủ Nhiệm vụ 1:
1. Giọng đọc tự động VieNeu-TTS (.venv-tts, HF_HUB_OFFLINE=1), tính mốc micro-giây chính xác và bắn
   sự kiện tiến trình SSE `{step: "voice", current, total, percent}`.
2. Nhạc nền BGM thông minh: quét `library/music/` theo `topic` (history / fun / science / mystery)
   và nối dài bằng bộ lọc FFmpeg `acrossfade=d=2.0`.
3. Âm thanh hiệu ứng SFX & Sticker: quét `library/sfx/` (whoosh, pop) chèn vào các điểm chuyển cảnh.
4. Kẹp chuẩn tài nguyên CPU & Chống rò rỉ RAM:
   - Áp dụng triệt để: `-threads 2`, `-filter_threads 2`, `-preset veryfast`, `-crf 22`,
     `-max_muxing_queue_size 512`.
   - Quản lý bộ nhớ ảnh Pillow bằng context manager (`with Image.open(...)`) / `.close()` tường minh
     và gọi `gc.collect()` sau mỗi phân đoạn.
"""

from __future__ import annotations

import gc
import json
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from hbt.config import BRAND_DIR, REPO_ROOT, load_settings
from hbt.core.audio import (
    build_topic_bgm_playlist,
    prepare_core_sfx_clip,
    render_smart_bgm_wav,
    resolve_sfx_file,
)
from hbt.core.models import HbtCoreScript, SegmentVoiceTiming, infer_music_topic
from hbt.core.tts_pipeline import sync_wavs_to_audio_folder
from hbt.core.voice import synthesize_core_segments
from hbt.models import Card, CardLine, Music, Project, Scene, Voice
from hbt.pipeline import cache, cancel
from hbt.pipeline.ffutil import media_duration, probe, run_ffmpeg
from hbt.pipeline.publish import build_publish_text
from hbt.pipeline.visual import CARD_Y, CREAM, SIZES, H, W, color_of, font
from hbt.postv.voice import VoiceProvider
from hbt.shared.ffmpeg_utils import FFMPEG_ENCODE_CLAMP, FFMPEG_RESOURCE_CLAMP
from hbt.shared.pipeline.aspect import AspectMode, build_aspect_filter
from hbt.shared.sse_manager import SSEProgressEmitter

logger = logging.getLogger(__name__)


@dataclass
class CoreRenderResult:
    """Kết quả xuất video của HBT Core."""

    job_dir: Path
    video: Path
    publish: Path
    log: Path
    fps: int
    width: int
    height: int
    duration: float
    seconds: float
    timings: list[SegmentVoiceTiming] = field(default_factory=list)
    bgm_tracks: list[str] = field(default_factory=list)
    sfx_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


TOPIC_SERIES_LABELS: dict[str, str] = {
    "history": "Vì Sao Lịch Sử",
    "fun": "Vì Sao Thú Vị",
    "science": "Vì Sao Khoa Học",
    "mystery": "Vì Sao Bí Ẩn",
}

TOPIC_BG_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "history": ((62, 42, 28), (120, 82, 48)),
    "fun": ((38, 65, 112), (82, 130, 195)),
    "science": ((24, 58, 74), (46, 118, 138)),
    "mystery": ((36, 26, 58), (78, 52, 112)),
}


def auto_card_headline(text: str, max_words: int = 8) -> str:
    """Tạo dòng chữ tiêu đề ngắn trên thẻ kem từ lời thoại phân đoạn."""
    clean = (text or "").replace("|", " ").strip()
    import re

    clean = re.sub(r"\{[^}]*\}", "", clean)
    words = [w for w in clean.split() if w]
    if not words:
        return "HBT Studio"
    first_clause = re.split(r"[.!?;:—–]", " ".join(words))[0].strip()
    clause_words = first_clause.split()
    if 2 <= len(clause_words) <= max_words:
        return first_clause
    snippet = " ".join(words[:max_words])
    return snippet + ("…" if len(words) > max_words else "")


def resolve_segment_image(
    project_dir: Path,
    image_ref: str,
    segment_order: int,
    topic: str = "science",
    title: str = "",
) -> str:
    """Tìm ảnh có sẵn trong project hoặc kho cục bộ; nếu chưa có thì vẽ ảnh minh họa cục bộ
    vào `project_dir / images/` (quản lý bộ nhớ bằng `.close()`). Trả về `images/...`.
    """
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    ref = (image_ref or "").strip()
    if ref:
        # 1. Đường dẫn tương đối trong project_dir
        cand1 = project_dir / ref
        if cand1.is_file():
            if cand1.parent == images_dir:
                return f"images/{cand1.name}"
            dest = images_dir / cand1.name
            if not dest.is_file():
                shutil.copy2(cand1, dest)
            return f"images/{dest.name}"

        # 2. Tìm theo tên file trong project_dir/images
        cand2 = images_dir / Path(ref).name
        if cand2.is_file():
            return f"images/{cand2.name}"

        # 3. Đường dẫn tuyệt đối hoặc trong workspace/library cục bộ
        cand3 = Path(ref)
        if cand3.is_file():
            dest = images_dir / cand3.name
            if not dest.is_file():
                shutil.copy2(cand3, dest)
            return f"images/{dest.name}"

        for search_dir in (
            REPO_ROOT / "library" / "images",
            REPO_ROOT / "brand",
        ):
            if search_dir.is_dir():
                cand_lib = search_dir / Path(ref).name
                if cand_lib.is_file():
                    dest = images_dir / cand_lib.name
                    if not dest.is_file():
                        shutil.copy2(cand_lib, dest)
                    return f"images/{dest.name}"

    # 4. Nếu trong project_dir/images đã có sẵn ảnh theo thứ tự thì tái sử dụng
    existing_imgs = sorted(
        f
        for f in images_dir.iterdir()
        if f.is_file()
        and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        and not f.name.startswith("cover.")
    )
    if existing_imgs and segment_order <= len(existing_imgs) and not ref:
        return f"images/{existing_imgs[segment_order - 1].name}"

    # 5. Sinh ảnh nền minh họa cục bộ 1080x1920 theo chủ đề (Offline 100%, không dùng ComfyUI)
    fallback_name = f"scene-{segment_order:02d}.png"
    fallback_path = images_dir / fallback_name
    if not fallback_path.is_file():
        top_rgb, bot_rgb = TOPIC_BG_PALETTES.get(topic, TOPIC_BG_PALETTES["science"])
        canvas = Image.new("RGB", (W, H), top_rgb)
        try:
            draw = ImageDraw.Draw(canvas)
            step = 8
            for y in range(0, H, step):
                ratio = y / max(1, H - 1)
                r = int(top_rgb[0] * (1 - ratio) + bot_rgb[0] * ratio)
                g = int(top_rgb[1] * (1 - ratio) + bot_rgb[1] * ratio)
                b = int(top_rgb[2] * (1 - ratio) + bot_rgb[2] * ratio)
                draw.rectangle((0, y, W, min(H, y + step)), fill=(r, g, b))
            # Họa tiết khung viền cổ điển nhẹ nhàng
            draw.rounded_rectangle(
                (54, 80, W - 54, H - 80),
                radius=32,
                outline=(246, 238, 222),
                width=3,
            )
            if title:
                f_sub = font("Bold", 40)
                badge = TOPIC_SERIES_LABELS.get(topic, "HBT Core").upper()
                tw = draw.textlength(badge, font=f_sub)
                draw.text(((W - tw) / 2, H - 180), badge, font=f_sub, fill=(246, 238, 222))
            canvas.save(fallback_path, format="PNG")
        finally:
            canvas.close()

    return f"images/{fallback_name}"


def sync_script_to_project(
    project: Project,
    project_dir: Path,
    script: HbtCoreScript,
) -> Project:
    """Đồng bộ kịch bản `HbtCoreScript` (V1/V2) vào `Project` (`project.json`) chuẩn của HBT.

    Nếu kịch bản có ít hơn 3 phân đoạn (trong khi model `Project` cũ yêu cầu tối thiểu 3 cảnh),
    vẫn giữ nguyên danh sách phân đoạn trong `core_script.json` và tự động điền đủ cảnh hợp lệ
    cho `project.json` để không bao giờ làm đứt gãy logic cũ.
    """
    music_topic = infer_music_topic(script.topic, script.title)
    project.title = script.title
    project.series = TOPIC_SERIES_LABELS.get(music_topic, project.series or "Hay Biết Tốt")

    new_scenes: list[Scene] = []
    for seg in script.segments:
        rel_img = resolve_segment_image(
            project_dir,
            seg.image,
            seg.order,
            topic=music_topic,
            title=script.title,
        )
        headline = (seg.title or seg.card_text or auto_card_headline(seg.text)).strip()
        card = Card(
            y="top",
            lines=[
                CardLine(
                    text=headline[:90],
                    size="m",
                    color="primary" if seg.order == 1 else "ink",
                )
            ],
        )
        new_scenes.append(
            Scene(
                image=rel_img,
                card=card,
                labels=[],
                voice=seg.text,
                punch=bool(seg.punch or seg.sfx == "impact"),
                caption_y=None,
            )
        )

    # Đảm bảo tương thích ngược với ràng buộc MIN_SCENES=3..MAX_SCENES=12 của Project.scenes
    while len(new_scenes) < 3 and new_scenes:
        last = new_scenes[-1]
        new_scenes.append(
            last.model_copy(
                deep=True,
                update={"voice": last.voice, "punch": False},
            )
        )
    if len(new_scenes) > 12:
        new_scenes = new_scenes[:12]

    project.scenes = new_scenes
    # Lưu kèm core_script.json để giữ nguyên trạng 100% các trường order, text, image, sfx của V1/V2
    core_json_path = project_dir / "core_script.json"
    core_json_path.write_text(
        json.dumps(script.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return project


def build_core_scene_layers_safe(
    scene_dict: dict[str, Any],
    img_src: Path,
    base_out: Path,
    card_out: Path,
    theme: dict[str, str],
    *,
    aspect_mode: AspectMode = "fill",
) -> None:
    """Vẽ ảnh nền + thẻ kem + phụ đề tóm tắt bằng Pillow với quản lý bộ nhớ nghiêm ngặt:
    dùng context manager `with Image.open(...)`, gọi `.close()` cho mọi ảnh trung gian
    và gọi tường minh `gc.collect()` sau khi xử lý xong phân đoạn.
    """
    base_out.parent.mkdir(parents=True, exist_ok=True)
    card_out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Cắt chuẩn 1080x1920 bằng context manager và .close()
    with Image.open(img_src) as raw_im:
        rgb_im = raw_im.convert("RGB")
        try:
            if aspect_mode == "fit":
                bg_blur = ImageOps.fit(rgb_im, (W, H), Image.LANCZOS).filter(
                    ImageFilter.GaussianBlur(radius=25)
                )
                fg_fit = ImageOps.contain(rgb_im, (W, H), Image.LANCZOS)
                try:
                    bg_blur.paste(fg_fit, ((W - fg_fit.width) // 2, (H - fg_fit.height) // 2))
                    bg_blur.save(base_out)
                finally:
                    fg_fit.close()
                    bg_blur.close()
            else:
                fitted = ImageOps.fit(rgb_im, (W, H), Image.LANCZOS)
                try:
                    fitted.save(base_out)
                finally:
                    fitted.close()
        finally:
            rgb_im.close()

    # 2. Vẽ lớp thẻ chữ giấy kem + hộp thoại lời đọc trên nền trong suốt
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    try:
        card = scene_dict.get("card") or {}
        lines = card.get("lines") or []
        y_raw = card.get("y", "top")
        y_pos = CARD_Y.get(y_raw, 110) if isinstance(y_raw, str) else int(y_raw)

        tmp_draw = ImageDraw.Draw(lay)
        maxw, pad = 960, 36
        rows: list[tuple[str, Any, tuple[int, int, int], int]] = []
        for ln in lines:
            txt = str(ln.get("text", "")).strip()
            if not txt:
                continue
            sz = SIZES.get(ln.get("size", "m"), 62)
            f = font("ExtraBold" if sz >= 70 else "Bold", sz)
            col = color_of(ln.get("color", "ink"), theme)
            # Wrap dòng
            words = txt.split()
            cur = ""
            wrapped: list[str] = []
            for w_tok in words:
                cand = f"{cur} {w_tok}".strip()
                if tmp_draw.textlength(cand, font=f) <= maxw - 2 * pad or not cur:
                    cur = cand
                else:
                    wrapped.append(cur)
                    cur = w_tok
            if cur:
                wrapped.append(cur)
            for r_txt in wrapped:
                rows.append((r_txt, f, col, int(sz * 1.28)))

        if rows:
            bw = max(tmp_draw.textlength(r[0], font=r[1]) for r in rows) + 2 * pad
            bh = sum(r[3] for r in rows) + 2 * pad - 8
            border = color_of("primary", theme)
            card_im = Image.new("RGBA", (int(bw) + 30, int(bh) + 30), (0, 0, 0, 0))
            try:
                d = ImageDraw.Draw(card_im)
                d.rounded_rectangle((12, 14, bw + 12, bh + 14), 18, fill=(0, 0, 0, 110))
                d.rounded_rectangle(
                    (0, 0, bw, bh),
                    18,
                    fill=CREAM + (255,),
                    outline=border + (255,),
                    width=5,
                )
                yy = pad - 6
                for r_txt, f, col, lh in rows:
                    d.text(((bw - d.textlength(r_txt, font=f)) / 2, yy), r_txt, font=f, fill=col)
                    yy += lh
                lay.alpha_composite(card_im, (int((W - card_im.width) / 2), int(y_pos)))
            finally:
                card_im.close()

        # Vẽ phụ đề lời thoại ở vùng an toàn dưới (y=1380)
        voice_text = str(scene_dict.get("voice", "")).replace("|", " ").strip()
        if voice_text:
            f_cap = font("ExtraBold", 56)
            words = voice_text.split()
            cap_lines: list[str] = []
            cur = ""
            for w_tok in words:
                cand = f"{cur} {w_tok}".strip()
                if tmp_draw.textlength(cand, font=f_cap) <= 920 or not cur:
                    cur = cand
                else:
                    cap_lines.append(cur)
                    cur = w_tok
            if cur:
                cap_lines.append(cur)
            cap_lines = cap_lines[:4]
            lh = 74
            y0 = 1420 - (len(cap_lines) * lh) // 2
            for li, line_str in enumerate(cap_lines):
                tw = tmp_draw.textlength(line_str, font=f_cap)
                xx = (W - tw) / 2
                yy = y0 + li * lh
                tmp_draw.text((xx + 3, yy + 6), line_str, font=f_cap, fill=(0, 0, 0, 160))
                tmp_draw.text(
                    (xx, yy),
                    line_str,
                    font=f_cap,
                    fill=(255, 212, 59) if li == 0 else (255, 255, 255),
                    stroke_width=6,
                    stroke_fill=(15, 15, 25),
                )

        lay.save(card_out)
    finally:
        lay.close()
        gc.collect()


def render_core_segment_clip(
    base_png: Path,
    card_png: Path,
    duration_s: float,
    segment_index1: int,
    out_mp4: Path,
    *,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    punch: bool = False,
    aspect_mode: AspectMode = "fill",
) -> Path:
    """Dựng video clip cho 1 phân đoạn với kẹp chuẩn tài nguyên FFmpeg:
    `-threads 2`, `-filter_threads 2`, `-preset veryfast`, `-crf 22`, `-max_muxing_queue_size 512`.
    """
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.8, round(duration_s, 3))
    n_frames = max(1, int(round(dur * fps)))

    if punch:
        z_expr = "1.12-0.08*(on/" + str(n_frames) + ")"
    elif segment_index1 % 2 == 1:
        z_expr = "1.0+0.06*(on/" + str(n_frames) + ")"
    else:
        z_expr = "1.06-0.06*(on/" + str(n_frames) + ")"

    aspect_fc = build_aspect_filter(
        aspect_mode,
        width=width,
        height=height,
        input_label="0:v",
        output_label="bg_norm",
    )
    fc = (
        f"{aspect_fc};"
        f"[bg_norm]zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={n_frames}:s={width}x{height}:fps={fps}[bg];"
        f"[1:v]scale={width}:{height},format=rgba,fade=t=in:st=0.10:d=0.30:alpha=1[card];"
        f"[bg][card]overlay=0:0:shortest=1,format=yuv420p[v]"
    )

    tmp_mp4 = out_mp4.with_name(out_mp4.stem + ".tmp.mp4")
    run_ffmpeg(
        [
            *FFMPEG_RESOURCE_CLAMP,
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-framerate",
            str(fps),
            "-i",
            base_png,
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-framerate",
            str(fps),
            "-i",
            card_png,
            "-filter_complex",
            fc,
            "-map",
            "[v]",
            "-frames:v",
            str(n_frames),
            "-r",
            str(fps),
            *FFMPEG_ENCODE_CLAMP,
            tmp_mp4,
        ]
    )
    cache.publish_atomic(tmp_mp4, out_mp4)
    gc.collect()
    return out_mp4


def mix_core_audio_track(
    voice_wav: Path,
    bgm_wav: Path | None,
    sfx_events: list[tuple[Path, int]],
    total_duration_s: float,
    out_wav: Path,
) -> Path:
    """Trộn giọng đọc VieNeu-TTS + BGM (đã nối acrossfade=d=2.0) + các hiệu ứng SFX chuyển cảnh
    theo mốc thời gian bằng FFmpeg kẹp `-threads 2`, `-filter_threads 2`.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str | Path] = ["-i", voice_wav]
    filter_parts: list[str] = [
        f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad=whole_dur={total_duration_s:.3f},atrim=0:{total_duration_s:.3f},volume=1.0[voice]"
    ]
    mix_labels: list[str] = ["[voice]"]
    input_idx = 1

    if bgm_wav is not None and bgm_wav.is_file():
        inputs.extend(["-i", bgm_wav])
        filter_parts.append(
            f"[{input_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"atrim=0:{total_duration_s:.3f},volume=0.16[bgm]"
        )
        mix_labels.append("[bgm]")
        input_idx += 1

    for sfx_i, (sfx_path, delay_ms) in enumerate(sfx_events):
        if not sfx_path.is_file():
            continue
        inputs.extend(["-i", sfx_path])
        lbl = f"[sfx{sfx_i}]"
        delay_val = max(0, int(delay_ms))
        filter_parts.append(
            f"[{input_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume=0.42,adelay={delay_val}|{delay_val}{lbl}"
        )
        mix_labels.append(lbl)
        input_idx += 1

    if len(mix_labels) == 1:
        filter_parts.append("[voice]alimiter=limit=0.95[aout]")
    else:
        filter_parts.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0,"
            f"alimiter=limit=0.95[aout]"
        )

    fc = ";".join(filter_parts)
    run_ffmpeg(
        [
            *FFMPEG_RESOURCE_CLAMP,
            *inputs,
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-t",
            f"{total_duration_s:.3f}",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            out_wav,
        ]
    )
    return out_wav


def render_hbt_core_auto(
    project_dir: Path,
    script: HbtCoreScript,
    *,
    voice_provider: VoiceProvider | None = None,
    voice_id: str | None = None,
    library_dir: Path | None = None,
    brand_dir: Path | None = None,
    fps: int = 30,
    preview: bool = False,
    aspect_mode: AspectMode = "fill",
    job_id: str | None = None,
    progress: Callable[..., None] | None = None,
    cancel_token: cancel.CancelToken | None = None,
) -> CoreRenderResult:
    """Thực thi toàn bộ chuỗi tự động HBT Core (dùng chung cho V1 & V2):
    Sinh giọng VieNeu-TTS -> BGM acrossfade=d=2.0 -> Chèn SFX -> Render FFmpeg kẹp luồng.
    """
    with cancel.use_token(cancel_token):
        return _render_hbt_core_auto_impl(
            project_dir=project_dir,
            script=script,
            voice_provider=voice_provider,
            voice_id=voice_id,
            library_dir=library_dir,
            brand_dir=brand_dir,
            fps=fps,
            preview=preview,
            aspect_mode=aspect_mode,
            job_id=job_id,
            progress=progress,
        )


def _render_hbt_core_auto_impl(
    *,
    project_dir: Path,
    script: HbtCoreScript,
    voice_provider: VoiceProvider | None,
    voice_id: str | None,
    library_dir: Path | None,
    brand_dir: Path | None,
    fps: int,
    preview: bool,
    aspect_mode: AspectMode,
    job_id: str | None,
    progress: Callable[..., None] | None,
) -> CoreRenderResult:
    t0 = time.time()
    project_dir = Path(project_dir).resolve()
    settings = load_settings()
    lib_dir = Path(library_dir or settings.library_dir).resolve()
    _ = brand_dir or BRAND_DIR

    jid = job_id or time.strftime("%Y%m%d-%H%M%S")
    job_dir = project_dir / "renders" / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    build_dir = project_dir / "build" / "core"
    build_dir.mkdir(parents=True, exist_ok=True)

    log_path = job_dir / "log.txt"
    warnings: list[str] = []

    emitter = SSEProgressEmitter(progress)

    def emit(pct: float, step: str, message: str, **extra: Any) -> None:
        cancel.check_current()
        line = f"[{time.time() - t0:6.1f}s] [{step}] {message}"
        with log_path.open("a", encoding="utf-8") as lf:
            lf.write(line + "\n")
        emitter.emit(pct, step, message, **extra)

    # 1. Đồng bộ script vào project.json
    emit(2.0, "init", f"Khởi tạo kịch bản '{script.title}' (chủ đề: {script.topic})")
    pj_path = project_dir / "project.json"
    if pj_path.is_file():
        project = Project.model_validate(json.loads(pj_path.read_text(encoding="utf-8")))
    else:
        project = Project(
            slug=project_dir.name, title=script.title, scenes=[Scene() for _ in range(3)]
        )
    project = sync_script_to_project(project, project_dir, script)

    # 2. Sinh giọng VieNeu-TTS từng phân đoạn + bắn SSE {step: "voice", current, total, percent}
    def on_voice_sse(ev: dict[str, Any]) -> None:
        v_pct = float(ev.get("percent", 0))
        overall_pct = round(5.0 + v_pct * 0.30, 1)
        emit(
            overall_pct,
            "voice",
            str(ev.get("message", "Đang sinh giọng VieNeu-TTS")),
            current=ev.get("current", 0),
            total=ev.get("total", 0),
            percent=ev.get("percent", 0),
        )

    voice_wav, timings = synthesize_core_segments(
        script.segments,
        project_dir,
        voice_provider=voice_provider,
        voice_id=voice_id,
        on_sse_event=on_voice_sse,
    )
    sync_wavs_to_audio_folder(
        [(t.order, Path(t.wav_path)) for t in timings],
        project_dir,
    )
    project.voice = Voice(file="voice.wav")

    # Lưu bảng mốc thời gian micro-giây của các segment
    timings_path = build_dir / "segment_timings.json"
    timings_path.write_text(
        json.dumps([t.model_dump(mode="json") for t in timings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_duration_s = max(
        float(media_duration(voice_wav) or 0.0),
        sum(max(0.8, t.duration_s + 0.22) for t in timings),
    )

    # 3. Nhạc nền BGM thông minh (theo topic + acrossfade=d=2.0)
    music_topic = infer_music_topic(script.topic, script.title)
    emit(38.0, "bgm", f"Chọn nhạc nền BGM theo chủ đề '{music_topic}' (acrossfade=d=2.0)")
    bgm_playlist = build_topic_bgm_playlist(
        lib_dir,
        total_duration_s,
        topic=music_topic,
        seed=project.slug,
    )
    bgm_wav: Path | None = None
    bgm_names: list[str] = [p.name for p in bgm_playlist] if bgm_playlist else []
    existing_bgm = [p for p in bgm_playlist if p.is_file()]
    if existing_bgm:
        bgm_out = build_dir / "bgm_acrossfade.wav"
        try:
            bgm_wav = render_smart_bgm_wav(existing_bgm, total_duration_s, bgm_out)
            if bgm_wav and bgm_wav.is_file():
                shutil.copy2(bgm_wav, project_dir / "music.wav")
                project.music = Music(file="music.wav", credit=", ".join(dict.fromkeys(bgm_names)))
        except Exception as exc:
            logger.warning("Không nối được nhạc nền BGM: %s", exc)
            warnings.append(f"Bỏ qua BGM do lỗi FFmpeg: {exc}")

    # 4. Quét & chuẩn bị SFX chuyển thẻ kem / chuyển ảnh từ library/sfx/
    emit(45.0, "sfx", "Quét thư viện library/sfx/ và chèn hiệu ứng âm thanh chuyển cảnh")
    sfx_events: list[tuple[Path, int]] = []
    sfx_used: list[str] = []
    sfx_cache_dir = build_dir / "sfx"
    sfx_cache_dir.mkdir(parents=True, exist_ok=True)

    for idx, (seg, timing) in enumerate(zip(script.segments, timings, strict=False)):
        sfx_src = resolve_sfx_file(lib_dir, seg.sfx, index=idx)
        if sfx_src is not None:
            if sfx_src.is_file():
                prepped_sfx = sfx_cache_dir / f"sfx_{idx + 1:02d}_{sfx_src.stem}.wav"
                if not prepped_sfx.is_file():
                    try:
                        prepare_core_sfx_clip(sfx_src, prepped_sfx)
                    except Exception as exc:
                        logger.warning("Không chuẩn bị được SFX %s: %s", sfx_src.name, exc)
                        continue
                delay_ms = int(round(timing.start_us / 1000.0))
                sfx_events.append((prepped_sfx, delay_ms))
            sfx_used.append(sfx_src.name)

    # 5. Vẽ thẻ kem & dựng clip từng phân đoạn (Pillow .close() + gc.collect() + FFmpeg kẹp luồng)
    width, height = (540, 960) if preview else (1080, 1920)
    out_fps = 30 if preview else fps
    theme_dict = project.theme.model_dump()
    segment_clips: list[Path] = []
    total_segs = len(script.segments)

    for idx, (seg, timing) in enumerate(zip(script.segments, timings, strict=False), start=1):
        cancel.check_current()
        seg_pct = round(50.0 + (idx / max(1, total_segs)) * 30.0, 1)
        emit(
            seg_pct,
            "render",
            f"Dựng hình phân đoạn {idx}/{total_segs}",
            current=idx,
            total=total_segs,
            percent=int(round((idx / max(1, total_segs)) * 100)),
        )

        rel_img = resolve_segment_image(
            project_dir,
            seg.image,
            seg.order,
            topic=music_topic,
            title=script.title,
        )
        img_src = project_dir / rel_img
        base_png = build_dir / f"base_{idx:02d}.png"
        card_png = build_dir / f"card_{idx:02d}.png"
        headline = (seg.title or seg.card_text or auto_card_headline(seg.text)).strip()
        scene_dict = {
            "card": {
                "y": "top",
                "lines": [
                    {
                        "text": headline[:90],
                        "size": "m",
                        "color": "primary" if idx == 1 else "ink",
                    }
                ],
            },
            "voice": seg.text,
            "labels": [],
        }

        build_core_scene_layers_safe(
            scene_dict, img_src, base_png, card_png, theme_dict, aspect_mode=aspect_mode
        )

        # Thời lượng clip phân đoạn khớp với thời lượng giọng đọc + khoảng nghỉ
        seg_dur_s = timing.duration_s + (0.22 if idx < total_segs else 0.30)
        seg_dur_s = max(0.8, seg_dur_s)
        clip_path = build_dir / f"seg_clip_{idx:02d}.mp4"
        render_core_segment_clip(
            base_png,
            card_png,
            seg_dur_s,
            idx,
            clip_path,
            fps=out_fps,
            width=width,
            height=height,
            punch=bool(seg.punch or seg.sfx == "impact"),
            aspect_mode=aspect_mode,
        )
        segment_clips.append(clip_path)
        gc.collect()

    # Lưu lại project.json đã đồng bộ đầy đủ ảnh, giọng, nhạc
    (project_dir / "project.json").write_text(
        json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 6. Trộn âm thanh tổng (Giọng VieNeu + BGM acrossfade + SFX)
    emit(84.0, "mix", "Trộn âm thanh (Giọng VieNeu-TTS + BGM acrossfade + SFX)")
    mixed_wav = build_dir / "final_mix.wav"
    mix_core_audio_track(voice_wav, bgm_wav, sfx_events, total_duration_s, mixed_wav)

    # 7. Ghép các clip phân đoạn và âm thanh thành video.mp4 hoàn chỉnh với kẹp tài nguyên FFmpeg
    emit(90.0, "compose", "Ghép nối video hoàn chỉnh (kẹp tài nguyên CPU/RAM)")
    concat_list_path = build_dir / "clips.ffconcat"
    concat_lines = ["ffconcat version 1.0"]
    for cp in segment_clips:
        escaped = cp.resolve().as_posix().replace("'", "'\\''")
        concat_lines.append(f"file '{escaped}'")
    concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    video_out = job_dir / "video.mp4"
    partial_video = job_dir / "video.part.mp4"
    run_ffmpeg(
        [
            *FFMPEG_RESOURCE_CLAMP,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-i",
            mixed_wav,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-r",
            str(out_fps),
            *FFMPEG_ENCODE_CLAMP,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            partial_video,
        ]
    )
    cache.publish_atomic(partial_video, video_out)
    gc.collect()

    # 8. Ghi publish.txt và meta.json
    publish_path = job_dir / "publish.txt"
    publish_path.write_text(build_publish_text(project), encoding="utf-8")

    try:
        info = probe(video_out)
        actual_duration = float(info.get("format", {}).get("duration", total_duration_s))
    except Exception:
        actual_duration = total_duration_s

    elapsed = round(time.time() - t0, 2)
    meta = {
        "job_id": jid,
        "mode": "hbt_core_auto",
        "topic": script.topic,
        "preview": preview,
        "fps": out_fps,
        "width": width,
        "height": height,
        "duration": round(actual_duration, 3),
        "lufs": -14.0,
        "aligner": "vieneu_microsecond",
        "render_seconds": elapsed,
        "bgm_tracks": bgm_names,
        "sfx_used": sfx_used,
        "segments_count": len(script.segments),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (job_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    emit(100.0, "done", f"Hoàn tất dựng video ({actual_duration:.1f}s)")
    return CoreRenderResult(
        job_dir=job_dir,
        video=video_out,
        publish=publish_path,
        log=log_path,
        fps=out_fps,
        width=width,
        height=height,
        duration=round(actual_duration, 3),
        seconds=elapsed,
        timings=timings,
        bgm_tracks=bgm_names,
        sfx_used=sfx_used,
        warnings=warnings,
    )
