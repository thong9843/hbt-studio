"""Prompt cho Gemini API sinh kịch bản Chatting theo §5."""

from __future__ import annotations

# ruff: noqa: E501
SYSTEM_PROMPT = """Bạn là biên kịch video ngắn tiếng Việt cho kênh giải trí. Chuyển câu chuyện được cung cấp thành một đoạn chat nhắn tin giữa các nhân vật.
Luật:
- Viết lại hoàn toàn bằng tiếng Việt tự nhiên, giọng người trẻ Việt Nam nhắn tin (ngắn, có "á", "hả", "trời ơi", viết tắt vừa phải). Đổi tên người, địa danh sang tên Việt. Không chép nguyên văn bài gốc.
- 2 đến 8 nhân vật (hỗ trợ nhóm chat nhiều người). Nhân vật kể chuyện chính là "me" (bên phải).
- 12 đến 60 tin nhắn tùy theo thời lượng mục tiêu. Mỗi tin ngắn gọn dễ đọc, tổng dưới 5000 ký tự.
- Tin đầu tiên phải gây tò mò ngay. Có cao trào và một cú twist hoặc câu chốt hài ở cuối.
- TUYỆT ĐỐI KHÔNG gắn `sticker` sau mỗi câu thoại hay ở các câu hỏi/đáp thông thường. Chỉ gắn `sticker` (tối đa 1 đến 3 sticker cho TOÀN BỘ cuộc hội thoại, không bao giờ ở 2 tin liên tiếp) vào đúng những câu cao trào cảm xúc mạnh nhất, cú twist bất ngờ hoặc câu chốt hài hước (punchline). Chỉ dùng tag: soc, cuoi, khoc, gian, ngai, yeu, nghi, can, bat_luc, ok.
- Có thể gợi ý `media_hint` (chuỗi tiếng Việt ngắn mô tả ảnh/clip minh họa, hoặc `null`) ở tối đa 1-2 tin nhắn cao trào/bằng chứng (vd: "Ảnh chụp màn hình chuyển khoản", "Clip phản ứng bất ngờ").
- Không có: rượu bia, máu me, bạo lực, thuốc, chính trị, tình dục, chửi thề nặng, thông tin cá nhân thật.
- Chỉ trả về JSON đúng schema."""


def build_user_prompt(
    title: str,
    body: str,
    comments: list[str] | None = None,
    platform: str = "messenger",
    target_duration_s: float | None = None,
    memes_summary: list[dict[str, object]] | None = None,
) -> str:
    """Tạo user prompt chuẩn cho Gemini API."""
    comment_text = "\n".join(f"- {c}" for c in (comments or [])) if comments else "Không có"
    dur_hint = ""
    if target_duration_s:
        est_msgs = max(12, min(60, int(target_duration_s / 3.5)))
        dur_hint = (
            f"\nThời lượng mục tiêu: ~{int(target_duration_s)} giây (khoảng {est_msgs} tin nhắn)."
        )
    meme_hint = ""
    if memes_summary:
        lines = [
            f"- {m.get('id')}: {m.get('title')} | tags={m.get('tags')} | topic={m.get('topic')}"
            for m in memes_summary[:25]
        ]
        meme_hint = (
            "\nKho Meme có sẵn (chỉ chọn `meme_id` tối đa 1-3 lần khi đúng câu cao trào khớp `topic`, "
            "không chọn trùng):\n" + "\n".join(lines)
        )
    return (
        f"Nền tảng: {platform}{dur_hint}{meme_hint}\n"
        f"Tiêu đề gốc: {title}\n"
        f"Nội dung:\n{body}\n"
        f"Bình luận nổi bật:\n{comment_text}"
    )
