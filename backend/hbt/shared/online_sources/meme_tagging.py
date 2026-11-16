"""Tự động gắn tag/chủ đề và khớp ngữ cảnh thông minh cho kho Meme (`library/memes/index.json`)."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from hbt.pipeline.ffutil import media_duration

# Bộ từ khóa ánh xạ tag chuẩn hóa -> (từ khóa tiếng Anh/Việt, mô tả chủ đề mặc định)
TAG_RULES: list[tuple[str, tuple[str, ...], str]] = [
    (
        "bat_ngo",
        (
            "shock",
            "shocked",
            "surprise",
            "omg",
            "what",
            "wtf",
            "soc",
            "bat ngo",
            "ngac nhien",
            "speed",
        ),
        "Bất ngờ ngã ngửa khi nghe tin sốc",
    ),
    (
        "hai_huoc",
        ("laugh", "funny", "lol", "haha", "meme", "cuoi", "hai", "giggle", "hehe", "goat", "hyena"),
        "Cười khoái chí trước tình huống hài hước",
    ),
    (
        "ca_khia",
        ("smirk", "side eye", "troll", "sassy", "ca khia", "kheo", "coy", "wink"),
        "Cà khịa nhẹ nhàng đầy ẩn ý",
    ),
    (
        "that_vong",
        ("sad", "disappointed", "fail", "bruh", "rip", "cry", "khoc", "that vong", "chan", "buon"),
        "Thất vọng, bất lực trước sự thật phũ phàng",
    ),
    (
        "tuc_gian",
        ("angry", "mad", "rage", "furious", "gian", "tuc", "cay", "trump"),
        "Tức giận bùng nổ trước câu chuyện vô lý",
    ),
    (
        "ngai_ngung",
        ("awkward", "shy", "embarrassed", "ngai", "nguong", "nervous"),
        "Ngại ngùng, sượng trân không biết nói gì",
    ),
    (
        "vo_tay",
        ("clap", "applause", "bravo", "congrats", "vo tay", "chuc mung", "nice", "ok", "thumbs"),
        "Vỗ tay tán thưởng hoặc chốt kèo thành công",
    ),
    (
        "drama",
        ("drama", "tea", "gossip", "popcorn", "hóng", "hong", "cang", "twist"),
        "Hóng drama căng thẳng, tình tiết bất ngờ",
    ),
    (
        "meo",
        ("cat", "kitty", "meow", "meo", "kitten"),
        "Biểu cảm mèo đáng yêu hoặc ngơ ngác",
    ),
    (
        "tien_bac",
        ("money", "cash", "rich", "broke", "salary", "tien", "luong", "chuyen khoan", "gia"),
        "Phản ứng về tiền bạc, lương thưởng hoặc chi tiêu",
    ),
]

TAG_KEYWORDS: dict[str, tuple[str, ...]] = {tag: kws for tag, kws, _ in TAG_RULES}
TAG_TOPICS: dict[str, str] = {tag: topic for tag, _, topic in TAG_RULES}


def _fold_text(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (text or "").lower())
    no_marks = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s_]+", " ", no_marks.replace("-", " ").replace("_", " "))


def normalize_tags(raw_tags: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in raw_tags or []:
        clean = re.sub(r"[^a-z0-9_]+", "_", _fold_text(t).strip()).strip("_")
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def auto_tag_meme(
    title: str,
    tags_hint: list[str] | None = None,
    *,
    use_gemini: bool = False,
) -> tuple[list[str], str]:
    """Tự động sinh `tags` và `topic` ngắn gọn từ tên file/tiêu đề và gợi ý gốc."""
    combined = f"{title} {' '.join(tags_hint or [])}".strip()
    folded = _fold_text(combined)

    matched_tags: list[str] = []
    matched_topics: list[str] = []
    for tag, kws, topic in TAG_RULES:
        if any(kw in folded for kw in kws):
            matched_tags.append(tag)
            if not matched_topics:
                matched_topics.append(topic)

    # Giữ thêm tag gợi ý gốc đã chuẩn hóa nếu có
    for extra in normalize_tags(tags_hint):
        if extra not in matched_tags and len(matched_tags) < 6:
            matched_tags.append(extra)

    if not matched_tags:
        matched_tags = ["hai_huoc", "drama"]
    topic = matched_topics[0] if matched_topics else f"Biểu cảm minh họa: {title.strip()[:80]}"
    return matched_tags, topic


def load_memes_index(memes_dir: Path) -> list[dict[str, Any]]:
    idx_path = memes_dir / "index.json"
    if not idx_path.is_file():
        return []
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_memes_index(memes_dir: Path, items: list[dict[str, Any]]) -> None:
    memes_dir.mkdir(parents=True, exist_ok=True)
    idx_path = memes_dir / "index.json"
    tmp = idx_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, idx_path)


def batch_auto_tag_memes(memes_dir: Path, *, use_gemini: bool = False) -> dict[str, Any]:
    """Quét toàn bộ thư mục meme, chuẩn hóa metadata và tự gắn tag/topic cho các mục còn thiếu."""
    memes_dir.mkdir(parents=True, exist_ok=True)
    items = load_memes_index(memes_dir)
    by_file = {str(it.get("file", "")): it for it in items if isinstance(it, dict)}

    updated = 0
    for p in sorted(memes_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in {
            ".mp4",
            ".mov",
            ".webm",
            ".gif",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:
            continue
        if p.name.endswith("_thumb.jpg") or p.name == "index.json":
            continue
        entry = by_file.get(p.name)
        if entry is None:
            entry = {
                "id": p.stem,
                "file": p.name,
                "title": p.stem.replace("-", " ").replace("_", " ").strip(),
                "source": "local",
                "thumb": f"{p.stem}_thumb.jpg"
                if (memes_dir / f"{p.stem}_thumb.jpg").is_file()
                else "",
            }
            items.append(entry)
            by_file[p.name] = entry

        if not entry.get("duration_sec") and p.suffix.lower() in {".mp4", ".mov", ".webm", ".gif"}:
            try:
                dur = media_duration(p)
            except Exception:
                dur = 0.0
            if dur:
                entry["duration_sec"] = round(float(dur), 2)

        existing_tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
        existing_topic = str(entry.get("topic") or "").strip()
        if not existing_tags or not existing_topic:
            tags, topic = auto_tag_meme(
                str(entry.get("title") or p.stem),
                existing_tags,
                use_gemini=use_gemini,
            )
            if not existing_tags:
                entry["tags"] = tags
            if not existing_topic:
                entry["topic"] = topic
            updated += 1

    save_memes_index(memes_dir, items)
    return {"ok": True, "total": len(items), "updated": updated, "items": items}


def update_meme_metadata(
    memes_dir: Path,
    meme_id: str,
    *,
    tags: list[str] | None = None,
    topic: str | None = None,
    title: str | None = None,
) -> dict[str, Any] | None:
    items = load_memes_index(memes_dir)
    target: dict[str, Any] | None = None
    for it in items:
        if str(it.get("id")) == meme_id or str(it.get("file")) == meme_id:
            if tags is not None:
                it["tags"] = normalize_tags(tags)
            if topic is not None:
                it["topic"] = topic.strip()
            if title is not None and title.strip():
                it["title"] = title.strip()
            target = it
            break
    if target is not None:
        save_memes_index(memes_dir, items)
    return target


def match_meme_by_context(
    text: str,
    memes_index: list[dict[str, Any]],
    *,
    used_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """So khớp câu thoại với `tags` và `topic` trong `index.json` để chọn đúng meme ngữ cảnh."""
    if not memes_index:
        return None
    used = used_ids or set()
    folded_text = _fold_text(text)

    # Suy luận các tag cảm xúc từ câu thoại
    inferred_tags: set[str] = set()
    for tag, kws, _ in TAG_RULES:
        if any(kw in folded_text for kw in kws):
            inferred_tags.add(tag)

    best_item: dict[str, Any] | None = None
    best_score = 0.0
    text_words = {w for w in folded_text.split() if len(w) >= 2}

    for item in memes_index:
        mid = str(item.get("id") or item.get("file") or "")
        if not mid or mid in used:
            continue
        item_tags = {str(t).lower() for t in (item.get("tags") or [])}
        topic_words = {w for w in _fold_text(str(item.get("topic") or "")).split() if len(w) >= 2}
        title_words = {w for w in _fold_text(str(item.get("title") or "")).split() if len(w) >= 2}

        score = 0.0
        score += len(inferred_tags & item_tags) * 3.0
        score += len(text_words & topic_words) * 1.5
        score += len(text_words & title_words) * 1.0
        if score > best_score:
            best_score = score
            best_item = item

    return best_item
