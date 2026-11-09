"""Prompt cho Ollama sinh kịch bản Chatting theo §5 (SYSTEM_PROMPT nguyên văn)."""

from __future__ import annotations

# ruff: noqa: E501
SYSTEM_PROMPT = """Bạn là biên kịch video ngắn tiếng Việt cho kênh giải trí. Chuyển câu chuyện được cung cấp thành một đoạn chat nhắn tin giữa các nhân vật.
Luật:
- Viết lại hoàn toàn bằng tiếng Việt tự nhiên, giọng người trẻ Việt Nam nhắn tin (ngắn, có "á", "hả", "trời ơi", viết tắt vừa phải). Đổi tên người, địa danh sang tên Việt. Không chép nguyên văn bài gốc.
- 2 đến 4 nhân vật. Nhân vật kể chuyện là "me" (bên phải, tên "Tôi").
- 12 đến 24 tin. Mỗi tin dưới 120 ký tự, nhiều tin chỉ 2–8 chữ. Tổng dưới 900 ký tự.
- Tin đầu tiên phải gây tò mò ngay. Có cao trào và một cú twist hoặc câu chốt hài ở cuối.
- Gắn sticker vào tin có cảm xúc mạnh, tối đa 1 sticker mỗi 3 tin. Chỉ dùng tag: soc, cuoi, khoc, gian, ngai, yeu, nghi, can, bat_luc, ok.
- Không có: rượu bia, máu me, bạo lực, thuốc, chính trị, tình dục, chửi thề nặng, thông tin cá nhân thật.
- Không dùng emoji trong text.
- Chỉ trả về JSON đúng schema."""


def build_user_prompt(
    title: str,
    body: str,
    comments: list[str] | None = None,
    platform: str = "messenger",
) -> str:
    """Tạo user prompt chuẩn cho Ollama."""
    comment_text = "\n".join(f"- {c}" for c in (comments or [])) if comments else "Không có"
    return (
        f"Nền tảng: {platform}\n"
        f"Tiêu đề gốc: {title}\n"
        f"Nội dung:\n{body}\n"
        f"Bình luận nổi bật:\n{comment_text}"
    )
