"""Căn chữ bằng khoảng lặng theo hai cấp (dùng khi chưa có Whisper), IMPLEMENT.md mục 5.2 và 4d.

Cấp 1: ghép các cảnh (mỗi cảnh là một đoạn lời) với các nhóm đoạn tiếng liên tiếp, chi phí theo tổng
thời lượng so với trọng số của cảnh.
Cấp 2: trong từng cảnh, ghép các cụm câu với các đoạn tiếng của cảnh đó (quy hoạch động của
reference). Nếu cảnh có ít đoạn hơn số cụm thì hạ dần ngưỡng khoảng lặng, chỉ trong phạm vi cảnh.
Cuối cùng quyết định có tự động bỏ đoạn thừa ở cuối file giọng hay không (4d.2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .align import _align_silence_segments, speech_segments, split_phrases
from .text import weight

# (độ dài khoảng lặng tối thiểu, ngưỡng ồn): từ thô đến mịn
LEVELS = ((0.25, "-38dB"), (0.18, "-36dB"), (0.12, "-35dB"), (0.08, "-34dB"))
MAX_DROP = 3
AUTO_DROP_MIN_GAIN = 1.0  # chi phí ghép phải giảm ít nhất mức này
AUTO_DROP_MIN_LAST_SEG = 1.5  # giây; đoạn cuối phải dài ít nhất mức này
SEG_COUNT_PENALTY = 0.05  # cấp 1: lệch giữa số đoạn được gán và số cụm của cảnh
# Cấp 1: cảnh kết thúc bằng dấu cuối câu (. ? !) thì ranh giới phải rơi vào khoảng nghỉ dài. Ngưỡng
# tính theo chính file: PAUSE_THRESHOLD_RATIO × phân vị 75 của các khoảng nghỉ giữa hai đoạn.
PAUSE_WEIGHT = 4.0
PAUSE_THRESHOLD_RATIO = 0.85
MAX_SCENE_SEGS = 16
MIN_SEG = 0.05


class AlignError(RuntimeError):
    """Không ghép được lời đọc với giọng nói."""


@dataclass
class SilenceAlignment:
    times: list[tuple[float, float]]
    dropped: int  # số đoạn cuối đã bỏ (coi là đoạn thừa)
    cost: float
    warning: str | None = None  # nghi có đoạn thừa nhưng chưa tự cắt
    refined_scenes: list[int] = field(default_factory=list)  # cảnh phải hạ ngưỡng khoảng lặng


class _SegmentCache:
    """Các đoạn tiếng nói theo từng mức ngưỡng (chạy silencedetect khi cần, mỗi mức một lần)."""

    def __init__(self, wav: str, total: float):
        self.wav, self.total = wav, total
        self._levels: dict[int, list[tuple[float, float]]] = {}

    def level(self, i: int) -> list[tuple[float, float]]:
        if i not in self._levels:
            self._levels[i] = speech_segments(self.wav, self.total, *LEVELS[i])
        return self._levels[i]


def _clip(segs: Sequence[tuple[float, float]], lo: float, hi: float) -> list[tuple[float, float]]:
    out = []
    for s, e in segs:
        s2, e2 = max(s, lo), min(e, hi)
        if e2 - s2 > MIN_SEG:
            out.append((s2, e2))
    return out


# ---------------------------------------------------------------- cấp 1
def _pause_threshold(segs: Sequence[tuple[float, float]]) -> float:
    gaps = sorted(segs[i + 1][0] - segs[i][1] for i in range(len(segs) - 1))
    if not gaps:
        return 0.0
    return PAUSE_THRESHOLD_RATIO * gaps[min(len(gaps) - 1, int(0.75 * len(gaps)))]


def match_scenes(
    weights: Sequence[float],
    phrase_counts: Sequence[int],
    segs: Sequence[tuple[float, float]],
    ends_sentence: Sequence[bool] | None = None,
) -> tuple[float, list[tuple[int, int]]]:
    """Gán cho mỗi cảnh một nhóm đoạn tiếng liên tiếp (dùng hết các đoạn, mỗi cảnh ≥ 1 đoạn).

    Chi phí = lệch giữa tổng thời lượng và trọng số của cảnh, cộng phạt khi ranh giới sau một cảnh
    kết thúc bằng dấu cuối câu (`ends_sentence`) rơi vào khoảng nghỉ ngắn.
    Trả về (chi phí, [(đoạn đầu, số đoạn)] theo từng cảnh)."""
    n, s = len(weights), len(segs)
    if s < n:
        raise AlignError(f"Giọng chỉ có {s} đoạn tiếng nhưng kịch bản có {n} cảnh")
    prefix = [0.0]
    for a, b in segs:
        prefix.append(prefix[-1] + (b - a))
    rate = sum(weights) / prefix[-1]
    threshold = _pause_threshold(segs)
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {(0, 0): (0.0, None)}
    for k in range(n):
        for j in range(s):
            if (k, j) not in best:
                continue
            c0 = best[(k, j)][0]
            for b in range(1, min(MAX_SCENE_SEGS, s - j - (n - k - 1)) + 1):
                dur = prefix[j + b] - prefix[j]
                c = (
                    c0
                    + math.log(dur * rate / weights[k]) ** 2
                    + SEG_COUNT_PENALTY * abs(b - phrase_counts[k])
                )
                if ends_sentence is not None and ends_sentence[k] and k < n - 1:
                    gap = segs[j + b][0] - segs[j + b - 1][1]
                    c += PAUSE_WEIGHT * max(0.0, threshold - gap)
                key = (k + 1, j + b)
                if key not in best or c < best[key][0]:
                    best[key] = (c, (j, b))
    if (n, s) not in best:
        raise AlignError("Không ghép được các cảnh với giọng nói")
    assign: list[tuple[int, int]] = []
    key = (n, s)
    while key != (0, 0):
        j, b = best[key][1]
        assign.append((j, b))
        key = (key[0] - 1, j)
    assign.reverse()
    return best[(n, s)][0], assign


# ---------------------------------------------------------------- cấp 2
def _align_scene(
    tokens: list[dict], segs: list[tuple[float, float]], cache: _SegmentCache
) -> tuple[float, list[tuple[float, float]], bool]:
    """Cụm câu ↔ đoạn tiếng trong một cảnh. Trả về (chi phí, thời gian token, đã hạ ngưỡng?)."""
    phrases = len(split_phrases(tokens))
    chosen, refined = segs, False
    if len(segs) < phrases:
        lo, hi = segs[0][0], segs[-1][1]
        for lv in range(1, len(LEVELS)):
            fine = _clip(cache.level(lv), lo, hi)
            if len(fine) > len(chosen):
                chosen, refined = fine, True
            if len(chosen) >= phrases:
                break
    try:
        cost, times = _align_silence_segments(tokens, chosen)
    except RuntimeError:  # quá nhiều cụm dồn vào ít đoạn: nới giới hạn nhóm của reference
        cost, times = _align_silence_segments(tokens, chosen, max_group=max(phrases, len(chosen)))
    return cost, times, refined


def _solve(
    tokens: Sequence[dict],
    groups: list[list[int]],
    segs: list[tuple[float, float]],
    cache: _SegmentCache,
) -> tuple[float, list[tuple[float, float]], list[int]]:
    weights = [sum(weight(tokens[i]) for i in g) for g in groups]
    counts = [len(split_phrases([tokens[i] for i in g])) for g in groups]
    ends = [bool(tokens[g[-1]]["sentence_end"]) for g in groups]
    cost, assign = match_scenes(weights, counts, segs, ends)
    times: list[tuple[float, float] | None] = [None] * len(tokens)
    refined_scenes = []
    for k, (g, (j, b)) in enumerate(zip(groups, assign, strict=True)):
        c, local, refined = _align_scene([tokens[i] for i in g], segs[j : j + b], cache)
        cost += c
        if refined:
            refined_scenes.append(k)
        for i, t in zip(g, local, strict=True):
            times[i] = t
    return cost, times, refined_scenes  # type: ignore[return-value]


# ---------------------------------------------------------------- quyết định cắt đuôi (4d.2)
def decide_tail(
    costs: dict[int, float], segs: Sequence[tuple[float, float]], guard: int
) -> tuple[int, str | None]:
    """Chọn số đoạn cuối bỏ đi. Trả về (số đoạn bỏ, cảnh báo hoặc None).

    Chỉ tự động bỏ khi (a) chi phí ghép giảm ≥ AUTO_DROP_MIN_GAIN và (b) đoạn cuối dài ≥
    AUTO_DROP_MIN_LAST_SEG. Ngược lại giữ nguyên; nếu bỏ vẫn làm chi phí giảm thì cảnh báo."""
    options = {k: c for k, c in costs.items() if 1 <= k <= guard}
    if not options:
        return 0, None
    k = min(options, key=options.get)
    gain = costs[0] - options[k]
    if gain <= 0:
        return 0, None
    last_len = segs[-1][1] - segs[-1][0]
    if gain >= AUTO_DROP_MIN_GAIN and last_len >= AUTO_DROP_MIN_LAST_SEG:
        return k, None
    extra = segs[-1][1] - segs[-k][0]
    return 0, f"Có thể có đoạn thừa ở cuối file giọng ({extra:.2f} giây), chưa cắt".replace(
        ".", ","
    )


def align_scenes(
    tokens: Sequence[dict],
    scene_of: Sequence[int],
    wav: str,
    total: float,
    max_drop: int = MAX_DROP,
) -> SilenceAlignment:
    """Căn thời gian từng token bằng khoảng lặng, hai cấp (cảnh → cụm câu)."""
    groups: list[list[int]] = []
    for i, sc in enumerate(scene_of):
        if not groups or sc != scene_of[groups[-1][0]]:
            groups.append([])
        groups[-1].append(i)
    cache = _SegmentCache(wav, total)

    # Cấp độ ngưỡng toàn cục: đủ đoạn cho mỗi cảnh (thô nhất có thể)
    base: list[tuple[float, float]] = []
    for lv in range(len(LEVELS)):
        base = cache.level(lv)
        if len(base) >= len(groups):
            break
    phrases = sum(len(split_phrases([tokens[i] for i in g])) for g in groups)
    guard = min(max_drop, max(0, len(base) - phrases))

    solved: dict[int, tuple[float, list, list[int]]] = {}
    for drop in range(guard + 1):
        try:
            solved[drop] = _solve(tokens, groups, base[: len(base) - drop], cache)
        except (AlignError, ValueError, ZeroDivisionError):
            if drop == 0:
                raise AlignError(
                    "Không ghép được lời đọc với giọng nói, hãy kiểm tra kịch bản"
                ) from None
    drop, warning = decide_tail({k: v[0] for k, v in solved.items()}, base, guard)
    cost, times, refined = solved[drop]
    return SilenceAlignment(times, drop, cost, warning, refined)
