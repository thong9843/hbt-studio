# 06 — Câu hỏi mở PostV

Ngày 29/10/2026 · Mã `C-nn` được `02-PRD.md` và `IMPLEMENT-POSTV.md` dẫn chiếu.
Cách dùng: mỗi câu có phương án, **đề xuất** (in đậm) và mốc bị chặn. Chủ dự án chọn một phương án; trả lời xong thì chuyển câu sang bảng 1 và ghi vào `IMPLEMENT-POSTV.md`.
Ký hiệu: **[KC]** đã kiểm chứng · **[SL]** suy luận · **[?]** chưa biết.

## 1. Đã chốt (29/10/2026)

| Mã   | Chốt                                                                               | Ghi ở                          |
| ---- | ---------------------------------------------------------------------------------- | ------------------------------ |
| K-01 | Chép bước 2–4 của `_render_project` vào `postv/` ở PV đầu (không sửa `render.py`)  | PRD D15, IMPLEMENT-POSTV mục 6 |
| K-02 | fps xuất hỗ trợ 30, 50, 60                                                         | PRD D12                        |
| K-03 | PostV bỏ giới hạn ký tự (đó là giới hạn gói Vbee); cảnh báo theo giây 35–75 s      | PRD D11                        |
| K-04 | Giọng PostV = **VieNeu-TTS local** thay Vbee; không chia lượt, không cắt quảng cáo | PRD D10, 7b                    |
| K-05 | Nền: nhiều video full HD 60 fps có giấy phép; ngắn hơn lời thì nối clip khác       | PRD D13                        |
| K-06 | Bìa: ưu tiên `thumbnail.image`, không có thì lấy khung gameplay                    | PRD D14                        |
| K-07 | Đợt fix/cover-drop làm một lượt sau khi xong hết PostV                             | PLAN Nhật ký 29/10             |
| K-08 | Chỉ kiểm đường CUDA trên máy mới; mọi việc còn lại làm trên máy cũ                 | PRD D17                        |
| K-09 | Thẻ hiện dần 0,35 s mặc định; phóng 0,25 s là tuỳ chọn                             | IMPLEMENT-POSTV mục 6          |

## 2. Câu cần chốt

