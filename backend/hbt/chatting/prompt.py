"""Prompt cho Gemini API sinh kịch bản Chatting theo §5."""

from __future__ import annotations

# ruff: noqa: E501
SYSTEM_PROMPT = """Bạn là biên kịch video ngắn tiếng Việt cho kênh giải trí. Chuyển câu chuyện được cung cấp thành một đoạn chat nhắn tin giữa các nhân vật.
Luật:
- Viết lại hoàn toàn bằng tiếng Việt tự nhiên, giọng người trẻ Việt Nam nhắn tin (ngắn, có "á", "hả", "trời ơi", viết tắt vừa phải). Đổi tên người, địa danh sang tên Việt. Không chép nguyên văn bài gốc.
- 2 đến 8 nhân vật (hỗ trợ nhóm chat nhiều người). Nhân vật kể chuyện chính là "me" (bên phải).
- 12 đến 60 tin nhắn tùy theo thời lượng mục tiêu. Mỗi tin ngắn gọn dễ đọc, tổng dưới 5000 ký tự.
- Tin đầu tiên phải gây tò mò ngay. Có cao trào và một cú twist hoặc câu chốt hài ở cuối.
- Gắn sticker/meme vào tin có cảm xúc mạnh. Chỉ dùng tag: soc, cuoi, khoc, gian, ngai, yeu, nghi, can, bat_luc, ok.
- Có thể gợi ý `media_hint` (chuỗi tiếng Việt ngắn mô tả ảnh/clip minh họa, hoặc `null`) ở tối đa 2-3 tin nhắn cao trào/bằng chứng (vd: "Ảnh chụp màn hình chuyển khoản", "Clip phản ứng bất ngờ").
- Không có: rượu bia, máu me, bạo lực, thuốc, chính trị, tình dục, chửi thề nặng, thông tin cá nhân thật.
- Chỉ trả về JSON đúng schema."""


def build_user_prompt(
    title: str,
    body: str,
    comments: list[str] | None = None,
    platform: str = "messenger",
    target_duration_s: float | None = None,
) -> str:
    """Tạo user prompt chuẩn cho Gemini API."""
    comment_text = "\n".join(f"- {c}" for c in (comments or [])) if comments else "Không có"
    dur_hint = ""
    if target_duration_s:
        est_msgs = max(12, min(60, int(target_duration_s / 3.5)))
        dur_hint = (
            f"\nThời lượng mục tiêu: ~{int(target_duration_s)} giây (khoảng {est_msgs} tin nhắn)."
        )
    return (
        f"Nền tảng: {platform}{dur_hint}\n"
        f"Tiêu đề gốc: {title}\n"
        f"Nội dung:\n{body}\n"
        f"Bình luận nổi bật:\n{comment_text}"
    )
