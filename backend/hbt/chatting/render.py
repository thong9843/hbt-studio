"""Bộ dựng video Chatting theo §8:
- Vẽ trạng thái PNG qua Pillow
- Ghi ffconcat
- Trộn giọng (-14 LUFS) và nhạc (-27 LUFS ducking)
- Một lệnh FFmpeg (60 fps 1080x1920 hoặc 30 fps 540x960 xem nhanh)
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import wave
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from hbt.chatting.draw import ChatFrameRenderer
from hbt.chatting.models import ChatDoc, Message
from hbt.chatting.stickers import pick_sticker
from hbt.chatting.themes import get_theme
from hbt.chatting.timeline import build_timeline
from hbt.chatting.voice import synthesize_chat_voices
from hbt.pipeline import audio
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.postv.voice import VoiceProvider

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


def assemble_voice_track(
    audio_events: list[tuple[float, Path, float]],
    total_duration: float,
    out_wav: Path,
    sample_rate: int = 24000,
) -> None:
    """Tạo track giọng duy nhất bằng cách đặt từng file wav vào đúng mốc thời gian."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(total_duration * sample_rate)
    buffer = bytearray(total_samples * 2)  # 16-bit mono

    for start_time, wav_path, _dur in audio_events:
        if not wav_path.is_file():
            continue
        try:
            with wave.open(str(wav_path), "rb") as wf:
                channels = wf.getnchannels()
                rate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                raw_data = wf.readframes(wf.getnframes())

                # Chuyển đổi sang mono sample_rate nếu khác
                if rate != sample_rate or channels != 1 or sampwidth != 2:
                    # Dùng ffmpeg resample nhanh
                    tmp_resampled = wav_path.with_name(f"{wav_path.stem}_resampled.wav")
                    run_ffmpeg(
                        [
                            "-y",
                            "-v",
                            "error",
                            "-i",
                            str(wav_path),
                            "-ac",
                            "1",
                            "-ar",
                            str(sample_rate),
                            "-c:a",
                            "pcm_s16le",
                            str(tmp_resampled),
                        ]
                    )
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
                    buffer[start_idx:end_idx] = raw_data[:copy_len]
        except Exception as e:
            logger.warning("Không trộn được wav %s: %s", wav_path, e)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(buffer)


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
) -> Path:
    """Dựng video Chatting (preview 540x960 30fps hoặc full 1080x1920 60fps)."""

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

    # 2. Xây dựng timeline (30-35%)
    tick(32, "Lập mốc thời gian")
    timeline = build_timeline(doc, voice_durations)

    target_duration = min(10.0, timeline.total_duration) if preview else timeline.total_duration
    fps = 30 if preview else 60
    width = 540 if preview else 1080
    height = 960 if preview else 1920

    # 3. Vẽ các khung hình Pillow (35-60%)
    tick(35, "Vẽ giao diện chat")
    theme = get_theme(doc.platform)

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

    renderer = ChatFrameRenderer(theme, doc.characters, avatar_images)
    content_area_h = renderer.theme.frame_max_height - renderer.theme.header_height

    # Tạo danh sách frame png + ffconcat
    concat_lines = ["ffconcat version 1.0\n"]
    total_states = len(timeline.states)
    frame_counter = 0
    current_scroll_y = 0

    def save_subframe(
        v_msgs: list[Message],
        s_typing: bool = False,
        t_char_id: str | None = None,
        t_pulse: int = 0,
        s_img: Image.Image | None = None,
        s_right: bool = False,
        scale_msg: float = 1.0,
        s_seen: bool = True,
        s_scroll: int | None = None,
        dur: float = 0.05,
    ) -> None:
        nonlocal frame_counter
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
        )
        fname = f"frame_{frame_counter:05d}.png"
        fpath = frames_dir / fname
        img.save(fpath, format="PNG")
        concat_lines.append(f"file '{fname}'\n")
        concat_lines.append(f"duration {dur:.3f}\n")
        frame_counter += 1

    for i, state in enumerate(timeline.states):
        if state.start_time >= target_duration:
            break

        stk_img = None
        if state.active_sticker:
            stk_file = pick_sticker(library_dir, state.active_sticker, doc.background.seed)
            if stk_file and stk_file.is_file():
                try:
                    stk_img = Image.open(stk_file).convert("RGBA")
                except Exception:
                    pass

        visible_msgs = doc.messages[: state.visible_count]
        frame_dur = min(state.duration, max(0.01, target_duration - state.start_time))

        # Tính toán độ cuộn mong muốn
        total_content_h = renderer.get_content_height(
            visible_msgs,
            show_typing=state.show_typing,
            active_sticker_img=stk_img,
            show_seen=state.show_seen,
        )
        target_scroll_y = max(0, total_content_h - content_area_h)

        # 1. Trường hợp typing: 12 sub-frames tạo sóng sin nhấp nhô mượt
        if state.show_typing:
            num_sub = 12
            sub_dur = frame_dur / num_sub
            for k in range(num_sub):
                if target_scroll_y > current_scroll_y:
                    t = min(1.0, (k + 1) / 6.0)
                    ease = 1.0 - (1.0 - t) ** 2
                    scroll_k = int(current_scroll_y + (target_scroll_y - current_scroll_y) * ease)
                else:
                    scroll_k = target_scroll_y
                save_subframe(
                    v_msgs=visible_msgs,
                    s_typing=True,
                    t_char_id=state.typing_char_id,
                    t_pulse=k,
                    s_img=stk_img,
                    s_right=state.sticker_from_right,
                    scale_msg=1.0,
                    s_seen=state.show_seen,
                    s_scroll=scroll_k,
                    dur=sub_dur,
                )
            current_scroll_y = target_scroll_y

        # 2. Trường hợp popup tin nhắn: 6 sub-frames tạo scale ease-out và cuộn trượt
        elif state.scale_last_msg < 1.0:
            scales = [0.72, 0.84, 0.94, 1.02, 1.01, 1.0]
            num_sub = len(scales)
            sub_dur = frame_dur / num_sub
            for k, scale in enumerate(scales):
                if target_scroll_y > current_scroll_y:
                    t = (k + 1) / float(num_sub)
                    ease = 1.0 - (1.0 - t) ** 2
                    scroll_k = int(current_scroll_y + (target_scroll_y - current_scroll_y) * ease)
                else:
                    scroll_k = target_scroll_y
                save_subframe(
                    v_msgs=visible_msgs,
                    s_typing=False,
                    t_char_id=None,
                    t_pulse=0,
                    s_img=stk_img,
                    s_right=state.sticker_from_right,
                    scale_msg=scale,
                    s_seen=state.show_seen,
                    s_scroll=scroll_k,
                    dur=sub_dur,
                )
            current_scroll_y = target_scroll_y

        # 3. Trường hợp cuộn mượt khi xuất hiện nội dung dài vượt trang
        elif target_scroll_y > current_scroll_y and frame_dur >= 0.2:
            scroll_dur = min(0.18, frame_dur * 0.5)
            num_sub = 6
            sub_dur = scroll_dur / num_sub
            for k in range(num_sub):
                t = (k + 1) / float(num_sub)
                ease = 1.0 - (1.0 - t) ** 2
                scroll_k = int(current_scroll_y + (target_scroll_y - current_scroll_y) * ease)
                save_subframe(
                    v_msgs=visible_msgs,
                    s_typing=False,
                    t_char_id=None,
                    t_pulse=0,
                    s_img=stk_img,
                    s_right=state.sticker_from_right,
                    scale_msg=state.scale_last_msg,
                    s_seen=state.show_seen,
                    s_scroll=scroll_k,
                    dur=sub_dur,
                )
            current_scroll_y = target_scroll_y
            remain_dur = frame_dur - scroll_dur
            if remain_dur > 0.005:
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
                    dur=remain_dur,
                )

        # 4. Giữ frame tĩnh cho các pha thoại và pha nghỉ
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
                dur=frame_dur,
            )

        pct = 35 + int(25 * (i + 1) / total_states)
        tick(pct, f"Vẽ trạng thái {i + 1}/{total_states}")

    # File cuối của ffconcat
    if frame_counter > 0:
        last_file_name = f"frame_{frame_counter - 1:05d}.png"
        concat_lines.append(f"file '{last_file_name}'\n")

    concat_file = frames_dir / "frames.ffconcat"
    concat_file.write_text("".join(concat_lines), encoding="utf-8")

    # 4. Trộn âm thanh (60-75%)
    tick(60, "Trộn âm thanh và nhạc nền")
    voice_mix_wav = build_dir / "voice_mix.wav"
    event_tuples = [(e.start_time, e.wav_path, e.duration) for e in timeline.audio_events]
    assemble_voice_track(event_tuples, target_duration, voice_mix_wav)

    music_file = pick_music_file(library_dir, doc.music)
    final_audio = build_dir / "final_audio.wav"

    if music_file and music_file.is_file():
        try:
            # Ducking: giọng -14 LUFS, nhạc -27 LUFS
            audio.mix_audio(
                voice_mix_wav, music_file, 0.0, target_duration, final_audio, build_dir, []
            )
        except Exception as e:
            logger.warning("Trộn nhạc ducking thất bại: %s, dùng track giọng thuần", e)
            shutil.copyfile(voice_mix_wav, final_audio)
    else:
        shutil.copyfile(voice_mix_wav, final_audio)

    # 5. Dựng video cuối bằng một lệnh FFmpeg (75-95%)
    tick(75, "Dựng video FFmpeg")
    bg_file = pick_background_clip(library_dir, doc.background.name)

    render_id = int(time.time())
    out_mp4 = renders_dir / f"render_{render_id}.mp4"

    cmd: list[str] = [
        "-y",
        "-v",
        "error",
    ]

    # Input 0: Background
    if bg_file and bg_file.is_file():
        cmd.extend(["-stream_loop", "-1", "-i", str(bg_file)])
    else:
        # Fallback nền màu tối
        cmd.extend(["-f", "lavfi", "-i", f"color=c=#1A1A24:s={width}x{height}:r={fps}"])

    # Input 1: Frames concat
    cmd.extend(["-f", "concat", "-safe", "0", "-i", str(concat_file)])

    # Input 2: Audio
    cmd.extend(["-i", str(final_audio)])

    # Filter complex
    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}[bg];"
        f"[1:v]scale={width}:{height}[fg];"
        f"[bg][fg]overlay=0:0[v]"
    )
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            f"{target_duration:.3f}",
            str(out_mp4),
        ]
    )

    run_ffmpeg(cmd)

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
