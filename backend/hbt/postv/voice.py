"""Giọng đọc PostV: VieNeu-TTS qua tiến trình con, giọng nhập file, giọng giả cho CI (6c, 6d).

`VoiceProvider` là cổng của IMPLEMENT.md mục 12 (`synthesize(text, voice_id) -> bytes`), thêm
`synthesize_many` để một tiến trình con nạp mô hình một lần rồi đọc nhiều đoạn. `VieNeuProvider`
chạy `voice_worker.py` bằng Python của `backend/.venv-tts`; trọng số chỉ đọc ở `models/hf_vieneu`
và không bao giờ tải từ mạng (N4). `FileVoice` là đường nhập file (không sinh gì).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from hbt.pipeline import cancel
from hbt.postv.models import PostvProject

BACKEND_DIR = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("voice_worker.py")
VIENEU_VERSION = "3.8.3"  # khớp backend/requirements-tts.txt
WORKER_REV = 2  # đổi khi cách sinh giọng đổi (vô hiệu cache)
WEIGHTS_REPO = "models--pnnbao-ump--VieNeu-TTS-v3-Turbo"
DEFAULT_NARRATOR = "Adam bựa"  # K-35: giọng mặc định của người dẫn
GAP_SECONDS = 0.25  # khoảng nghỉ giữa hai đoạn (6d)
CHARS_PER_SECOND = 16.5  # tốc độ đọc đo ở PV0 (6c)
POLL_SECONDS = 0.2
NARRATOR, POST = "narrator", "post"

ItemDone = Callable[[int, str], None]  # (chỉ số trong lô, "begin" | "done")


class VoiceError(RuntimeError):
    """Sinh giọng thất bại (lỗi worker, hết giờ, giọng không có…)."""


class VoiceUnavailable(VoiceError):
    """VieNeu chưa dùng được: chưa cài gói hoặc thiếu trọng số (API trả 503)."""


@dataclass(frozen=True)
class VoiceInfo:
    id: str
    label: str
    gender: str = ""  # "Nam" | "Nữ" | ""
    region: str = ""
    style: str = ""

    def view(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "gender": self.gender,
            "region": self.region,
            "style": self.style,
        }


@dataclass(frozen=True)
class VoiceStatus:
    installed: bool  # có venv-tts và gói vieneu
    weights: bool  # có trọng số ở models/hf_vieneu
    note: str = ""  # lời nhắn tiếng Việt khi chưa dùng được

    @property
    def ok(self) -> bool:
        return self.installed and self.weights


@dataclass(frozen=True)
class SynthItem:
    text: str
    voice_id: str
    out: Path  # file WAV đích


def parse_voice_label(label: str, voice_id: str) -> VoiceInfo:
    """`⭐ Adam bựa — Nam · Bắc · Phong cách tự nhiên` → giới tính, vùng, phong cách."""
    _, _, tail = label.partition(" — ")
    parts = [p.strip() for p in tail.split("·")] if tail else []
    parts += [""] * (3 - len(parts))
    return VoiceInfo(voice_id, label.lstrip("⭐ ").strip(), parts[0], parts[1], parts[2])


class VoiceProvider(Protocol):
    def status(self) -> VoiceStatus: ...

    def list_voices(self) -> list[VoiceInfo]: ...

    def synthesize(self, text: str, voice_id: str) -> bytes: ...

    def synthesize_many(self, items: Sequence[SynthItem], on_item: ItemDone | None = None) -> None:
        """Ghi từng `item.out` (WAV mono 16-bit). Ném VoiceError / RenderCancelled."""


class _SingleMixin:
    def synthesize(self, text: str, voice_id: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="hbt-voice-") as tmp:
            out = Path(tmp) / "one.wav"
            self.synthesize_many([SynthItem(text, voice_id, out)])
            return out.read_bytes()


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    proc.wait()


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


class VieNeuProvider(_SingleMixin):
    def __init__(
        self,
        models_dir: Path,
        venv: Path | None = None,
        cache_file: Path | None = None,
        timeout_base: float = 180.0,
    ):
        self.home = Path(models_dir) / "hf_vieneu"
        self.venv = venv or BACKEND_DIR / ".venv-tts"
        self.cache_file = cache_file
        self.timeout_base = timeout_base
        self._voices: list[VoiceInfo] | None = None

    # ---------------------------------------------------------------- trạng thái
    def status(self) -> VoiceStatus:
        site = [*self.venv.glob("Lib/site-packages/vieneu")]
        site += [*self.venv.glob("lib/*/site-packages/vieneu")]
        if not venv_python(self.venv).is_file() or not site:
            return VoiceStatus(
                False,
                False,
                "Chưa cài VieNeu. Chạy: python -m venv backend/.venv-tts rồi "
                "backend/.venv-tts/Scripts/python -m pip install -r backend/requirements-tts.txt "
                "(xem README).",
            )
        if not next((self.home / "hub" / WEIGHTS_REPO / "snapshots").glob("*"), None):
            return VoiceStatus(
                True,
                False,
                f"Thiếu trọng số VieNeu ở {self.home}. App không tự tải; chép thư mục "
                "models/hf_vieneu từ máy đã có (xem README).",
            )
        return VoiceStatus(True, True)

    def require(self) -> None:
        st = self.status()
        if not st.ok:
            raise VoiceUnavailable(st.note)

    # ---------------------------------------------------------------- danh sách giọng
    def list_voices(self) -> list[VoiceInfo]:
        if self._voices is not None:
            return self._voices
        cached = self._read_cache()
        if cached is not None:
            self._voices = cached
            return cached
        self.require()
        with tempfile.TemporaryDirectory(prefix="hbt-voice-") as tmp:
            data = self._run({"mode": "voices"}, Path(tmp), timeout=self.timeout_base)
        voices = [parse_voice_label(label, vid) for label, vid in data["voices"]]
        if not voices:
            raise VoiceError("VieNeu không trả giọng nào")
        self._voices = voices
        self._write_cache(voices)
        return voices

    def _read_cache(self) -> list[VoiceInfo] | None:
        if self.cache_file is None or not self.cache_file.is_file():
            return None
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if data.get("vieneu") != VIENEU_VERSION:
                return None
            return [VoiceInfo(**v) for v in data["voices"]] or None
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _write_cache(self, voices: list[VoiceInfo]) -> None:
        if self.cache_file is None:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {"vieneu": VIENEU_VERSION, "voices": [v.view() for v in voices]}
            self.cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass  # chỉ là bộ nhớ đệm

    # ---------------------------------------------------------------- sinh giọng
    def synthesize_many(self, items: Sequence[SynthItem], on_item: ItemDone | None = None) -> None:
        if not items:
            return
        self.require()
        for it in items:
            it.out.parent.mkdir(parents=True, exist_ok=True)
        est = sum(len(i.text) for i in items) / CHARS_PER_SECOND
        req = {
            "mode": "synth",
            "items": [{"text": i.text, "voice": i.voice_id, "out": str(i.out)} for i in items],
        }
        with tempfile.TemporaryDirectory(prefix="hbt-voice-") as tmp:
            self._run(req, Path(tmp), timeout=self.timeout_base + est * 3, on_item=on_item)
        missing = [i.out.name for i in items if not i.out.is_file()]
        if missing:
            raise VoiceError("VieNeu không ghi đủ file giọng: " + ", ".join(missing[:3]))

    def _run(
        self, req: dict, work: Path, *, timeout: float, on_item: ItemDone | None = None
    ) -> dict:
        out_path, err_path, prog = work / "out.json", work / "err.txt", work / "progress.txt"
        request = {
            **req,
            "hf_home": str(self.home.resolve()),
            "out": str(out_path),
            "progress": str(prog),
        }
        req_path = work / "req.json"
        req_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        cmd = [str(venv_python(self.venv)), "-I", "-X", "utf8", str(WORKER), str(req_path)]
        env = {**os.environ, "HF_HOME": request["hf_home"], "HF_HUB_OFFLINE": "1"}
        token = cancel.current()
        deadline = time.monotonic() + timeout
        seen = 0
        with err_path.open("wb") as err:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=err, cwd=BACKEND_DIR, env=env
            )
            if token is not None:
                token.track(proc)
            try:
                while True:
                    try:
                        proc.wait(timeout=POLL_SECONDS)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    cancel.check_current()
                    seen = _drain_progress(prog, seen, on_item)
                    if time.monotonic() >= deadline:
                        raise VoiceError(f"VieNeu quá giới hạn {int(timeout)} giây")
            finally:
                _kill(proc)
                if token is not None:
                    token.untrack(proc)
        cancel.check_current()
        _drain_progress(prog, seen, on_item)
        if out_path.is_file():
            data = json.loads(out_path.read_text(encoding="utf-8"))
            if data.get("ok"):
                return data
            when = "lúc đọc" if data.get("stage") == "run" else "lúc nạp mô hình"
            raise VoiceError(f"VieNeu lỗi {when}: {data.get('error', '?')}")
        tail = err_path.read_text(encoding="utf-8", errors="replace").strip()[-300:]
        raise VoiceError(f"Tiến trình VieNeu thoát mã {proc.returncode} {tail}".strip())


def _drain_progress(path: Path, seen: int, on_item: ItemDone | None) -> int:
    if on_item is None:
        return seen
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return seen
    for line in lines[seen:]:
        state, _, idx = line.partition(" ")
        if state in ("begin", "done") and idx.isdigit():
            on_item(int(idx), state)
    return len(lines)


class FileVoice:
    """Giọng nhập file: không sinh gì, nên dùng `synthesize` là lỗi (UI chỉ cho tải file lên)."""

    def status(self) -> VoiceStatus:
        return VoiceStatus(True, True)

    def list_voices(self) -> list[VoiceInfo]:
        return []

    def synthesize(self, text: str, voice_id: str) -> bytes:
        raise VoiceError("Giọng nhập file không tự sinh; hãy tải file giọng lên")

    def synthesize_many(self, items: Sequence[SynthItem], on_item: ItemDone | None = None) -> None:
        raise VoiceError("Giọng nhập file không tự sinh; hãy tải file giọng lên")


FAKE_VOICES = [
    VoiceInfo("Adam bựa", "Adam bựa — Nam", "Nam", "Bắc", "Phong cách tự nhiên"),
    VoiceInfo("Trúc Ly", "Trúc Ly — Nữ", "Nữ", "Bắc", "Phong cách tự nhiên"),
    VoiceInfo("Thiện Minh", "Thiện Minh — Nam", "Nam", "Bắc", "Phong cách kể chuyện"),
    VoiceInfo("Mai Anh", "Mai Anh — Nữ", "Nữ", "Bắc", "Phong cách tin tức"),
    VoiceInfo("Hải Đăng", "Hải Đăng — Nam", "Nam", "Bắc", "Phong cách tự nhiên"),
    VoiceInfo("Thùy Dung", "Thùy Dung — Nữ", "Nữ", "Nam", "Phong cách tin tức"),
]


@dataclass
class FakeVoice(_SingleMixin):
    """Giọng giả cho CI và test: WAV sin, dài `ký tự / 16,5` giây, không cần VieNeu."""

    voices: list[VoiceInfo] = field(default_factory=lambda: list(FAKE_VOICES))
    ok: bool = True
    fail_on: str | None = None  # đoạn chứa chuỗi này thì ném VoiceError
    delay: float = 0.0  # chờ mỗi đoạn (để test huỷ)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def status(self) -> VoiceStatus:
        return VoiceStatus(self.ok, self.ok, "" if self.ok else "Chưa cài VieNeu (giả)")

    def list_voices(self) -> list[VoiceInfo]:
        if not self.ok:
            raise VoiceUnavailable("Chưa cài VieNeu (giả)")
        return self.voices

    def synthesize_many(self, items: Sequence[SynthItem], on_item: ItemDone | None = None) -> None:
        if not self.ok:
            raise VoiceUnavailable("Chưa cài VieNeu (giả)")
        for i, it in enumerate(items):
            if on_item:
                on_item(i, "begin")
            deadline = time.monotonic() + self.delay
            while time.monotonic() < deadline:
                cancel.check_current()
                time.sleep(0.01)
            cancel.check_current()
            if self.fail_on and self.fail_on in it.text:
                raise VoiceError(f"Giọng giả lỗi ở '{it.text[:20]}'")
            self.calls.append((it.text, it.voice_id))
            _write_tone(it.out, max(0.3, len(it.text) / CHARS_PER_SECOND), it.voice_id)
            if on_item:
                on_item(i, "done")


SAMPLE_RATE = 48000


def _write_tone(path: Path, seconds: float, voice_id: str) -> None:
    import math
    import struct

    freq = 180 + (sum(map(ord, voice_id)) % 40) * 10
    n = int(seconds * SAMPLE_RATE)
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * t / SAMPLE_RATE)))
        for t in range(n)
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)


# ------------------------------------------------------------------ chia giọng cho từng người
def segment_speaker(role: str, ref: str | None, speaker: str | None) -> str:
    """Ai đọc đoạn: ghi tay thì theo đó; còn lại post→post, comment→id bình luận, khác→narrator."""
    if speaker:
        return speaker
    if role == "post":
        return POST
    if role == "comment" and ref:
        return ref
    return NARRATOR


def resolve_cast(
    speakers: Sequence[str], manual: dict[str, str], seed: int, voices: Sequence[VoiceInfo]
) -> dict[str, str]:
    """Giọng của từng người: ô chọn tay > người dẫn mặc định Adam bựa > bốc ngẫu nhiên theo `seed`.

    Ngẫu nhiên không trùng giữa những người trong cùng video (hết giọng mới cho trùng) và xen
    nam/nữ khi có nhãn. Cùng đầu vào → cùng kết quả."""
    by_id = {v.id: v for v in voices}
    for who, vid in manual.items():
        if who in speakers and vid not in by_id:
            raise VoiceError(f"Giọng '{vid}' của '{who}' không có trong danh sách giọng")
    cast = {s: manual[s] for s in speakers if s in manual}
    if NARRATOR in speakers and NARRATOR not in cast:
        cast[NARRATOR] = DEFAULT_NARRATOR if DEFAULT_NARRATOR in by_id else voices[0].id
    pool = sorted(voices, key=lambda v: v.id)
    random.Random(seed).shuffle(pool)
    used = set(cast.values())
    last_gender = by_id[cast[speakers[0]]].gender if speakers[0] in cast else ""
    for who in speakers:
        if who in cast:
            last_gender = by_id[cast[who]].gender or last_gender
            continue
        free = [v for v in pool if v.id not in used] or pool
        other = [v for v in free if v.gender and v.gender != last_gender]
        pick = (other or free)[0]
        cast[who] = pick.id
        used.add(pick.id)
        last_gender = pick.gender or last_gender
    return {s: cast[s] for s in speakers}


# ------------------------------------------------------------------ cache và nối đoạn
def cache_key(text: str, voice_id: str) -> str:
    raw = json.dumps([VIENEU_VERSION, WORKER_REV, voice_id, text], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def join_wavs(
    parts: Sequence[Path], out: Path, gap: float = GAP_SECONDS
) -> list[tuple[float, float]]:
    """Nối các WAV cùng định dạng, giữa hai đoạn chèn `gap` giây im lặng. Trả (bắt đầu, kết thúc)
    của từng đoạn (giây) trong file nối; mốc lấy từ độ dài từng file nên không cần căn chữ."""
    spans: list[tuple[float, float]] = []
    tmp = out.with_name(out.name + ".tmp")
    with wave.open(str(tmp), "wb") as dst:
        t = 0.0
        for i, p in enumerate(parts):
            with wave.open(str(p), "rb") as src:
                if i == 0:
                    dst.setparams(src.getparams())
                elif (src.getframerate(), src.getsampwidth(), src.getnchannels()) != (
                    dst.getframerate(), dst.getsampwidth(), dst.getnchannels()
                ):  # fmt: skip
                    raise VoiceError("Các đoạn giọng khác định dạng, không nối được")
                if i > 0:
                    pad = int(gap * dst.getframerate())
                    dst.writeframes(b"\x00" * pad * dst.getsampwidth() * dst.getnchannels())
                    t += pad / dst.getframerate()
                frames = src.readframes(src.getnframes())
                dst.writeframes(frames)
                dur = src.getnframes() / src.getframerate()
            spans.append((round(t, 3), round(t + dur, 3)))
            t += dur
    os.replace(tmp, out)
    return spans


@dataclass
class VoicePlanItem:
    index: int  # chỉ số đoạn trong `project.segments`
    speaker: str
    voice_id: str
    text: str

    @property
    def key(self) -> str:
        return cache_key(self.text, self.voice_id)


@dataclass
class VoiceResult:
    file: Path
    seconds: float
    segments: list[dict]
    cast: dict[str, str]
    generated: int
    cached: int
    signature: str


Progress = Callable[[float, str, str], None]


def plan_signature(plan: Sequence[VoicePlanItem]) -> str:
    return hashlib.sha256("|".join(p.key for p in plan).encode()).hexdigest()[:16]


def synthesize_plan(
    plan: Sequence[VoicePlanItem],
    folder: Path,
    provider: VoiceProvider,
    cast: dict[str, str],
    progress: Progress | None = None,
) -> VoiceResult:
    """Sinh (bỏ qua đoạn đã có trong cache) rồi nối thành `voice.wav` ở thư mục dự án.

    Cache: `build/voice/<hash lời + giọng>.wav`. Tiến độ: 3→95 % theo số đoạn, rồi nối."""
    total = len(plan)
    cache = folder / "build" / "voice"
    cache.mkdir(parents=True, exist_ok=True)

    def report(done: int, msg: str) -> None:
        if progress:
            progress(3 + 92 * done / max(total, 1), "voice", msg)

    paths = [cache / f"{p.key}.wav" for p in plan]
    todo = [k for k, path in enumerate(paths) if not path.is_file()]
    cached = total - len(todo)
    if cached:
        report(cached, f"Dùng lại {cached}/{total} đoạn đã có")
    if todo:
        items = [SynthItem(plan[k].text, plan[k].voice_id, paths[k]) for k in todo]

        def on_item(i: int, state: str) -> None:
            n = cached + i + (1 if state == "done" else 0)
            if state == "begin":
                report(n, f"Đang đọc đoạn {n + 1}/{total}")
            else:
                report(n, f"Xong đoạn {n}/{total}")

        provider.synthesize_many(items, on_item)
    if progress:
        progress(96, "voice", "Đang nối các đoạn")
    out = folder / "voice.wav"
    for old in folder.glob("voice.*"):  # bản cũ khác đuôi (mp3…) không còn đúng
        if old.is_file() and old.name != "voice.wav":
            old.unlink()
    spans = join_wavs(paths, out)
    segments = [
        {"index": p.index, "speaker": p.speaker, "voice_id": p.voice_id, "start": a, "end": b}
        for p, (a, b) in zip(plan, spans, strict=True)
    ]
    sig = plan_signature(plan)
    meta = {"signature": sig, "seconds": spans[-1][1], "segments": segments, "cast": cast}
    (folder / "build").mkdir(exist_ok=True)
    (folder / "build" / "voice_segments.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return VoiceResult(out, spans[-1][1], segments, cast, len(todo), cached, sig)


def speakers_of(project: PostvProject) -> list[str]:
    """Những người có lời đọc, theo thứ tự xuất hiện (người dẫn trước nếu có đoạn của họ)."""
    seen: list[str] = []
    for seg in project.segments:
        if not seg.voice.strip():
            continue
        who = segment_speaker(seg.role, seg.ref, seg.speaker)
        if who not in seen:
            seen.append(who)
    return seen


def build_plan(
    project: PostvProject, voices: Sequence[VoiceInfo]
) -> tuple[list[VoicePlanItem], dict[str, str]]:
    """Kế hoạch sinh giọng: mỗi đoạn có lời → (người đọc, giọng, chữ). Chữ gửi nguyên cho VieNeu
    (không `{cách đọc}`, K-33). Trả kèm `cast` đã chia cho từng người."""
    speakers = speakers_of(project)
    if not speakers:
        raise VoiceError("Chưa có đoạn nào có lời đọc")
    cast = resolve_cast(speakers, project.voice.cast, project.voice.seed, voices)
    plan = []
    for i, seg in enumerate(project.segments):
        text = seg.voice.strip()
        if not text:
            continue
        who = segment_speaker(seg.role, seg.ref, seg.speaker)
        plan.append(VoicePlanItem(i, who, cast[who], text))
    return plan, cast


def voice_cache_size(folder: Path) -> int:
    d = folder / "build" / "voice"
    return sum(f.stat().st_size for f in d.glob("*.wav")) if d.is_dir() else 0


__all__ = [
    "DEFAULT_NARRATOR",
    "FakeVoice",
    "FileVoice",
    "SynthItem",
    "VieNeuProvider",
    "VoiceError",
    "VoiceInfo",
    "VoiceProvider",
    "VoiceUnavailable",
    "build_plan",
    "resolve_cast",
    "segment_speaker",
]
