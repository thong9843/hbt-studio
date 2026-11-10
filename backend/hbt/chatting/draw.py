"""Vẽ giao diện chat Messenger / Zalo lên video bằng Pillow theo §7."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from hbt.chatting.models import Character, Message
from hbt.chatting.themes.base import ChatTheme

FONTS_DIR = Path(__file__).resolve().parents[1] / "fonts"
FONT_REGULAR = FONTS_DIR / "BeVietnamPro-Medium.ttf"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Chia văn bản thành các dòng không vượt quá max_width."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current_line = words[0]

    for w in words[1:]:
        test_line = f"{current_line} {w}"
        bbox = font.getbbox(test_line)
        line_w = bbox[2] - bbox[0]
        if line_w <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = w
    lines.append(current_line)
    return lines


def draw_rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """Tạo mask hình chữ nhật bo góc 8-bit alpha."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), size], radius=radius, fill=255)
    return mask


def draw_asymmetric_rounded_rect(
    img: Image.Image,
    box: tuple[int, int, int, int],
    radii: tuple[int, int, int, int],  # (r_top_left, r_top_right, r_bottom_right, r_bottom_left)
    fill: str | tuple[int, ...],
) -> None:
    """Vẽ hình chữ nhật với 4 góc bo bất đối xứng cho grouped bubble."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    r_tl, r_tr, r_br, r_bl = radii
    max_r = min(w // 2, h // 2)
    r_tl = min(r_tl, max_r)
    r_tr = min(r_tr, max_r)
    r_br = min(r_br, max_r)
    r_bl = min(r_bl, max_r)

    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)

    # Vùng trung tâm
    md.rectangle([max(r_tl, r_bl), 0, w - max(r_tr, r_br), h], fill=255)
    md.rectangle([0, max(r_tl, r_tr), w, h - max(r_bl, r_br)], fill=255)

    # 4 góc
    if r_tl > 0:
        md.pieslice([0, 0, r_tl * 2, r_tl * 2], 180, 270, fill=255)
    else:
        md.rectangle([0, 0, max_r, max_r], fill=255)

    if r_tr > 0:
        md.pieslice([w - r_tr * 2, 0, w, r_tr * 2], 270, 360, fill=255)
    else:
        md.rectangle([w - max_r, 0, w, max_r], fill=255)

    if r_br > 0:
        md.pieslice([w - r_br * 2, h - r_br * 2, w, h], 0, 90, fill=255)
    else:
        md.rectangle([w - max_r, h - max_r, w, h], fill=255)

    if r_bl > 0:
        md.pieslice([0, h - r_bl * 2, r_bl * 2, h], 90, 180, fill=255)
    else:
        md.rectangle([0, h - max_r, max_r, h], fill=255)

    color_layer = Image.new("RGBA", (w, h), fill)
    img.paste(color_layer, (x0, y0), mask)


def make_circular_avatar(avatar_img: Image.Image | None, char: Character, size: int) -> Image.Image:
    """Tạo avatar hình tròn. Nếu không có ảnh, vẽ vòng tròn kèm chữ cái đầu."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    if avatar_img is not None:
        resized = avatar_img.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size, size), fill=255)
        canvas.paste(resized, (0, 0), mask)
    else:
        # Vẽ vòng tròn màu theo tên
        color_hash = sum(ord(c) for c in char.name) % 4
        colors = [
            (0, 132, 255, 255),  # xanh dương
            (244, 182, 48, 255),  # vàng
            (34, 165, 91, 255),  # xanh lá
            (178, 34, 40, 255),  # đỏ HBT
        ]
        bg_col = colors[color_hash]
        draw.ellipse((0, 0, size - 1, size - 1), fill=bg_col)
        initial = (char.name[0] if char.name else "U").upper()
        font = get_font(int(size * 0.5), bold=True)
        bbox = font.getbbox(initial)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            ((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1]),
            initial,
            fill="#FFFFFF",
            font=font,
        )

    return canvas


