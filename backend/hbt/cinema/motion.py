"""Đường cong chuyển động (Easing curves, Spring vật lý & Keyframe interpolation)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

EasingName = Literal[
    "linear",
    "ease_out_cubic",
    "ease_in_out_cubic",
    "ease_out_back",
    "spring",
]


def clamp01(t: float) -> float:
    """Giới hạn hệ số tiến độ về đoạn [0.0, 1.0]."""
    return max(0.0, min(1.0, float(t)))


def ease_out_cubic(t: float) -> float:
    u = clamp01(t)
    inv = 1.0 - u
    return 1.0 - inv * inv * inv


def ease_in_out_cubic(t: float) -> float:
    u = clamp01(t)
    if u < 0.5:
        return 4.0 * u * u * u
    return 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    u = clamp01(t)
    c1 = float(overshoot)
    c3 = c1 + 1.0
    m = u - 1.0
    return 1.0 + c3 * (m * m * m) + c1 * (m * m)


def spring(t: float, *, stiffness: float = 180.0, damping: float = 16.0) -> float:
    """Đáp ứng lò xo tắt dần từ 0.0 hội tụ mượt về 1.0 theo tiến độ t in [0, 1]."""
    u = clamp01(t)
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    omega = math.sqrt(max(1.0, float(stiffness)))
    zeta = max(0.15, float(damping) / (2.0 * omega))
    # Hệ số thời gian giả lập ~1.0s cho khoảng [0, 1]
    tau = u * 1.1
    if zeta < 1.0:
        wd = omega * math.sqrt(1.0 - zeta * zeta)
        env = math.exp(-zeta * omega * tau)
        val = 1.0 - env * (math.cos(wd * tau) + (zeta * omega / wd) * math.sin(wd * tau))
    else:
        env = math.exp(-omega * tau)
        val = 1.0 - env * (1.0 + omega * tau)
    # Kéo chính xác điểm cuối về 1.0 khi u tiến tới 1.0
    blend = u**4
    return val * (1.0 - blend) + 1.0 * blend


def apply_easing(t: float, easing: EasingName = "ease_out_cubic") -> float:
    if easing == "linear":
        return clamp01(t)
    if easing == "ease_in_out_cubic":
        return ease_in_out_cubic(t)
    if easing == "ease_out_back":
        return ease_out_back(t)
    if easing == "spring":
        return spring(t)
    return ease_out_cubic(t)


class Keyframe(BaseModel):
    """Một điểm khóa thời gian cho thuộc tính chuyển động."""

    t: float
    value: float
    easing: EasingName = "ease_out_cubic"


def evaluate_track(
    keyframes: Sequence[Keyframe],
    t_sec: float,
    *,
    default: float = 0.0,
) -> float:
    """Nội suy giá trị trên trục keyframe tại thời điểm `t_sec`."""
    if not keyframes:
        return float(default)
    ordered = sorted(keyframes, key=lambda k: k.t)
    if t_sec <= ordered[0].t:
        return float(ordered[0].value)
    if t_sec >= ordered[-1].t:
        return float(ordered[-1].value)

    for left, right in zip(ordered, ordered[1:], strict=False):
        if left.t <= t_sec <= right.t:
            span = right.t - left.t
            if span <= 1e-6:
                return float(right.value)
            u = apply_easing((t_sec - left.t) / span, right.easing)
            return float(left.value + (right.value - left.value) * u)
    return float(ordered[-1].value)
