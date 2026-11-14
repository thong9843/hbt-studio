"""Vẽ giao diện chat Messenger / Zalo lên video bằng Pillow theo §7."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from hbt.chatting.models import Character, Message
from hbt.chatting.sources import format_scene_transition, is_scene_transition
from hbt.chatting.themes.base import ChatTheme
from hbt.pipeline.ffutil import probe

MEDIA_MAX_WIDTH = 560
MEDIA_MAX_HEIGHT = 720
MEDIA_CORNER_RADIUS = 20

FONTS_DIR = Path(__file__).resolve().parents[1] / "fonts"
FONT_REGULAR = FONTS_DIR / "BeVietnamPro-Medium.ttf"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"

FONT_EMOJI_CANDIDATES = [
    Path("C:/Windows/Fonts/seguiemj.ttf"),
    Path("C:/Windows/Fonts/Segoe UI Emoji.ttf"),
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
]

EMOJI_REGEX = re.compile(
    r"(\u00a9|\u00ae|[\u2000-\u3300]|\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|[\U00010000-\U0010ffff])"
    r"(?:[\ufe00-\ufe0f]|[\U0001F3FB-\U0001F3FF]|\u200d(?:\u00a9|\u00ae|[\u2000-\u3300]|\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|[\U00010000-\U0010ffff])(?:[\ufe00-\ufe0f]|[\U0001F3FB-\U0001F3FF])?)*",
    re.UNICODE,
)

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


def get_emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    """Tải font Segoe UI Emoji trên Windows hoặc font emoji hệ thống để vẽ emoji màu sắc nét."""
    for p in FONT_EMOJI_CANDIDATES:
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return None


def segment_text_and_emojis(text: str) -> list[tuple[str, bool]]:
    """Tách câu thành các phân đoạn văn bản thường và emoji Unicode."""
    pos = 0
    segments = []
    for m in EMOJI_REGEX.finditer(text):
        start, end = m.span()
        if start > pos:
            segments.append((text[pos:start], False))
        segments.append((m.group(0), True))
        pos = end
    if pos < len(text):
        segments.append((text[pos:], False))
    return segments


def measure_line_width(
    text: str,
    font_text: ImageFont.FreeTypeFont,
    font_emoji: ImageFont.FreeTypeFont | None = None,
) -> int:
    """Đo chính xác chiều rộng dòng chữ có chứa emoji."""
    total_w = 0
    for seg, is_emoji in segment_text_and_emojis(text):
        if is_emoji and font_emoji:
            bbox = font_emoji.getbbox(seg)
            w = bbox[2] - bbox[0]
            total_w += max(w, int(font_emoji.size * 1.05))
        else:
            bbox = font_text.getbbox(seg)
            total_w += bbox[2] - bbox[0]
    return total_w


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    font_emoji: ImageFont.FreeTypeFont | None = None,
) -> list[str]:
    """Chia văn bản thành các dòng không vượt quá max_width, tính đúng chiều rộng emoji."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current_line = words[0]

    for w in words[1:]:
        test_line = f"{current_line} {w}"
        line_w = measure_line_width(test_line, font, font_emoji)
        if line_w <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = w
    lines.append(current_line)
    return lines


