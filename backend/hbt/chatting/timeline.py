"""Tính toán mốc thời gian (timeline) từ độ dài wav theo §8."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hbt.chatting.models import ChatDoc


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


def build_timeline(
    doc: ChatDoc,
    voice_durations: list[tuple[int, Path, float]],
) -> ChatTimeline:
    """Tạo timeline chi tiết cho video chat:
    - 0.4s mở đầu (khung chat trống)
    - Mỗi tin:
      - Nếu tin bên trái: 0.6s gõ phím ("đang nhập")
      - 0.15s pop tin nhắn (scale 0.85 -> 1.0)
      - Độ dài đọc wav
      - Nếu có sticker: 0.8s hiện sticker
      - 0.25s nghỉ
    - Cuối: giữ 1.5s
    """
    char_map = {c.id: c for c in doc.characters}
    dur_map = {idx: (path, dur) for idx, path, dur in voice_durations}

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

    for idx, msg in enumerate(doc.messages):
        char = char_map.get(msg.from_)
        is_right = (char.side == "right") if char else False
        wav_path, wav_dur = dur_map.get(idx, (Path(""), 1.0))

        # Nếu tin bên trái: hiện "đang nhập" 0.6s
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
                show_seen=(idx == len(doc.messages) - 1),
            )
        )
        cur_time += wav_dur

        # Nếu có sticker: hiện sticker 0.8s
        if msg.sticker:
            states.append(
                TimelineState(
                    start_time=cur_time,
                    duration=0.8,
                    visible_count=idx + 1,
                    active_sticker=msg.sticker,
                    sticker_from_right=is_right,
                    show_seen=True,
                )
            )
            cur_time += 0.8

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
            visible_count=len(doc.messages),
            show_seen=True,
        )
    )
    cur_time += 1.5

    return ChatTimeline(
        total_duration=round(cur_time, 3),
        states=states,
        audio_events=audio_events,
    )
