"""Căn thời gian từng chữ của kịch bản với giọng đọc.

Hai cách:
  1. whisper  : nhận dạng giọng bằng faster-whisper (GPU), lấy mốc thời gian từng âm tiết,
                rồi so khớp với kịch bản (kịch bản luôn là nguồn chữ chuẩn).
  2. silence  : không cần model, dựa vào các khoảng lặng + độ dài chữ để ước lượng.
"""
import difflib
import math
import re
import subprocess

from .text import norm, weight


# ---------------------------------------------------------------- whisper
_MODEL = None


def _load_model(size: str):
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel  # import muộn: không bắt buộc cài
        try:
            _MODEL = WhisperModel(size, device="cuda", compute_type="int8_float16")
        except Exception:
            _MODEL = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODEL


def whisper_syllables(wav: str, prompt: str, size: str = "large-v3"):
    model = _load_model(size)
    segments, _ = model.transcribe(
        wav, language="vi", word_timestamps=True, beam_size=5,
        initial_prompt=prompt[:220], condition_on_previous_text=False,
    )
    out = []
    for seg in segments:
        for w in seg.words or []:
            parts = [p for p in (norm(x) for x in w.word.split()) if p]
            if not parts:
                continue
            step = (w.end - w.start) / len(parts)
            for i, p in enumerate(parts):
                out.append((p, w.start + i * step, w.start + (i + 1) * step))
    return out


def align_whisper(tokens, wav, size="large-v3"):
    script = [(ti, s) for ti, t in enumerate(tokens) for s in t["syl"]]
    prompt = " ".join(t["disp"] for t in tokens)
    heard = whisper_syllables(wav, prompt, size)
    if not heard:
        raise RuntimeError("Whisper không nhận ra giọng nói")
    sm = difflib.SequenceMatcher(a=[s for _, s in script], b=[h[0] for h in heard], autojunk=False)
    times = [None] * len(script)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            times[a + k] = (heard[b + k][1], heard[b + k][2])
    _interpolate(times, script, heard[0][1], heard[-1][2])
    return _syllables_to_tokens(tokens, script, times)


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
        for k, w in zip(range(i, j), ws):
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
        ["ffmpeg", "-hide_banner", "-i", wav, "-af", f"silencedetect=noise={noise}:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    v = [float(x) for x in re.findall(r"silence_(?:start|end): ([0-9.]+)", out)]
    return list(zip(v[0::2], v[1::2]))


def speech_segments(wav, total):
    segs, prev = [], 0.0
    for s, e in silences(wav):
        if s - prev > 0.05:
            segs.append((prev, s))
        prev = e
    if total - prev > 0.05:
        segs.append((prev, total))
    return segs


def align_silence(tokens, wav, total):
    """Ghép từng cụm câu (tách theo dấu câu) với các đoạn có tiếng nói bằng quy hoạch động."""
    segs = speech_segments(wav, total)
    phrases, cur = [], []
    for i, t in enumerate(tokens):
        cur.append(i)
        if t["phrase_end"] or i == len(tokens) - 1:
            phrases.append(cur)
            cur = []
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
            for a in range(1, min(P - i, 6) + 1):
                for b in range(1, min(S - j, 6) + 1):
                    if a > 1 and b > 1:
                        continue
                    c = c0 + math.log(sum(dur[j:j + b]) * rate / sum(pw[i:i + a])) ** 2 + 0.15 * (a + b - 2)
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
        gsegs = segs[j:j + b]
        ids = [t for p in phrases[i:i + a] for t in p]
        ws = [weight(tokens[t]) for t in ids]
        total_sp = sum(e - s for s, e in gsegs)

        def at(x):
            for s, e in gsegs:
                if x <= e - s:
                    return s + x
                x -= e - s
            return gsegs[-1][1]

        x = 0.0
        for t, w in zip(ids, ws):
            d = total_sp * w / sum(ws)
            res[t] = (at(x), at(x + d))
            x += d
    return res


def align(tokens, wav, total, method="auto", model_size="large-v3", log=print):
    if method in ("auto", "whisper"):
        try:
            r = align_whisper(tokens, wav, model_size)
            log("Căn phụ đề bằng Whisper: OK")
            return r
        except Exception as e:  # noqa: BLE001
            if method == "whisper":
                raise
            log(f"Không dùng được Whisper ({e.__class__.__name__}), chuyển sang căn theo khoảng lặng")
    return align_silence(tokens, wav, total)
