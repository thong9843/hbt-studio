# 06 — Câu hỏi mở PostV

Ngày 29/10/2026 (cập nhật sau khi chủ dự án trả lời và gửi video mẫu `postv-thu-01_v2_1080p60.mp4`).
Mã `C-nn` được `02-PRD.md` và `IMPLEMENT-POSTV.md` dẫn chiếu. Mỗi câu còn mở có phương án, **đề xuất** (in đậm) và mốc bị chặn.
Ký hiệu: **[KC]** đã kiểm chứng · **[SL]** suy luận · **[?]** chưa biết.

## 1. Đã chốt

| Mã   | Chốt                                                                                                                                                                                     | Từ câu    | Ghi ở                          |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------------ |
| K-01 | Chép bước 2–4 của `_render_project` vào `postv/` ở PV đầu (không sửa `render.py`)                                                                                                        | —         | PRD D15                        |
| K-02 | fps xuất hỗ trợ 30, 50, 60                                                                                                                                                               | —         | PRD D12                        |
| K-03 | PostV bỏ giới hạn ký tự (đó là giới hạn gói Vbee); chỉ nhắc từ 120 s trở lên; **thời lượng tự do, dưới 2 phút**                                                                          | —         | PRD D11                        |
| K-04 | Giọng PostV = VieNeu-TTS local thay Vbee; không chia lượt, không cắt quảng cáo                                                                                                           | —         | PRD D10, 7b                    |
| K-05 | Nền: nhiều video có giấy phép; ngắn hơn lời thì nối clip khác                                                                                                                            | —         | PRD D13                        |
| K-06 | Bìa: ưu tiên `thumbnail.image`, không có thì lấy khung gameplay                                                                                                                          | —         | PRD D14                        |
| K-07 | Đợt fix/cover-drop làm một lượt sau khi xong hết PostV                                                                                                                                   | —         | PLAN Nhật ký 29/10             |
| K-08 | Chỉ kiểm đường CUDA trên máy mới; việc còn lại làm trên máy cũ                                                                                                                           | —         | PRD D17                        |
| K-10 | Nền là video **dọc** 1080×1920; **chỉ nhận video dọc** (không cắt, không lấp khung)                                                                                                      | C-01      | IMPLEMENT-POSTV mục 4, R4      |
| K-11 | fps mặc định PostV **60** (30 và 50 vẫn chọn được)                                                                                                                                       | C-05      | PRD D12                        |
| K-12 | Outro 60 fps: dùng clip `outro_4s_60fps.mp4` có sẵn. 30 và 50 fps dùng clip 50 (chỉ dựng clip 30 nếu PV0 thấy nhịp lệch)                                                                 | C-06      | IMPLEMENT-POSTV R6             |
| K-13 | Giấy phép trọng số VieNeu: bỏ qua (chủ dự án: miễn phí). PV0 chỉ chép nguyên văn giấy phép vào docs                                                                                      | C-03      | PRD mục 6                      |
| K-14 | Cài VieNeu: thử trong `backend/.venv`; nếu hoá ra cần phần mềm hệ thống hoặc driver thì dừng và hỏi (CLAUDE.md)                                                                          | C-04      | IMPLEMENT-POSTV PV4            |
| K-15 | Hiệu ứng thẻ: bộ **"Mượt"** mặc định, **"Nảy"** tuỳ chọn (mô tả ở IMPLEMENT-POSTV mục 6). Thay K-09                                                                                      | C-07      | PRD D21                        |
| K-16 | Số lượt xem/like trên thẻ **chạy tăng dần tới giá trị nhập**, bật mặc định khi có giá trị                                                                                                | C-11      | PRD D20                        |
| K-17 | Nối clip nền: **cắt thẳng**, mỗi clip 7,5 s hoặc 15 s (đo từ video mẫu), chọn theo `seed` để dựng lại giống nhau                                                                         | C-12      | IMPLEMENT-POSTV mục 6          |
| K-18 | `publish.txt` có dòng "Nguồn" (nếu có link); nút Xoá nguồn xoá chữ nguồn, giữ kịch bản                                                                                                   | C-13      | PRD D22                        |
| K-19 | Giọng VieNeu **có sẵn** trước; nhân bản giọng làm sau PV4                                                                                                                                | C-15      | PRD D22                        |
| K-20 | Không tách hàm bước 2–4 khỏi `render.py` trong giai đoạn PostV; cân nhắc ở đợt dọn nợ sau PostV, cùng đợt fix/cover-drop (đề xuất, chờ bạn phản đối)                                     | C-16      | IMPLEMENT-POSTV mục 6          |
| K-21 | **Mẫu làm trước = "Thẻ theo đoạn"** theo video mẫu (thẻ hook, bài, bình luận, đoạn commentary không thẻ). "Thẻ cố định" thành biến thể ở PV7                                             | video mẫu | PRD D7, mục 7c                 |
| K-22 | **Giữ nguyên tên tài khoản** như bài đã dán, không che gì (avatar vẫn là hình người xám trơn; không logo nền tảng). Bỏ ẩn danh của brief #4/D4                                           | C-10      | PRD D4, D18                    |
| K-23 | Phụ đề: mặc định kiểu HBT (vàng); thêm preset màu **vàng, xanh lá, xanh dương, đỏ** và **ô chọn màu tuỳ chỉnh** (hex); ô nhấn thẻ hook cùng màu                                          | C-08      | PRD D19, IMPLEMENT-POSTV mục 6 |
| K-24 | Mọi cảnh báo **chỉ nhắc**, kể cả thiếu commentary và trích nguyên văn. Thời lượng không cố định, nhắc từ 120 s trở lên                                                                   | C-09      | PRD D5, D11                    |
| K-25 | Sticker (làm sau, PV7): chỉ nguồn miễn phí không cần ghi công: Kenney (CC0), Pixabay (Content License), Noto Emoji (Apache 2.0). `source`/`license` của sticker tuỳ chọn, thiếu chỉ nhắc | C-14      | PRD Could                      |

