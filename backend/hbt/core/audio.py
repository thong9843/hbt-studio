"""Nhạc nền BGM thông minh (từ Chatting) & Âm thanh hiệu ứng SFX (từ PostV) cho HBT Core.

Nhiệm vụ 1.2 - Nhạc nền BGM thông minh:
- Tự động quét thư mục cục bộ `library/music/` theo `"topic"` (`history / fun / science / mystery`)
  hoặc ngẫu nhiên.
- Tự động nối các bài nhạc dài bằng bộ lọc FFmpeg `acrossfade=d=2.0`, không để video bị ngắt nhạc.

Nhiệm vụ 1.3 - Âm thanh hiệu ứng SFX & Sticker:
- Quét thư mục cục bộ `library/sfx/` (`whoosh`, `pop`...) để chèn âm thanh chuyển thẻ kem / ảnh.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

from hbt.pipeline.ffutil import media_duration, run_ffmpeg
from shared.ffmpeg_utils import ACROSSFADE_DURATION_S, build_acrossfade_filter_graph

logger = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

# Ánh xạ từ topic (history / fun / science / mystery) sang các từ khoá mood trong library/music/
TOPIC_MOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "history": ("drama", "kịch tính", "căng thẳng", "tâm trạng", "slow", "confession"),
    "fun": ("quirky", "hài hước", "vui nhộn", "comic", "dí dỏm", "wacky", "nhí nhảnh", "nhanh"),
    "science": ("chill", "lofi", "tích cực", "tươi sáng", "nhẹ nhàng", "thư giãn", "positive"),
    "mystery": ("sneaky", "lén lút", "drama", "kịch tính", "căng thẳng", "mystery"),
}

SFX_KEYWORDS: dict[str, tuple[str, ...]] = {
    "whoosh": ("swoosh", "whoosh", "swipe", "transition", "fast-swoosh", "wind"),
    "pop": ("pop", "bubble", "click", "ding", "snap"),
    "impact": ("hit", "boom", "punch", "thud", "slam", "riser"),
}


def scan_music_by_topic(
    library_dir: Path,
    topic: str | None = None,
    *,
    seed: int | str | None = None,
) -> list[Path]:
    """Quét `library/music/` theo `topic` (history / fun / science / mystery) hoặc ngẫu nhiên.

    Ưu tiên các bài có `moods` hoặc tên khớp với chủ đề trước, sau đó nối thêm các bài còn lại
    để danh sách phát luôn đủ dài cho mọi thời lượng video.
    """
    music_dir = library_dir / "music"
    if not music_dir.is_dir():
        return []

    all_files = sorted(
        f for f in music_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    )
    if not all_files:
        return []

    # Đọc index.json nếu có để lấy moods của từng file
    file_moods: dict[str, list[str]] = {}
    index_path = music_dir / "index.json"
    if index_path.is_file():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(entries, list):
                for item in entries:
                    if isinstance(item, dict) and item.get("file"):
                        moods = [str(m).lower() for m in (item.get("moods") or [])]
                        title = str(item.get("title", "")).lower()
                        file_moods[str(item["file"])] = [*moods, title]
        except Exception:
            pass

    topic_key = (topic or "").strip().lower()
    keywords = TOPIC_MOOD_KEYWORDS.get(topic_key, ())

    matched: list[Path] = []
    others: list[Path] = []

    for f in all_files:
        haystack = " ".join([f.stem.lower(), *file_moods.get(f.name, [])])
        if keywords and any(kw in haystack for kw in keywords):
            matched.append(f)
        else:
            others.append(f)

    rng = random.Random(seed) if seed is not None else random.Random()
    rng.shuffle(matched)
    rng.shuffle(others)

    return matched + others


def build_topic_bgm_playlist(
    library_dir: Path,
    target_duration_s: float,
    *,
    topic: str | None = None,
    seed: int | str | None = None,
    crossfade_s: float = ACROSSFADE_DURATION_S,
) -> list[Path]:
    """Chọn danh sách bài nhạc BGM sao cho tổng thời lượng sau khi trừ `acrossfade=d=2.0`
    luôn phủ kín toàn bộ `target_duration_s` (không bao giờ ngắt nhạc giữa chừng).
    """
    candidates = scan_music_by_topic(library_dir, topic=topic, seed=seed)
    if not candidates:
        return []

    playlist: list[Path] = []
    accumulated = 0.0
    needed = max(target_duration_s + 4.0, 10.0)
    idx = 0

    while accumulated < needed and idx < 50:
        track = candidates[idx % len(candidates)]
        try:
            dur = float(media_duration(track) or 30.0)
        except Exception:
            dur = 30.0
        dur = max(dur, 5.0)
        playlist.append(track)
        if len(playlist) == 1:
            accumulated += dur
        else:
            accumulated += max(1.0, dur - crossfade_s)
        idx += 1

    return playlist


def render_smart_bgm_wav(
    playlist: list[Path],
    target_duration_s: float,
    out_wav: Path,
    *,
    crossfade_s: float = ACROSSFADE_DURATION_S,
) -> Path | None:
    """Nối danh sách nhạc nền bằng bộ lọc FFmpeg `acrossfade=d=2.0` và kẹp `-threads 2`."""
    if not playlist:
        return None

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if len(playlist) == 1:
        try:
            d0 = float(media_duration(playlist[0]) or 0.0)
        except Exception:
            d0 = 0.0
        if 0.0 < d0 < target_duration_s + 2.0:
            # Lặp lại bài nhạc duy nhất và nối bằng acrossfade=d=2.0 để không bị ngắt quãng
            repeats = max(2, int((target_duration_s + 4.0) / max(d0 - crossfade_s, 2.0)) + 1)
            playlist = [playlist[0]] * min(repeats, 12)

    inputs: list[str | Path] = []
    for track in playlist:
        inputs.extend(["-i", track])

    fc, out_label = build_acrossfade_filter_graph(
        len(playlist),
        target_duration_s,
        crossfade_s=crossfade_s,
    )
    run_ffmpeg(
        [
            "-threads",
            "2",
            "-filter_threads",
            "2",
            *inputs,
            "-filter_complex",
            fc,
            "-map",
            out_label,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            out_wav,
        ]
    )
    return out_wav if out_wav.is_file() else None


def scan_sfx_library(library_dir: Path) -> list[dict[str, Any]]:
    """Quét toàn bộ thư mục `library/sfx/` và phân loại (`whoosh`, `pop`, `impact`, `other`)."""
    sfx_dir = library_dir / "sfx"
    if not sfx_dir.is_dir():
        return []

    files = sorted(f for f in sfx_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS)
    results: list[dict[str, Any]] = []
    for f in files:
        stem = f.stem.lower()
        category = "other"
        for cat, kws in SFX_KEYWORDS.items():
            if any(k in stem for k in kws):
                category = cat
                break
        results.append(
            {
                "id": f.stem,
                "name": f.name,
                "category": category,
                "path": f,
            }
        )
    return results


def resolve_sfx_file(
    library_dir: Path,
    sfx_name: str | None,
    *,
    index: int = 0,
) -> Path | None:
    """Tìm file SFX trong `library/sfx/` khớp với `sfx_name` (vd: `"whoosh"`, `"pop"`)."""
    if not sfx_name:
        return None
    q = sfx_name.strip().lower()
    if q in ("none", "off", "ắt", "tat", "không", "khong", ""):
        return None

    entries = scan_sfx_library(library_dir)
    if not entries:
        return None

    # 1. Khớp chính xác tên file hoặc stem
    for e in entries:
        if e["name"].lower() == q or e["id"].lower() == q:
            return e["path"]

    # 2. Khớp theo category (whoosh / pop / impact)
    cat_alias = "whoosh" if q in ("swoosh", "whoosh", "transition", "chuyển cảnh") else q
    cat_matches = [e["path"] for e in entries if e["category"] == cat_alias]
    if cat_matches:
        return cat_matches[index % len(cat_matches)]

    # 3. Khớp chuỗi con trong tên file
    sub_matches = [e["path"] for e in entries if q in e["id"].lower()]
    if sub_matches:
        return sub_matches[index % len(sub_matches)]

    # 4. Mặc định trả về whoosh đầu tiên nếu có, hoặc file đầu tiên trong kho
    whoosh_matches = [e["path"] for e in entries if e["category"] == "whoosh"]
    if whoosh_matches:
        return whoosh_matches[index % len(whoosh_matches)]
    return entries[index % len(entries)]["path"]


def prepare_core_sfx_clip(sfx_src: Path, out_wav: Path, max_dur_s: float = 0.75) -> Path:
    """Chuẩn hoá SFX từ `library/sfx/` sang WAV 48kHz stereo ngắn gọn kèm fade-out."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    fade_st = max(0.1, max_dur_s - 0.18)
    af = (
        f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=0:{max_dur_s:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={fade_st:.3f}:d=0.18"
    )
    run_ffmpeg(
        [
            "-threads",
            "2",
            "-filter_threads",
            "2",
            "-i",
            sfx_src,
            "-af",
            af,
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
