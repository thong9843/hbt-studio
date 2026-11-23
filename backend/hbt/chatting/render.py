"""Bộ dựng video Chatting theo §8:
- Vẽ trạng thái PNG qua Pillow
- Ghi ffconcat
- Trộn giọng (-14 LUFS) và nhạc (-27 LUFS ducking)
- Một lệnh FFmpeg (60 fps 1080x1920 hoặc 30 fps 540x960 xem nhanh)
"""

from __future__ import annotations

import gc
import json
import logging
import math
import shutil
import struct
import time
import wave
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from hbt.chatting.audio import mix_voice_and_bgm_playlist
from hbt.chatting.draw import ChatFrameRenderer, compute_meme_rect
from hbt.chatting.html_renderer import HtmlChatSession
from hbt.chatting.models import ChatDoc, Message
from hbt.chatting.sources import is_scene_transition
from hbt.chatting.stickers import (
    SUPPORTED_IMAGE_EXTS,
    extract_meme_audio,
    find_meme_by_emojis,
    get_meme_metadata,
    load_sticker_or_meme_image,
    pick_sticker,
    resolve_meme_or_sticker_path,
    resolve_sfx_path,
)
from hbt.chatting.themes import get_theme
from hbt.chatting.timeline import MAX_VIDEO_DURATION_S, build_timeline
from hbt.chatting.voice import synthesize_chat_voices
from hbt.pipeline.ffutil import media_duration, run_ffmpeg
from hbt.postv.voice import VoiceProvider
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP
from hbt.shared.pipeline.aspect import AspectMode, build_aspect_filter

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


def cubic_ease_out(t: float) -> float:
    """Hàm nội suy Cubic Ease-Out 1 - (1 - t)^3 cho chuyển động 60fps dịu mắt."""
    tc = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - tc) ** 3


def cosine_ease_in_out(t: float) -> float:
    """Hàm nội suy Cosine Ease-In-Out mượt mà cho chuyển trang & co giãn khung chat."""
    tc = max(0.0, min(1.0, t))
    return 0.5 * (1.0 - math.cos(math.pi * tc))


def spring_scale_curve(num_frames: int = 18) -> list[float]:
    """Đường cong Spring Easing 18 sub-frames (0.80 -> 0.92 -> 1.03 -> 0.99 -> 1.0) chuẩn 60fps."""
    if num_frames <= 1:
        return [1.0]
    anchors = [
        (0.00, 0.80),
        (0.28, 0.92),
        (0.58, 1.03),
        (0.80, 0.99),
        (1.00, 1.00),
    ]
    out: list[float] = []
    for k in range(num_frames):
        t = k / float(num_frames - 1)
        val = 1.0
        for j in range(len(anchors) - 1):
            t0, v0 = anchors[j]
            t1, v1 = anchors[j + 1]
            if t0 <= t <= t1:
                local_t = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
                # Smoothstep cục bộ giúp chuyển tiếp vận tốc giữa các neo nảy hoàn toàn liên tục
                smooth = local_t * local_t * (3.0 - 2.0 * local_t)
                val = v0 + (v1 - v0) * smooth
                break
        out.append(round(val, 4))
    return out


