# Bàn giao HBT Studio cho Gemini (22/10/2026)

> Người viết: Claude (người rà soát của dự án). Người code trước: Claude Code (M0–M3). Từ nay: Gemini.
> Chủ dự án: Thong. Mọi quyết định chưa có trong tài liệu → **hỏi chủ dự án**, không tự quyết.

## 0. Đọc theo thứ tự

1. `GEMINI.md` (gốc repo): trỏ tới các file dưới.
2. `CLAUDE.md`: **luật làm việc, áp dụng cho bạn y hệt** như cho Claude Code (đọc "Claude Code" là "bạn").
3. File này.
4. `PLAN.md` (mục tiêu, nhật ký quyết định) và `IMPLEMENT.md` v1.4 (đặc tả; quan trọng: mục 4, 4b–4e, 5, 6, 7, 9, 11).
5. `reference/pipeline/*.py`: code đã chạy thật, **giữ nguyên tham số** khi đối chiếu.
6. `DESIGN-HBT.md`: chỉ khi phải sửa giao diện.

**Không đọc, không làm theo, không commit** `DESIGN.md` hay `DESIGN-nike.md` (tài liệu bên thứ ba) nếu thấy trong máy.

## 1. Sản phẩm

Web app **chạy local** (127.0.0.1) dựng video ngắn 9:16 tiếng Việt cho kênh "Hay Biết Tuốt". Người dùng đưa vào: 3–12 ảnh cảnh, lời đọc từng cảnh, file giọng (Vbee), nhạc nền. App xuất: video 1080×1920 **50fps** có phóng ảnh mượt, chuyển cảnh nhoè chuyển động, thẻ chữ, **phụ đề karaoke**, nhạc tự hạ khi có giọng, **outro 4 giây**, ảnh bìa, tiêu đề/hashtag. Backend Python 3.11 + FastAPI + FFmpeg + Pillow; frontend React + Vite + Tailwind.

## 2. Trạng thái hiện tại

| Mốc | Nội dung | Trạng thái |
|---|---|---|
| M0 | Khung dự án, /health | Xong, tag `v0.1.1` |
| M1 | Bộ dựng video (CLI) | Xong, tag `v0.2.0` |
| M2 | API, job, SSE | Xong, tag `v0.3.0` (main `4673488`, CI xanh) |
| M3 | Giao diện 4 màn | **Đang khép**, nhánh `feat/m3-ui`, **chưa push**. pytest 400, Vitest 59 xanh |
| M4 | Hoàn thiện hệ thống | Chưa làm |

Kiểm tra nhanh: `npm run dev` (giao diện 127.0.0.1:5173), `npm run lint`, `npm run test`, `python -m cli render workspace/samples/muoi`.

## 3. Ưu tiên của chủ dự án (mới, 22/10/2026)

1. **Hệ thống chạy đúng, ổn định, hiệu quả** quan trọng hơn giao diện. Giao diện chỉ cần **dùng được và rõ ràng**, gần tinh thần `DESIGN-HBT.md`, không cần đẹp, không làm việc trang trí.
2. **Không đổi tham số chất lượng của bản xuất đẹp** (đã duyệt bằng mắt): 50fps, phóng ảnh 3 lần, easing, nhoè chuyển động, CRF 16, −14 LUFS.
3. Không mất dữ liệu người dùng (ảnh, giọng, project) trong mọi thao tác.

## 4. Việc 1: Khép M3 (chỉ phần hệ thống)