def draw_text_with_emoji(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font_text: ImageFont.FreeTypeFont,
    font_emoji: ImageFont.FreeTypeFont | None,
    fill: Any,
) -> int:
    """Vẽ từng đoạn văn bản kết hợp Segoe UI Emoji với embedded_color=True để emoji sắc nét."""
    x, y = xy
    cur_x = x
    for seg, is_emoji in segment_text_and_emojis(text):
        if is_emoji and font_emoji:
            bbox = font_emoji.getbbox(seg)
            w = max(bbox[2] - bbox[0], int(font_emoji.size * 1.05))
            try:
                draw.text((cur_x, y), seg, font=font_emoji, fill=fill, embedded_color=True)
            except Exception:
                draw.text((cur_x, y), seg, font=font_text, fill=fill)
            cur_x += w
        else:
            bbox = font_text.getbbox(seg)
            w = bbox[2] - bbox[0]
            draw.text((cur_x, y), seg, font=font_text, fill=fill)
            cur_x += w
    return cur_x - x


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
    """Vẽ hình chữ nhật với 4 góc bo bất đối xứng cho grouped bubble không bị khuyết góc."""
    x0, y0, x1, y1 = box
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    r_tl, r_tr, r_br, r_bl = radii
    max_r = min(w // 2, h // 2)
    r_tl = max(0, min(r_tl, max_r))
    r_tr = max(0, min(r_tr, max_r))
    r_br = max(0, min(r_br, max_r))
    r_bl = max(0, min(r_bl, max_r))

    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)

    # Độc lập từng góc: xóa ô vuông góc rồi vẽ pieslice chuẩn xác
    if r_tl > 0:
        md.rectangle([0, 0, r_tl, r_tl], fill=0)
        md.pieslice([0, 0, r_tl * 2, r_tl * 2], 180, 270, fill=255)
    if r_tr > 0:
        md.rectangle([w - r_tr, 0, w, r_tr], fill=0)
        md.pieslice([w - r_tr * 2, 0, w, r_tr * 2], 270, 360, fill=255)
    if r_br > 0:
        md.rectangle([w - r_br, h - r_br, w, h], fill=0)
        md.pieslice([w - r_br * 2, h - r_br * 2, w, h], 0, 90, fill=255)
    if r_bl > 0:
        md.rectangle([0, h - r_bl, r_bl, h], fill=0)
        md.pieslice([0, h - r_bl * 2, r_bl * 2, h], 90, 180, fill=255)

    color_layer = Image.new("RGBA", (w, h), fill)
    img.paste(color_layer, (x0, y0), mask)


GROUP_CHAR_COLORS: list[tuple[str, tuple[int, int, int, int]]] = [
    ("#0084FF", (0, 132, 255, 255)),  # Xanh dương
    ("#E67E22", (230, 126, 34, 255)),  # Cam
    ("#22A55B", (34, 165, 91, 255)),  # Xanh lá
    ("#D946EF", (217, 70, 239, 255)),  # Tím hồng
    ("#E11D48", (225, 29, 72, 255)),  # Đỏ hồng
    ("#0EA5E9", (14, 165, 233, 255)),  # Xanh ngọc
]