def assemble_voice_track(
    audio_events: list[tuple[float, Path, float] | tuple[float, Path, float, float]],
    total_duration: float,
    out_wav: Path,
    sample_rate: int = 24000,
) -> None:
    """Tạo track âm thanh tổng hợp (giọng nói + SFX + meme) với hỗ trợ gain_db từng lớp."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(total_duration * sample_rate)
    buffer = bytearray(total_samples * 2)  # 16-bit mono

    for ev in audio_events:
        start_time = ev[0]
        audio_path = ev[1]
        gain_db = float(ev[3]) if len(ev) >= 4 else 0.0
        gain_lin = 10.0 ** (gain_db / 20.0) if gain_db != 0.0 else 1.0
        if not audio_path.is_file():
            continue
        try:
            raw_data = b""
            # Nếu là file wav chuẩn
            if audio_path.suffix.lower() == ".wav":
                try:
                    with wave.open(str(audio_path), "rb") as wf:
                        channels = wf.getnchannels()
                        rate = wf.getframerate()
                        sampwidth = wf.getsampwidth()
                        if rate == sample_rate and channels == 1 and sampwidth == 2:
                            raw_data = wf.readframes(wf.getnframes())
                except Exception:
                    raw_data = b""

            # Nếu chưa có raw_data hoặc là file mp3/cần resample: dùng ffmpeg convert sang mono wav
            if not raw_data:
                tmp_resampled = out_wav.parent / f"tmp_{time.time_ns()}_{audio_path.stem}.wav"
                run_ffmpeg(
                    [
                        "-y",
                        "-v",
                        "error",
                        *FFMPEG_RESOURCE_CLAMP,
                        "-i",
                        str(audio_path),
                        "-ac",
                        "1",
                        "-ar",
                        str(sample_rate),
                        "-c:a",
                        "pcm_s16le",
                        str(tmp_resampled),
                    ]
                )
                if tmp_resampled.is_file():
                    with wave.open(str(tmp_resampled), "rb") as rwf:
                        raw_data = rwf.readframes(rwf.getnframes())
                    try:
                        tmp_resampled.unlink(missing_ok=True)
                    except Exception:
                        pass

            start_idx = int(start_time * sample_rate) * 2
            end_idx = min(len(buffer), start_idx + len(raw_data))
            copy_len = end_idx - start_idx
            if copy_len > 0 and start_idx < len(buffer):
                # Cộng dồn mẫu PCM 16-bit kèm hệ số gain_lin chống lấn át giọng đọc
                for k in range(0, copy_len, 2):
                    cur_val = struct.unpack_from("<h", buffer, start_idx + k)[0]
                    add_raw = struct.unpack_from("<h", raw_data, k)[0]
                    add_val = int(round(add_raw * gain_lin)) if gain_lin != 1.0 else add_raw
                    mixed = max(-32768, min(32767, cur_val + add_val))
                    struct.pack_into("<h", buffer, start_idx + k, mixed)
        except Exception as e:
            logger.warning("Không trộn được âm thanh %s: %s", audio_path, e)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(buffer)


def pick_sfx_file(library_dir: Path, kind: str) -> Path | None:
    """Lấy file hiệu ứng âm thanh từ library/sfx/ (pop, typing, ding)."""
    sfx_dir = library_dir / "sfx"
    if not sfx_dir.is_dir():
        return None
    if kind == "pop":
        cand = sfx_dir / "dragon-studio-pop-402324.mp3"
        if cand.is_file():
            return cand
        cand_list = sorted(sfx_dir.glob("*pop*.mp3"))
        return cand_list[0] if cand_list else None
    if kind == "typing":
        cand = sfx_dir / "universfield-fast-swoosh-383967.mp3"
        if cand.is_file():
            return cand
        cand_list = sorted(sfx_dir.glob("*swoosh*.mp3"))
        return cand_list[0] if cand_list else None
    if kind == "ding":
        cand = sfx_dir / "freesound_community-snd_fragment_retrievewav-14728.mp3"
        if cand.is_file():
            return cand
        return None
    return None


def pick_background_clip(library_dir: Path, bg_name: str | None) -> Path | None:
    """Chọn clip gameplay từ library/backgrounds/."""
    bg_dir = library_dir / "backgrounds"
    if not bg_dir.is_dir():
        return None

    if bg_name:
        candidate = bg_dir / bg_name
        if candidate.is_file():
            return candidate
        candidate_mp4 = bg_dir / f"{bg_name}.mp4"
        if candidate_mp4.is_file():
            return candidate_mp4

    # Chọn file mp4 đầu tiên có sẵn
    mp4s = sorted(bg_dir.glob("*.mp4"))
    return mp4s[0] if mp4s else None


def pick_music_file(library_dir: Path, music_name: str | None) -> Path | None:
    """Chọn file nhạc từ library/music/."""
    music_dir = library_dir / "music"
    if not music_dir.is_dir():
        return None

    if music_name:
        for ext in (".mp3", ".wav", ".m4a"):
            cand = music_dir / f"{music_name}{ext}"
            if cand.is_file():
                return cand

    mp3s = sorted(music_dir.glob("*.mp3"))
    return mp3s[0] if mp3s else None


def render_chat_video(
    workspace_dir: Path,
    slug: str,
    doc: ChatDoc,
    voice_provider: VoiceProvider,
    library_dir: Path,
    brand_dir: Path,
    preview: bool = False,
    progress: ProgressCallback | None = None,
    aspect_mode: AspectMode | None = None,
) -> Path:
    """Dựng video Chatting (preview 540x960 30fps hoặc full 1080x1920 60fps)."""
    effective_aspect: AspectMode = "fit" if aspect_mode is None else aspect_mode

    def tick(pct: int, msg: str) -> None:
        if progress:
            progress(pct, msg)

    tick(5, "Chuẩn bị")
    project_dir = workspace_dir / "chatting" / slug
    build_dir = project_dir / "build"
    renders_dir = project_dir / "renders"
    frames_dir = build_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    renders_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sinh giọng cho các tin nhắn (10-30%)
    tick(10, "Sinh giọng đọc tin nhắn")
    voice_durations = synthesize_chat_voices(workspace_dir, slug, doc, voice_provider)
    tick(30, "Đã sinh giọng")

    # 2. Xây dựng timeline (30-35%), hỗ trợ tối đa 300.0s (5 phút)
    tick(32, "Lập mốc thời gian")
    max_dur_cap = float(getattr(doc, "target_duration_s", None) or MAX_VIDEO_DURATION_S)
    timeline = build_timeline(
        doc,
        voice_durations,
        library_dir=library_dir,
        max_duration=min(MAX_VIDEO_DURATION_S, max_dur_cap),
    )

    target_duration = (
        min(10.0, timeline.total_duration)
        if preview
        else min(MAX_VIDEO_DURATION_S, timeline.total_duration)
    )
    fps = 30 if preview else 60
    width = 540 if preview else 1080
    height = 960 if preview else 1920

    # 3. Vẽ các khung hình Pillow theo từng phân đoạn (Chunked Concat) để tối ưu RAM (35-60%)
    tick(35, "Vẽ giao diện chat theo phân đoạn")
    theme = get_theme(doc.platform)
    bg_file = pick_background_clip(library_dir, doc.background.name)
    bg_dur = media_duration(bg_file) if (bg_file and bg_file.is_file()) else None

    # Nạp ảnh avatar nếu có
    avatar_images: dict[str, Image.Image] = {}
    for c in doc.characters:
        if c.avatar:
            av_path = project_dir / c.avatar
            if av_path.is_file():
                try:
                    avatar_images[c.id] = Image.open(av_path).convert("RGBA")
                except Exception:
                    pass

    renderer = ChatFrameRenderer(theme, doc.characters, avatar_images, project_dir=project_dir)
    video_media_spans: dict[int, list[tuple[float, float, Path, int, int, int, int]]] = {}
    coord_scale = width / 1080.0

    from hbt.app_settings import AppSettingsStore
    from hbt.shared.pipeline.watermark import render_watermark_png

    wm_cfg = AppSettingsStore(workspace_dir).load().watermark
    wm_img: Image.Image | None = None
    if wm_cfg.enabled:
        wm_png = build_dir / "watermark_1080.png"
        render_watermark_png(wm_png, wm_cfg, width=1080, height=1920, brand_dir=brand_dir)
        if wm_png.is_file():
            try:
                with Image.open(wm_png) as raw_wm:
                    wm_img = raw_wm.convert("RGBA")
            except Exception:
                wm_img = None

    active_states = [s for s in timeline.states if s.start_time < target_duration]
    total_states = max(1, len(active_states))

    # Bộ nhớ theo phiên video: ưu tiên `msg.meme_id` từ Smart Asset Director, fallback xoay vòng
    used_memes: set[str] = set()
    state_meme_files: dict[int, Path] = {}
    for st_idx, st in enumerate(active_states):
        if st.active_sticker:
            chosen: Path | None = None
            if st.visible_count > 0:
                cur_msg = doc.messages[st.visible_count - 1]
                chosen = resolve_meme_or_sticker_path(
                    library_dir, getattr(cur_msg, "meme_id", None)
                )
                if chosen is not None:
                    used_memes.add(chosen.name)
                else:
                    msg_text = getattr(cur_msg, "display_text", None) or cur_msg.text
                    chosen = find_meme_by_emojis(library_dir, msg_text, used_memes=used_memes)
            if chosen is None:
                chosen = pick_sticker(
                    library_dir, st.active_sticker, doc.background.seed, used_memes=used_memes
                )
            if chosen is not None and chosen.is_file():
                state_meme_files[st_idx] = chosen

    chunk_size = 15  # Xử lý tối đa 15 state mỗi chunk để giữ RAM ổn định trên 16GB
    chunk_files: list[Path] = []
    frame_counter = 0
    current_scroll_y: float = 0.0
    acc_time: float = 0.0
    prev_page_msgs: list[Message] = []
    prev_card_h: int = 360

    chunk_concat_lines: list[str] = []
    chunk_pngs: list[Path] = []
    last_chunk_fname = ""

    html_session = HtmlChatSession(doc.platform)
    html_session.start()

    def snap_dur(raw_d: float) -> float:
        """Khóa mốc frame tích lũy `round(acc_t * fps)` để không rơi/lặp frame."""
        nonlocal acc_time
        t_start = round(acc_time * fps) / float(fps)
        acc_time += max(1.0 / float(fps), raw_d)
        t_end = round(acc_time * fps) / float(fps)
        return max(1.0 / float(fps), round(t_end - t_start, 5))

    def emit_image_frame(img: Image.Image, raw_dur: float, *, add_wm: bool = True) -> None:
        nonlocal frame_counter, last_chunk_fname
        fname = f"frame_{frame_counter:05d}.png"
        fpath = frames_dir / fname
        if add_wm and wm_img is not None:
            img.alpha_composite(wm_img)
        img.save(fpath, format="PNG", compress_level=1)
        dur = snap_dur(raw_dur)
        chunk_pngs.append(fpath)
        chunk_concat_lines.append(f"file '{fname}'\n")
        chunk_concat_lines.append(f"duration {dur:.5f}\n")
        last_chunk_fname = fname
        frame_counter += 1

    def save_subframe(
        v_msgs: list[Message],
        s_typing: bool = False,
        t_char_id: str | None = None,
        t_pulse: int = 0,
        s_img: Image.Image | None = None,
        s_right: bool = False,
        scale_msg: float = 1.0,
        s_seen: bool = True,
        s_scroll: float | None = None,
        is_cutin: bool = False,
        dur: float = 0.05,
        msg_opacity: float = 1.0,
        msg_offset_y: float = 0.0,
        typing_opacity: float = 1.0,
        meme_opacity: float = 1.0,
        meme_scale: float = 1.0,
        frame_h_override: int | None = None,
    ) -> None:
        nonlocal frame_counter, last_chunk_fname
        fname = f"frame_{frame_counter:05d}.png"
        fpath = frames_dir / fname

        is_anim_frame = (
            msg_opacity < 0.999
            or abs(msg_offset_y) > 0.1
            or typing_opacity < 0.999
            or meme_opacity < 0.999
            or abs(meme_scale - 1.0) > 0.001
            or frame_h_override is not None
        )
        used_html = False
        if html_session.active and not is_cutin and s_img is None and not is_anim_frame:
            state_json = renderer.build_html_state(
                visible_messages=v_msgs,
                show_typing=s_typing,
                typing_pulse_step=t_pulse,
                scale_last_msg=scale_msg,
                show_seen=s_seen,
                scroll_offset_override=s_scroll,
            )
            used_html = html_session.render_frame(state_json, fpath)

        if used_html:
            if wm_img is not None and not is_cutin:
                with Image.open(fpath) as rendered:
                    rgba = rendered.convert("RGBA")
                    rgba.alpha_composite(wm_img)
                    rgba.save(fpath, format="PNG", compress_level=1)
                    rgba.close()
        else:
            img = renderer.render_chat_view(
                visible_messages=v_msgs,
                show_typing=s_typing,
                typing_char_id=t_char_id,
                typing_pulse_step=t_pulse,
                active_sticker_img=s_img,
                sticker_from_right=s_right,
                scale_last_msg=scale_msg,
                show_seen=s_seen,
                scroll_offset_override=s_scroll,
                is_meme_cutin=is_cutin,
                last_msg_opacity=msg_opacity,
                last_msg_offset_y=msg_offset_y,
                typing_opacity=typing_opacity,
                meme_opacity=meme_opacity,
                meme_scale=meme_scale,
                frame_height_override=frame_h_override,
            )
            if wm_img is not None and not is_cutin:
                img.alpha_composite(wm_img)
            img.save(fpath, format="PNG", compress_level=1)
            img.close()

        snapped = snap_dur(dur)
        chunk_pngs.append(fpath)
        chunk_concat_lines.append(f"file '{fname}'\n")
        chunk_concat_lines.append(f"duration {snapped:.5f}\n")
        last_chunk_fname = fname
        frame_counter += 1

    for chunk_idx in range(0, len(active_states), chunk_size):
        chunk_states = active_states[chunk_idx : chunk_idx + chunk_size]
        chunk_concat_lines.clear()
        chunk_concat_lines.append("ffconcat version 1.0\n")
        chunk_pngs.clear()
        last_chunk_fname = ""
        chunk_start_time = chunk_states[0].start_time
        chunk_total_dur = 0.0

        for local_i, state in enumerate(chunk_states):
            global_i = chunk_idx + local_i
            stk_img = None
            if state.active_sticker:
                stk_file = state_meme_files.get(global_i)
                if stk_file and stk_file.is_file():
                    # Ảnh/WebP/GIF vẽ bằng Pillow; video .mp4/.webm ghép colorkey bằng FFmpeg
                    if not state.is_meme_cutin or stk_file.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                        try:
                            stk_img = load_sticker_or_meme_image(stk_file)
                        except Exception:
                            pass

            visible_msgs = renderer.paginate_messages(
                doc.messages[: state.visible_count],
                show_typing=state.show_typing,
                active_sticker_img=stk_img,
                show_seen=state.show_seen,
            )
            frame_dur = min(state.duration, max(0.01, target_duration - state.start_time))
            chunk_total_dur += frame_dur
            target_scroll_y = 0.0

            if not state.show_typing:
                for m_idx, m_path, cx, cy, mw, mh in renderer.compute_video_media_rects(
                    visible_msgs, 0.0
                ):
                    sx = int(round(cx * coord_scale))
                    sy = int(round(cy * coord_scale))
                    sw = max(16, (int(round(mw * coord_scale)) // 2) * 2)
                    sh = max(16, (int(round(mh * coord_scale)) // 2) * 2)
                    video_media_spans.setdefault(m_idx, []).append(
                        (state.start_time, state.start_time + frame_dur, m_path, sx, sy, sw, sh)
                    )

            target_card_h = renderer.compute_card_height(
                visible_msgs, show_typing=state.show_typing, show_seen=state.show_seen
            )

            # 1. Typing 60fps: fade-in 0.20s, sóng 3 chấm chậm (~1.1s/chu kỳ), fade-out 0.18s
            if state.show_typing:
                num_sub = max(12, int(round(frame_dur * fps)))
                sub_dur = frame_dur / float(num_sub)
                fade_in_s = min(0.20, frame_dur * 0.35)
                fade_out_s = min(0.18, frame_dur * 0.30)
                for k in range(num_sub):
                    t_local = (k + 0.5) * sub_dur
                    if t_local < fade_in_s:
                        t_op = cubic_ease_out(t_local / max(0.01, fade_in_s))
                    elif t_local > (frame_dur - fade_out_s):
                        t_op = cubic_ease_out((frame_dur - t_local) / max(0.01, fade_out_s))
                    else:
                        t_op = 1.0
                    p_h = cubic_ease_out((k + 1) / float(num_sub))
                    cur_h = int(round(prev_card_h + (target_card_h - prev_card_h) * p_h))
                    save_subframe(
                        v_msgs=visible_msgs,
                        s_typing=True,
                        t_char_id=state.typing_char_id,
                        t_pulse=k,
                        s_img=None,
                        s_right=state.sticker_from_right,
                        scale_msg=1.0,
                        s_seen=state.show_seen,
                        s_scroll=target_scroll_y,
                        dur=sub_dur,
                        typing_opacity=t_op,
                        frame_h_override=cur_h,
                    )
                prev_card_h = target_card_h
                current_scroll_y = target_scroll_y

            # 2. Xuất hiện tin nhắn dịu 60fps (0.40s) + Cross-Fade 0.45s khi sang trang mới
            elif state.scale_last_msg < 1.0:
                is_page_reset = bool(prev_page_msgs) and len(visible_msgs) < len(prev_page_msgs)
                if is_page_reset:
                    xfade_dur = min(0.45, frame_dur)
                    num_xf = max(12, int(round(xfade_dur * fps)))
                    sub_dur = xfade_dur / float(num_xf)
                    old_img = renderer.render_chat_view(
                        visible_messages=prev_page_msgs,
                        show_typing=False,
                        show_seen=True,
                        frame_height_override=prev_card_h,
                    )
                    new_img = renderer.render_chat_view(
                        visible_messages=visible_msgs,
                        show_typing=False,
                        show_seen=state.show_seen,
                        frame_height_override=target_card_h,
                    )
                    for k in range(num_xf):
                        alpha = cosine_ease_in_out((k + 1) / float(num_xf))
                        blended = Image.blend(old_img, new_img, alpha)
                        emit_image_frame(blended, sub_dur)
                        blended.close()
                    old_img.close()
                    new_img.close()
                    remain = frame_dur - xfade_dur
                    if remain > 0.01:
                        save_subframe(
                            v_msgs=visible_msgs,
                            s_seen=state.show_seen,
                            dur=remain,
                            frame_h_override=target_card_h,
                        )
                else:
                    num_sub = max(12, int(round(frame_dur * fps)))
                    sub_dur = frame_dur / float(num_sub)
                    for k in range(num_sub):
                        p = (k + 1) / float(num_sub)
                        ease = cubic_ease_out(p)
                        sc = 0.97 + 0.03 * ease
                        off_y = 22.0 * (1.0 - ease)
                        cur_h = int(round(prev_card_h + (target_card_h - prev_card_h) * ease))
                        save_subframe(
                            v_msgs=visible_msgs,
                            s_typing=False,
                            s_img=None,
                            s_right=state.sticker_from_right,
                            scale_msg=sc,
                            s_seen=state.show_seen,
                            s_scroll=target_scroll_y,
                            dur=sub_dur,
                            msg_opacity=ease,
                            msg_offset_y=off_y,
                            frame_h_override=cur_h,
                        )
                prev_page_msgs = list(visible_msgs)
                prev_card_h = target_card_h
                current_scroll_y = target_scroll_y

            # 3. Meme/Sticker tĩnh: fade-in + scale 0.94->1.0 (0.28s), hold, fade-out (0.25s)
            elif state.is_meme_cutin and stk_img is not None:
                in_d = min(0.28, frame_dur * 0.35)
                out_d = min(0.25, frame_dur * 0.30)
                hold_d = max(0.0, frame_dur - in_d - out_d)
                n_in = max(6, int(round(in_d * fps)))
                for k in range(n_in):
                    ease = cubic_ease_out((k + 1) / float(n_in))
                    save_subframe(
                        v_msgs=visible_msgs,
                        s_img=stk_img,
                        s_right=state.sticker_from_right,
                        s_seen=state.show_seen,
                        is_cutin=True,
                        dur=in_d / float(n_in),
                        meme_opacity=ease,
                        meme_scale=0.94 + 0.06 * ease,
                        frame_h_override=target_card_h,
                    )
                if hold_d > 0.01:
                    save_subframe(
                        v_msgs=visible_msgs,
                        s_img=stk_img,
                        s_right=state.sticker_from_right,
                        s_seen=state.show_seen,
                        is_cutin=True,
                        dur=hold_d,
                        meme_opacity=1.0,
                        meme_scale=1.0,
                        frame_h_override=target_card_h,
                    )
                n_out = max(6, int(round(out_d * fps)))
                for k in range(n_out):
                    ease_out = 1.0 - cubic_ease_out((k + 1) / float(n_out))
                    save_subframe(
                        v_msgs=visible_msgs,
                        s_img=stk_img,
                        s_right=state.sticker_from_right,
                        s_seen=state.show_seen,
                        is_cutin=True,
                        dur=out_d / float(n_out),
                        meme_opacity=max(0.0, ease_out),
                        meme_scale=1.0,
                        frame_h_override=target_card_h,
                    )
                prev_page_msgs = list(visible_msgs)
                prev_card_h = target_card_h

            # 4. Đoạn đứng yên lúc đọc thoại / nghỉ: tái sử dụng 1 frame tĩnh (tối ưu tốc độ CPU)
            else:
                current_scroll_y = target_scroll_y
                save_subframe(
                    v_msgs=visible_msgs,
                    s_typing=False,
                    t_char_id=None,
                    t_pulse=0,
                    s_img=stk_img,
                    s_right=state.sticker_from_right,
                    scale_msg=state.scale_last_msg,
                    s_seen=state.show_seen,
                    s_scroll=current_scroll_y,
                    is_cutin=bool(state.is_meme_cutin and stk_img is not None),
                    dur=frame_dur,
                    frame_h_override=target_card_h,
                )
                prev_page_msgs = list(visible_msgs)
                prev_card_h = target_card_h

            pct = 35 + int(25 * (global_i + 1) / total_states)
            tick(pct, f"Vẽ & nén phân đoạn {global_i + 1}/{total_states}")
            if stk_img is not None:
                stk_img.close()

        # Kết thúc chunk concat
        if last_chunk_fname:
            chunk_concat_lines.append(f"file '{last_chunk_fname}'\n")
        chunk_concat_file = frames_dir / f"chunk_{chunk_idx // chunk_size:03d}.ffconcat"
        chunk_concat_file.write_text("".join(chunk_concat_lines), encoding="utf-8")

        chunk_mp4 = frames_dir / f"chunk_{chunk_idx // chunk_size:03d}.mp4"
        chunk_cmd: list[str] = [
            "-y",
            "-v",
            "error",
            "-threads",
            "2",
            "-filter_threads",
            "2",
            "-filter_complex_threads",
            "2",
        ]
        if bg_file and bg_file.is_file():
            bg_offset = (chunk_start_time % bg_dur) if (bg_dur and bg_dur > 0) else 0.0
            chunk_cmd.extend(["-stream_loop", "-1", "-ss", f"{bg_offset:.3f}", "-i", str(bg_file)])
        else:
            chunk_cmd.extend(["-f", "lavfi", "-i", f"color=c=#1A1A24:s={width}x{height}:r={fps}"])

        chunk_cmd.extend(["-f", "concat", "-safe", "0", "-i", str(chunk_concat_file)])
        bg_aspect = build_aspect_filter(
            effective_aspect,
            width=width,
            height=height,
            input_label="0:v",
            output_label="bg_norm",
        )
        chunk_filter = (
            f"{bg_aspect};"
            f"[bg_norm]fps={fps}[bg];"
            f"[1:v]scale={width}:{height}[fg];"
            "[bg][fg]overlay=0:0[v]"
        )
        chunk_cmd.extend(
            [
                "-filter_complex",
                chunk_filter,
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-max_muxing_queue_size",
                "512",
                "-an",
                "-t",
                f"{chunk_total_dur:.3f}",
                str(chunk_mp4),
            ]
        )
        run_ffmpeg(chunk_cmd)
        chunk_files.append(chunk_mp4)

        # Dọn dẹp ngay toàn bộ sub-frame PNG tạm thời và ffconcat của chunk vừa xử lý
        for p in chunk_pngs:
            p.unlink(missing_ok=True)
        chunk_concat_file.unlink(missing_ok=True)
        gc.collect()

    html_session.close()

    chunks_concat = frames_dir / "chunks.ffconcat"
    chunks_concat.write_text(
        "ffconcat version 1.0\n" + "".join(f"file '{c.name}'\n" for c in chunk_files),
        encoding="utf-8",
    )

    # 4. Trộn âm thanh và SFX (60-75%)
    tick(60, "Trộn âm thanh và nhạc nền")
    voice_mix_wav = build_dir / "voice_mix.wav"
    event_tuples: list[tuple[float, Path, float] | tuple[float, Path, float, float]] = [
        (e.start_time, e.wav_path, e.duration, 0.0) for e in timeline.audio_events
    ]

    # Kích hoạt âm thanh SFX từ library/sfx/ với gain dịu tai (không gắt, không át giọng VieNeu)
    sfx_pop = pick_sfx_file(library_dir, "pop")
    sfx_typing = pick_sfx_file(library_dir, "typing")
    sfx_ding = pick_sfx_file(library_dir, "ding")
    char_sides = {c.id: c.side for c in doc.characters}

    for st_idx, state in enumerate(active_states):
        if state.show_typing and sfx_typing:
            event_tuples.append((state.start_time, sfx_typing, 0.4, -7.0))
        elif state.scale_last_msg < 1.0:
            if state.visible_count > 0:
                last_m = doc.messages[state.visible_count - 1]
                if not is_scene_transition(last_m.text):
                    if sfx_pop:
                        pop_gain = -5.5 if char_sides.get(last_m.from_) == "left" else -4.0
                        event_tuples.append((state.start_time, sfx_pop, 0.3, pop_gain))
                    # Trộn thêm SFX điểm nhấn nếu tin nhắn có `sfx_id` (-16 LUFS đã chuẩn hóa)
                    if getattr(last_m, "sfx_id", None):
                        punch_sfx = resolve_sfx_path(library_dir, last_m.sfx_id)
                        if punch_sfx is not None and punch_sfx.is_file():
                            event_tuples.append((state.start_time, punch_sfx, 1.8, -5.0))
        elif state.active_sticker:
            meme_audio_played = False
            if state.is_meme_cutin:
                stk_file = state_meme_files.get(st_idx)
                if stk_file and stk_file.is_file():
                    meta = get_meme_metadata(library_dir, stk_file.name)
                    st_time = float(meta.get("start_time", 0.0))
                    meme_wav = build_dir / f"meme_{stk_file.stem}_s{int(st_time * 10)}.wav"
                    if not (meme_wav.is_file() and meme_wav.stat().st_size > 1000):
                        extract_meme_audio(
                            stk_file,
                            meme_wav,
                            start_time=st_time,
                            max_duration=state.duration,
                        )
                    if meme_wav.is_file() and meme_wav.stat().st_size > 1000:
                        # Giảm audio gốc của clip meme xuống -8dB so với giọng VieNeu
                        event_tuples.append((state.start_time, meme_wav, state.duration, -8.0))
                        meme_audio_played = True
            if not meme_audio_played and sfx_ding:
                event_tuples.append((state.start_time, sfx_ding, 0.5, -6.0))

    assemble_voice_track(event_tuples, target_duration, voice_mix_wav)

    final_audio = build_dir / "final_audio.wav"
    mix_voice_and_bgm_playlist(
        voice_mix_wav=voice_mix_wav,
        library_dir=library_dir,
        music_name=doc.music,
        total_duration=target_duration,
        out_wav=final_audio,
        workdir=build_dir,
    )

    # 5. Ghép các phân đoạn video + Colorkey Meme Overlay + Audio (75-95%)
    tick(75, "Ghép video FFmpeg theo phân đoạn")
    render_id = int(time.time())
    out_mp4 = renders_dir / f"render_{render_id}.mp4"

    # Thu thập danh sách meme video chuyển động đặt DƯỚI đáy khung chat (không đè chữ) + fade in/out
    meme_clips: list[tuple[Path, float, float, float, int, int, int, int]] = []
    for st_idx, state in enumerate(active_states):
        if state.is_meme_cutin and state.active_sticker:
            stk_file = state_meme_files.get(st_idx)
            if (
                stk_file
                and stk_file.is_file()
                and stk_file.suffix.lower() in (".mp4", ".mov", ".webm")
            ):
                meta = get_meme_metadata(library_dir, stk_file.name)
                ss_start = float(meta.get("start_time", 0.0))
                m_dur = min(state.duration, max(0.5, target_duration - state.start_time))
                card_bot = renderer.compute_card_bottom_y(
                    doc.messages[: state.visible_count],
                    show_typing=False,
                    show_seen=state.show_seen,
                )
                mx, my, mw, mh = compute_meme_rect(card_bot, 720, 480)
                sx = int(round(mx * coord_scale))
                sy = int(round(my * coord_scale))
                sw = max(64, (int(round(mw * coord_scale)) // 2) * 2)
                sh = max(64, (int(round(mh * coord_scale)) // 2) * 2)
                meme_clips.append((stk_file, state.start_time, m_dur, ss_start, sx, sy, sw, sh))

    cmd: list[str] = [
        "-y",
        "-v",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(chunks_concat),
        "-i",
        str(final_audio),
    ]

    if meme_clips or video_media_spans:
        next_inp_idx = 2
        filter_parts: list[str] = ["[0:v]null[v_base]"]
        prev_v = "v_base"

        if meme_clips:
            for k, (m_path, m_start, m_dur, ss_start, mx, my, mw, mh) in enumerate(meme_clips):
                cmd.extend(["-ss", f"{ss_start:.2f}", "-t", f"{m_dur:.2f}", "-i", str(m_path)])
                inp_idx = next_inp_idx
                next_inp_idx += 1
                fade_in = min(0.28, m_dur * 0.3)
                fade_out = min(0.25, m_dur * 0.28)
                fade_out_st = max(0.0, m_dur - fade_out)
                filter_parts.append(
                    f"[{inp_idx}:v]format=rgba,colorkey=0x00FF00:0.3:0.1,"
                    f"scale={mw}:{mh}:force_original_aspect_ratio=decrease:flags=lanczos,"
                    f"fade=t=in:st=0:d={fade_in:.3f}:alpha=1,"
                    f"fade=t=out:st={fade_out_st:.3f}:d={fade_out:.3f}:alpha=1,"
                    f"setpts=PTS-STARTPTS+{m_start:.4f}/TB[m{k}]"
                )
                next_v = f"v_meme{k}"
                filter_parts.append(
                    f"[{prev_v}][m{k}]overlay=x={mx}+({mw}-w)/2:y={my}+({mh}-h)/2:"
                    f"enable='between(t,{m_start:.4f},{m_start + m_dur:.4f})'"
                    f":eof_action=pass[{next_v}]"
                )
                prev_v = next_v

        for v_idx, (_msg_idx, spans) in enumerate(sorted(video_media_spans.items())):
            first_t = spans[0][0]
            last_t = spans[-1][1]
            m_path = spans[0][2]
            sx, sw, sh = spans[0][3], spans[0][5], spans[0][6]
            vis_dur = max(0.2, last_t - first_t)
            cmd.extend(["-stream_loop", "-1", "-t", f"{vis_dur:.3f}", "-i", str(m_path)])
            inp_idx = next_inp_idx
            next_inp_idx += 1
            filter_parts.append(
                f"[{inp_idx}:v]scale={sw}:{sh}:flags=lanczos,setsar=1,"
                f"setpts=PTS-STARTPTS+{first_t:.4f}/TB[vm{v_idx}]"
            )
            distinct_ys = list(dict.fromkeys(sp[4] for sp in spans))
            if len(distinct_ys) == 1:
                y_expr = str(distinct_ys[0])
            else:
                y_expr = str(spans[-1][4])
                for s_t, e_t, _p, _x, sy, _w, _h in reversed(spans[:-1]):
                    y_expr = f"if(between(t,{s_t:.4f},{e_t:.4f}),{sy},{y_expr})"
            enable_expr = "+".join(f"between(t,{s_t:.4f},{e_t:.4f})" for s_t, e_t, *_ in spans)
            next_v = f"v_media{v_idx}"
            filter_parts.append(
                f"[{prev_v}][vm{v_idx}]overlay=x={sx}:y='{y_expr}':"
                f"enable='{enable_expr}':eof_action=pass[{next_v}]"
            )
            prev_v = next_v

        filter_complex = ";".join(filter_parts)
        cmd.extend(
            [
                "-threads",
                "2",
                "-filter_threads",
                "2",
                "-filter_complex_threads",
                "2",
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{prev_v}]",
                "-map",
                "1:a",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-max_muxing_queue_size",
                "512",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{target_duration:.3f}",
                str(out_mp4),
            ]
        )
    else:
        # Không có meme overlay: nối thẳng stream video (-c:v copy) tiết kiệm tối đa CPU/RAM
        cmd.extend(
            [
                "-threads",
                "2",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-max_muxing_queue_size",
                "512",
                "-t",
                f"{target_duration:.3f}",
                str(out_mp4),
            ]
        )

    run_ffmpeg(cmd)

    # Dọn dẹp phân đoạn video tạm và giải phóng tài nguyên
    for cf in chunk_files:
        cf.unlink(missing_ok=True)
    chunks_concat.unlink(missing_ok=True)
    voice_mix_wav.unlink(missing_ok=True)
    final_audio.unlink(missing_ok=True)
    for av in avatar_images.values():
        av.close()
    avatar_images.clear()
    if wm_img is not None:
        wm_img.close()
    gc.collect()

    # Lưu metadata của lần render
    meta = {
        "id": render_id,
        "preview": preview,
        "fps": fps,
        "width": width,
        "height": height,
        "duration": target_duration,
        "created_at": time.time(),
        "video_file": out_mp4.name,
    }
    meta_file = renders_dir / f"render_{render_id}.json"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Nếu preview: sao chép làm preview.mp4 mặc định
    if preview:
        shutil.copyfile(out_mp4, project_dir / "preview.mp4")

    tick(100, "Hoàn thành")
    return out_mp4
