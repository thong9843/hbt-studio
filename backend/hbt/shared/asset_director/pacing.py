"""Lớp 2 — Pacing Governor: khóa cứng mật độ, khoảng nghỉ và ưu tiên cao trào."""

from __future__ import annotations

from hbt.shared.asset_director.models import BeatCue, PacingPolicy

ROLE_WEIGHTS: dict[str, int] = {
    "punchline": 5,
    "twist": 4,
    "reaction": 4,
    "build": 2,
    "setup": 1,
}

DEFAULT_BEAT_SECONDS = 2.5


def _est_time(cue: BeatCue, all_zero: bool) -> float:
    return (cue.index * DEFAULT_BEAT_SECONDS) if all_zero else float(cue.est_time_s)


def _spread_bonus(idx: int, total: int) -> float:
    if total <= 1:
        return 0.0
    pos = idx / float(total - 1)
    # Ưu tiên nửa sau và cao trào gần cuối (~0.65)
    return round(1.0 - abs(pos - 0.65), 4)


def _has_visual_signal(cue: BeatCue) -> bool:
    return bool((cue.meme_query or "").strip() or (cue.sticker_tag or "").strip())


class PacingGovernor:
    """Bộ điều tiết nhịp cứng bằng Python — LLM không thể vượt rào."""

    def __init__(self, policy: PacingPolicy | None = None) -> None:
        self.policy = policy or PacingPolicy()

    def effective_max_visual(
        self,
        total_beats: int,
        est_duration_sec: float | None = None,
    ) -> int:
        if total_beats <= 0:
            return 0
        msg_cap = max(2, int(total_beats * self.policy.visual_ratio_cap))
        if est_duration_sec is not None and est_duration_sec > 0:
            dur_target = max(
                2,
                min(
                    self.policy.max_visual_memes,
                    round(est_duration_sec / max(8.0, self.policy.target_seconds_per_meme)),
                ),
            )
            return min(dur_target, msg_cap, self.policy.max_visual_memes)
        return min(self.policy.max_visual_memes, msg_cap)

    def _is_skipped_opening(self, cue: BeatCue) -> bool:
        if not self.policy.skip_opening_setup or cue.index != 0:
            return False
        role = (cue.beat_role or "setup").strip().lower()
        return role == "setup"

    def _fits_gaps(
        self,
        cue: BeatCue,
        t_cur: float,
        kept: list[tuple[int, float]],
    ) -> bool:
        for k_idx, k_t in kept:
            if self.policy.forbid_consecutive and abs(cue.index - k_idx) <= 1:
                return False
            if abs(cue.index - k_idx) < self.policy.min_gap_beats:
                return False
            if abs(t_cur - k_t) < self.policy.min_gap_seconds:
                return False
        return True

    def select_visual_beats(self, cues: list[BeatCue]) -> list[int]:
        """Chọn tối đa `effective_max_visual` điểm rơi cân đối theo thời lượng (~1 meme/16s)."""
        n = len(cues)
        if n == 0:
            return []

        all_zero_t = all(c.est_time_s <= 0.0 for c in cues)
        est_total_dur = (
            (n * DEFAULT_BEAT_SECONDS) if all_zero_t else (max(c.est_time_s for c in cues) + 3.0)
        )
        limit = self.effective_max_visual(n, est_duration_sec=est_total_dur)
        if limit <= 0:
            return []

        primary: list[BeatCue] = [
            c
            for c in cues
            if not self._is_skipped_opening(c) and _has_visual_signal(c) and c.intensity >= 4
        ]

        # Hạ 1 bậc xuống intensity == 3 nếu cả video chưa có câu nào đạt mức 4
        if not primary:
            fallback = [
                c
                for c in cues
                if not self._is_skipped_opening(c)
                and _has_visual_signal(c)
                and c.intensity == 3
                and (c.beat_role or "").strip().lower() in ("punchline", "twist")
            ]
            if not fallback:
                return []
            best = max(
                fallback,
                key=lambda c: (
                    ROLE_WEIGHTS.get((c.beat_role or "").strip().lower(), 1),
                    _spread_bonus(c.index, n),
                    -c.index,
                ),
            )
            return [best.index]

        ranked = sorted(
            primary,
            key=lambda c: (
                c.intensity,
                ROLE_WEIGHTS.get((c.beat_role or "").strip().lower(), 1),
                _spread_bonus(c.index, n),
                -c.index,
            ),
            reverse=True,
        )

        kept: list[tuple[int, float]] = []
        for cue in ranked:
            if len(kept) >= limit:
                break
            t_cur = _est_time(cue, all_zero_t)
            if self._fits_gaps(cue, t_cur, kept):
                kept.append((cue.index, t_cur))

        # Nếu chưa đạt mục tiêu thời lượng, bổ sung các tin intensity == 3 có meme_query đều nhịp
        if len(kept) < limit:
            kept_indices = {k_idx for k_idx, _ in kept}
            secondary = [
                c
                for c in cues
                if c.index not in kept_indices
                and not self._is_skipped_opening(c)
                and bool((c.meme_query or "").strip())
                and c.intensity == 3
            ]
            while len(kept) < limit and secondary:
                best_cand: BeatCue | None = None
                best_key: tuple[float, int, float] = (-1.0, -1, -1.0)
                for c in secondary:
                    t_cur = _est_time(c, all_zero_t)
                    if not self._fits_gaps(c, t_cur, kept):
                        continue
                    min_dist = min(abs(t_cur - k_t) for _, k_t in kept) if kept else est_total_dur
                    key = (
                        min_dist,
                        ROLE_WEIGHTS.get((c.beat_role or "").strip().lower(), 1),
                        -float(c.index),
                    )
                    if key > best_key:
                        best_key = key
                        best_cand = c
                if best_cand is None:
                    break
                kept.append((best_cand.index, _est_time(best_cand, all_zero_t)))
                secondary = [c for c in secondary if c.index != best_cand.index]

        return sorted(idx for idx, _ in kept)

    def select_sfx_beats(self, cues: list[BeatCue]) -> list[int]:
        """Lọc độc lập điểm nhấn punch SFX theo max_punch_sfx và min_sfx_gap_seconds."""
        n = len(cues)
        if n == 0 or self.policy.max_punch_sfx <= 0:
            return []

        all_zero_t = all(c.est_time_s <= 0.0 for c in cues)
        candidates = [
            c
            for c in cues
            if not self._is_skipped_opening(c)
            and bool((c.sfx_query or "").strip())
            and c.intensity >= 4
        ]
        if not candidates:
            return []

        ranked = sorted(
            candidates,
            key=lambda c: (
                c.intensity,
                ROLE_WEIGHTS.get((c.beat_role or "").strip().lower(), 1),
                _spread_bonus(c.index, n),
                -c.index,
            ),
            reverse=True,
        )

        kept: list[tuple[int, float]] = []
        for cue in ranked:
            if len(kept) >= self.policy.max_punch_sfx:
                break
            t_cur = _est_time(cue, all_zero_t)
            ok = True
            for k_idx, k_t in kept:
                if self.policy.forbid_consecutive and abs(cue.index - k_idx) <= 1:
                    ok = False
                    break
                if abs(t_cur - k_t) < self.policy.min_sfx_gap_seconds:
                    ok = False
                    break
            if ok:
                kept.append((cue.index, t_cur))

        return sorted(idx for idx, _ in kept)

    def clamp_video_meme_duration(self, real_duration_s: float | None) -> float:
        lo, hi = self.policy.video_meme_duration_range
        if real_duration_s is not None and real_duration_s > 0:
            return round(max(lo, min(hi, float(real_duration_s))), 2)
        return round(min(hi, max(lo, 2.2)), 2)

    def static_sticker_duration(self, intensity: int = 4) -> float:
        lo, hi = self.policy.static_sticker_duration_range
        if intensity >= 5:
            return round(max(lo, min(hi, 1.5)), 2)
        if intensity == 4:
            return round(max(lo, min(hi, 1.1)), 2)
        return round(lo, 2)