def make_circular_avatar(
    avatar_img: Image.Image | None,
    char: Character,
    size: int,
    bg_color_override: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """Tạo avatar hình tròn. Nếu không có ảnh, vẽ vòng tròn màu phân biệt kèm chữ cái đầu."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    if avatar_img is not None:
        resized = avatar_img.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size, size), fill=255)
        canvas.paste(resized, (0, 0), mask)
    else:
        if bg_color_override is not None:
            bg_col = bg_color_override
        else:
            color_hash = sum(ord(c) for c in char.name) % len(GROUP_CHAR_COLORS)
            bg_col = GROUP_CHAR_COLORS[color_hash][1]
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
        project_dir: Path | None = None,
    ):
        self.theme = theme
        self.characters = {c.id: c for c in characters}
        self.avatar_images = avatar_images or {}
        self.project_dir = project_dir
        self._media_size_cache: dict[str, tuple[int, int] | None] = {}
        self.font_msg = get_font(theme.font_size)
        self.font_emoji = get_emoji_font(int(theme.font_size * 0.95))
        self.font_header_title = get_font(34, bold=True)
        self.font_header_status = get_font(24)
        self.font_seen = get_font(22)
        self.font_sender_name = get_font(22, bold=True)

        # Gán màu phân biệt cho từng thành viên trong Group Chat
        self.left_chars = [c for c in characters if c.side == "left"]
        self.is_group = len(self.left_chars) > 1
        self.char_colors: dict[str, tuple[str, tuple[int, int, int, int]]] = {}
        for idx, c in enumerate(self.left_chars):
            self.char_colors[c.id] = GROUP_CHAR_COLORS[idx % len(GROUP_CHAR_COLORS)]

    def get_char_color(self, char_id: str) -> tuple[str, tuple[int, int, int, int]]:
        if char_id in self.char_colors:
            return self.char_colors[char_id]
        return GROUP_CHAR_COLORS[0]

    def _resolve_media_path(self, msg: Message) -> Path | None:
        mtype = getattr(msg, "media_type", None)
        mpath_raw = getattr(msg, "media_path", None)
        if mtype not in ("image", "video") or not mpath_raw:
            return None
        p = Path(mpath_raw)
        if not p.is_absolute():
            if self.project_dir is None:
                return None
            p = self.project_dir / p
        return p if p.is_file() else None

    def resolve_message_media_size(self, msg: Message) -> tuple[int, int] | None:
        """Tính kích thước (w, h) của media đính kèm (rộng <= 560px, giữ tỷ lệ)."""
        mtype = getattr(msg, "media_type", None)
        mpath = self._resolve_media_path(msg)
        if mpath is None or mtype not in ("image", "video"):
            return None
        cache_key = f"{mtype}:{mpath}"
        if cache_key in self._media_size_cache:
            return self._media_size_cache[cache_key]

        iw, ih = 560, 315
        if mtype == "image":
            try:
                with Image.open(mpath) as im:
                    iw, ih = im.size
            except Exception:
                self._media_size_cache[cache_key] = None
                return None
        else:
            try:
                info = probe(mpath)
                vs = next(
                    (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
                    None,
                )
                if vs and int(vs.get("width", 0)) > 0 and int(vs.get("height", 0)) > 0:
                    iw, ih = int(vs["width"]), int(vs["height"])
            except Exception:
                iw, ih = 560, 315

        max_w = min(MEDIA_MAX_WIDTH, self.theme.bubble_max_width - 32)
        scale = min(max_w / max(1, iw), MEDIA_MAX_HEIGHT / max(1, ih), 1.0)
        disp_w = max(80, int(round(iw * scale)))
        disp_h = max(80, int(round(ih * scale)))
        if mtype == "video":
            disp_w = max(80, (disp_w // 2) * 2)
            disp_h = max(80, (disp_h // 2) * 2)
        res = (disp_w, disp_h)
        self._media_size_cache[cache_key] = res
        return res

    def measure_message(self, msg: Message) -> tuple[int, int, list[str]]:
        """Tính (chiều rộng, chiều cao, các dòng chữ) hỗ trợ emoji & media đính kèm."""
        raw_text = (getattr(msg, "display_text", None) or msg.text).strip()
        lines = (
            wrap_text(raw_text, self.font_msg, self.theme.bubble_max_width - 48, self.font_emoji)
            if raw_text
            else []
        )
        max_line_w = 0
        for line in lines:
            line_w = measure_line_width(line, self.font_msg, self.font_emoji)
            if line_w > max_line_w:
                max_line_w = line_w

        media_size = self.resolve_message_media_size(msg)
        line_h = self.theme.line_spacing
        if media_size is not None:
            mw, mh = media_size
            bubble_w = max(100, max_line_w + 48, mw + 32)
            if lines:
                bubble_h = 16 + len(lines) * line_h + 12 + mh + 16
            else:
                bubble_h = 16 + mh + 16
        else:
            bubble_w = max(100, max_line_w + 48)
            bubble_h = max(1, len(lines)) * line_h + 32
        return bubble_w, bubble_h, lines

    def draw_header(self, other_char: Character) -> Image.Image:
        """Vẽ header 120px của khung chat kiểu Messenger chuẩn (hỗ trợ cả chat nhóm)."""
        w = self.theme.frame_width
        h = self.theme.header_height
        header = Image.new("RGBA", (w, h), self.theme.header_bg)
        draw = ImageDraw.Draw(header)

        av_size = self.theme.header_avatar_size
        av_x = 28
        av_y = (h - av_size) // 2

        if self.is_group and len(self.left_chars) >= 2:
            # Header nhóm: vẽ 2 avatar chồng nhau chuẩn Messenger Group
            mini_size = int(av_size * 0.72)
            c1, c2 = self.left_chars[0], self.left_chars[1]
            _, col1 = self.get_char_color(c1.id)
            _, col2 = self.get_char_color(c2.id)
            av2 = make_circular_avatar(self.avatar_images.get(c2.id), c2, mini_size, col2)
            av1 = make_circular_avatar(self.avatar_images.get(c1.id), c1, mini_size, col1)
            header.paste(av2, (av_x + av_size - mini_size, av_y), av2)
            header.paste(av1, (av_x, av_y + av_size - mini_size), av1)
            av2.close()
            av1.close()
        else:
            av_img = self.avatar_images.get(other_char.id)
            _, col = self.get_char_color(other_char.id)
            av = make_circular_avatar(av_img, other_char, av_size, col)
            header.paste(av, (av_x, av_y), av)
            av.close()

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
        if self.is_group:
            names = ", ".join(c.name for c in self.left_chars[:3])
            if len(self.left_chars) > 3:
                names += "..."
            title = names
            status_text = f"{len(self.characters)} thành viên · Đang hoạt động"
        else:
            title = other_char.name
            status_text = self.theme.header_status_text

        # Cắt tiêu đề nếu quá dài chạm icon bên phải
        max_title_w = w - tx - 210
        while title and self.font_header_title.getbbox(title)[2] > max_title_w and len(title) > 5:
            title = title[:-4].rstrip() + "..."

        draw.text(
            (tx, av_y + 4),
            title,
            fill=self.theme.header_title_color,
            font=self.font_header_title,
        )

        status_y = av_y + 44
        draw.text(
            (tx, status_y),
            status_text,
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
            disp_text = getattr(msg, "display_text", None) or msg.text
            if is_scene_transition(disp_text):
                cur_y += 36 + 20
            else:
                char = self.characters.get(msg.from_)
                is_right = (char.side == "right") if char else False
                prev_is_trans = idx > 0 and is_scene_transition(
                    getattr(visible_messages[idx - 1], "display_text", None)
                    or visible_messages[idx - 1].text
                )
                same_prev = (
                    idx > 0 and visible_messages[idx - 1].from_ == msg.from_ and not prev_is_trans
                )
                if self.is_group and not is_right and not same_prev:
                    cur_y += 26
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
        scroll_offset_override: float | None = None,
        is_meme_cutin: bool = False,
    ) -> Image.Image:
        """Dựng một khung hình 1080x1920 hoàn chỉnh (tối ưu RAM cho kịch bản dài tới 5 phút)."""
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))

        frame_w = self.theme.frame_width
        frame_max_h = self.theme.frame_max_height
        top_y = self.theme.top_y
        frame_x = (CANVAS_WIDTH - frame_w) // 2

        # Xác định đối phương để vẽ header
        other_char = (
            self.left_chars[0]
            if self.left_chars
            else Character(id="other", name="Bạn bè", side="left")
        )

        header_img = self.draw_header(other_char)
        content_area_h = frame_max_h - self.theme.header_height

        # Tính tổng chiều cao nội dung và giữ toạ độ cuộn dạng float đến bước vẽ cuối
        sticker_for_layout = active_sticker_img if not is_meme_cutin else None
        total_content_h = self.get_content_height(
            visible_messages,
            show_typing=show_typing,
            active_sticker_img=sticker_for_layout,
            show_seen=show_seen,
        )
        if scroll_offset_override is not None:
            scroll_f = max(0.0, float(scroll_offset_override))
        elif total_content_h > content_area_h:
            scroll_f = float(total_content_h - content_area_h)
        else:
            scroll_f = 0.0

        # Chỉ cấp phát canvas vùng nhìn thấy (viewport) để tiết kiệm RAM tối đa
        visible_content = Image.new("RGBA", (frame_w, content_area_h), (0, 0, 0, 0))
        content_draw = ImageDraw.Draw(visible_content)

        def to_screen_y(y_pos: float) -> int:
            return round(y_pos - scroll_f)

        def in_viewport(y_top: int, item_h: int) -> bool:
            vy = y_top - scroll_f
            return (vy + item_h) >= -40 and vy <= content_area_h + 40

        cur_y = 20
        num_msgs = len(visible_messages)

        # 1. Vẽ mốc giờ đầu đoạn hội thoại ở giữa (không đọc TTS)
        if num_msgs > 0:
            if in_viewport(cur_y, 36):
                time_str = "Hôm nay 20:15"
                tbox = self.font_seen.getbbox(time_str)
                tw = tbox[2] - tbox[0]
                content_draw.text(
                    ((frame_w - tw) // 2, to_screen_y(cur_y)),
                    time_str,
                    fill="#8A8D91",
                    font=self.font_seen,
                )
            cur_y += 36

        for idx, msg in enumerate(visible_messages):
            # Mốc giờ chia giữa cuộc hội thoại dài
            if num_msgs >= 8 and idx == num_msgs // 2:
                if in_viewport(cur_y, 36):
                    mid_time_str = "20:18"
                    mtbox = self.font_seen.getbbox(mid_time_str)
                    mtw = mtbox[2] - mtbox[0]
                    content_draw.text(
                        ((frame_w - mtw) // 2, to_screen_y(cur_y)),
                        mid_time_str,
                        fill="#8A8D91",
                        font=self.font_seen,
                    )
                cur_y += 36

            # Xử lý đoạn chuyển cảnh ngoặc đơn "(5 phút sau)", "(10 phút sau tại nhà vệ sinh)"...
            disp_text = getattr(msg, "display_text", None) or msg.text
            if is_scene_transition(disp_text):
                pill_h = 36
                if in_viewport(cur_y, pill_h + 20):
                    clean_title = format_scene_transition(disp_text)
                    tbox = self.font_seen.getbbox(clean_title)
                    tw = tbox[2] - tbox[0]
                    th = tbox[3] - tbox[1]
                    pill_w = max(180, tw + 40)
                    px = (frame_w - pill_w) // 2
                    py = to_screen_y(cur_y + 4)
                    content_draw.rounded_rectangle(
                        [(px, py), (px + pill_w, py + pill_h)],
                        radius=18,
                        fill="#2A2B2E",
                        outline="#3A3B3C",
                        width=1,
                    )
                    content_draw.text(
                        (px + (pill_w - tw) // 2, py + (pill_h - th) // 2 - tbox[1]),
                        clean_title,
                        fill="#E4E6EB",
                        font=self.font_seen,
                    )
                cur_y += pill_h + 20
                continue

            is_last = (idx == num_msgs - 1) and not show_typing
            scale = scale_last_msg if is_last else 1.0

            char = self.characters.get(msg.from_)
            is_right = (char.side == "right") if char else False

            prev_is_trans = idx > 0 and is_scene_transition(
                getattr(visible_messages[idx - 1], "display_text", None)
                or visible_messages[idx - 1].text
            )
            next_is_trans = idx < num_msgs - 1 and is_scene_transition(
                getattr(visible_messages[idx + 1], "display_text", None)
                or visible_messages[idx + 1].text
            )
            same_prev = (
                idx > 0 and visible_messages[idx - 1].from_ == msg.from_ and not prev_is_trans
            )
            same_next = (
                idx < num_msgs - 1
                and visible_messages[idx + 1].from_ == msg.from_
                and not next_is_trans
            )

            # Group Chat: hiện tên nhân vật phía trên bubble bên trái nếu > 1 người đối thoại
            show_sender_name = self.is_group and not is_right and not same_prev
            name_h = 26 if show_sender_name else 0

            bubble_w, bubble_h, lines = self.measure_message(msg)

            # Bỏ qua việc vẽ bubble nằm hoàn toàn ngoài khung nhìn (tiết kiệm CPU & RAM)
            if not in_viewport(cur_y, name_h + bubble_h + 16):
                cur_y += name_h + bubble_h + 16
                continue

            if show_sender_name and char:
                char_hex, _ = self.get_char_color(char.id)
                av_size = self.theme.bubble_left_avatar_size
                content_draw.text(
                    (24 + av_size + 18, to_screen_y(cur_y)),
                    char.name,
                    fill=char_hex,
                    font=self.font_sender_name,
                )
                cur_y += 26

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

            # Vẽ chữ kèm emoji đầy đủ màu sắc nét không lỗi ô vuông
            text_y = 16
            for line in lines:
                draw_text_with_emoji(
                    b_draw, (24, text_y), line, self.font_msg, self.font_emoji, txt_color
                )
                text_y += self.theme.line_spacing

            media_size = self.resolve_message_media_size(msg)
            if media_size is not None:
                mw, mh = media_size
                media_x = (bubble_w - mw) // 2
                media_y = text_y + (12 if lines else 0)
                mtype = getattr(msg, "media_type", None)
                mpath = self._resolve_media_path(msg)
                if mtype == "image" and mpath is not None:
                    try:
                        with Image.open(mpath) as raw_m:
                            rgba_m = raw_m.convert("RGBA")
                            resized_m = rgba_m.resize((mw, mh), Image.Resampling.LANCZOS)
                            rgba_m.close()
                            rmask = draw_rounded_mask((mw, mh), MEDIA_CORNER_RADIUS)
                            b_img.paste(resized_m, (media_x, media_y), rmask)
                            resized_m.close()
                            rmask.close()
                    except Exception:
                        pass
                elif mtype == "video":
                    b_draw.rounded_rectangle(
                        [(media_x, media_y), (media_x + mw, media_y + mh)],
                        radius=MEDIA_CORNER_RADIUS,
                        fill=(15, 23, 42, 255),
                        outline=(51, 65, 85, 255),
                        width=2,
                    )

            if scale != 1.0 and scale > 0.1:
                sw = max(10, int(bubble_w * scale))
                sh = max(10, int(bubble_h * scale))
                scaled_img = b_img.resize((sw, sh), Image.Resampling.LANCZOS)
                b_img.close()
                b_img = scaled_img
                bubble_w, bubble_h = sw, sh

            draw_y = to_screen_y(cur_y)
            # Định vị trí x, y trên visible_content và kẹp toạ độ ngang an toàn
            if is_right:
                bx = frame_w - 28 - bubble_w
            else:
                av_size = self.theme.bubble_left_avatar_size
                if not same_next:
                    av_img = self.avatar_images.get(msg.from_)
                    fallback_char = Character(id="?", name="?", side="left")
                    _, char_rgba = self.get_char_color(msg.from_)
                    av = make_circular_avatar(av_img, char or fallback_char, av_size, char_rgba)
                    av_y = draw_y + bubble_h - av_size
                    visible_content.paste(av, (24, av_y), av)
                    av.close()
                bx = 24 + av_size + 14

            bx = max(0, min(frame_w - bubble_w, bx))
            visible_content.paste(b_img, (bx, draw_y), b_img)
            b_img.close()
            cur_y += bubble_h + 16

        # Nếu có typing indicator
        if show_typing:
            typing_b = self.draw_typing_bubble(pulse_step=typing_pulse_step)
            if in_viewport(cur_y, typing_b.height + 16):
                av_size = self.theme.bubble_left_avatar_size
                char = self.characters.get(typing_char_id or "left") or other_char
                av_img = self.avatar_images.get(char.id)
                _, char_rgba = self.get_char_color(char.id)
                av = make_circular_avatar(av_img, char, av_size, char_rgba)
                vy = to_screen_y(cur_y)
                visible_content.paste(av, (24, vy + typing_b.height - av_size), av)
                visible_content.paste(typing_b, (24 + av_size + 14, vy), typing_b)
                av.close()
            typing_b.close()
            cur_y += 64 + 16

        # Nếu có sticker hiện thông thường
        if active_sticker_img is not None and not is_meme_cutin:
            sw, sh = active_sticker_img.size
            if sw > 360 or sh > 360:
                scale_stk = 360.0 / max(sw, sh)
                stk_resized = active_sticker_img.resize(
                    (int(sw * scale_stk), int(sh * scale_stk)), Image.Resampling.LANCZOS
                )
            else:
                stk_resized = active_sticker_img

            if in_viewport(cur_y, stk_resized.height + 16):
                sx = (frame_w - 28 - stk_resized.width) if sticker_from_right else (24 + 48 + 14)
                visible_content.paste(stk_resized, (sx, to_screen_y(cur_y)), stk_resized)
            if stk_resized is not active_sticker_img:
                stk_resized.close()
            cur_y += (int(sh * (360.0 / max(sw, sh))) if (sw > 360 or sh > 360) else sh) + 16

        # Nếu có chỉ báo "Đã xem" dưới tin cuối của 'me'
        if show_seen and num_msgs > 0 and not show_typing:
            last_msg = visible_messages[-1]
            last_char = self.characters.get(last_msg.from_)
            if last_char and last_char.side == "right":
                if in_viewport(cur_y - 8, 28):
                    vy = to_screen_y(cur_y)
                    if self.theme.seen_style == "mini_avatar":
                        av_mini_size = self.theme.seen_mini_avatar_size
                        _, col = self.get_char_color(other_char.id)
                        mini_av = make_circular_avatar(None, other_char, av_mini_size, col)
                        visible_content.paste(
                            mini_av, (frame_w - 28 - av_mini_size, vy - 8), mini_av
                        )
                        mini_av.close()
                    else:
                        bbox = self.font_seen.getbbox(self.theme.seen_text)
                        tw = bbox[2] - bbox[0]
                        content_draw.text(
                            (frame_w - 28 - tw, vy - 8),
                            self.theme.seen_text,
                            fill="#8E8E93",
                            font=self.font_seen,
                        )

        # Tạo khung hoàn chỉnh
        frame_surface = Image.new("RGBA", (frame_w, frame_max_h), self.theme.bg_color)
        frame_surface.paste(header_img, (0, 0))
        frame_surface.paste(visible_content, (0, self.theme.header_height), visible_content)

        # Bo góc toàn bộ khung chat
        mask = draw_rounded_mask((frame_w, frame_max_h), self.theme.corner_radius)
        canvas.paste(frame_surface, (frame_x, top_y), mask)

        # Giải phóng tài nguyên ảnh tạm ngay lập tức
        header_img.close()
        visible_content.close()
        frame_surface.close()
        mask.close()

        return canvas

    def compute_video_media_rects(
        self,
        visible_messages: list[Message],
        scroll_offset: float = 0.0,
    ) -> list[tuple[int, Path, int, int, int, int]]:
        """Trả về danh sách (msg_idx, video_path, canvas_x, canvas_y, w, h) đang hiển thị."""
        frame_w = self.theme.frame_width
        frame_max_h = self.theme.frame_max_height
        top_y = self.theme.top_y
        frame_x = (CANVAS_WIDTH - frame_w) // 2
        content_top_y = top_y + self.theme.header_height
        content_area_h = frame_max_h - self.theme.header_height

        rects: list[tuple[int, Path, int, int, int, int]] = []
        cur_y = 20
        num_msgs = len(visible_messages)
        if num_msgs > 0:
            cur_y += 36

        for idx, msg in enumerate(visible_messages):
            if num_msgs >= 8 and idx == num_msgs // 2:
                cur_y += 36
            disp_text = getattr(msg, "display_text", None) or msg.text
            if is_scene_transition(disp_text):
                cur_y += 36 + 20
                continue

            char = self.characters.get(msg.from_)
            is_right = (char.side == "right") if char else False
            prev_is_trans = idx > 0 and is_scene_transition(
                getattr(visible_messages[idx - 1], "display_text", None)
                or visible_messages[idx - 1].text
            )
            same_prev = (
                idx > 0 and visible_messages[idx - 1].from_ == msg.from_ and not prev_is_trans
            )
            show_sender_name = self.is_group and not is_right and not same_prev
            if show_sender_name and char:
                cur_y += 26

            bubble_w, bubble_h, lines = self.measure_message(msg)
            draw_y = round(cur_y - scroll_offset)

            if getattr(msg, "media_type", None) == "video":
                mpath = self._resolve_media_path(msg)
                media_size = self.resolve_message_media_size(msg)
                if mpath is not None and media_size is not None:
                    mw, mh = media_size
                    if is_right:
                        bx = frame_w - 28 - bubble_w
                    else:
                        av_size = self.theme.bubble_left_avatar_size
                        bx = 24 + av_size + 14
                    bx = max(0, min(frame_w - bubble_w, bx))
                    media_x = bx + (bubble_w - mw) // 2
                    media_y = (
                        draw_y + 16 + len(lines) * self.theme.line_spacing + (12 if lines else 0)
                    )
                    if media_y >= 0 and (media_y + mh) <= content_area_h:
                        rects.append(
                            (
                                idx,
                                mpath,
                                frame_x + media_x,
                                content_top_y + media_y,
                                mw,
                                mh,
                            )
                        )

            cur_y += bubble_h + 16

        return rects
