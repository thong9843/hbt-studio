"""Căn thời gian từng chữ của kịch bản với giọng đọc.

Hai cách:
  1. whisper  : nhận dạng giọng bằng faster-whisper (tiến trình con, xem `whisper.py`), lấy mốc
                thời gian từng âm tiết, rồi so khớp với kịch bản (kịch bản luôn là nguồn chữ chuẩn).
  2. silence  : không cần model, dựa vào các khoảng lặng + độ dài chữ để ước lượng.
"""

import difflib
import math
import re
import subprocess
from dataclasses import dataclass

from .text import weight


# ---------------------------------------------------------------- whisper
# Whisper chạy ở tiến trình con (`whisper.py`); ở đây chỉ so khớp âm tiết nghe được với kịch bản.
@dataclass
class Match:
    times: list[tuple[float, float]]  # mốc từng token
    matched_ratio: float  # tỉ lệ âm tiết kịch bản khớp âm tiết nghe được
    last_token_matched: bool  # âm tiết cuối của token cuối có khớp thật (không phải nội suy)
    last_matched_end: float | None  # hết âm tiết khớp cuối cùng; None nếu không khớp âm tiết nào
    heard_end: float  # hết âm tiết cuối cùng Whisper nghe được (kể cả phần thừa)


def match_script(tokens, heard) -> Match:
    """Khớp âm tiết Whisper nghe được với kịch bản (kịch bản luôn là nguồn chữ chuẩn)."""
    if not heard:
        raise RuntimeError("Whisper không nhận ra giọng nói")
    script = [(ti, s) for ti, t in enumerate(tokens) for s in t["syl"]]
    sm = difflib.SequenceMatcher(a=[s for _, s in script], b=[h[0] for h in heard], autojunk=False)
    times = [None] * len(script)
    matched = 0
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            times[a + k] = (heard[b + k][1], heard[b + k][2])
        matched += n
    anchors = [t for t in times if t is not None]
    last_matched = bool(script) and times[-1] is not None
    last_end = anchors[-1][1] if anchors else None
    _interpolate(times, script, heard[0][1], heard[-1][2])
    return Match(
        times=_syllables_to_tokens(tokens, script, times),
        matched_ratio=matched / len(script) if script else 0.0,
        last_token_matched=last_matched,
        last_matched_end=last_end,
        heard_end=heard[-1][2],
    )


def _interpolate(times, script, t0, t1):
    n = len(times)
    i = 0
    while i < n:
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        a = times[i - 1][1] if i > 0 else t0
        b = times[j][0] if j < n else t1
        if b < a:
            b = a
        ws = [1 + 0.12 * len(script[k][1]) for k in range(i, j)]
        tot = sum(ws)
        t = a
        for k, w in zip(range(i, j), ws, strict=False):
            d = (b - a) * w / tot
            times[k] = (t, t + d)
            t += d
        i = j


def _syllables_to_tokens(tokens, script, times):
    res = []
    for ti in range(len(tokens)):
        ks = [k for k, (t, _) in enumerate(script) if t == ti]
        res.append((times[ks[0]][0], times[ks[-1]][1]))
    return res


# ---------------------------------------------------------------- silence fallback
def silences(wav, min_dur=0.25, noise="-38dB"):
    out = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            wav,
            "-af",
            f"silencedetect=noise={noise}:d={min_dur}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    v = [float(x) for x in re.findall(r"silence_(?:start|end): ([0-9.]+)", out)]
    return list(zip(v[0::2], v[1::2], strict=False))


def speech_segments(wav, total, min_dur=0.25, noise="-38dB"):
    segs, prev = [], 0.0
    for s, e in silences(wav, min_dur, noise):
        if s - prev > 0.05:
            segs.append((prev, s))
        prev = e
    if total - prev > 0.05:
        segs.append((prev, total))
    return segs


def split_phrases(tokens):
    """Chia token thành cụm câu theo dấu câu (`phrase_end`); trả về danh sách chỉ số token."""
    phrases, cur = [], []
    for i, t in enumerate(tokens):
        cur.append(i)
        if t["phrase_end"] or i == len(tokens) - 1:
            phrases.append(cur)
            cur = []
    return phrases


def _align_silence_segments(tokens, segs, max_group=6):
    """Quy hoạch động ghép cụm câu ↔ đoạn tiếng nói; trả về (chi phí, thời gian từng token).

    `max_group`: số cụm (hoặc số đoạn) tối đa gộp vào một nhóm; reference dùng 6."""
    phrases = split_phrases(tokens)
    pw = [sum(weight(tokens[i]) for i in p) for p in phrases]
    dur = [e - s for s, e in segs]
    rate = sum(pw) / sum(dur)
    P, S = len(phrases), len(segs)
    best = {(0, 0): (0.0, None)}
    for i in range(P + 1):
        for j in range(S + 1):
            if (i, j) not in best:
                continue
            c0 = best[(i, j)][0]
            for a in range(1, min(P - i, max_group) + 1):
                for b in range(1, min(S - j, max_group) + 1):
                    if a > 1 and b > 1:
                        continue
                    c = (
                        c0
                        + math.log(sum(dur[j : j + b]) * rate / sum(pw[i : i + a])) ** 2
                        + 0.15 * (a + b - 2)
                    )
                    k = (i + a, j + b)
                    if k not in best or c < best[k][0]:
                        best[k] = (c, (i, j, a, b))
    if (P, S) not in best:
        raise RuntimeError("Không ghép được lời đọc với giọng nói, hãy kiểm tra kịch bản")
    groups, k = [], (P, S)
    while k != (0, 0):
        i, j, a, b = best[k][1]
        groups.append((i, a, j, b))
        k = (i, j)
    groups.reverse()
    res = [None] * len(tokens)
    for i, a, j, b in groups:
        gsegs = segs[j : j + b]
        ids = [t for p in phrases[i : i + a] for t in p]
        ws = [weight(tokens[t]) for t in ids]
        total_sp = sum(e - s for s, e in gsegs)

        def at(x):
            for s, e in gsegs:  # noqa: B023 — at() chỉ gọi trong cùng vòng lặp
                if x <= e - s:
                    return s + x
                x -= e - s
            return gsegs[-1][1]  # noqa: B023

        x = 0.0
        for t, w in zip(ids, ws, strict=False):
            d = total_sp * w / sum(ws)
            res[t] = (at(x), at(x + d))
            x += d
    return best[(P, S)][0], res


def align_silence(tokens, wav, total):
    """Ghép từng cụm câu (tách theo dấu câu) với các đoạn có tiếng nói bằng quy hoạch động."""
    return _align_silence_segments(tokens, speech_segments(wav, total))[1]
