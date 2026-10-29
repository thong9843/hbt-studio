# 06 — Câu hỏi mở PostV

Ngày 29/10/2026 (cập nhật sau khi chủ dự án trả lời và gửi video mẫu `postv-thu-01_v2_1080p60.mp4`).
Mã `C-nn` được `02-PRD.md` và `IMPLEMENT-POSTV.md` dẫn chiếu. Mỗi câu còn mở có phương án, **đề xuất** (in đậm) và mốc bị chặn.
Ký hiệu: **[KC]** đã kiểm chứng · **[SL]** suy luận · **[?]** chưa biết.

## 1. Đã chốt

| Mã   | Chốt                                                                                                                                                 | Từ câu    | Ghi ở                     |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------- |
| K-01 | Chép bước 2–4 của `_render_project` vào `postv/` ở PV đầu (không sửa `render.py`)                                                                    | —         | PRD D15                   |
| K-02 | fps xuất hỗ trợ 30, 50, 60                                                                                                                           | —         | PRD D12                   |
| K-03 | PostV bỏ giới hạn ký tự (đó là giới hạn gói Vbee); cảnh báo theo giây 35–75 s                                                                        | —         | PRD D11                   |
| K-04 | Giọng PostV = VieNeu-TTS local thay Vbee; không chia lượt, không cắt quảng cáo                                                                       | —         | PRD D10, 7b               |
| K-05 | Nền: nhiều video có giấy phép; ngắn hơn lời thì nối clip khác                                                                                        | —         | PRD D13                   |
| K-06 | Bìa: ưu tiên `thumbnail.image`, không có thì lấy khung gameplay                                                                                      | —         | PRD D14                   |
| K-07 | Đợt fix/cover-drop làm một lượt sau khi xong hết PostV                                                                                               | —         | PLAN Nhật ký 29/10        |
| K-08 | Chỉ kiểm đường CUDA trên máy mới; việc còn lại làm trên máy cũ                                                                                       | —         | PRD D17                   |
| K-10 | Nền là video **dọc** 1080×1920; **chỉ nhận video dọc** (không cắt, không lấp khung)                                                                  | C-01      | IMPLEMENT-POSTV mục 4, R4 |
| K-11 | fps mặc định PostV **60** (30 và 50 vẫn chọn được)                                                                                                   | C-05      | PRD D12                   |
| K-12 | Outro 60 fps: dùng clip `outro_4s_60fps.mp4` có sẵn. 30 và 50 fps dùng clip 50 (chỉ dựng clip 30 nếu PV0 thấy nhịp lệch)                             | C-06      | IMPLEMENT-POSTV R6        |
| K-13 | Giấy phép trọng số VieNeu: bỏ qua (chủ dự án: miễn phí). PV0 chỉ chép nguyên văn giấy phép vào docs                                                  | C-03      | PRD mục 6                 |
| K-14 | Cài VieNeu: thử trong `backend/.venv`; nếu hoá ra cần phần mềm hệ thống hoặc driver thì dừng và hỏi (CLAUDE.md)                                      | C-04      | IMPLEMENT-POSTV PV4       |
| K-15 | Hiệu ứng thẻ: bộ **"Mượt"** mặc định, **"Nảy"** tuỳ chọn (mô tả ở IMPLEMENT-POSTV mục 6). Thay K-09                                                  | C-07      | PRD D21                   |
| K-16 | Số lượt xem/like trên thẻ **chạy tăng dần tới giá trị nhập**, bật mặc định khi có giá trị                                                            | C-11      | PRD D20                   |
| K-17 | Nối clip nền: **cắt thẳng**, mỗi clip 7,5 s hoặc 15 s (đo từ video mẫu), chọn theo `seed` để dựng lại giống nhau                                     | C-12      | IMPLEMENT-POSTV mục 6     |
| K-18 | `publish.txt` có dòng "Nguồn" (nếu có link); nút Xoá nguồn xoá chữ nguồn, giữ kịch bản                                                               | C-13      | PRD D22                   |
| K-19 | Giọng VieNeu **có sẵn** trước; nhân bản giọng làm sau PV4                                                                                            | C-15      | PRD D22                   |
| K-20 | Không tách hàm bước 2–4 khỏi `render.py` trong giai đoạn PostV; cân nhắc ở đợt dọn nợ sau PostV, cùng đợt fix/cover-drop (đề xuất, chờ bạn phản đối) | C-16      | IMPLEMENT-POSTV mục 6     |
| K-21 | **Mẫu làm trước = "Thẻ theo đoạn"** theo video mẫu (thẻ hook, bài, bình luận, đoạn commentary không thẻ). "Thẻ cố định" thành biến thể ở PV7         | video mẫu | PRD D7, mục 7c            |