## 2. Còn mở (1 câu, không chặn thiết kế)

| Mã   | Câu hỏi                                                                                         | Phương án                                                                                                                                                         | Chặn mốc |
| ---- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| C-02 | Thêm mẫu chữ dán từ Threads. Mẫu 1 đã có và cho thấy định dạng rất đều (IMPLEMENT-POSTV mục 5b) | **A. Thêm 2–4 mẫu khác (có ảnh/video, bình luận trả lời lồng, bài ngắn/dài) vào `workspace/samples/` trước PV2.** B. Làm theo mẫu 1, gặp định dạng lạ thì sửa tay | PV2      |

## 3. PV0 phải trả lời bằng số đo

| #   | Đo                                                                                             | Phục vụ            |
| --- | ---------------------------------------------------------------------------------------------- | ------------------ |
| M1  | VieNeu trên CPU máy cũ: tốc độ (fp32/int8), chất lượng tiếng Việt, đọc `{}` thế nào            | K-04, K-14, PV4    |
| M2  | Whisper `small` CPU trên giọng VieNeu: tỉ lệ khớp, thời gian                                   | PV4, PV5           |
| M3  | Tốc độ đọc VieNeu (ký tự/giây) → 120 s bằng bao nhiêu ký tự (để ước thời lượng)                | C-09               |
| M4  | Outro 30 fps và 50 fps từ clip 50 (nhịp lệch có thấy được không)                               | K-12               |
| M5  | ffmpeg một lệnh (nền + thẻ có hiệu ứng + phụ đề) 60 s ở 60/50/30 fps trên máy cũ               | thời gian dựng PV5 |
| M6  | Giấy phép trọng số VieNeu (chép nguyên văn vào docs, 1 dòng)                                   | K-13               |
| M7  | Khung chữ thẻ trong video mẫu (cỡ chữ, bo góc, màu, khoảng cách) đo chi tiết hơn từ khung hình | `story_cards.json` |
