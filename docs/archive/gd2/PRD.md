# HBT Studio — PRD Giai đoạn 2 (Tạo nội dung HBT tự động)

> Duyệt 02/11/2026. Đặc tả kỹ thuật: `IMPLEMENT-GD2.md`. Mẫu prompt: `PROMPT-KICH-BAN.md`.
> Tham chiếu: `PLAN.md` §2 và §6b, `IMPLEMENT.md` §12 và §13.B4, PostV (VieNeu, PVA).

## 1. Mục tiêu

**Một chủ đề → một bản nháp HBT đầy đủ để duyệt.** Chi phí 0, app **không gọi API trên mạng**. Ba điểm duyệt giữ nguyên: **kịch bản → ảnh → video**. AI không tự đăng.

## 2. Người dùng và bối cảnh

- Một người dùng (chủ dự án), Windows, chạy local, hai máy: máy cũ (i5-10400, không GPU, 16 GB) và máy mới (i5-14400F, RTX 2060 Super 8 GB, 32 GB).
- Không giả định có GPU: tính năng cần GPU phải có đường tay chạy được trên máy cũ.
- Kênh "Hay Biết Tuốt": video ngắn tiếng Việt, 9:16, 50 fps, lời đọc tối đa 750 ký tự.

## 3. Luồng sử dụng

1. Chủ dự án nhờ **Claude chat** viết kịch bản theo mẫu `PROMPT-KICH-BAN.md`, nhận về **một khối JSON nháp** (`hbt_draft: 1`).
2. Ở Trang chủ, bấm **Tạo dự án từ JSON nháp**, dán hoặc thả file. App kiểm (K1–K18), hiện lỗi / cảnh báo, rồi tạo dự án và `draft.json`. **Điểm duyệt 1: kịch bản.**
3. Bước **Ảnh**: mỗi cảnh có prompt sẵn + nút Sao chép.
   - Đường tay: tạo ảnh ở Gemini web, thả vào đúng cảnh.
   - Máy mới có ComfyUI: nút tạo ảnh từng cảnh / cả bộ (G4).
   - **Điểm duyệt 2: ảnh** ("đã duyệt ảnh").
4. Bước **Giọng**: VieNeu local cho HBT (chọn giọng một lần, app nhớ), hoặc thả file Vbee như cũ.
5. Nhạc: tự chọn bài khớp `music_mood` trong thư viện, không khớp thì để trống.
6. Xem nhanh → Xuất bản đẹp. **Điểm duyệt 3: video.**

## 4. Quyết định đã chốt

| #   | Chốt                                                                        |
| --- | --------------------------------------------------------------------------- |
| D1  | Kịch bản không gọi API; app nhận JSON nháp                                  |
| D2  | Ảnh: ComfyUI local trên máy mới; máy cũ hoặc ComfyUI không chạy → đường tay |
| D3  | Giọng: thêm VieNeu local cho HBT, giữ Vbee (thả file)                       |
| D4  | Đặc tả → docs (G0) → code (G1–G4)                                           |

Các quyết định kỹ thuật E1–E7 nằm ở `IMPLEMENT-GD2.md`.

## 5. Phạm vi và mốc

| Mốc | Nội dung                                                                    | Máy | Buổi | Tag               |
| --- | --------------------------------------------------------------------------- | --- | ---- | ----------------- |
| G0  | Docs `docs/gd2/`, PLAN §6b, sửa luật push trong `CLAUDE.md`                 | Cũ  | 0,5  | không             |
| G1  | `hbt_draft: 1`, Tạo dự án từ nháp, `draft.json`, kiểm K13–K18, tự chọn nhạc | Cũ  | 1,5  | `v1.11.0`         |
| G2  | Bước Ảnh: prompt từng cảnh, Sao chép, thả ảnh đúng cảnh, "đã duyệt ảnh"     | Cũ  | 1    | gộp với G3        |
| G3  | Giọng VieNeu cho HBT, tiến độ x/N, vẫn thả Vbee                             | Cũ  | 1,5  | `v1.13.0` (G2+G3) |
| G4  | `ImageProvider` ComfyUI, từng cảnh / cả bộ, huỷ được, rẽ đường tay          | Mới | 2    | `v1.14.0`         |

Thứ tự G1 → G2 → G3 → G4.

## 6. Không làm trong GĐ2

- App gọi API kịch bản (Claude / Gemini API).
- Vbee API.
- Tự đăng lên nền tảng.
- Tải ảnh hoặc nhạc từ mạng.
- Cài ComfyUI thay chủ dự án.
- Đổi tham số bản đẹp HBT; sửa `backend/hbt/pipeline/`, `backend/hbt/models.py`, `api/projects.py`.

## 7. Tiêu chí thành công

| #   | Tiêu chí                                                                                                                                                 |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | Dán JSON nháp mẫu (3 cảnh) → dự án có đủ cảnh, thẻ, publish, thumbnail; `draft.json` giữ `topic`, `series_hint`, `music_mood`, `sources`, `image_prompt` |
| S2  | JSON sai (K13–K15) không tạo gì; cảnh báo (K16–K18) vẫn tạo dự án                                                                                        |
| S3  | Máy cũ làm trọn một video HBT bằng đường tay (prompt → Gemini web → thả ảnh → giọng → dựng)                                                              |
| S4  | Máy mới có ComfyUI sinh được ảnh 768×1344 cho từng cảnh; tắt ComfyUI thì tự rẽ đường tay, không lỗi                                                      |
| S5  | Giọng VieNeu cho HBT: `{cách đọc}` đọc chữ trong ngoặc, `                                                                                                | ` nghỉ 0,25 s; lần sau mở app giọng đã chọn được nhớ |
| S6  | `PIPELINE_VERSION` không đổi; `git diff <tag trước> -- backend/hbt/pipeline/ reference/ backend/hbt/models.py backend/hbt/api/projects.py` rỗng          |
| S7  | Không có request ra mạng từ mã app (ComfyUI chỉ `127.0.0.1:8188`)                                                                                        |

## 8. Rủi ro

| Rủi ro                         | Cách giảm                                                                                     |
| ------------------------------ | --------------------------------------------------------------------------------------------- |
| Claude chat xuất JSON sai dạng | Mẫu prompt có ví dụ hợp lệ; bước Kiểm báo dòng:cột (K1)                                       |
| Số liệu bịa                    | `sources[]` bắt buộc dạng; K16 cảnh báo số không có trong nguồn nào; chủ dự án duyệt ở điểm 1 |
| Ảnh có chữ hoặc bản đồ VN      | App nối phần phủ định; K17 cảnh báo từ cấm; duyệt ảnh ở điểm 2                                |
| ComfyUI không chạy / máy cũ    | Đường tay luôn có                                                                             |
| VieNeu đọc sai số / từ mượn    | `{cách đọc}` như Vbee; nghe thử trước khi dựng                                                |
