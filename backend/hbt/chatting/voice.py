"""Tạo giọng VieNeu cho từng tin nhắn Chatting theo §9 (dùng lại voice_worker của PostV)."""

from __future__ import annotations

import hashlib
import logging
import re
import wave
from pathlib import Path

from hbt.chatting.models import ChatDoc
from hbt.chatting.sources import is_scene_transition
from hbt.pipeline.ffutil import media_duration
from hbt.postv.censor import CensorStore, compile_censor, find_censor_hits
from hbt.postv.voice import SynthItem, VoiceProvider

logger = logging.getLogger(__name__)

DEFAULT_CHAR_VOICES = {
    "me": "Adam bựa",
    "left_1": "Trúc Ly",
    "left_2": "Thiện Minh",
    "left_3": "Mai Anh",
}

FEMALE_VOICES: tuple[str, ...] = ("Trúc Ly", "Mai Anh", "Thùy Dung")
MALE_VOICES: tuple[str, ...] = ("Adam bựa", "Thiện Minh", "Hải Đăng")

_FEMALE_NAME_HINTS = (
    "linh",
    "huong",
    "hương",
    "trang",
    "mai",
    "lan",
    "ngoc",
    "ngọc",
    "thao",
    "thảo",
    "nhi",
    "vy",
    "my",
    "truc",
    "trúc",
    "hoa",
    "yen",
    "yến",
    "quynh",
    "quỳnh",
    "nga",
    "chi",
    "phuong",
    "phương",
    "nhung",
    "oanh",
    "huyen",
    "huyền",
    "ngan",
    "ngân",
    "dung",
    "thuy",
    "thùy",
    "thuý",
    "thúy",
    "van",
    "vân",
    "mẹ",
    "chị",
    "cô",
    "em gái",
    "vợ",
    "bạn gái",
    "nữ",
)

_MALE_NAME_HINTS = (
    "nam",
    "minh",
    "hung",
    "hùng",
    "tuan",
    "tuấn",
    "dung",
    "dũng",
    "hai",
    "hải",
    "dang",
    "đăng",
    "khanh",
    "khánh",
    "bao",
    "bảo",
    "huy",
    "khang",
    "khoa",
    "duc",
    "đức",
    "long",
    "phong",
    "quan",
    "quân",
    "son",
    "sơn",
    "tung",
    "tùng",
    "bố",
    "ba",
    "chú",
    "thầy",
    "chồng",
    "bạn trai",
    "anh trai",
)

_FEMALE_PRONOUN_RE = re.compile(
    r"\b(?:bà|chị|em gái|con nhỏ|bà ơi|bà nội|chị em|bà già|mấy bà)\b",
    re.IGNORECASE,
)
_MALE_PRONOUN_RE = re.compile(
    r"\b(?:ông ơi|thằng|anh trai|bố mày|cha nội|mấy ông)\b",
    re.IGNORECASE,
)


def infer_character_gender(
    name: str,
    *,
    explicit_gender: str | None = None,
    dialogue_samples: list[str] | None = None,
) -> str:
    """Xác định giới tính nhân vật ('female' | 'male') từ trường tường minh, tên hoặc xưng hô."""
    eg = str(explicit_gender or "").strip().lower()
    if eg in ("female", "male"):
        return eg

    low_name = (name or "").strip().lower()
    name_tokens = set(re.findall(r"[a-zà-ỹ]+", low_name))

    # Ưu tiên khớp tên riêng / danh xưng
    if any((h in low_name if " " in h else h in name_tokens) for h in _FEMALE_NAME_HINTS):
        return "female"
    if any((h in low_name if " " in h else h in name_tokens) for h in _MALE_NAME_HINTS):
        return "male"

    # Fallback theo xưng hô trong lời thoại
    joined = " ".join(dialogue_samples or [])
    fem_hits = len(_FEMALE_PRONOUN_RE.findall(joined))
    male_hits = len(_MALE_PRONOUN_RE.findall(joined))
    if fem_hits > male_hits:
        return "female"
    if male_hits > fem_hits:
        return "male"
    return "male"