## 2. Còn mở (5 câu)

| Mã   | Câu hỏi                                                                                                                                                                                                                                | Phương án                                                                                                                                                                                                                                                                                                                                   | Chặn mốc |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| C-02 | Mẫu bài Threads: bạn **copy cả bài + bình luận** từ trang Threads rồi dán vào file. Tôi cần 3–5 file mẫu                                                                                                                               | **A. Bạn dán 3–5 mẫu vào `docs/postv/samples/*.txt` (có thể đổi tên tài khoản thành `user1`, `user2`…) trước khi bắt đầu PV2.** B. Làm ô dán trước, tách theo dòng trống, sửa tay hoàn toàn, sửa bộ tách sau khi có mẫu                                                                                                                     | PV2      |
| C-08 | **Phụ đề.** Bạn nói "như HBT", nhưng video mẫu dùng chữ HOA + từ đang đọc xanh lá, 1–3 từ. Chọn kiểu nào?                                                                                                                              | **A. Như HBT: cơ chế karaoke của HBT (từ đang đọc đổi màu vàng `#FFD43B`, hoa/thường theo kịch bản), nhưng chỉ 1–3 từ mỗi lần.** B. Như video mẫu: CHỮ HOA, trắng viền đen, từ đang đọc xanh lá, y ≈ 76 %. Cả hai đều là preset, đổi được sau                                                                                               | PV5      |
| C-09 | **Ngưỡng cảnh báo là gì?** Ở bước Xuất, nút Kiểm tra hiện dòng vàng khi: video quá ngắn/dài (ngoài 35–75 s), phần góc nhìn riêng của bạn quá ít, hoặc kịch bản gần như đọc nguyên văn bài người khác. Câu hỏi: chỉ nhắc hay chặn luôn? | **A. Chỉ nhắc (dòng vàng, vẫn xuất được): ngoài 35–75 s; commentary < 30 % thời lượng; trích nguyên văn > 70 %. Riêng thiếu hẳn commentary thì chặn (đã chốt từ brief).** B. Chặn xuất khi ngoài 15–90 s. C. Không nhắc gì                                                                                                                  | PV2      |
| C-10 | **Tên tài khoản hiển thị trên thẻ.** Tôi chưa hiểu "như tbh" nghĩa là gì, bạn nói rõ giúp. Video mẫu hiện tên dạng `_momon.nga_`, trông như tên thật; brief và PRD D4 yêu cầu ẩn danh                                                  | **A. Mặc định tên giả do app đặt (`nguoi_dung_1`, `nguoi_dung_2`…), mỗi thẻ sửa tay được.** B. Gõ tay từng tên (app không tự điền). C. Giữ nguyên tên tài khoản như trong bài đã dán (rủi ro lộ danh tính, ngược quyết định D4 của brief)                                                                                                   | PV3      |
| C-14 | **Sticker** bạn bảo tôi đề xuất thư viện. Có cần sticker không (video mẫu không có)?                                                                                                                                                   | **A. Làm sau (PV7). Thư viện đề xuất, mỗi sticker lưu `source` + `license` như nền: Kenney (CC0), Noto Emoji/Noto Animated Emoji (Google, Apache 2.0 / CC BY 4.0), Twemoji (CC BY 4.0, phải ghi công). Tôi kiểm lại điều khoản nguyên văn khi làm PV7 [SL].** B. Không làm sticker. C. Dùng meme tự tải về (bạn tự chịu giấy phép từng ảnh) | PV7      |

## 3. PV0 phải trả lời bằng số đo

| #   | Đo                                                                                             | Phục vụ            |
| --- | ---------------------------------------------------------------------------------------------- | ------------------ |
| M1  | VieNeu trên CPU máy cũ: tốc độ (fp32/int8), chất lượng tiếng Việt, đọc `{}` thế nào            | K-04, K-14, PV4    |
| M2  | Whisper `small` CPU trên giọng VieNeu: tỉ lệ khớp, thời gian                                   | PV4, PV5           |
| M3  | Tốc độ đọc VieNeu (ký tự/giây) → 35–75 s bằng bao nhiêu ký tự                                  | C-09               |
| M4  | Outro 30 fps và 50 fps từ clip 50 (nhịp lệch có thấy được không)                               | K-12               |
| M5  | ffmpeg một lệnh (nền + thẻ có hiệu ứng + phụ đề) 60 s ở 60/50/30 fps trên máy cũ               | thời gian dựng PV5 |
| M6  | Giấy phép trọng số VieNeu (chép nguyên văn vào docs, 1 dòng)                                   | K-13               |
| M7  | Khung chữ thẻ trong video mẫu (cỡ chữ, bo góc, màu, khoảng cách) đo chi tiết hơn từ khung hình | `story_cards.json` |
