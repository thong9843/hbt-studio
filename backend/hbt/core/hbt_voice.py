"""Giọng VieNeu cho dự án HBT (IMPLEMENT-GD2 mục 6 G3, E4).

Khác PostV (K-33 gửi nguyên văn cho VieNeu): lời HBT có `{cách đọc}` và `|` nên phải tiền xử lý:
- `hiển thị{cách đọc}` → "cách đọc" (bỏ chữ hiển thị trước `{}`, giữ dấu câu ngay sau `}`);
- `|` → ngắt thành đoạn mới, nghỉ 0,25 s;
- mỗi cảnh một hay nhiều đoạn, nối bằng khoảng im 0,25 s (`GAP_SECONDS`) → `voice.wav`.
Dùng lại bộ sinh giọng, cache và hàm nối WAV của PostV; không đụng `pipeline/`."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.models import Project
from hbt.pipeline.text import RAW_TOKEN_RE, TOKEN_RE
from hbt.postv.voice import (
    GAP_SECONDS,
    SynthItem,
    VoiceError,
    VoiceProvider,
    cache_key,
    join_wavs,
)
from hbt.storage import _remove_siblings

META_FILE = "hbt_voice.json"  # trong `build/`
Progress = Callable[[float, str, str], None]


def spoken_chunks(voice: str) -> list[str]:
    """Lời đọc của một cảnh → các đoạn gửi VieNeu (đã xử lý `{}` và `|`, bỏ đoạn rỗng)."""
    chunks: list[list[str]] = [[]]
    for raw in RAW_TOKEN_RE.findall(voice):
        if raw == "|":
            chunks.append([])
            continue
        m = TOKEN_RE.match(raw)
        word = (m.group("spoken").strip() + m.group("punct")) if m else raw
        if word.strip():
            chunks[-1].append(word.strip())
    return [" ".join(c) for c in chunks if c]


@dataclass
class HbtChunk:
    scene: int  # chỉ số cảnh (từ 0)
    text: str
    voice_id: str

    @property
    def key(self) -> str:
        return cache_key(self.text, self.voice_id)


def build_hbt_plan(project: Project, voice_id: str) -> list[HbtChunk]:
    plan = [
        HbtChunk(i, text, voice_id)
        for i, scene in enumerate(project.scenes)
        for text in spoken_chunks(scene.voice)
    ]
    if not plan:
        raise VoiceError("Chưa có cảnh nào có lời đọc")
    return plan


def plan_signature(plan: Sequence[HbtChunk]) -> str:
    raw = "|".join(f"{c.scene}:{c.key}" for c in plan)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def voiced_scene_count(plan: Sequence[HbtChunk]) -> int:
    return len({c.scene for c in plan})


@dataclass
class HbtVoiceResult:
    file: Path
    seconds: float
    scenes: list[dict]
    generated: int
    cached: int
    signature: str


def synthesize_hbt(
    plan: Sequence[HbtChunk],
    folder: Path,
    provider: VoiceProvider,
    progress: Progress | None = None,
) -> HbtVoiceResult:
    """Sinh (bỏ qua đoạn đã có trong cache `build/voice/`), nối, thay `voice.*` cũ bằng `voice.wav`.

    Tiến độ 3→95 % theo số đoạn, thông báo theo cảnh ("Đang đọc cảnh x/N"), rồi nối."""
    total = len(plan)
    n_scenes = voiced_scene_count(plan)
    order = {s: k + 1 for k, s in enumerate(dict.fromkeys(c.scene for c in plan))}
    cache = folder / "build" / "voice"
    cache.mkdir(parents=True, exist_ok=True)

    def report(done: int, msg: str) -> None:
        if progress:
            progress(3 + 92 * done / max(total, 1), "voice", msg)

    paths = [cache / f"{c.key}.wav" for c in plan]
    todo = [k for k, path in enumerate(paths) if not path.is_file()]
    cached = total - len(todo)
    if cached:
        report(cached, f"Dùng lại {cached}/{total} đoạn đã có")
    if todo:
        items = [SynthItem(plan[k].text, plan[k].voice_id, paths[k]) for k in todo]

        def on_item(i: int, state: str) -> None:
            chunk = plan[todo[i]]
            n = order[chunk.scene]
            done = cached + i + (1 if state == "done" else 0)
            verb = "Đang đọc" if state == "begin" else "Xong"
            report(done, f"{verb} cảnh {n}/{n_scenes}")

        provider.synthesize_many(items, on_item)
    if progress:
        progress(96, "voice", "Đang nối các cảnh")

    build = folder / "build"
    joined = build / "hbt_voice.joined.wav"
    spans = join_wavs(paths, joined, GAP_SECONDS)
    _remove_siblings(folder, "voice")  # bản cũ (mp3, wav tải lên…) không còn đúng
    out = folder / "voice.wav"
    os.replace(joined, out)

    scenes: list[dict] = []
    for chunk, (a, b) in zip(plan, spans, strict=True):
        if scenes and scenes[-1]["scene"] == chunk.scene:
            scenes[-1]["end"] = b
        else:
            scenes.append({"scene": chunk.scene, "start": a, "end": b})
    sig = plan_signature(plan)
    seconds = spans[-1][1]
    meta = {
        "signature": sig,
        "voice_id": plan[0].voice_id,
        "sha256": _sha256(out),
        "seconds": seconds,
        "scenes": scenes,
    }
    (build / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return HbtVoiceResult(out, seconds, scenes, len(todo), cached, sig)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_meta(folder: Path) -> dict | None:
    path = folder / "build" / META_FILE
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) and "signature" in meta else None


def from_vieneu(project: Project, folder: Path) -> dict | None:
    """Meta của lần sinh VieNeu nếu `voice.wav` hiện tại đúng là file đó (so băm), ngược lại None.

    Thả file Vbee đuôi .wav sẽ ghi đè `voice.wav` nên không thể chỉ dựa vào tên file."""
    meta = read_meta(folder)
    v = project.voice
    if meta is None or v is None or v.file != "voice.wav":
        return None
    path = folder / "voice.wav"
    if not path.is_file() or meta.get("sha256") != _sha256(path):
        return None
    return meta


def is_stale(project: Project, folder: Path) -> bool | None:
    """Lời đã đổi sau lần sinh giọng VieNeu chưa? None = không rõ (không có `hbt_voice.json`,
    hoặc giọng hiện tại không phải file VieNeu đã sinh, vd thả file Vbee)."""
    meta = from_vieneu(project, folder)
    if meta is None:
        return None
    voice_id = meta.get("voice_id")
    if not isinstance(voice_id, str):
        return None
    try:
        plan = build_hbt_plan(project, voice_id)
    except VoiceError:
        return True  # đã sinh nhưng giờ không còn lời nào
    return meta["signature"] != plan_signature(plan)
