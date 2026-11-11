"""Nhận diện nhạc nền BGM tuyệt đối từ `library/music/` và dựng Playlist acrossfade cho PostV."""

from __future__ import annotations

import logging
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hbt.chatting.audio import build_bgm_playlist, list_music_files, render_bgm_playlist_wav
from hbt.config import REPO_ROOT
from hbt.library import MusicLibrary
from hbt.models import Music
from hbt.pipeline.ffutil import ffmpeg_exe
from hbt.postv.models import PostvProject

SFX_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")
_TRANSITION_KEYWORDS = ("swoosh", "whoosh", "pop", "retrieve", "ting", "chime", "click", "swipe")
_EMPHASIS_KEYWORDS = ("bass", "drop", "scratch", "laugh", "trumpet", "trombone", "boom", "hit")

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BgmTrack:
    id: str
    file: str
    title: str
    credit: str
    path: Path

    def to_music(self, file_override: str | None = None) -> Music:
        return Music(file=file_override or self.file, credit=self.credit)


def resolve_library_dir(library_dir: Path | str | None = None) -> Path:
    """Trả về đường dẫn tuyệt đối tới thư mục thư viện (`library/`)."""
    if library_dir is None:
        return (REPO_ROOT / "library").resolve()
    p = Path(library_dir)
    if not p.is_absolute():
        return (REPO_ROOT / p).resolve()
    return p.resolve()


def resolve_music_dir(library_dir: Path | str | None = None) -> Path:
    """Trả về đường dẫn tuyệt đối tới thư mục `library/music/`."""
    return resolve_library_dir(library_dir) / "music"


def _slug_fallback(stem: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return clean or "bgm"


def list_available_bgm(library_dir: Path | str | None = None) -> list[BgmTrack]:
    """Quét `index.json` và file nhạc thực tế trong `library/music/` (đường dẫn tuyệt đối)."""
    lib_root = resolve_library_dir(library_dir)
    music_dir = lib_root / "music"
    items: list[BgmTrack] = []
    seen_files: set[Path] = set()

    try:
        entries = MusicLibrary(lib_root).list()
    except Exception as exc:
        log.warning("Không đọc được index.json trong %s: %s", music_dir, exc)
        entries = []

    for entry in entries:
        target = (music_dir / entry.file).resolve()
        if target.is_file():
            items.append(
                BgmTrack(
                    id=entry.id,
                    file=entry.file,
                    title=entry.title,
                    credit=entry.credit,
                    path=target,
                )
            )
            seen_files.add(target)

    # Bổ sung file âm thanh có thật trên đĩa nếu chưa khai báo trong index.json
    for path in list_music_files(lib_root):
        resolved = path.resolve()
        if resolved not in seen_files:
            items.append(
                BgmTrack(
                    id=_slug_fallback(path.stem),
                    file=path.name,
                    title=path.stem,
                    credit="",
                    path=resolved,
                )
            )
            seen_files.add(resolved)

    return items


def pick_default_bgm(
    library_dir: Path | str | None = None,
    preferred_id: str | None = None,
    rng: random.Random | None = None,
) -> BgmTrack | None:
    """Chọn bài BGM theo `preferred_id` hoặc ngẫu nhiên 1 bài mặc định từ `library/music/`."""
    items = list_available_bgm(library_dir)
    if not items:
        return None

    if preferred_id and preferred_id.strip():
        needle = preferred_id.strip()
        for track in items:
            if needle in (track.id, track.file, track.path.name, track.path.stem):
                return track

    chooser = rng or random
    return chooser.choice(items)


def resolve_project_music_src(
    project: PostvProject,
    project_dir: Path,
    library_dir: Path | str | None = None,
) -> Path | None:
    """Tìm file nhạc nền của dự án: ưu tiên trong project_dir, rơi về `library/music/`."""
    if project.music is None:
        return None
    lib_root = resolve_library_dir(library_dir)
    music_dir = lib_root / "music"

    if project.music.file:
        local = (project_dir / project.music.file).resolve()
        if local.is_file():
            return local
        in_lib = (music_dir / project.music.file).resolve()
        if in_lib.is_file():
            return in_lib

    if project.music.credit:
        for track in list_available_bgm(lib_root):
            if track.credit and track.credit == project.music.credit:
                return track.path
    return None


def build_postv_bgm_playlist_wav(
    library_dir: Path | str | None,
    first_music_name: str | None,
    total_duration: float,
    out_wav: Path,
    crossfade_s: float = 2.0,
) -> list[tuple[Path, float]]:
    """Tạo Playlist BGM phủ kín 100% `total_duration` với filter `acrossfade=d=2.0`."""
    lib_root = resolve_library_dir(library_dir)
    playlist = build_bgm_playlist(
        lib_root, first_music_name, total_duration, crossfade_s=crossfade_s
    )
    if not playlist:
        return []
    render_bgm_playlist_wav(
        playlist,
        total_duration,
        out_wav,
        crossfade_s=crossfade_s,
        fade_out_s=2.0,
        volume_db=None,
    )
    return playlist


def list_sfx_files(library_dir: Path | str | None = None) -> list[Path]:
    """Quét toàn bộ file hiệu ứng âm thanh trong `library/sfx/`."""
    sfx_dir = resolve_library_dir(library_dir) / "sfx"
    if not sfx_dir.is_dir():
        return []
    return sorted(
        [p for p in sfx_dir.iterdir() if p.is_file() and p.suffix.lower() in SFX_EXTS],
        key=lambda p: p.name.casefold(),
    )


def categorize_sfx_files(library_dir: Path | str | None = None) -> tuple[list[Path], list[Path]]:
    """Phân loại SFX thành (chuyển cảnh thẻ, nhấn mạnh/cao trào) từ `library/sfx/`."""
    all_sfx = list_sfx_files(library_dir)
    if not all_sfx:
        return [], []
    transitions = [p for p in all_sfx if any(kw in p.stem.lower() for kw in _TRANSITION_KEYWORDS)]
    emphases = [p for p in all_sfx if any(kw in p.stem.lower() for kw in _EMPHASIS_KEYWORDS)]
    if not transitions:
        transitions = list(all_sfx)
    if not emphases:
        emphases = list(all_sfx)
    return transitions, emphases


def prepare_sfx_clip(
    src: Path,
    out_wav: Path,
    max_duration: float = 0.75,
    fade_out: float = 0.12,
) -> Path:
    """Giải mã, cắt gọn theo `max_duration` và fade-out mượt cho một clip SFX/meme."""
    if out_wav.is_file() and out_wav.stat().st_size > 1000:
        return out_wav
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.15, float(max_duration))
    fo = min(max(0.05, float(fade_out)), dur * 0.45)
    st = max(0.0, dur - fo)
    af = f"afade=t=in:st=0:d=0.015,afade=t=out:st={st:.4f}:d={fo:.4f}"
    cmd = [
        ffmpeg_exe(),
        "-v",
        "error",
        "-y",
        "-i",
        str(src),
        "-t",
        f"{dur:.4f}",
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-af",
        af,
        str(out_wav),
    ]
    subprocess.run(cmd, check=True)
    return out_wav
