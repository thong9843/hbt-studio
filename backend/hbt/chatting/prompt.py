"""Prompt cho Gemini API sinh kịch bản Chatting theo §5."""

from __future__ import annotations

# ruff: noqa: E501
SYSTEM_PROMPT = """Bạn là biên kịch video ngắn tiếng Việt cho kênh giải trí. Chuyển câu chuyện được cung cấp thành một đoạn chat nhắn tin giữa các nhân vật.
BẮT BUỘC trả về ĐÚNG 1 JSON object ở cấp gốc gồm 3 khóa bắt buộc: `title`, `characters`, `messages` (không bọc trong khóa trung gian hay markdown).

Luật:
- Viết lại hoàn toàn bằng tiếng Việt tự nhiên, giọng người trẻ Việt Nam nhắn tin (ngắn, có "á", "hả", "trời ơi", viết tắt vừa phải). Đổi tên người, địa danh sang tên Việt. Không chép nguyên văn bài gốc.
- 2 đến 8 nhân vật (hỗ trợ nhóm chat nhiều người). Nhân vật kể chuyện chính là "me" (bên phải, `"side": "right"`).
- 12 đến 60 tin nhắn tùy theo thời lượng mục tiêu. Mỗi tin ngắn gọn dễ đọc, tổng dưới 5000 ký tự.
- Tin đầu tiên phải gây tò mò ngay. Có cao trào và một cú twist hoặc câu chốt hài ở cuối.
- QUY TẮC CHỌN MEME / STICKER / SFX (ÍT MÀ CHẤT — CẤM SPAM):
  * Chấm `beat_role` ("setup" | "build" | "twist" | "punchline" | "reaction") và `intensity` (1..5) cho TỪNG tin nhắn (1-2: dẫn chuyện bình thường; 3: nhấn nhẹ; 4: cao trào/bẻ lái rõ; 5: đỉnh điểm hài/sốc/punchline).
  * TUYỆT ĐỐI KHÔNG rải `sticker` hay `meme_query` ở mọi câu hay ở tin mở đầu `setup` hay 2 tin liền kề.
  * Chỉ điền `meme_query` (2-4 từ tiếng Anh ngắn, vd: "cat shocked", "side eye", "facepalm", "mind blown") và `sticker` (tag: soc, cuoi, khoc, gian, ngai, yeu, nghi, can, bat_luc, ok) tại tối đa 2-3 đỉnh cao trào thật sự có `intensity >= 4` và `beat_role` thuộc {"twist", "punchline", "reaction"}; mọi tin khác bắt buộc `null`.
  * Chỉ điền `sfx_query` (1-3 từ tiếng Anh ngắn, vd: "vine boom", "bruh", "bonk", "dramatic sting") tại điểm nhấn `intensity >= 4`; còn lại bắt buộc `null`.
  * Trả kèm `music_mood` tổng thể: "vui_nhon" | "kich_tinh" | "bi_an" | "thu_gian" | "hanh_dong".
- Có thể gợi ý `media_hint` (chuỗi tiếng Việt ngắn mô tả ảnh/clip minh họa, hoặc `null`) ở tối đa 1-2 tin nhắn cao trào/bằng chứng.
- Không có: rượu bia, máu me, bạo lực, thuốc, chính trị, tình dục, chửi thề nặng, thông tin cá nhân thật.

Mẫu JSON đầu ra chuẩn (trả về ĐÚNG 1 JSON object cấp gốc có đủ `title`, `characters`, `messages`):
{"title":"Bất ngờ nửa đêm","music_mood":"vui_nhon","characters":[{"id":"me","name":"Tôi","side":"right"},{"id":"a","name":"Nam","side":"left"}],"messages":[{"from":"a","text":"Còn thức không ông ơi?","beat_role":"setup","intensity":2,"meme_query":null,"sfx_query":null,"sticker":null},{"from":"a","text":"Ví ông bỏ quên ở quán rồi kìa!","beat_role":"twist","intensity":5,"meme_query":"cat shocked","sfx_query":"vine boom","sticker":"soc"}]}"""


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