| Mã   | Câu hỏi                                                                                                                | Phương án                                                                                                                                                                                                                                       | Chặn mốc |
| ---- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| C-01 | Video nền của bạn **dọc (9:16) hay ngang (16:9)**? Nếu ngang, lấp khung 1080×1920 thế nào?                             | **A. Nếu ngang: khung ngang đặt giữa, trên/dưới là nền mờ của chính clip (không phóng, giữ nét).** B. Cắt giữa 9:16 rồi phóng ~1,8× (mờ hơn). C. Chỉ nhận video dọc. Nếu đã dọc: cắt giữa, có tuỳ chọn lệch trái/phải (`focus_x`). Đo thử ở PV0 | PV3      |
| C-02 | Mẫu copy cả trang Threads (3–5 mẫu đã che tên) để viết bộ tách bài/bình luận                                           | **A. Bạn đưa 3–5 mẫu vào `docs/postv/samples/` (đã che tên/tài khoản) ở PV0.** B. Bắt đầu bằng ô dán + tách theo dòng trống, sửa tay hoàn toàn, nâng cấp sau                                                                                    | PV2      |
| C-03 | Giấy phép **trọng số** VieNeu-TTS có cho dùng trong kênh kiếm tiền không? (mã nguồn Apache 2.0 [KC], trọng số **[?]**) | **A. PV0 tôi đọc trang/model card và ghi nguyên văn; bạn xác nhận.** B. Không rõ thì giữ `FileVoice` (nhập file) làm đường chính, VieNeu chỉ để thử                                                                                             | PV4      |
| C-04 | Cài VieNeu cần gì ngoài gói Python trong `backend/.venv` (vd phần mềm cấp hệ thống, tải trọng số về `models/`)?        | **A. Thử trong `.venv`; nếu cần phần mềm hệ thống hoặc driver thì dừng và hỏi bạn trước (CLAUDE.md).** B. Bạn tự cài trước rồi tôi chỉ gọi                                                                                                      | PV4      |
| C-05 | fps mặc định của PostV? (nguồn nền 60 fps; xuất 50 fps từ 60 fps lặp/bỏ khung không đều)                               | A. 50 như đề xuất ban đầu (khớp bản đẹp HBT). **B. 60 mặc định cho PostV (khớp nguồn, đã có outro 60 fps); 50 và 30 vẫn chọn được.** C. 30 cho nhẹ máy cũ                                                                                       | PV5      |
| C-06 | Outro ở 30 fps: dùng clip 50 fps ép `fps=30`, hay dựng sẵn clip 30 fps?                                                | **A. Đo ở PV0; nếu nhịp lệch thấy được thì dựng `outro_4s_30fps.mp4` bằng `outro_reference.py` (như cách làm bản 60 fps).** B. Luôn dùng clip 50 ép fps                                                                                         | PV5      |
| C-07 | Hiệu ứng thẻ vào/ra                                                                                                    | **A. Hiện dần 0,35 s (như `CARD_FADE`), mờ dần cuối; "phóng 0,25 s" bật được ở Cài đặt mẫu.** B. Luôn phóng từ nhỏ 0,25 s (như mẫu A). C. Trượt vào/ra 0,4 s (như chuyển cảnh HBT)                                                              | PV5      |
| C-08 | Kiểu phụ đề mặc định                                                                                                   | **A. Hooked: 1–3 từ, chữ thường, trắng viền tối, từ đang đọc đổi `#FFD43B`, giữa-thấp (y ≈ 60 %).** B. Như mẫu A: hộp đỏ bo góc ở từ đang đọc, y ≈ 77 %. C. Như mẫu B: CHỮ HOA, từ đang đọc xanh lá. Tất cả đổi được trong cấu hình mẫu         | PV5      |
| C-09 | Ngưỡng cảnh báo                                                                                                        | **A. Cảnh báo (không chặn) ngoài 35–75 s; cảnh báo khi phần commentary < 30 % thời lượng hoặc khi trích nguyên văn > 70 %.** B. Chặn xuất khi ngoài 15–90 s. C. Không cảnh báo                                                                  | PV2      |
| C-10 | Tên hiển thị trên thẻ                                                                                                  | **A. Cố định "Người dùng ẩn danh", sửa được; avatar vòng tròn trơn.** B. Tên ngẫu nhiên kiểu `user_1234`. C. Không hiện tên                                                                                                                     | PV3      |
| C-11 | Số like/bình luận trên thẻ có chạy số tăng dần như mẫu A?                                                              | **A. Tắt mặc định; bật được (Should).** B. Bật mặc định. C. Không làm                                                                                                                                                                           | PV5      |
| C-12 | Cách nối nhiều clip nền khi một clip ngắn hơn lời                                                                      | **A. Cắt thẳng, mỗi clip dùng ≥ 8 s, chọn/nối theo `seed` để dựng lại giống nhau.** B. Hoà 0,3 s giữa clip. C. Lặp lại clip đầu                                                                                                                 | PV5      |
| C-13 | Ghi nguồn khi đăng và gỡ video khi chủ bài yêu cầu                                                                     | **A. `publish.txt` có dòng "Nguồn: <url đã lưu>" (nếu có); nút Xoá nguồn xoá chữ nguồn, giữ kịch bản.** B. Không ghi nguồn lên `publish.txt` (chỉ lưu trong project)                                                                            | PV8      |
| C-14 | Mẫu B "Chuỗi bình luận" và sticker                                                                                     | **A. Làm sau PV6 (Could); sticker chỉ từ thư viện có giấy phép.** B. Không làm trong giai đoạn này                                                                                                                                              | PV7      |
| C-15 | Giọng VieNeu: giọng có sẵn hay nhân bản từ mẫu 3–8 s của bạn [KC]                                                      | **A. Giọng có sẵn trước; nhân bản sau PV4 nếu giấy phép (C-03) cho phép.** B. Nhân bản ngay từ PV4                                                                                                                                              | PV4      |
| C-16 | Khi nào tách hàm bước 2–4 khỏi `render.py` cho dùng chung (đỡ trùng mã)?                                               | **A. Không tách trong giai đoạn PostV (giữ `PIPELINE_VERSION`); cân nhắc ở đợt dọn nợ sau PostV, cùng đợt fix/cover-drop.** B. Tách ở PV5 (ngoại lệ có duyệt, `PIPELINE_VERSION` đổi một lần như `v1.1.0`)                                      | sau PV8  |

## 3. Việc PV0 phải trả lời bằng số đo

| #   | Đo                                                               | Trả lời câu        |
| --- | ---------------------------------------------------------------- | ------------------ |
| M1  | Hướng, độ phân giải, fps, codec của 3–5 clip nền bạn đưa         | C-01, C-05         |
| M2  | VieNeu: tốc độ trên CPU máy cũ (fp32/int8), chất lượng, đọc `{}` | C-03, C-04, C-15   |
| M3  | Whisper `small` CPU trên giọng VieNeu: tỉ lệ khớp, thời gian     | PV4, PV5           |
| M4  | Tốc độ đọc VieNeu (ký tự/giây) → 35–75 s bằng bao nhiêu ký tự    | C-09               |
| M5  | Outro 30 fps từ clip 50                                          | C-06               |
| M6  | ffmpeg một lệnh (nền + thẻ + phụ đề) 60 s ở 30/50/60 fps, máy cũ | thời gian dựng PV5 |
| M7  | Giấy phép trọng số VieNeu (nguyên văn)                           | C-03               |
