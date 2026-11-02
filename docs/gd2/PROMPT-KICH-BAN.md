# Mẫu prompt: nhờ Claude chat viết kịch bản HBT (JSON nháp `hbt_draft: 1`)

> Cách dùng: mở Claude chat, dán **toàn bộ khối "Prompt" bên dưới**, thay `{CHỦ ĐỀ}` (và tuỳ chọn `{SỐ CẢNH}`), gửi. Chép JSON nhận về vào app: Trang chủ → **Tạo dự án từ JSON nháp**.
> Đặc tả schema và mã kiểm K13–K18: `docs/gd2/IMPLEMENT-GD2.md`. Dạng thẻ chữ: `IMPLEMENT.md` 13.B4.

## Prompt

```text
Bạn viết kịch bản video ngắn tiếng Việt (dọc 9:16, 40–60 giây) cho kênh "Hay Biết Tuốt".
Chủ đề: {CHỦ ĐỀ}
Số cảnh: {SỐ CẢNH, mặc định 8; cho phép 3–12}

Trả về DUY NHẤT một khối JSON hợp lệ (không giải thích, không chữ ngoài JSON), đúng dạng dưới đây.

QUY TẮC LỜI ĐỌC (voice)
- Tổng lời đọc của cả video ≤ 750 ký tự. Mỗi cảnh một hai câu ngắn, dễ nghe.
- Dùng dấu | để chỗ nghỉ ngắn (0,25 giây).
- Số, từ viết tắt, từ mượn: viết kèm cách đọc trong {} ngay sau, ví dụ 10{mười}, CO2{xi ô hai}, 2024{hai nghìn không trăm hai mươi bốn}. Phần trong {} chỉ để đọc, không hiện trên phụ đề.
- Không dùng từ nhạy cảm (rượu bia, máu, ma tuý, chính trị, tôn giáo, bạo lực…). Giọng trung tính, có tính giải thích.

QUY TẮC THẺ CHỮ (card)
- "y": "top" | "upper" | "middle" | "lower". "size": "s" | "m" | "l" | "xl". "color": "ink" | "primary" | "accent" (hoặc #RRGGBB).
- Tối đa 3 dòng; chỉ một dòng màu "accent". Số ký tự mỗi dòng: xl ≤ 10, l ≤ 15, m ≤ 22, s ≤ 26. Viết HOA, không dùng | { }.
- "punch": true cho cảnh cần nhấn mạnh (ít thôi). "labels": [] và "caption_y": null nếu không cần.

QUY TẮC NGUỒN (sources)
- Mọi con số trong lời đọc (kể cả 10 trong 10{mười}) phải xuất hiện trong "claim" của một mục trong "sources". Mỗi nguồn có id duy nhất, claim, url thật (trang uy tín: tổ chức y tế, khoa học, đại học). Không bịa số liệu hay đường dẫn; không chắc thì bỏ số liệu đó.

QUY TẮC ẢNH (image_prompt)
- Mỗi cảnh một "image_prompt" bằng tiếng Anh, mô tả cảnh dọc 9:16, kết thúc bằng "vertical 9:16".
- KHÔNG chữ, KHÔNG biển hiệu, KHÔNG bản đồ (đặc biệt không bản đồ Việt Nam) trong ảnh. Không dùng các từ: text, chữ, map, bản đồ, Vietnam map.

CÁC TRƯỜNG KHÁC
- "music_mood": một từ tiếng Việt chỉ tâm trạng nhạc (ví dụ: tò mò, hồi hộp, trầm lắng).
- "series_hint": tên series gợi ý (có thể rỗng).
- "publish": "hook" (một câu mở đầu thu hút) và "hashtags" (3–6 từ, không dấu cách, không #).
- "thumbnail": "scene" là số thứ tự cảnh (bắt đầu từ 1), "lines" 2–3 dòng chữ HOA, "series": "", "accent": "#FFD43B".
- KHÔNG thêm trường nào khác (không "image", "music", "title", "slug", "theme", "settings").

DẠNG JSON (mẫu hợp lệ, 3 cảnh; bản của bạn có số cảnh theo yêu cầu)
{ MẪU BÊN DƯỚI }
```

Khi dán vào Claude chat, thay dòng `{ MẪU BÊN DƯỚI }` bằng nguyên khối JSON ở mục tiếp theo.

## Mẫu JSON hợp lệ (3 cảnh)

```json
{
  "hbt_draft": 1,
  "topic": "Vì sao muỗi thích đốt một số người hơn?",
  "series_hint": "Vì sao…",
  "music_mood": "tò mò",
  "sources": [
    {
      "id": "s1",
      "claim": "Muỗi phát hiện CO2 từ xa khoảng 10 m",
      "url": "https://www.cdc.gov/mosquitoes/"
    }
  ],
  "scenes": [
    {
      "voice": "Có người ngồi cả buổi không sao, | có người bị đốt sưng cả chân.",
      "card": {
        "y": "top",
        "lines": [
          { "text": "VÌ SAO MUỖI", "size": "l", "color": "ink" },
          { "text": "CHỌN BẠN?", "size": "xl", "color": "accent" }
        ]
      },
      "labels": [],
      "punch": true,
      "caption_y": null,
      "image_prompt": "close-up of a mosquito on human skin, macro photo, vertical 9:16"
    },
    {
      "voice": "Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét.",
      "card": {
        "y": "top",
        "lines": [{ "text": "CO2 TỪ 10 MÉT", "size": "l", "color": "ink" }]
      },
      "labels": [],
      "punch": false,
      "caption_y": null,
      "image_prompt": "person breathing out in warm evening air, vertical 9:16"
    },
    {
      "voice": "Thở nhiều, đổ mồ hôi nhiều | thì muỗi tìm bạn dễ hơn.",
      "card": {
        "y": "top",
        "lines": [{ "text": "THỞ NHIỀU = DỄ BỊ ĐỐT", "size": "m", "color": "ink" }]
      },
      "labels": [],
      "punch": false,
      "caption_y": null,
      "image_prompt": "person jogging at dusk near a pond, vertical 9:16"
    }
  ],
  "publish": {
    "hook": "Bạn có phải \"nam châm hút muỗi\"?",
    "hashtags": ["haybiettuot", "muoi", "visao"]
  },
  "thumbnail": {
    "scene": 1,
    "lines": ["VÌ SAO MUỖI", "CHỌN BẠN?"],
    "series": "",
    "accent": "#FFD43B"
  }
}
```

## Sau khi nhận JSON

1. Dán vào Trang chủ → **Tạo dự án từ JSON nháp**. Lỗi (K13–K15, K1–K12) thì chép nguyên thông báo gửi lại Claude chat: "Sửa JSON theo các lỗi sau".
2. Cảnh báo K16 (số chưa có nguồn): kiểm lại số liệu; K17 (prompt có từ cấm) và K18 (thiếu prompt): sửa trong bước Ảnh.
3. Tự kiểm số liệu và nguồn trước khi duyệt kịch bản: Claude chat có thể sai.
