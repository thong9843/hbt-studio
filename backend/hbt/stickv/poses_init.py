"""Khởi tạo bộ 8 dáng nhân vật người que chuẩn HBT Studio (Supersampling 3x PNG nền trong suốt).

Vẽ bằng Pillow ở độ phân giải 3x (1536x1920) rồi thu nhỏ LANCZOS về 512x640
để nét vẽ vector mịn mượt không răng cưa, đầy đủ khớp vai-khuỷu tay-bàn tay-đầu gối-bàn chân,
mắt có tròng/lông mày biểu cảm, cà vạt đỏ HBT và đạo cụ vector sắc nét.
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

INK = (24, 32, 48, 255)
RIM = (255, 255, 255, 235)
HEAD_FILL = (255, 253, 248, 255)
HBT_RED = (217, 35, 46, 255)
HBT_AMBER = (245, 158, 11, 255)
HBT_GOLD = (250, 204, 21, 255)
TEAR_BLUE = (56, 189, 248, 255)

_SCALE = 3
_W = 512 * _SCALE
_H = 640 * _SCALE


def _limb(
    draw: ImageDraw.ImageDraw,
    pts: list[tuple[float, float]],
    width: int = 34,
    color: tuple[int, int, int, int] = INK,
    *,
    rim: bool = True,
    hand_or_foot: str | None = None,
) -> None:
    """Vẽ chi có khớp tròn (vai/khuỷu/gối) và bàn tay/bàn chân ở điểm cuối."""
    if rim:
        rim_w = width + 14
        draw.line(pts, fill=RIM, width=rim_w, joint="curve")
        for x, y in pts:
            r = rim_w / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=RIM)
    draw.line(pts, fill=color, width=width, joint="curve")
    for x, y in pts:
        r = width / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    ex, ey = pts[-1]
    if hand_or_foot == "hand":
        hr = width * 0.72
        draw.ellipse((ex - hr - 4, ey - hr - 4, ex + hr + 4, ey + hr + 4), fill=RIM)
        draw.ellipse(
            (ex - hr, ey - hr, ex + hr, ey + hr),
            fill=HEAD_FILL,
            outline=INK,
            width=10,
        )
    elif hand_or_foot == "foot":
        fx0, fy0 = ex - width * 0.55, ey - width * 0.35
        fx1, fy1 = ex + width * 1.15, ey + width * 0.52
        draw.rounded_rectangle((fx0 - 4, fy0 - 4, fx1 + 4, fy1 + 4), radius=18, fill=RIM)
        draw.rounded_rectangle((fx0, fy0, fx1, fy1), radius=16, fill=INK)


def _draw_head(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    r: float = 164,
    *,
    headband: bool = False,
) -> None:
    draw.ellipse((cx - r - 9, cy - r - 9, cx + r + 9, cy + r + 9), fill=RIM)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=HEAD_FILL, outline=INK, width=30)
    if headband:
        draw.arc(
            (cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10),
            start=204,
            end=336,
            fill=HBT_RED,
            width=34,
        )


def _draw_tie(draw: ImageDraw.ImageDraw, nx: float, ny: float, tilt: float = 0.0) -> None:
    pts = [
        (nx, ny),
        (nx - 32 + tilt, ny + 114),
        (nx + tilt * 1.3, ny + 190),
        (nx + 32 + tilt, ny + 114),
    ]
    draw.polygon(pts, fill=HBT_RED, outline=INK)
    draw.ellipse((nx - 20, ny - 10, nx + 20, ny + 26), fill=HBT_AMBER, outline=INK, width=6)


def _draw_eyes(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    dx: float = 56,
    dy: float = -18,
    style: str = "normal",
) -> None:
    lx, rx, ey = cx - dx, cx + dx, cy + dy
    if style == "happy":
        for ex in (lx, rx):
            draw.arc((ex - 28, ey - 20, ex + 28, ey + 24), start=190, end=350, fill=INK, width=16)
    elif style == "shock":
        for ex in (lx, rx):
            draw.ellipse(
                (ex - 32, ey - 32, ex + 32, ey + 32),
                fill=(255, 255, 255, 255),
                outline=INK,
                width=14,
            )
            draw.ellipse((ex - 10, ey - 10, ex + 10, ey + 10), fill=INK)
    elif style == "sad":
        for ex in (lx, rx):
            draw.ellipse((ex - 16, ey - 16, ex + 16, ey + 16), fill=INK)
        _limb(draw, [(lx - 34, ey - 26), (lx + 20, ey - 46)], width=13, rim=False)
        _limb(draw, [(rx + 34, ey - 26), (rx - 20, ey - 46)], width=13, rim=False)
    elif style == "angry":
        for ex in (lx, rx):
            draw.ellipse((ex - 18, ey - 18, ex + 18, ey + 18), fill=HBT_RED, outline=INK, width=6)
        _limb(draw, [(lx - 36, ey - 46), (lx + 24, ey - 20)], width=16, rim=False)
        _limb(draw, [(rx + 36, ey - 46), (rx - 24, ey - 20)], width=16, rim=False)
    else:
        for ex in (lx, rx):
            draw.ellipse(
                (ex - 22, ey - 26, ex + 22, ey + 26),
                fill=(255, 255, 255, 255),
                outline=INK,
                width=9,
            )
            draw.ellipse((ex - 11, ey - 12, ex + 11, ey + 12), fill=INK)
            draw.ellipse((ex - 6, ey - 10, ex + 1, ey - 3), fill=(255, 255, 255, 255))
        _limb(draw, [(lx - 24, ey - 42), (lx + 22, ey - 44)], width=11, rim=False)
        _limb(draw, [(rx - 22, ey - 44), (rx + 24, ey - 42)], width=11, rim=False)


def _draw_mouth(draw: ImageDraw.ImageDraw, cx: float, cy: float, style: str = "smile") -> None:
    my = cy + 64
    if style == "smile":
        draw.arc((cx - 48, my - 30, cx + 48, my + 34), start=15, end=165, fill=INK, width=16)
    elif style == "open_happy":
        draw.chord(
            (cx - 54, my - 24, cx + 54, my + 48),
            start=0,
            end=180,
            fill=HBT_RED,
            outline=INK,
            width=14,
        )
    elif style == "shock":
        draw.ellipse((cx - 34, my - 20, cx + 34, my + 48), fill=HBT_RED, outline=INK, width=14)
    elif style == "think":
        _limb(draw, [(cx - 34, my + 10), (cx + 32, my)], width=15, rim=False)
    elif style == "sad":
        draw.arc((cx - 44, my + 4, cx + 44, my + 58), start=195, end=345, fill=INK, width=15)
    elif style == "angry":
        draw.polygon(
            [(cx - 46, my + 28), (cx - 18, my - 6), (cx + 18, my - 6), (cx + 46, my + 28)],
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
    """Vẽ một dáng nhân vật người que chuẩn (Supersampling 3x -> 512x640 RGBA)."""
    if pose not in DEFAULT_POSES:
        raise ValueError(f"Dáng không hợp lệ: {pose}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    try:
        draw = ImageDraw.Draw(canvas)
        cx = _W * 0.48
        head_y = 330.0
        neck_y = 504.0
        hip_y = 1110.0

        draw.ellipse((cx - 280, 1620, cx + 280, 1720), fill=(15, 23, 42, 52))

        if pose == "explain":
            _limb(draw, [(cx, hip_y), (cx - 140, 1390), (cx - 165, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y), (cx + 140, 1390), (cx + 165, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, neck_y), (cx, hip_y)])
            _limb(draw, [(cx, neck_y + 58), (cx - 175, 780), (cx - 110, 975)], hand_or_foot="hand")
            _limb(draw, [(cx, neck_y + 58), (cx + 225, 615), (cx + 410, 510)], hand_or_foot="hand")
            _limb(draw, [(cx + 400, 515), (cx + 585, 345)], width=20, color=HBT_AMBER)
            _draw_tie(draw, cx, neck_y + 18)
            _draw_head(draw, cx, head_y, headband=True)
            _draw_eyes(draw, cx + 14, head_y, style="normal")
            _draw_mouth(draw, cx + 14, head_y, style="smile")

        elif pose == "think":
            _limb(draw, [(cx, hip_y), (cx - 115, 1395), (cx - 135, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y), (cx + 125, 1395), (cx + 105, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, neck_y), (cx - 18, hip_y)])
            _limb(draw, [(cx, neck_y + 58), (cx - 165, 840), (cx + 15, 840)], hand_or_foot="hand")
            _limb(draw, [(cx, neck_y + 58), (cx + 180, 720), (cx + 68, 495)], hand_or_foot="hand")
            _draw_tie(draw, cx, neck_y + 14)
            _draw_head(draw, cx - 14, head_y)
            _draw_eyes(draw, cx - 14, head_y, dy=-26, style="normal")
            _draw_mouth(draw, cx - 14, head_y, style="think")
            draw.ellipse((cx + 255, 132, cx + 398, 276), fill=HBT_GOLD, outline=INK, width=14)
            draw.rectangle((cx + 300, 272, cx + 354, 318), fill=HBT_AMBER, outline=INK, width=9)

        elif pose == "shock":
            _limb(draw, [(cx, hip_y), (cx - 200, 1380), (cx - 230, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y), (cx + 200, 1380), (cx + 230, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, neck_y), (cx, hip_y)])
            _limb(draw, [(cx, neck_y + 58), (cx - 255, 510), (cx - 315, 290)], hand_or_foot="hand")
            _limb(draw, [(cx, neck_y + 58), (cx + 255, 510), (cx + 315, 290)], hand_or_foot="hand")
            _draw_tie(draw, cx, neck_y + 18)
            _draw_head(draw, cx, head_y)
            _draw_eyes(draw, cx, head_y, style="shock")
            _draw_mouth(draw, cx, head_y, style="shock")
            _limb(draw, [(cx - 330, 135), (cx - 255, 218)], width=22, color=HBT_RED)
            _limb(draw, [(cx + 330, 135), (cx + 255, 218)], width=22, color=HBT_AMBER)

        elif pose == "happy":
            _limb(draw, [(cx, hip_y - 45), (cx - 180, 1350), (cx - 245, 1560)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y - 45), (cx + 180, 1350), (cx + 245, 1560)], hand_or_foot="foot")
            _limb(draw, [(cx, neck_y - 30), (cx, hip_y - 45)])
            _limb(draw, [(cx, neck_y + 30), (cx - 240, 390), (cx - 345, 210)], hand_or_foot="hand")
            _limb(draw, [(cx, neck_y + 30), (cx + 240, 390), (cx + 345, 210)], hand_or_foot="hand")
            _draw_tie(draw, cx, neck_y - 12)
            _draw_head(draw, cx, head_y - 30, headband=True)
            _draw_eyes(draw, cx, head_y - 30, style="happy")
            _draw_mouth(draw, cx, head_y - 30, style="open_happy")
            _draw_star(draw, cx - 345, 405, 50, HBT_GOLD)
            _draw_star(draw, cx + 352, 375, 56, HBT_AMBER)

        elif pose == "run":
            rcx = cx + 60
            _limb(
                draw, [(rcx - 45, hip_y), (rcx - 285, 1320), (rcx - 405, 1545)], hand_or_foot="foot"
            )
            _limb(
                draw, [(rcx - 45, hip_y), (rcx + 210, 1305), (rcx + 165, 1628)], hand_or_foot="foot"
            )
            _limb(draw, [(rcx + 45, neck_y + 30), (rcx - 45, hip_y)])
            _limb(
                draw,
                [(rcx + 36, neck_y + 75), (rcx - 210, 660), (rcx - 285, 840)],
                hand_or_foot="hand",
            )
            _limb(
                draw,
                [(rcx + 36, neck_y + 75), (rcx + 278, 630), (rcx + 398, 480)],
                hand_or_foot="hand",
            )
            _draw_tie(draw, rcx + 36, neck_y + 36, tilt=-42)
            _draw_head(draw, rcx + 68, head_y + 22, headband=True)
            _draw_eyes(draw, rcx + 90, head_y + 22, style="normal")
            _draw_mouth(draw, rcx + 90, head_y + 22, style="smile")
            for sy in (390, 630, 885):
                _limb(draw, [(135, sy), (315, sy)], width=20, color=HBT_AMBER, rim=False)

        elif pose == "rich":
            _limb(draw, [(cx, hip_y), (cx - 135, 1395), (cx - 158, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y), (cx + 135, 1395), (cx + 158, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, neck_y), (cx, hip_y)])
            _limb(draw, [(cx, neck_y + 58), (cx - 195, 750), (cx - 315, 600)], hand_or_foot="hand")
            _limb(draw, [(cx, neck_y + 58), (cx + 195, 750), (cx + 315, 600)], hand_or_foot="hand")
            _draw_tie(draw, cx, neck_y + 18)
            _draw_head(draw, cx, head_y)
            draw.rounded_rectangle(
                (cx - 128, head_y - 54, cx - 12, head_y + 18), radius=18, fill=INK
            )
            draw.rounded_rectangle(
                (cx + 12, head_y - 54, cx + 128, head_y + 18), radius=18, fill=INK
            )
            _limb(draw, [(cx - 14, head_y - 24), (cx + 14, head_y - 24)], width=14, rim=False)
            _draw_mouth(draw, cx, head_y, style="open_happy")
            for mx, my in ((cx - 345, 450), (cx + 345, 435), (cx + 412, 615)):
                draw.ellipse(
                    (mx - 62, my - 62, mx + 62, my + 62), fill=HBT_GOLD, outline=INK, width=14
                )

        elif pose == "sad":
            _limb(draw, [(cx, hip_y + 30), (cx - 98, 1410), (cx - 112, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y + 30), (cx + 98, 1410), (cx + 112, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx - 15, neck_y + 60), (cx, hip_y + 30)])
            _limb(
                draw,
                [(cx - 15, neck_y + 105), (cx - 142, 930), (cx - 105, 1155)],
                hand_or_foot="hand",
            )
            _limb(
                draw,
                [(cx - 15, neck_y + 105), (cx + 142, 930), (cx + 105, 1155)],
                hand_or_foot="hand",
            )
            _draw_tie(draw, cx - 12, neck_y + 69)
            _draw_head(draw, cx - 27, head_y + 68)
            _draw_eyes(draw, cx - 27, head_y + 68, style="sad")
            _draw_mouth(draw, cx - 27, head_y + 68, style="sad")
            draw.ellipse((cx - 108, head_y + 93, cx - 66, head_y + 153), fill=TEAR_BLUE)

        elif pose == "angry":
            _limb(draw, [(cx, hip_y), (cx - 172, 1395), (cx - 202, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, hip_y), (cx + 172, 1395), (cx + 202, 1650)], hand_or_foot="foot")
            _limb(draw, [(cx, neck_y), (cx, hip_y)])
            _limb(draw, [(cx, neck_y + 58), (cx - 248, 765), (cx - 142, 952)], hand_or_foot="hand")
            _limb(draw, [(cx, neck_y + 58), (cx + 248, 765), (cx + 142, 952)], hand_or_foot="hand")
            _draw_tie(draw, cx, neck_y + 18)
            _draw_head(draw, cx, head_y)
            _draw_eyes(draw, cx, head_y, style="angry")
            _draw_mouth(draw, cx, head_y, style="angry")
            vx, vy = cx + 144, head_y - 129
            _limb(
                draw,
                [(vx - 26, vy), (vx, vy + 26), (vx - 26, vy + 54)],
                width=16,
                color=HBT_RED,
                rim=False,
            )
            _limb(
                draw,
                [(vx + 26, vy), (vx, vy + 26), (vx + 26, vy + 54)],
                width=16,
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
    print(f"Đã khởi tạo {len(paths)} dáng người que 3x tại {paths[0].parent}")