| # | Việc | Tiêu chí xong |
|---|---|---|
| A1 | **(BẮT BUỘC) Ảnh cảnh đặt tên duy nhất** theo hash nội dung (`images/<sha256 16 ký tự>.<đuôi>`), không theo vị trí. Thêm `DELETE /api/projects/{slug}/scenes/{scene_index}` (giữ ràng buộc 3–12). Khi lưu, dọn ảnh trong `images/` không còn cảnh nào tham chiếu. Tự chuyển project cũ dạng `scene-01.png` khi mở. Giao diện dùng API xoá mới | Test: đổi thứ tự rồi tải ảnh mới cho 1 cảnh → hash ảnh các cảnh khác không đổi; xoá cảnh → ảnh của nó bị dọn, ảnh khác còn; project cũ mở được |
| A2 | API nhạc theo tên file: chỉ tên trong thư mục thư viện; chặn `/`, `\`, `..`, đường dẫn tuyệt đối; chỉ đuôi mp3/wav/m4a/ogg | Test chặn từng trường hợp |
| A3 | Bản **Xem nhanh** nhẹ hơn: giữ 540×960, 30fps; CRF ~30, âm thanh 96 kbps | 50 giây video < ~10 MB. Bản đẹp không đổi |
| A4 | **Đo lại thời gian dựng bản đẹp** tập mẫu khi máy rảnh (không mở trình duyệt/Playwright). M1 đo 145 s, lần chạy M3 là 261 s | Báo số đo và tên máy. Chậm hơn 20% so với 145 s thì tìm nguyên nhân và sửa |
| A5 | CI thêm `npm run build` | CI xanh |
| A6 | Thêm `npm run e2e` (Playwright, chạy máy cá nhân, không đưa vào CI): mở trang, tạo project, thêm 3 cảnh, lưu, tải lại | Chạy được, ghi vào README |

**Không làm (đưa vào backlog, ghi trong IMPLEMENT mục 11):** thay biểu tượng bằng lucide-react, thêm font 400/600, ảnh chụp màn hình, chuyển trang trượt/mờ.

**Đóng M3** theo quy trình mốc trong `CLAUDE.md`: lint + test xanh → push `feat/m3-ui` (chủ dự án đã cho phép push nhánh này) → CI xanh → commit `chore(M3): done` → báo cáo → **chờ chủ dự án duyệt** → merge `--no-ff` vào main, tag `v0.4.0`.

## 5. Việc 2: M4 (hoàn thiện hệ thống)

Làm trên nhánh `feat/m4-system`, sau khi M3 đã merge.

| # | Việc | Đặc tả |
|---|---|---|
| B1 | **Căn chữ bằng Whisper** theo phần cứng: có CUDA → `large-v3` int8_float16; không GPU → `small` int8 (đổi được trong Cài đặt). Cache `timing.json` theo hash giọng + hash kịch bản. Lỗi hoặc quá giới hạn thời gian → tự rơi về căn khoảng lặng, ghi log. Giải phóng model sau khi căn | IMPLEMENT 5.2 |
| B2 | Lệnh `python -m cli bench-align <dự án> [--models small,medium,large-v3]`: thời gian, tỉ lệ âm tiết khớp kịch bản, độ lệch mốc cắt cảnh so với căn khoảng lặng | IMPLEMENT 5.2 |
| B3 | Cắt đuôi file giọng bằng Whisper: `end(token cuối) + 0,35 s` | IMPLEMENT 4d.1 |
| B4 | Kiểm tra từ nhạy cảm (`data/sensitive_words.json`, mức info/warn/block) cho thẻ chữ, nhãn, lời đọc, dòng bìa | IMPLEMENT mục 7 |
| B5 | Thư viện nhạc có **id** ổn định trong `library/music/index.json`; API nhạc đổi sang id; tự chọn đoạn nhạc | IMPLEMENT 6.1–6.2 |
| B6 | Ảnh bìa `cover_9x16.jpg` + `youtube_3x2.jpg` | IMPLEMENT 4e. Font tiêu đề: Bricolage Grotesque (OFL, đã duyệt tải từ kho Google Fonts kèm giấy phép); thiếu thì dự phòng Be Vietnam Pro ExtraBold |
| B7 | `publish.txt` có khối `[Thumbnail]` (dòng chữ bìa, tên 2 file) | IMPLEMENT mục 8, 4e |
| B8 | **Dọn cache**: `build/` có thể phình to (clip trung gian chất lượng cao). Thêm `python -m cli clean [--older-than 7d]` và nút trong Cài đặt; không bao giờ xoá `images/`, giọng, nhạc, `renders/` | Mới, hỏi chủ dự án nếu cần giới hạn khác |
| B9 | **Golden test cuối Giai đoạn 1**: dựng tập muỗi trên máy cũ (CPU) và máy mới (GPU) | Phụ đề lệch < 0,05 s ở các mốc so sánh; báo thời gian từng bước |

**Giai đoạn 1 xong khi:** M4 merge, tag `v1.0.0`, chủ dự án làm trọn một video thật bằng giao diện không mở terminal.

## 6. Bẫy đã gặp (đừng lặp lại)

- FFmpeg 6.1.1 không in dòng `------` trước danh sách `-filters`; nhận diện dòng theo dạng "cờ + tên".
- Huỷ job đúng lúc đang ghi khung từng để lại tiến trình `ffmpeg` mồ côi; mọi tiến trình con phải được `wait()`; có test thu dọn tiến trình.
- Windows: thời điểm sửa file chỉ chính xác ~15 ms; hash file không được dựa vào kích thước + thời gian.
- Khoá cache phải gồm hash mã nguồn pipeline, nếu không cache cũ làm sai kết quả.
- Outro không lời từng ra 2,05 s: luôn dùng nền im lặng đúng 4,0 s.
- `alimiter` phải có `level=0`, nếu không tự nâng mức (outro lên −13 LUFS).
- `voice.wav` của outro là mono −16,2 LUFS; mức cuối đo sau trộn stereo, chỉnh gain về −14,0.
- Cú pháp `100{một trăm}`: ngoặc nhọn chứa khoảng trắng, không tách bằng `split()` thuần.
- Căn khoảng lặng từng cắt nhầm câu kết thật thành "quảng cáo": giữ điều kiện bảo vệ ở IMPLEMENT 4d.
- Từng commit khi test đỏ vì nối lệnh bằng `;`: luôn `&&` và `set -o pipefail`.

## 7. Máy của chủ dự án

| | Máy cũ (đang dùng) | Máy mới |
|---|---|---|
| CPU / GPU / RAM | i5-10400 / không / 16 GB | i5-14400F / RTX 2060 Super 8 GB / 32 GB |

Không giả định có GPU. Python dự án ghim 3.11 (tạo venv bằng `py -3.11`).

## 8. Báo cáo sau mỗi mốc

Gồm: việc đã làm, số test, số đo (thời gian dựng, kích thước, LUFS, fps), các quyết định tự đưa ra, câu hỏi cho chủ dự án, hash commit cuối. Ngắn gọn, dạng bảng.
