"""Che từ nhạy cảm khi dựng: tìm khoảng thời gian, tắt tiếng giọng, bíp 1 kHz (mục 6b).

Khớp trên **token** của lời đọc (đã tách theo từng đoạn) nên không phụ thuộc vị trí ký tự: từ che
= chuỗi token liền nhau có phần chữ (bỏ dấu câu hai đầu) trùng từng chữ của từ che, có dấu, không
phân biệt hoa thường, theo ranh giới từ ("đéo" không trùng "đeo"). Căn chữ và phụ đề dùng giọng
**chưa che** nên mốc không lệch; chỉ bản trộn âm thanh dùng giọng đã tắt tiếng.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.pipeline import audio
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.postv.censor import CensorMatcher, normalize

PAD = 0.06  # nới mỗi bên: aligner khoảng lặng kém chính xác hơn Whisper
BLEEP_HZ = 1000
BLEEP_VOL = 0.35  # mức trước loudnorm (chỉnh bằng tai ở PV5, chốt giữ 0,35)
BLEEP_FADE = 0.005
FRAME_SAMPLES = 64
_EDGE = re.compile(r"^\W+|\W+$")


@dataclass(frozen=True)
class Window:
    start: float
    end: float
    word: str
    token_ids: tuple[int, ...]


def token_core(disp: str) -> str:
    """Chữ của token để so khớp: bỏ dấu câu hai đầu, NFC, chữ thường."""
    return normalize(_EDGE.sub("", disp))


def find_token_runs(
    tokens: Sequence[dict], scene_of: Sequence[int], matchers: Sequence[CensorMatcher]
) -> list[tuple[int, int, str]]:
    """[(token đầu, token cuối, từ che)] không chồng nhau, theo thứ tự. Không vượt ranh giới đoạn.
    Từ che dài hơn được ưu tiên khi hai từ chồng nhau."""
    cores = [token_core(t["disp"]) for t in tokens]
    words = sorted(
        ((m.word, normalize(m.word).split()) for m in matchers),
        key=lambda w: -len(w[1]),
    )
    taken = [False] * len(tokens)
    runs: list[tuple[int, int, str]] = []
    for word, parts in words:
        n = len(parts)
        if not n:
            continue
        for i in range(len(tokens) - n + 1):
            span = range(i, i + n)
            if any(taken[j] for j in span) or scene_of[i] != scene_of[i + n - 1]:
                continue
            if all(cores[i + k] == parts[k] for k in range(n)):
                runs.append((i, i + n - 1, word))
                for j in span:
                    taken[j] = True
    return sorted(runs)


def censor_windows(
    tokens: Sequence[dict],
    scene_of: Sequence[int],
    times: Sequence[tuple[float, float]],
    matchers: Sequence[CensorMatcher],
    total: float,
) -> list[Window]:
    """Khoảng thời gian cần che: đầu token đầu tới cuối token cuối, nới PAD; gộp khoảng chồng."""
    out: list[Window] = []
    for first, last, word in find_token_runs(tokens, scene_of, matchers):
        start = max(times[first][0] - PAD, 0.0)
        end = min(max(times[last][1], times[first][0]) + PAD, total)
        ids = tuple(range(first, last + 1))
        if out and start <= out[-1].end:
            prev = out[-1]
            out[-1] = Window(prev.start, max(prev.end, end), prev.word, prev.token_ids + ids)
        else:
            out.append(Window(start, end, word, ids))
    return out


def masked_tokens(windows: Sequence[Window]) -> set[int]:
    return {i for w in windows for i in w.token_ids}


def mute_voice(src: Path, dst: Path, windows: Sequence[Window]) -> None:
    """Bản sao `src` tắt tiếng trong các khoảng cần che (`volume=enable=between(…):volume=0`)."""
    # `enable` tính theo từng khung âm thanh: chia khung nhỏ (64 mẫu ≈ 1,5 ms) cho mép chính xác
    parts = [f"volume=enable='between(t,{w.start:.3f},{w.end:.3f})':volume=0" for w in windows]
    chain = ",".join([f"asetnsamples=n={FRAME_SAMPLES}:p=0", *parts])
    run_ffmpeg(["-i", src, "-af", chain, "-c:a", "pcm_s16le", dst])


def synth_bleep(seconds: float, out: Path) -> None:
    """Tiếng bíp 1 kHz tổng hợp bằng ffmpeg (cùng cách `synth_whoosh`), fade 5 ms hai đầu."""
    fade = min(BLEEP_FADE, seconds / 2)
    run_ffmpeg([
        "-f", "lavfi", "-i", f"aevalsrc='0.8*sin(2*PI*{BLEEP_HZ}*t)':d={seconds:.3f}:s={audio.SR}",
        "-af", f"afade=t=in:d={fade},afade=t=out:st={seconds - fade:.3f}:d={fade}",
        "-ar", str(audio.SR), "-ac", "2", out,
    ])  # fmt: skip


def bleep_sfx(windows: Sequence[Window], workdir: Path) -> list[tuple[Path, float, float]]:
    """Mỗi khoảng một tiếng bíp đúng độ dài, dạng `(file, giây, âm lượng)` cho `mix_audio(sfx=)`."""
    sfx = []
    for k, w in enumerate(windows):
        path = workdir / f"bleep_{k}_{int(round((w.end - w.start) * 1000))}ms.wav"
        if not path.exists():
            synth_bleep(w.end - w.start, path)
        sfx.append((path, w.start, BLEEP_VOL))
    return sfx
