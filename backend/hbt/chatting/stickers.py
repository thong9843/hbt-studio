"""Quản lý thư viện meme / sticker local (library/memes/) theo §6 và CH5."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

from PIL import Image

from hbt.chatting.models import VALID_STICKER_TAGS
from hbt.pipeline.ffutil import run_ffmpeg

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTS = {".png", ".webp", ".gif", ".jpg", ".jpeg"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".webm"}


EMOJI_TAG_MAP = {
    "gian": ["🤬", "🔨", "🔥", "😡", "💢", "👿", "😤"],
    "cuoi": ["🤣", "😂", "😹", "😆", "😅", "🤪"],
    "soc": ["👁️👄👁️", "😱", "😳", "🤯", "😮", "🙀"],
    "khoc": ["😭", "😢", "🥺", "😿", "💔"],
    "ngai": ["🤡", "🌚", "👀", "😬", "🙈"],
    "yeu": ["❤️", "💖", "😍", "🥰", "💕", "😘"],
    "nghi": ["🤔", "🤨", "🧐"],
    "can": ["😑", "😐", "🫥", "🤐"],
    "bat_luc": ["🤦", "🤦‍♂️", "🤦‍♀️", "😮‍💨", "💀", "⚰️"],
    "ok": ["👍", "👌", "✅", "💯"],
}


def get_memes_dir(library_dir: Path) -> Path:
    base = Path(library_dir).resolve()
    memes_dir = base / "memes"
    if memes_dir.is_dir():
        return memes_dir
    alt_dir = base / "meme"
    if alt_dir.is_dir():
        return alt_dir
    # Fallback thư mục cũ nếu có
    stickers_dir = base / "stickers"
    return stickers_dir if stickers_dir.is_dir() else memes_dir


def load_memes_metadata(library_dir: Path) -> list[dict[str, Any]]:
    """Đọc danh sách meme kèm metadata (file, tags, emojis, start_time, duration)."""
    memes_dir = get_memes_dir(library_dir)
    index_file = memes_dir / "index.json"
    entries: list[dict[str, Any]] = []
    if index_file.is_file():
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "memes" in data and isinstance(data["memes"], list):
                entries = [m for m in data["memes"] if isinstance(m, dict)]
            elif isinstance(data, list):
                entries = [m for m in data if isinstance(m, dict)]
            elif isinstance(data, dict):
                # Legacy format: { "soc": ["cat.mp4"] }
                for tag, files in data.items():
                    for f in files:
                        entries.append(
                            {
                                "file": f,
                                "tags": [tag],
                                "emojis": [],
                                "start_time": 0.0,
                                "duration": 3.5,
                            }
                        )
        except Exception as e:
            logger.warning("Không đọc được memes/index.json: %s", e)

    # Bổ sung mọi file video meme có thật trên đĩa dù chưa khai báo trong index.json
    known_files = {str(item.get("file") or "") for item in entries}
    if memes_dir.is_dir():
        for path in sorted(memes_dir.iterdir(), key=lambda p: p.name.lower()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTS:
                if path.name not in known_files:
                    entries.append(
                        {
                            "file": path.name,
                            "tags": ["ok"],
                            "emojis": [],
                            "start_time": 0.0,
                            "duration": 3.5,
                        }
                    )
                    known_files.add(path.name)
    return entries


def get_meme_metadata(library_dir: Path, meme_file_or_name: Path | str) -> dict[str, Any]:
    """Lấy thông tin metadata cao trào của 1 clip meme."""
    name = (
        meme_file_or_name.name
        if isinstance(meme_file_or_name, Path)
        else Path(meme_file_or_name).name
    )
    for m in load_memes_metadata(library_dir):
        if m.get("file") == name:
            return m
    return {
        "file": name,
        "tags": [],
        "emojis": [],
        "start_time": 0.0,
        "duration": 3.5,
    }


def find_meme_by_emojis(
    library_dir: Path,
    text: str,
    used_memes: set[str] | None = None,
) -> Path | None:
    """Nhận diện cụm emoji cuối câu (vd: 🤬🔨🔥, 🤣🤣🤣, 👁️👄👁️) và xoay vòng meme không lặp lại."""
    memes_dir = get_memes_dir(library_dir)
    meta_list = load_memes_metadata(library_dir)

    # 1. Tìm tất cả meme khớp emoji đạt điểm cao nhất (kèm tag chính nếu cần fallback xoay vòng)
    scored: list[tuple[int, Path, list[str]]] = []
    for m in meta_list:
        emojis = m.get("emojis", [])
        score = sum(text.count(em) for em in emojis)
        if score > 0:
            cand = memes_dir / m["file"]
            if cand.is_file():
                scored.append((score, cand, m.get("tags", [])))

    if scored:
        max_score = max(s for s, _, _ in scored)
        top_cands = [p for s, p, _ in scored if s == max_score]
        if used_memes is not None:
            unused = [p for p in top_cands if p.name not in used_memes]
            if unused:
                chosen = random.choice(unused)
                used_memes.add(chosen.name)
                return chosen
            # Nếu ứng viên khớp trực tiếp đã dùng hết -> xoay vòng trong cùng nhóm tag
            first_tags = scored[0][2]
            if first_tags:
                tag_pick = pick_sticker(library_dir, first_tags[0], used_memes=used_memes)
                if tag_pick is not None:
                    return tag_pick
            # Fallback nếu tag chỉ có duy nhất clip này: reset và chọn lại
            used_memes.difference_update({p.name for p in top_cands})
            chosen = random.choice(top_cands)
            used_memes.add(chosen.name)
            return chosen
        return random.choice(top_cands)

    # 2. So khớp theo nhóm cảm xúc emoji chung kèm xoay vòng used_memes
    if "👁️👄👁️" in text or "👁👄👁" in text:
        return pick_sticker(library_dir, "soc", used_memes=used_memes)

    scores = {}
    for tag, emojis in EMOJI_TAG_MAP.items():
        score = sum(text.count(em) for em in emojis)
        if score > 0:
            scores[tag] = score
    if scores:
        best_tag = max(scores.items(), key=lambda x: x[1])[0]
        return pick_sticker(library_dir, best_tag, used_memes=used_memes)

    return None


def load_index(library_dir: Path) -> dict[str, list[str]]:
    """Đọc index.json và tổng hợp danh sách file theo từng tag hợp lệ."""
    metadata = load_memes_metadata(library_dir)
    res = {tag: [] for tag in sorted(VALID_STICKER_TAGS)}
    for item in metadata:
        fname = item.get("file", "")
        for t in item.get("tags", []):
            if t in res and fname and fname not in res[t]:
                res[t].append(fname)
    return res


def count_stickers_per_tag(library_dir: Path) -> dict[str, int]:
    """Đếm số meme/sticker theo từng tag."""
    index = load_index(library_dir)
    return {tag: len(index.get(tag, [])) for tag in sorted(VALID_STICKER_TAGS)}


def pick_sticker(
    library_dir: Path,
    tag: str,
    seed: int = 0,  # Giữ tham số tương thích ngược, dùng random.choice xoay vòng
    used_memes: set[str] | None = None,
) -> Path | None:
    """Chọn ngẫu nhiên file meme/sticker theo tag, loại trừ `used_memes` và tự reset khi hết kho."""
    _ = seed
    if tag not in VALID_STICKER_TAGS:
        logger.warning("Tag sticker không hợp lệ: %s", tag)
        return None

    memes_dir = get_memes_dir(library_dir)
    index = load_index(library_dir)
    files = index.get(tag, [])

    if not files:
        logger.warning("Tag '%s' chưa có file meme nào trong %s", tag, memes_dir)
        return None

    # Gom toàn bộ đường dẫn tồn tại trên đĩa
    existing_paths: list[Path] = []
    for fname in files:
        full_path = memes_dir / fname
        if full_path.is_file():
            existing_paths.append(full_path)
            continue
        sub_path = memes_dir / tag / fname
        if sub_path.is_file():
            existing_paths.append(sub_path)

    if not existing_paths:
        logger.warning("File meme không tồn tại trong %s cho tag '%s'", memes_dir, tag)
        return None

    if used_memes is None:
        return random.choice(existing_paths)

    unused = [p for p in existing_paths if p.name not in used_memes]
    if not unused:
        # Toàn bộ kho clip của tag đã dùng hết -> reset nhóm clip này để xoay vòng lượt mới
        used_memes.difference_update({p.name for p in existing_paths})
        unused = existing_paths

    chosen = random.choice(unused)
    used_memes.add(chosen.name)
    return chosen


def extract_meme_audio(
    meme_file: Path,
    out_wav: Path,
    start_time: float = 0.0,
    max_duration: float = 3.5,
) -> bool:
    """Trích xuất âm thanh gốc từ clip meme tại mốc cao trào (-ss start_time -t duration)."""
    if not meme_file.is_file():
        return False
    if meme_file.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
        return False

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "-y",
        "-v",
        "error",
    ]
    if start_time > 0:
        cmd.extend(["-ss", f"{start_time:.2f}"])
    cmd.extend(
        [
            "-i",
            str(meme_file),
            "-t",
            str(max_duration),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ]
    )
    try:
        run_ffmpeg(cmd)
        return out_wav.is_file() and out_wav.stat().st_size > 1000
    except Exception as e:
        logger.warning("Không trích được audio từ meme %s: %s", meme_file, e)
        return False


def remove_green_screen(img: Image.Image) -> Image.Image:
    """Tách phông xanh lá (colorkey #00FF00) sang nền trong suốt qua bytearray."""
    rgba = img.convert("RGBA")
    raw_bytes = bytearray(rgba.tobytes())
    for i in range(0, len(raw_bytes), 4):
        r = raw_bytes[i]
        g = raw_bytes[i + 1]
        b = raw_bytes[i + 2]
        a = raw_bytes[i + 3]
        if g > 115 and g > r * 1.25 and g > b * 1.25:
            raw_bytes[i + 3] = 0
        elif g > 100 and g > r * 1.15 and g > b * 1.15:
            edge_alpha = max(0, int(a * (1.0 - (g - max(r, b)) / 60.0)))
            raw_bytes[i + 3] = edge_alpha

    return Image.frombytes("RGBA", rgba.size, bytes(raw_bytes))


def load_sticker_or_meme_image(
    file_path: Path, cache_dir: Path | None = None, start_time: float = 0.0
) -> Image.Image | None:
    """Nạp ảnh sticker từ file ảnh hoặc trích frame video meme phông xanh tại mốc cao trào."""
    if not file_path.is_file():
        return None

    ext = file_path.suffix.lower()

    # 1. Nếu là file ảnh tĩnh
    if ext in SUPPORTED_IMAGE_EXTS:
        try:
            return Image.open(file_path).convert("RGBA")
        except Exception as e:
            logger.warning("Lỗi mở ảnh %s: %s", file_path, e)
            return None

    # 2. Nếu là clip video phông xanh (mp4, mov, webm)
    if ext in SUPPORTED_VIDEO_EXTS:
        st_tag = int(start_time * 10)
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            frame_png = cache_dir / f"{file_path.stem}_s{st_tag}.png"
        else:
            frame_png = file_path.with_suffix(f".thumb_s{st_tag}.png")

        if not frame_png.is_file():
            try:
                ss_pos = round(start_time + 0.3, 2)
                run_ffmpeg(
                    [
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        str(ss_pos),
                        "-i",
                        str(file_path),
                        "-vframes",
                        "1",
                        str(frame_png),
                    ]
                )
            except Exception as e:
                logger.warning("Lỗi trích frame từ video meme %s: %s", file_path, e)
                return None

        if frame_png.is_file():
            try:
                raw_img = Image.open(frame_png)
                return remove_green_screen(raw_img)
            except Exception as e:
                logger.warning("Lỗi xử lý frame meme %s: %s", frame_png, e)
                return None

    return None