def assign_character_voices(
    characters: list[dict[str, object]],
    messages: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Gán giọng VieNeu khớp giới tính nữ/nam cho danh sách nhân vật (không gán nhầm giọng)."""
    msgs_by_char: dict[str, list[str]] = {}
    all_texts: list[str] = []
    for m in messages or []:
        cid = str(m.get("from") or "")
        txt = str(m.get("text") or "")
        msgs_by_char.setdefault(cid, []).append(txt)
        all_texts.append(txt)

    # Nếu đối phương gọi nhân vật bằng "bà"/"chị", nhân vật đó cũng là nữ
    addressed_fem = any(re.search(r"\b(?:bà|chị|bà ơi)\b", t, re.IGNORECASE) for t in all_texts)

    f_idx = 0
    m_idx = 0
    for c in characters:
        cid = str(c.get("id") or "")
        name = str(c.get("name") or "")
        explicit = c.get("gender")
        # Gộp lời thoại của chính nhân vật và câu đối phương xưng hô để suy đoán chính xác
        samples = list(msgs_by_char.get(cid, []))
        if addressed_fem and not explicit and not samples:
            samples = all_texts
        gender = infer_character_gender(
            name,
            explicit_gender=str(explicit) if explicit else None,
            dialogue_samples=samples or (all_texts if addressed_fem else []),
        )
        c["gender"] = gender
        cur_voice = str(c.get("voice") or "").strip()
        if gender == "female":
            if cur_voice not in FEMALE_VOICES:
                c["voice"] = FEMALE_VOICES[f_idx % len(FEMALE_VOICES)]
            f_idx += 1
        else:
            if cur_voice not in MALE_VOICES:
                c["voice"] = MALE_VOICES[m_idx % len(MALE_VOICES)]
            m_idx += 1
    return characters


# Chỉ lọc mốc giờ UI dạng hh:mm (20:15, 10:30 PM); giữ nguyên "2h sáng", "9 giờ 30" trong lời thoại
TIME_PATTERNS = [
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b"),
]

_TTS_SLANG_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(\d{1,2})h(\d{1,2})\b", re.IGNORECASE), r"\1 giờ \2"),
    (re.compile(r"\b(\d{1,2})h\b", re.IGNORECASE), r"\1 giờ"),
    (re.compile(r"\b(\d+)p\b", re.IGNORECASE), r"\1 phút"),
    (re.compile(r"\b(\d+)k\b", re.IGNORECASE), r"\1 nghìn"),
    (re.compile(r"\brep\b", re.IGNORECASE), "rép"),
    (re.compile(r"\bcrush\b", re.IGNORECASE), "cờ rớt"),
    (re.compile(r"\b(?:inbox|ib)\b", re.IGNORECASE), "in bốc"),
    (re.compile(r"\bfb\b", re.IGNORECASE), "phây búc"),
)


def normalize_vietnamese_for_tts(text: str) -> str:
    """Chuẩn hóa giờ viết tắt & từ lóng chat sang cách đọc tiếng Việt tự nhiên cho VieNeu-TTS."""
    s = (text or "").strip()
    if not s:
        return ""
    for pat, repl in _TTS_SLANG_RULES:
        s = pat.sub(repl, s)
    return re.sub(r"\s+", " ", s).strip()


META_PATTERNS = [
    re.compile(r"\[(?:sticker|meme|ảnh|video|voice|audio|image|gif)[^\]]*\]", re.IGNORECASE),
    re.compile(r"\b(?:đã xem|đã gửi|đã nhận|seen|active\s*\d+\w*\s*ago)\b", re.IGNORECASE),
]

PAREN_ACTION_PATTERN = re.compile(r"\(.*?\)", re.DOTALL)
BRACKET_META_PATTERN = re.compile(r"\[.*?\]", re.DOTALL)

EMOJI_REGEX = re.compile(
    r"(\u00a9|\u00ae|[\u2000-\u3300]|\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|[\U00010000-\U0010ffff])"
    r"(?:[\ufe00-\ufe0f]|[\U0001F3FB-\U0001F3FF]|\u200d(?:\u00a9|\u00ae|[\u2000-\u3300]|\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|[\U00010000-\U0010ffff])(?:[\ufe00-\ufe0f]|[\U0001F3FB-\U0001F3FF])?)*",
    re.UNICODE,
)


def clean_spoken_text(text: str) -> str:
    """Tách sạch lời thoại để TTS VieNeu chỉ đọc câu nói thuần túy của nhân vật:
    lọc sạch toàn bộ emoji, mốc thời gian, ký tự hành động trong ngoặc đơn (...),
    và các trạng thái [seen], [sticker]...
    """
    if is_scene_transition(text):
        return ""

    s = text.strip()
    for p in TIME_PATTERNS:
        s = p.sub("", s)
    for p in META_PATTERNS:
        s = p.sub("", s)
    s = PAREN_ACTION_PATTERN.sub("", s)
    s = BRACKET_META_PATTERN.sub("", s)
    s = EMOJI_REGEX.sub("", s)
    # Dọn dẹp khoảng trắng dư thừa
    s = re.sub(r"\s+", " ", s).strip()
    # Nếu chỉ còn dấu câu lẻ loi (vd: '-', ':', '·', '—') thì coi như rỗng
    if re.fullmatch(r"[-—:.,;~·!?\s]*", s):
        return ""
    return s


def get_voice_cache_dir(project_dir: Path) -> Path:
    d = project_dir / "build" / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def text_hash(voice_id: str, text: str) -> str:
    s = f"{voice_id}:{text.strip()}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


def create_placeholder_wav(dest: Path, duration_s: float, sample_rate: int = 24000) -> None:
    """Tạo file wav giữ chỗ (âm thanh mẫu/yên lặng) khi TTS chưa sẵn sàng."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    num_frames = int(duration_s * sample_rate)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Ghi các sample 0 (yên lặng)
        wf.writeframes(b"\x00\x00" * num_frames)


def get_wav_duration(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return round(frames / float(rate), 3)
    except Exception:
        dur = media_duration(wav_path)
        return dur if dur is not None else 1.0


def check_censor_text(workspace_dir: Path, text: str) -> bool:
    """Kiểm tra có từ che K-41 trong text không."""
    try:
        store = CensorStore(workspace_dir)
        matchers = compile_censor(store.load().words)
        hits = find_censor_hits(text, matchers)
        return len(hits) > 0
    except Exception:
        return False


def synthesize_chat_voices(
    workspace_dir: Path,
    slug: str,
    doc: ChatDoc,
    voice_provider: VoiceProvider,
) -> list[tuple[int, Path, float]]:
    """Sinh giọng cho toàn bộ tin nhắn trong doc.
    Trả về danh sách: [(message_index, wav_path, duration_s), ...]
    """
    project_dir = workspace_dir / "chatting" / slug
    cache_dir = get_voice_cache_dir(project_dir)

    char_map = {c.id: c for c in doc.characters}
    results: list[tuple[int, Path, float]] = []
    items_to_synth: list[tuple[int, SynthItem]] = []

    # Kiểm tra trạng thái TTS
    status = voice_provider.status() if hasattr(voice_provider, "status") else None
    tts_ready = status.ok if status else False

    for idx, msg in enumerate(doc.messages):
        char = char_map.get(msg.from_)
        voice_id = char.voice if char and char.voice else DEFAULT_CHAR_VOICES.get("me", "Adam bựa")
        raw_spoken = (
            msg.spoken_text
            if getattr(msg, "spoken_text", None) is not None
            else clean_spoken_text(msg.text)
        )
        spoken = normalize_vietnamese_for_tts(raw_spoken)

        # Nếu là chuyển cảnh ngoặc đơn hoặc sau khi lọc lời thoại mà rỗng
        is_trans = is_scene_transition(msg.text)
        if is_trans or not spoken:
            dur = 1.2 if is_trans else 1.0
            h = text_hash(voice_id, f"transition_{idx}" if is_trans else f"empty_{idx}")
            out_file = cache_dir / f"silent_{h}.wav"
            if not (out_file.is_file() and out_file.stat().st_size > 44):
                create_placeholder_wav(out_file, dur)
            results.append((idx, out_file, dur))
            continue

        h = text_hash(voice_id, spoken)
        out_file = cache_dir / f"{h}.wav"

        if out_file.is_file() and out_file.stat().st_size > 44:
            results.append((idx, out_file, get_wav_duration(out_file)))
        else:
            items_to_synth.append((idx, SynthItem(text=spoken, voice_id=voice_id, out=out_file)))

    if items_to_synth:
        if tts_ready:
            try:
                synth_list = [item for _, item in items_to_synth]
                voice_provider.synthesize_many(synth_list)
                for idx, item in items_to_synth:
                    dur = get_wav_duration(item.out)
                    results.append((idx, item.out, dur))
            except Exception as e:
                logger.warning("VieNeu synthesize_many thất bại: %s, dùng âm thanh giữ chỗ", e)
                for idx, item in items_to_synth:
                    dur = max(1.0, round(len(item.text) / 14.0, 2))
                    create_placeholder_wav(item.out, dur)
                    results.append((idx, item.out, dur))
        else:
            # Fallback tạo placeholder wav nếu chưa cài hoặc thiếu weights
            for idx, item in items_to_synth:
                dur = max(1.0, round(len(item.text) / 14.0, 2))
                create_placeholder_wav(item.out, dur)
                results.append((idx, item.out, dur))

    results.sort(key=lambda r: r[0])
    return results