class ChatFrameRenderer:
    def __init__(
        self,
        theme: ChatTheme,
        characters: list[Character],
        avatar_images: dict[str, Image.Image] | None = None,
    ):
        self.theme = theme
        self.characters = {c.id: c for c in characters}
        self.avatar_images = avatar_images or {}
        self.font_msg = get_font(theme.font_size)
        self.font_header_title = get_font(34, bold=True)
        self.font_header_status = get_font(24)
        self.font_seen = get_font(22)

    def measure_message(self, msg: Message) -> tuple[int, int, list[str]]:
        """Tính (chiều rộng bubble, chiều cao bubble, các dòng chữ)."""
        lines = wrap_text(msg.text, self.font_msg, self.theme.bubble_max_width - 48)
        max_line_w = 0
        for line in lines:
            bbox = self.font_msg.getbbox(line)
            w = bbox[2] - bbox[0]
            if w > max_line_w:
                max_line_w = w

        bubble_w = max(100, max_line_w + 48)
        line_h = self.theme.line_spacing
        bubble_h = len(lines) * line_h + 32
        return bubble_w, bubble_h, lines

    def draw_header(self, other_char: Character) -> Image.Image:
        """Vẽ header 120px của khung chat kiểu Messenger chuẩn."""
        w = self.theme.frame_width
        h = self.theme.header_height
        header = Image.new("RGBA", (w, h), self.theme.header_bg)
        draw = ImageDraw.Draw(header)

        # Avatar
        av_size = self.theme.header_avatar_size
        av_img = self.avatar_images.get(other_char.id)
        av = make_circular_avatar(av_img, other_char, av_size)
        av_x = 28
        av_y = (h - av_size) // 2
        header.paste(av, (av_x, av_y), av)

        # Chấm xanh Active trực tiếp trên góc dưới avatar (chuẩn Messenger)
        dot_r = 7
        dot_cx = av_x + av_size - 8
        dot_cy = av_y + av_size - 8
        draw.ellipse(
            (dot_cx - dot_r - 2, dot_cy - dot_r - 2, dot_cx + dot_r + 2, dot_cy + dot_r + 2),
            fill="#FFFFFF",
        )
        draw.ellipse(
            (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
            fill="#31A24C",
        )

        # Text info
        tx = av_x + av_size + 20
        title = other_char.name
        draw.text(
            (tx, av_y + 4),
            title,
            fill=self.theme.header_title_color,
            font=self.font_header_title,
        )

        status_y = av_y + 44
        draw.text(
            (tx, status_y),
            self.theme.header_status_text,
            fill=self.theme.header_status_color,
            font=self.font_header_status,
        )

        # Các icon hành động bên phải Messenger (Gọi thoại, Video call, Thông tin)
        # 1. Video call icon
        vx = w - 120
        vy = h // 2
        draw.rounded_rectangle([(vx - 14, vy - 10), (vx + 6, vy + 10)], radius=4, fill="#0084FF")
        draw.polygon(
            [(vx + 6, vy - 5), (vx + 16, vy - 11), (vx + 16, vy + 11), (vx + 6, vy + 5)],
            fill="#0084FF",
        )

        # 2. Audio call icon (ống nghe)
        px = w - 180
        py = h // 2
        draw.rounded_rectangle(
            [(px - 7, py - 11), (px + 7, py + 11)], radius=5, outline="#0084FF", width=3
        )
        draw.ellipse([(px - 2, py + 3), (px + 2, py + 7)], fill="#0084FF")

        # 3. Info icon (chữ i trong hình tròn)
        ix = w - 50
        iy = h // 2
        draw.ellipse([(ix - 12, iy - 12), (ix + 12, iy + 12)], outline="#0084FF", width=2)
        draw.ellipse([(ix - 2, iy - 7), (ix + 2, iy - 3)], fill="#0084FF")
        draw.rectangle([(ix - 1.5, iy - 1), (ix + 1.5, iy + 7)], fill="#0084FF")

        # Viền mờ ngăn cách header
        draw.line([(0, h - 1), (w, h - 1)], fill="#F0F2F5", width=1)
        return header

    def draw_typing_bubble(self, pulse_step: int = 0) -> Image.Image:
        """Vẽ bong bóng 3 chấm 'đang nhập' với animation sóng sin nhấp nhô mượt mà."""
        w, h = 128, 64
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([(0, 0), (w, h)], radius=32, fill=self.theme.bubble_left_bg)

        # 3 chấm sóng sin
        dot_r = 6
        cy = h // 2
        spacing = 22
        start_x = (w - (2 * spacing + 2 * dot_r)) // 2

        for i in range(3):
            dx = start_x + i * spacing
            offset_y = int(math.sin(pulse_step * 0.45 + i * 1.05) * 6)
            y = cy + offset_y
            draw.ellipse(
                (dx, y - dot_r, dx + dot_r * 2, y + dot_r),
                fill=self.theme.typing_dot_color,
            )

        return img

    def get_content_height(
        self,
        visible_messages: list[Message],
        show_typing: bool = False,
        active_sticker_img: Image.Image | None = None,
        show_seen: bool = True,
    ) -> int:
        """Tính toán tổng chiều cao nội dung tin nhắn để phục vụ nội suy cuộn mượt."""
        cur_y = 20
        if visible_messages:
            cur_y += 36  # Header timestamp divider

        num_msgs = len(visible_messages)
        for idx, msg in enumerate(visible_messages):
            if num_msgs >= 8 and idx == num_msgs // 2:
                cur_y += 36
            _, bubble_h, _ = self.measure_message(msg)
            cur_y += bubble_h + 16

        if show_typing:
            cur_y += 64 + 16

        if active_sticker_img is not None:
            sw, sh = active_sticker_img.size
            if sw > 360 or sh > 360:
                scale_stk = 360.0 / max(sw, sh)
                stk_h = int(sh * scale_stk)
            else:
                stk_h = sh
            cur_y += stk_h + 16

        if show_seen and num_msgs > 0 and not show_typing:
            cur_y += 28

        return cur_y + 20

    def render_chat_view(
        self,
        visible_messages: list[Message],
        show_typing: bool = False,
        typing_char_id: str | None = None,
        typing_pulse_step: int = 0,
        active_sticker_img: Image.Image | None = None,
        sticker_from_right: bool = False,
        scale_last_msg: float = 1.0,
        show_seen: bool = True,
        scroll_offset_override: int | None = None,
    ) -> Image.Image:
        """Dựng một khung hình 1080x1920 hoàn chỉnh (trong suốt bên ngoài khung chat)."""
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))

        frame_w = self.theme.frame_width
        frame_max_h = self.theme.frame_max_height
        top_y = self.theme.top_y
        frame_x = (CANVAS_WIDTH - frame_w) // 2

        # Xác định đối phương để vẽ header
        other_chars = [c for c in self.characters.values() if c.side == "left"]
        other_char = (
            other_chars[0] if other_chars else Character(id="other", name="Bạn bè", side="left")
        )

        header_img = self.draw_header(other_char)
        content_area_h = frame_max_h - self.theme.header_height

        # Tạo dải tin nhắn trong content area
        content_img = Image.new("RGBA", (frame_w, 4000), (0, 0, 0, 0))
        content_draw = ImageDraw.Draw(content_img)

        cur_y = 20
        num_msgs = len(visible_messages)

        # 1. Vẽ mốc giờ đầu đoạn hội thoại ở giữa (không đọc TTS)
        if num_msgs > 0:
            time_str = "Hôm nay 20:15"
            tbox = self.font_seen.getbbox(time_str)
            tw = tbox[2] - tbox[0]
            content_draw.text(
                ((frame_w - tw) // 2, cur_y),
                time_str,
                fill="#8A8D91",
                font=self.font_seen,
            )
            cur_y += 36

        for idx, msg in enumerate(visible_messages):
            # Mốc giờ chia giữa cuộc hội thoại dài
            if num_msgs >= 8 and idx == num_msgs // 2:
                mid_time_str = "20:18"
                mtbox = self.font_seen.getbbox(mid_time_str)
                mtw = mtbox[2] - mtbox[0]
                content_draw.text(
                    ((frame_w - mtw) // 2, cur_y),
                    mid_time_str,
                    fill="#8A8D91",
                    font=self.font_seen,
                )
                cur_y += 36

            is_last = (idx == num_msgs - 1) and not show_typing
            scale = scale_last_msg if is_last else 1.0

            char = self.characters.get(msg.from_)
            is_right = (char.side == "right") if char else False

            # Tính bo góc grouped bubble chuẩn Messenger
            same_prev = idx > 0 and visible_messages[idx - 1].from_ == msg.from_
            same_next = idx < num_msgs - 1 and visible_messages[idx + 1].from_ == msg.from_

            radius_normal = (
                self.theme.bubble_right_radius if is_right else self.theme.bubble_left_radius
            )
            radius_small = 8

            if is_right:
                r_tr = radius_small if same_prev else radius_normal
                r_br = radius_small if same_next else radius_normal
                radii = (radius_normal, r_tr, r_br, radius_normal)
            else:
                r_tl = radius_small if same_prev else radius_normal
                r_bl = radius_small if same_next else radius_normal
                radii = (r_tl, radius_normal, radius_normal, r_bl)

            bubble_w, bubble_h, lines = self.measure_message(msg)

            # Tạo ảnh bubble riêng để có thể scale nếu cần
            b_img = Image.new("RGBA", (bubble_w, bubble_h), (0, 0, 0, 0))
            b_draw = ImageDraw.Draw(b_img)

            bg_color = self.theme.bubble_right_bg if is_right else self.theme.bubble_left_bg
            txt_color = (
                self.theme.bubble_right_text_color
                if is_right
                else self.theme.bubble_left_text_color
            )

            # Vẽ bo góc bất đối xứng cho grouped bubble
            draw_asymmetric_rounded_rect(b_img, (0, 0, bubble_w, bubble_h), radii, bg_color)

            # Vẽ chữ
            text_y = 16
            for line in lines:
                b_draw.text((24, text_y), line, fill=txt_color, font=self.font_msg)
                text_y += self.theme.line_spacing

            if scale != 1.0 and scale > 0.1:
                sw = max(10, int(bubble_w * scale))
                sh = max(10, int(bubble_h * scale))
                b_img = b_img.resize((sw, sh), Image.Resampling.LANCZOS)
                bubble_w, bubble_h = sw, sh

            # Định vị trí x, y trên content_img
            if is_right:
                bx = frame_w - 28 - bubble_w
            else:
                # Bên trái: chỉ tin cuối trong nhóm cùng người gửi mới hiện avatar
                av_size = self.theme.bubble_left_avatar_size
                if not same_next:
                    av_img = self.avatar_images.get(msg.from_)
                    fallback_char = Character(id="?", name="?", side="left")
                    av = make_circular_avatar(av_img, char or fallback_char, av_size)
                    content_img.paste(av, (24, cur_y + bubble_h - av_size), av)
                bx = 24 + av_size + 14

            content_img.paste(b_img, (bx, cur_y), b_img)
            cur_y += bubble_h + 16

        # Nếu có typing indicator
        if show_typing:
            typing_b = self.draw_typing_bubble(pulse_step=typing_pulse_step)
            av_size = self.theme.bubble_left_avatar_size
            char = self.characters.get(typing_char_id or "left") or other_char
            av_img = self.avatar_images.get(char.id)
            av = make_circular_avatar(av_img, char, av_size)
            content_img.paste(av, (24, cur_y + typing_b.height - av_size), av)
            content_img.paste(typing_b, (24 + av_size + 14, cur_y), typing_b)
            cur_y += typing_b.height + 16

        # Nếu có sticker hiện
        if active_sticker_img is not None:
            sw, sh = active_sticker_img.size
            if sw > 360 or sh > 360:
                scale_stk = 360.0 / max(sw, sh)
                stk_resized = active_sticker_img.resize(
                    (int(sw * scale_stk), int(sh * scale_stk)), Image.Resampling.LANCZOS
                )
            else:
                stk_resized = active_sticker_img

            sx = (frame_w - 28 - stk_resized.width) if sticker_from_right else (24 + 48 + 14)
            content_img.paste(stk_resized, (sx, cur_y), stk_resized)
            cur_y += stk_resized.height + 16

        # Nếu có chỉ báo "Đã xem" dưới tin cuối của 'me'
        if show_seen and num_msgs > 0 and not show_typing:
            last_msg = visible_messages[-1]
            last_char = self.characters.get(last_msg.from_)
            if last_char and last_char.side == "right":
                if self.theme.seen_style == "mini_avatar":
                    av_mini_size = self.theme.seen_mini_avatar_size
                    mini_av = make_circular_avatar(None, other_char, av_mini_size)
                    content_img.paste(mini_av, (frame_w - 28 - av_mini_size, cur_y - 8), mini_av)
                    cur_y += av_mini_size
                else:
                    bbox = self.font_seen.getbbox(self.theme.seen_text)
                    tw = bbox[2] - bbox[0]
                    content_draw.text(
                        (frame_w - 28 - tw, cur_y - 8),
                        self.theme.seen_text,
                        fill="#8E8E93",
                        font=self.font_seen,
                    )
                    cur_y += 24

        # Tính toán cuộn (áp dụng override nếu có animation cuộn mượt)
        total_content_h = cur_y + 20
        if scroll_offset_override is not None:
            scroll_offset = max(0, scroll_offset_override)
        elif total_content_h > content_area_h:
            scroll_offset = total_content_h - content_area_h
        else:
            scroll_offset = 0

        # Cắt phần hiển thị từ content_img
        box = (0, scroll_offset, frame_w, scroll_offset + content_area_h)
        visible_content = content_img.crop(box)

        # Tạo khung hoàn chỉnh
        frame_surface = Image.new("RGBA", (frame_w, frame_max_h), self.theme.bg_color)
        frame_surface.paste(header_img, (0, 0))
        frame_surface.paste(visible_content, (0, self.theme.header_height), visible_content)

        # Bo góc toàn bộ khung chat
        mask = draw_rounded_mask((frame_w, frame_max_h), self.theme.corner_radius)
        canvas.paste(frame_surface, (frame_x, top_y), mask)

        return canvas
