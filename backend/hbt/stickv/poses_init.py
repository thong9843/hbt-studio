"""Khởi tạo bộ 8 dáng nhân vật người que chuẩn HBT Studio (PNG nền trong suốt).

Vẽ bằng Pillow ở độ phân giải 2x (1024x1280) rồi thu nhỏ LANCZOS về 512x640
để nét vẽ vector sắc nét, có viền sáng nhẹ giúp nổi bật trên cả nền kem (#FAF7F0)
và nền tối (#111827), kèm điểm nhấn thương hiệu Đỏ (#D9232E) / Vàng (#F59E0B).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

from hbt.config import REPO_ROOT

DEFAULT_POSES: Final[tuple[str, ...]] = (
    "explain",
    "think",
    "shock",
    "happy",
    "run",
    "rich",
    "sad",
    "angry",
)

POSE_TITLES: Final[dict[str, str]] = {
    "explain": "Giải thích / Chỉ bảng",
    "think": "Suy nghĩ / Thắc mắc",
    "shock": "Bất ngờ / Sốc",
    "happy": "Vui vẻ / Hào hứng",
    "run": "Chạy / Vội vã",
    "rich": "Giàu có / Tiền bạc",
    "sad": "Buồn bã / Thất vọng",
    "angry": "Tức giận / Phản đối",
}

# Bảng màu chuẩn HBT Stickman (tương phản tốt trên cả nền sáng & tối)
INK = (28, 36, 52, 255)
RIM = (255, 255, 255, 225)
HEAD_FILL = (255, 253, 248, 255)
HBT_RED = (217, 35, 46, 255)
HBT_AMBER = (245, 158, 11, 255)
HBT_GOLD = (250, 204, 21, 255)
TEAR_BLUE = (56, 189, 248, 255)

_SCALE = 2
_W = 512 * _SCALE
_H = 640 * _SCALE


def _line(
    draw: ImageDraw.ImageDraw,
    pts: list[tuple[float, float]],
    width: int = 24,
    color: tuple[int, int, int, int] = INK,
    *,
    rim: bool = True,
) -> None:
    """Vẽ đoạn nét tròn đầu (joint/cap) kèm viền sáng nhẹ để nổi trên nền tối."""
    if rim:
        rim_w = width + 10
        draw.line(pts, fill=RIM, width=rim_w, joint="curve")
        for x, y in (pts[0], pts[-1]):
            r = rim_w / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=RIM)
    draw.line(pts, fill=color, width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):
        r = width / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _draw_head(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    r: float = 112,
    *,
    headband: bool = False,
) -> None:
    # Viền ngoài nhẹ
    draw.ellipse((cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6), fill=RIM)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=HEAD_FILL, outline=INK, width=22)
    if headband:
        draw.arc(
            (cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6),
            start=205,
            end=335,
            fill=HBT_RED,
            width=26,
        )


def _draw_tie(draw: ImageDraw.ImageDraw, nx: float, ny: float, tilt: float = 0.0) -> None:
    """Vẽ cà vạt Đỏ HBT ở cổ tạo điểm nhấn nhận diện."""
    pts = [
        (nx, ny),
        (nx - 22 + tilt, ny + 76),
        (nx + tilt * 1.3, ny + 128),
        (nx + 22 + tilt, ny + 76),
    ]
    draw.polygon(pts, fill=HBT_RED)
    draw.ellipse((nx - 14, ny - 8, nx + 14, ny + 18), fill=HBT_AMBER)


def _draw_eyes(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    dx: float = 38,
    dy: float = -12,
    style: str = "normal",
) -> None:
    lx, rx, ey = cx - dx, cx + dx, cy + dy
    if style == "happy":
        for ex in (lx, rx):
            draw.arc((ex - 20, ey - 14, ex + 20, ey + 18), start=190, end=350, fill=INK, width=12)
    elif style == "shock":
        for ex in (lx, rx):
            draw.ellipse(
                (ex - 22, ey - 22, ex + 22, ey + 22),
                fill=(255, 255, 255, 255),
                outline=INK,
                width=10,
            )
            draw.ellipse((ex - 7, ey - 7, ex + 7, ey + 7), fill=INK)
    elif style == "sad":
        for ex in (lx, rx):
            draw.ellipse((ex - 11, ey - 11, ex + 11, ey + 11), fill=INK)
        _line(draw, [(lx - 22, ey - 18), (lx + 14, ey - 32)], width=10, rim=False)
        _line(draw, [(rx + 22, ey - 18), (rx - 14, ey - 32)], width=10, rim=False)
    elif style == "angry":
        for ex in (lx, rx):
            draw.ellipse((ex - 12, ey - 12, ex + 12, ey + 12), fill=HBT_RED)
        _line(draw, [(lx - 24, ey - 32), (lx + 18, ey - 14)], width=12, rim=False)
        _line(draw, [(rx + 24, ey - 32), (rx - 18, ey - 14)], width=12, rim=False)
    else:
        for ex in (lx, rx):
            draw.ellipse((ex - 13, ey - 15, ex + 13, ey + 15), fill=INK)
            draw.ellipse((ex - 5, ey - 9, ex + 1, ey - 3), fill=(255, 255, 255, 255))


def _draw_mouth(draw: ImageDraw.ImageDraw, cx: float, cy: float, style: str = "smile") -> None:
    my = cy + 44
    if style == "smile":
        draw.arc((cx - 34, my - 22, cx + 34, my + 24), start=15, end=165, fill=INK, width=12)
    elif style == "open_happy":
        draw.chord(
            (cx - 38, my - 18, cx + 38, my + 34),
            start=0,
            end=180,
            fill=HBT_RED,
            outline=INK,
            width=10,
        )
    elif style == "shock":
        draw.ellipse((cx - 24, my - 14, cx + 24, my + 34), fill=HBT_RED, outline=INK, width=10)
    elif style == "think":
        _line(draw, [(cx - 24, my + 8), (cx + 22, my)], width=11, rim=False)
    elif style == "sad":
        draw.arc((cx - 30, my + 2, cx + 30, my + 40), start=195, end=345, fill=INK, width=11)
    elif style == "angry":
        draw.polygon(
            [(cx - 32, my + 20), (cx - 12, my - 4), (cx + 12, my - 4), (cx + 32, my + 20)],
            fill=(255, 255, 255, 255),
            outline=INK,
        )


def _draw_star(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple[int, int, int, int]
) -> None:
    pts: list[tuple[float, float]] = []
    for i in range(10):
        ang = math.radians(i * 36 - 90)
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    draw.polygon(pts, fill=color, outline=INK)


def render_pose_png(pose: str, out_path: Path) -> Path:
    """Vẽ một dáng nhân vật người que chuẩn và lưu ra PNG trong suốt 512x640."""
    if pose not in DEFAULT_POSES:
        raise ValueError(f"Dáng không hợp lệ: {pose}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    try:
        draw = ImageDraw.Draw(canvas)
        cx = _W * 0.48
        head_y = 220.0
        neck_y = 336.0
        hip_y = 740.0

        # Bóng đất mềm (2.5D grounding)
        draw.ellipse((cx - 190, 1080, cx + 190, 1150), fill=(15, 23, 42, 48))

        if pose == "explain":
            _line(draw, [(cx, hip_y), (cx - 95, 930), (cx - 115, 1100)])
            _line(draw, [(cx, hip_y), (cx + 95, 930), (cx + 115, 1100)])
            _line(draw, [(cx, neck_y), (cx, hip_y)])
            _line(draw, [(cx, neck_y + 40), (cx - 120, 520), (cx - 75, 650)])
            _line(draw, [(cx, neck_y + 40), (cx + 150, 410), (cx + 275, 340)])
            # Que chỉ bảng HBT Amber
            _line(draw, [(cx + 265, 345), (cx + 390, 235)], width=14, color=HBT_AMBER)
            _draw_tie(draw, cx, neck_y + 12)
            _draw_head(draw, cx, head_y, headband=True)
            _draw_eyes(draw, cx + 10, head_y, style="normal")
            _draw_mouth(draw, cx + 10, head_y, style="smile")

        elif pose == "think":
            _line(draw, [(cx, hip_y), (cx - 75, 930), (cx - 90, 1100)])
            _line(draw, [(cx, hip_y), (cx + 85, 930), (cx + 70, 1100)])
            _line(draw, [(cx, neck_y), (cx - 12, hip_y)])
            _line(draw, [(cx, neck_y + 40), (cx - 110, 560), (cx + 10, 560)])
            _line(draw, [(cx, neck_y + 40), (cx + 120, 480), (cx + 46, 330)])
            _draw_tie(draw, cx, neck_y + 10)
            _draw_head(draw, cx - 10, head_y)
            _draw_eyes(draw, cx - 10, head_y, dy=-18, style="normal")
            _draw_mouth(draw, cx - 10, head_y, style="think")
            # Bóng đèn / dấu hỏi vàng
            draw.ellipse((cx + 170, 88, cx + 266, 184), fill=HBT_GOLD, outline=INK, width=10)
            draw.rectangle((cx + 200, 182, cx + 236, 212), fill=HBT_AMBER, outline=INK, width=6)

        elif pose == "shock":
            _line(draw, [(cx, hip_y), (cx - 135, 920), (cx - 155, 1100)])
            _line(draw, [(cx, hip_y), (cx + 135, 920), (cx + 155, 1100)])
            _line(draw, [(cx, neck_y), (cx, hip_y)])
            _line(draw, [(cx, neck_y + 40), (cx - 170, 340), (cx - 210, 195)])
            _line(draw, [(cx, neck_y + 40), (cx + 170, 340), (cx + 210, 195)])
            _draw_tie(draw, cx, neck_y + 12)
            _draw_head(draw, cx, head_y)
            _draw_eyes(draw, cx, head_y, style="shock")
            _draw_mouth(draw, cx, head_y, style="shock")
            # Tia sét sốc Đỏ/Vàng
            _line(draw, [(cx - 220, 90), (cx - 170, 145)], width=16, color=HBT_RED)
            _line(draw, [(cx + 220, 90), (cx + 170, 145)], width=16, color=HBT_AMBER)

        elif pose == "happy":
            _line(draw, [(cx, hip_y - 30), (cx - 120, 900), (cx - 165, 1040)])
            _line(draw, [(cx, hip_y - 30), (cx + 120, 900), (cx + 165, 1040)])
            _line(draw, [(cx, neck_y - 20), (cx, hip_y - 30)])
            _line(draw, [(cx, neck_y + 20), (cx - 160, 260), (cx - 230, 140)])
            _line(draw, [(cx, neck_y + 20), (cx + 160, 260), (cx + 230, 140)])
            _draw_tie(draw, cx, neck_y - 8)
            _draw_head(draw, cx, head_y - 20, headband=True)
            _draw_eyes(draw, cx, head_y - 20, style="happy")
            _draw_mouth(draw, cx, head_y - 20, style="open_happy")
            _draw_star(draw, cx - 230, 270, 34, HBT_GOLD)
            _draw_star(draw, cx + 235, 250, 38, HBT_AMBER)

        elif pose == "run":
            rcx = cx + 40
            _line(draw, [(rcx - 30, hip_y), (rcx - 190, 880), (rcx - 270, 1030)])
            _line(draw, [(rcx - 30, hip_y), (rcx + 140, 870), (rcx + 110, 1085)])
            _line(draw, [(rcx + 30, neck_y + 20), (rcx - 30, hip_y)])
            _line(draw, [(rcx + 24, neck_y + 50), (rcx - 140, 440), (rcx - 190, 560)])
            _line(draw, [(rcx + 24, neck_y + 50), (rcx + 185, 420), (rcx + 265, 320)])
            _draw_tie(draw, rcx + 24, neck_y + 24, tilt=-28)
            _draw_head(draw, rcx + 45, head_y + 15, headband=True)
            _draw_eyes(draw, rcx + 60, head_y + 15, style="normal")
            _draw_mouth(draw, rcx + 60, head_y + 15, style="smile")
            # Vệt tốc độ
            for sy in (260, 420, 590):
                _line(draw, [(90, sy), (210, sy)], width=14, color=HBT_AMBER, rim=False)

        elif pose == "rich":
            _line(draw, [(cx, hip_y), (cx - 90, 930), (cx - 105, 1100)])
            _line(draw, [(cx, hip_y), (cx + 90, 930), (cx + 105, 1100)])
            _line(draw, [(cx, neck_y), (cx, hip_y)])
            _line(draw, [(cx, neck_y + 40), (cx - 130, 500), (cx - 210, 400)])
            _line(draw, [(cx, neck_y + 40), (cx + 130, 500), (cx + 210, 400)])
            _draw_tie(draw, cx, neck_y + 12)
            _draw_head(draw, cx, head_y)
            # Kính râm HBT ngầu
            draw.rounded_rectangle((cx - 86, head_y - 36, cx - 8, head_y + 12), radius=12, fill=INK)
            draw.rounded_rectangle((cx + 8, head_y - 36, cx + 86, head_y + 12), radius=12, fill=INK)
            _line(draw, [(cx - 10, head_y - 16), (cx + 10, head_y - 16)], width=10, rim=False)
            _draw_mouth(draw, cx, head_y, style="open_happy")
            # Đồng xu vàng
            for mx, my in ((cx - 230, 300), (cx + 230, 290), (cx + 275, 410)):
                draw.ellipse(
                    (mx - 42, my - 42, mx + 42, my + 42), fill=HBT_GOLD, outline=INK, width=10
                )

        elif pose == "sad":
            _line(draw, [(cx, hip_y + 20), (cx - 65, 940), (cx - 75, 1100)])
            _line(draw, [(cx, hip_y + 20), (cx + 65, 940), (cx + 75, 1100)])
            _line(draw, [(cx - 10, neck_y + 40), (cx, hip_y + 20)])
            _line(draw, [(cx - 10, neck_y + 70), (cx - 95, 620), (cx - 70, 770)])
            _line(draw, [(cx - 10, neck_y + 70), (cx + 95, 620), (cx + 70, 770)])
            _draw_tie(draw, cx - 8, neck_y + 46)
            _draw_head(draw, cx - 18, head_y + 45)
            _draw_eyes(draw, cx - 18, head_y + 45, style="sad")
            _draw_mouth(draw, cx - 18, head_y + 45, style="sad")
            # Giọt nước mắt
            draw.ellipse((cx - 72, head_y + 62, cx - 44, head_y + 102), fill=TEAR_BLUE)

        elif pose == "angry":
            _line(draw, [(cx, hip_y), (cx - 115, 930), (cx - 135, 1100)])
            _line(draw, [(cx, hip_y), (cx + 115, 930), (cx + 135, 1100)])
            _line(draw, [(cx, neck_y), (cx, hip_y)])
            _line(draw, [(cx, neck_y + 40), (cx - 165, 510), (cx - 95, 635)])
            _line(draw, [(cx, neck_y + 40), (cx + 165, 510), (cx + 95, 635)])
            _draw_tie(draw, cx, neck_y + 12)
            _draw_head(draw, cx, head_y)
            _draw_eyes(draw, cx, head_y, style="angry")
            _draw_mouth(draw, cx, head_y, style="angry")
            # Ký hiệu gân giận màu đỏ
            vx, vy = cx + 96, head_y - 86
            _line(
                draw,
                [(vx - 18, vy), (vx, vy + 18), (vx - 18, vy + 36)],
                width=11,
                color=HBT_RED,
                rim=False,
            )
            _line(
                draw,
                [(vx + 18, vy), (vx, vy + 18), (vx + 18, vy + 36)],
                width=11,
                color=HBT_RED,
                rim=False,
            )

        resized = canvas.resize((512, 640), Image.Resampling.LANCZOS)
        try:
            resized.save(out_path, format="PNG", optimize=True)
        finally:
            resized.close()
    finally:
        canvas.close()

    return out_path


def ensure_default_poses(poses_dir: Path | None = None) -> list[Path]:
    """Đảm bảo đủ 8 dáng người que chuẩn và index.json trong library/stickman/poses/."""
    target_dir = (
        Path(poses_dir) if poses_dir is not None else (REPO_ROOT / "library" / "stickman" / "poses")
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    entries: list[dict[str, object]] = []
    for pose in DEFAULT_POSES:
        png = target_dir / f"{pose}.png"
        if not png.is_file():
            render_pose_png(pose, png)
        created.append(png)
        entries.append(
            {
                "id": f"stickman-{pose}",
                "file": f"{pose}.png",
                "title": POSE_TITLES[pose],
                "tags": [pose, "stickman", "hbt"],
            }
        )

    index_path = target_dir / "index.json"
    if not index_path.is_file():
        index_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return created


if __name__ == "__main__":
    paths = ensure_default_poses()
    print(f"Đã khởi tạo {len(paths)} dáng người que tại {paths[0].parent}")
