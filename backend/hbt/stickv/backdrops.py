"""Bộ sinh phông nền động đa lĩnh vực (5 domain) cho StickV v7 bằng Pillow/NumPy."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

StickvDomain = Literal[
    "paper_classic",
    "physics_science",
    "history_geo",
    "psychology_story",
    "cosmos_mystery",
]

VALID_DOMAINS: tuple[StickvDomain, ...] = (
    "paper_classic",
    "physics_science",
    "history_geo",
    "psychology_story",
    "cosmos_mystery",
)

LOOP_DURATION_S = 4.0


def normalize_domain(raw: str | None) -> StickvDomain:
    val = (raw or "").strip().lower()
    if val == "cosmos":
        return "cosmos_mystery"
    if val in VALID_DOMAINS:
        return val  # type: ignore[return-value]
    return "paper_classic"


DOMAIN_PALETTES: dict[StickvDomain, dict[str, tuple[int, int, int, int]]] = {
    "paper_classic": {
        "bg": (250, 247, 240, 255),
        "grid": (235, 229, 216, 255),
        "card": (255, 255, 255, 250),
        "card_border": (220, 210, 192, 255),
        "text": (17, 24, 39, 255),
        "muted": (71, 85, 105, 255),
        "accent": (217, 35, 46, 255),
        "amber": (245, 158, 11, 255),
        "pill_bg": (254, 243, 199, 255),
        "pill_text": (146, 64, 14, 255),
        "takeaway_bg": (255, 247, 237, 255),
    },
    "physics_science": {
        "bg": (15, 23, 42, 255),
        "grid": (30, 41, 59, 255),
        "card": (24, 35, 56, 248),
        "card_border": (56, 189, 248, 95),
        "text": (248, 250, 252, 255),
        "muted": (203, 213, 225, 255),
        "accent": (56, 189, 248, 255),
        "amber": (250, 204, 21, 255),
        "pill_bg": (30, 58, 138, 255),
        "pill_text": (186, 230, 253, 255),
        "takeaway_bg": (15, 23, 42, 255),
    },
    "history_geo": {
        "bg": (243, 234, 216, 255),
        "grid": (200, 182, 150, 255),
        "card": (252, 248, 238, 250),
        "card_border": (200, 182, 150, 255),
        "text": (28, 25, 23, 255),
        "muted": (87, 83, 78, 255),
        "accent": (185, 28, 28, 255),
        "amber": (217, 119, 6, 255),
        "pill_bg": (254, 243, 199, 255),
        "pill_text": (120, 53, 15, 255),
        "takeaway_bg": (245, 238, 220, 255),
    },
    "psychology_story": {
        "bg": (20, 18, 29, 255),
        "grid": (38, 33, 56, 255),
        "card": (32, 28, 48, 248),
        "card_border": (250, 204, 21, 90),
        "text": (248, 250, 252, 255),
        "muted": (203, 213, 225, 255),
        "accent": (250, 204, 21, 255),
        "amber": (245, 158, 11, 255),
        "pill_bg": (63, 52, 94, 255),
        "pill_text": (254, 240, 138, 255),
        "takeaway_bg": (24, 20, 36, 255),
    },
    "cosmos_mystery": {
        "bg": (9, 13, 22, 255),
        "grid": (30, 41, 59, 255),
        "card": (17, 24, 39, 246),
        "card_border": (245, 158, 11, 100),
        "text": (248, 250, 252, 255),
        "muted": (203, 213, 225, 255),
        "accent": (245, 158, 11, 255),
        "amber": (56, 189, 248, 255),
        "pill_bg": (30, 41, 59, 255),
        "pill_text": (253, 230, 138, 255),
        "takeaway_bg": (12, 18, 30, 255),
    },
}


class BackdropRenderer:
    """Bộ sinh phông nền 30fps nhẹ CPU, cache lớp nền tĩnh + lặp mượt chu kỳ 4 giây."""

    def __init__(self, domain: str | None, width: int, height: int) -> None:
        self.domain: StickvDomain = normalize_domain(domain)
        self.width = max(64, int(width))
        self.height = max(64, int(height))
        self.palette = DOMAIN_PALETTES[self.domain]
        self._base: Image.Image = self._build_base()

        # Tọa độ sao xác định cho cosmos_mystery
        rng = np.random.default_rng(seed=42)
        self._far_stars = rng.random((45, 3))
        self._near_stars = rng.random((22, 3))

    def _build_base(self) -> Image.Image:
        bg_rgb = self.palette["bg"][:3]
        if self.domain == "psychology_story":
            # Radial spotlight ấm tập trung vào nhân vật
            yy, xx = np.mgrid[0 : self.height, 0 : self.width]
            cx = self.width * 0.5
            cy = self.height * 0.62
            dist = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 0.85) ** 2)
            max_r = max(self.width, self.height) * 0.62
            glow = np.clip(1.0 - dist / max(1.0, max_r), 0.0, 1.0) ** 1.8
            c0 = np.array([20, 18, 29], dtype=np.float32)
            c1 = np.array([46, 39, 70], dtype=np.float32)
            arr = (c0 + (c1 - c0) * glow[..., None]).astype(np.uint8)
            return Image.fromarray(arr, mode="RGB")

        img = Image.new("RGB", (self.width, self.height), bg_rgb)
        if self.domain == "paper_classic":
            draw = ImageDraw.Draw(img)
            pad = 24
            draw.rectangle(
                (pad, pad, self.width - pad, self.height - pad),
                outline=(226, 218, 203),
                width=2,
            )
        return img

    def render_frame(self, t_sec: float) -> Image.Image:
        """Trả về khung hình RGB ở thời điểm `t_sec` (chu kỳ lặp 4.0s)."""
        phase = (t_sec % LOOP_DURATION_S) / LOOP_DURATION_S  # [0, 1)
        angle = phase * 2.0 * math.pi
        frame = self._base.copy()
        draw = ImageDraw.Draw(frame, "RGBA")
        w, h = self.width, self.height

        if self.domain == "paper_classic":
            step = 72
            ox = int(round(phase * step))
            oy = int(round(phase * step * 0.5))
            dot_c = (210, 200, 184, 95)
            for x in range(ox - step, w + step, step):
                for y in range(oy - step, h + step, step):
                    draw.ellipse((x - 1, y - 1, x + 2, y + 2), fill=dot_c)

        elif self.domain == "physics_science":
            step = 84
            shift = int(round(phase * step))
            grid_c = (30, 41, 59, 210)
            for x in range(shift - step, w + step, step):
                draw.line([(x, 0), (x, h)], fill=grid_c, width=1)
            for y in range(shift - step, h + step, step):
                draw.line([(0, y), (w, y)], fill=grid_c, width=1)
            # Hạt quỹ đạo mờ
            for idx in range(6):
                a = angle + idx * (math.pi / 3.0)
                px = int(w * 0.5 + math.cos(a) * w * 0.34)
                py = int(h * 0.42 + math.sin(a * 2.0) * h * 0.16)
                draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=(56, 189, 248, 95))

        elif self.domain == "history_geo":
            step = 110
            ox = int(round(phase * step))
            line_c = (200, 182, 150, 130)
            for x in range(ox - step, w + step, step):
                draw.line([(x, 0), (x, h)], fill=line_c, width=1)
            for y in range(0, h, step):
                draw.line([(0, y), (w, y)], fill=line_c, width=1)
            # La bàn xoay mờ ở góc trên phải
            cx, cy, r = w - 110, 110, 56
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(185, 28, 28, 65), width=2)
            nx = cx + int(math.cos(angle) * (r - 8))
            ny = cy + int(math.sin(angle) * (r - 8))
            draw.line([(cx, cy), (nx, ny)], fill=(185, 28, 28, 90), width=3)

        elif self.domain == "psychology_story":
            pulse = 0.5 + 0.5 * math.sin(angle)
            r = int(min(w, h) * (0.28 + 0.03 * pulse))
            cx, cy = w // 2, int(h * 0.60)
            draw.ellipse(
                (cx - r, cy - r, cx + r, cy + r),
                outline=(250, 204, 21, int(28 + 20 * pulse)),
                width=3,
            )

        elif self.domain == "cosmos_mystery":
            for sx, sy, sb in self._far_stars:
                x = int(((sx + phase * 0.15) % 1.0) * w)
                y = int(sy * h)
                alpha = int(120 + 90 * math.sin(angle + sb * 6.28))
                draw.ellipse((x - 1, y - 1, x + 2, y + 2), fill=(226, 232, 240, max(40, alpha)))
            for sx, sy, sb in self._near_stars:
                x = int(((sx + phase * 0.35) % 1.0) * w)
                y = int(sy * h)
                alpha = int(160 + 90 * math.cos(angle + sb * 6.28))
                draw.ellipse((x - 2, y - 2, x + 3, y + 3), fill=(245, 158, 11, max(60, alpha)))

        return frame

    def close(self) -> None:
        self._base.close()
