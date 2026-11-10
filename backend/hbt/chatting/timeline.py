"""Tính toán mốc thời gian (timeline) từ độ dài wav theo §8."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hbt.chatting.models import ChatDoc
from hbt.chatting.sources import is_scene_transition


@dataclass(frozen=True)
class TimelineState:
    start_time: float
    duration: float
    visible_count: int
    show_typing: bool = False
    typing_char_id: str | None = None
    scale_last_msg: float = 1.0
    active_sticker: str | None = None
    sticker_from_right: bool = False
    show_seen: bool = True
    is_meme_cutin: bool = False


@dataclass(frozen=True)
class AudioEvent:
    start_time: float
    wav_path: Path
    duration: float


@dataclass(frozen=True)
class ChatTimeline:
    total_duration: float
    states: list[TimelineState]
    audio_events: list[AudioEvent]


MAX_VIDEO_DURATION_S = 300.0  # Trần thời lượng tối đa 5 phút


def build_timeline(
    doc: ChatDoc,
    voice_durations: list[tuple[int, Path, float]],
    library_dir: Path | None = None,
    max_duration: float | None = None,
) -> ChatTimeline:
    """Tạo timeline chi tiết cho video chat (tối đa 300.0s = 5 phút):
    - 0.4s mở đầu (khung chat trống)
    - Mỗi tin:
      - Nếu chuyển cảnh: 1.3s divider + 0.3s dừng kịch tính
      - Nếu tin bên trái: 0.6s gõ phím ("đang nhập")
      - 0.15s pop tin nhắn (scale 0.85 -> 1.0)
      - Độ dài đọc wav
      - Nếu có meme/sticker: 3.5s phóng to meme cut-in (hoặc bỏ qua nếu thiếu file)
      - 0.25s nghỉ
    - Cuối: giữ 1.5s
    """
    char_map = {c.id: c for c in doc.characters}
    dur_map = {idx: (path, dur) for idx, path, dur in voice_durations}
    ceiling = min(
        MAX_VIDEO_DURATION_S,
        float(max_duration or getattr(doc, "target_duration_s", None) or MAX_VIDEO_DURATION_S),
    )

    states: list[TimelineState] = []
    audio_events: list[AudioEvent] = []

    # 1. Mở đầu: 0.4s
    cur_time = 0.0
    states.append(
        TimelineState(
            start_time=0.0,
            duration=0.4,
            visible_count=0,
            show_typing=False,
        )
    )
    cur_time += 0.4

    last_visible = 0
    for idx, msg in enumerate(doc.messages):
        # Dừng thêm tin nếu đã chạm trần thời lượng (chừa 1.5s cuối)
        if cur_time >= max(2.0, ceiling - 1.5):
            break
        last_visible = idx + 1
        char = char_map.get(msg.from_)
        is_right = (char.side == "right") if char else False
        wav_path, wav_dur = dur_map.get(idx, (Path(""), 1.0))
        msg_text = getattr(msg, "display_text", None) or msg.text

        # 1. Trường hợp chuyển cảnh ngoặc đơn (5 phút sau), (10 phút sau tại nhà vệ sinh)...
        if is_scene_transition(msg_text):
            trans_dur = 1.3
            states.append(
                TimelineState(
                    start_time=cur_time,
                    duration=trans_dur,
                    visible_count=idx + 1,
                    show_typing=False,
                    scale_last_msg=1.0,
                    show_seen=False,
                    is_meme_cutin=False,
                )
            )
            cur_time += trans_dur

            # Khoảng nghỉ kịch tính 0.3s
            states.append(
                TimelineState(
                    start_time=cur_time,
                    duration=0.3,
                    visible_count=idx + 1,
                    show_typing=False,
                    show_seen=False,
                    is_meme_cutin=False,
                )
            )
            cur_time += 0.3
            continue

        # 2. Nếu tin bên trái: hiện "đang nhập" 0.6s
        if not is_right:
            states.append(
                TimelineState(
                    start_time=cur_time,
                    duration=0.6,
                    visible_count=idx,
                    show_typing=True,
                    typing_char_id=msg.from_,
                )
            )
            cur_time += 0.6

        # Pop tin nhắn: 0.15s (scale 0.85 -> 1.0)
        states.append(
            TimelineState(
                start_time=cur_time,
                duration=0.15,
                visible_count=idx + 1,
                scale_last_msg=0.85,
                show_seen=False,
            )
        )
        cur_time += 0.15

        # Đọc tin nhắn: wav_dur
        if wav_path.is_file():
            audio_events.append(
                AudioEvent(start_time=cur_time, wav_path=wav_path, duration=wav_dur)
            )

        states.append(
            TimelineState(
                start_time=cur_time,
                duration=wav_dur,
                visible_count=idx + 1,
                scale_last_msg=1.0,
                show_seen=(idx == len(doc.messages) - 1 and not msg.sticker),
            )
        )
        cur_time += wav_dur

        # Nếu có sticker/meme: Meme Cut-in Pause 3.5s phóng to giữa khung hình
        if msg.sticker:
            has_valid_meme = True
            if library_dir is not None:
                from hbt.chatting.stickers import pick_sticker

                stk_file = pick_sticker(library_dir, msg.sticker, doc.background.seed)
                has_valid_meme = stk_file is not None and stk_file.is_file()

            if has_valid_meme:
                meme_dur = 3.5
                states.append(
                    TimelineState(
                        start_time=cur_time,
                        duration=meme_dur,
                        visible_count=idx + 1,
                        active_sticker=msg.sticker,
                        sticker_from_right=is_right,
                        show_seen=True,
                        is_meme_cutin=True,
                    )
                )
                cur_time += meme_dur

        # Nghỉ giữa tin 0.25s (trừ tin cuối cùng)
        if idx < len(doc.messages) - 1:
            states.append(
                TimelineState(
                    start_time=cur_time,
                    duration=0.25,
                    visible_count=idx + 1,
                    show_seen=True,
                )
            )
            cur_time += 0.25

    # Giữ màn hình cuối 1.5s
    states.append(
        TimelineState(
            start_time=cur_time,
            duration=1.5,
            visible_count=last_visible or len(doc.messages),
            show_seen=True,
        )
    )
    cur_time += 1.5

    return ChatTimeline(
        total_duration=round(min(ceiling, cur_time), 3),
        states=states,
        audio_events=audio_events,
    )
