# HBT STUDIO — ĐẶC TẢ ĐẠI PHẪU GIAO DIỆN CHUẨN VEED.IO (BRIGHT MINIMALIST STUDIO) & FIX TRIỆT ĐỂ LỖI XUẤT VIDEO / LAG

> **Mục tiêu cốt lõi:** Đập đi xây lại toàn bộ lớp Frontend theo chuẩn **VEED.IO (Sáng · Tinh gọn · Hài hòa · Trực quan)** kết hợp tối ưu kiến trúc React/SSE và sửa dứt điểm 100% lỗi bấm **Xuất bản đẹp StickV** không hiện tiến độ / xoay vòng / treo lag trình duyệt.

---

## 1. BẤT BIẾN HỆ THỐNG & VÙNG CẤM (ZERO-REGRESSION)

- **Vùng cấm tuyệt đối (Không sửa dù 1 dòng):** `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
- **Môi trường & Tài nguyên:** Windows local (`127.0.0.1`, CPU `i5-10400`, không GPU rời). Giữ nguyên `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`), `STICKV_MP4_COMPAT_FLAGS` (`yuv420p -profile:v high -level 4.1 -c:a aac -ar 48000 -movflags +faststart`), chống khóa file `WinError 32`, Watermark `brand/hbt-logo-mark.png` và Outro 4s.
- **Bảo toàn dữ liệu local:** Giữ nguyên toàn bộ `library/`, `workspace/`, `assets/`, `brand/` và 2 stash cũ trên `feat/pv-comments-length`.
- **Ngôn ngữ & Font:** 100% chữ giao diện bằng tiếng Việt đặt trong `frontend/src/i18n/vi.ts`; font `Be Vietnam Pro` local; không cài thư viện animation JS nặng (`framer-motion`, `gsap`, `lottie`).

---

## 2. HẠNG MỤC 0 (ƯU TIÊN SỐ 1): SỬA DỨT ĐIỂM LỖI XUẤT BẢN ĐẸP STICKV & TREO LAG TRÌNH DUYỆT

1. **Triệt tiêu Deadlock Pipe FFmpeg trên Windows (`stickv/render.py`, `cinema/compositor.py`):**
   - Chuyển `stderr=subprocess.PIPE` sang ghi ra tệp tạm `*.ffmpeg.err.log` kết hợp `-nostats -loglevel error` và đăng ký `proc` vào `cancel._procs`.
2. **Kiến trúc `Single-Stream SSE Store` (`useJob.ts`, `RenderJobProvider.tsx`):**
   - Singleton `Map<jobId, EventSource>`: tối đa 1 kết nối cho mỗi `jobId` trên toàn ứng dụng.
   - Throttle cập nhật tiến độ `150ms` cho các sự kiện `progress` liên tiếp trong cùng bước.
   - Tuyệt đối không gọi `invalidateQueries` trong sự kiện `progress` hay khi `EventSource` ngắt tạm thời mà job vẫn đang `running`/`queued`; chỉ gọi `invalidateQueries` đúng 1 lần khi job chuyển trạng thái kết thúc (`done`/`failed`/`cancelled`).
3. **Bảo vệ luồng Worker Backend (`jobs.py`, `stickv/audio.py`):**
   - Phát sự kiện SSE `2.0%` ngay khi tạo job StickV; bọc worker bằng `try ... except BaseException` đảm bảo luôn chuyển `failed` và giải phóng khóa dự án nếu gặp lỗi; tự chuyển sang âm thanh dự phòng nếu `VieNeu-TTS` chưa cài.
   - Kiểm chứng bằng bài test tích hợp thật (`backend/tests/test_stickv_real_render.py`) dùng FastAPI + FFmpeg + `ffprobe` thật (`h264`, `yuv420p`, `48000 Hz`).

---

## 3. HỆ THỐNG THIẾT KẾ MỚI: "HBT VEED-INSPIRED BRIGHT MINIMALIST" (LUẬT 90 · 8 · 2)

| Vai trò Token                  | Bright Studio (Mặc định) | Quiet Dark (Chế độ Tối)  | Quy tắc sử dụng                                      |
| :----------------------------- | :----------------------- | :----------------------- | :--------------------------------------------------- |
| `--bg` / `--bg-app`            | `#F7F8FA`                | `#0E1015`                | Nền tổng thể không gian làm việc                     |
| `--card` / `--bg-surface`      | `#FFFFFF`                | `#151821`                | Sidebar, Topbar, Thẻ nội dung, Inspector             |
| `--soft` / `--bg-subtle`       | `#F1F3F6`                | `#1C202B`                | Ô nhập liệu, nền hover nhẹ                           |
| `--bg-canvas`                  | `#ECEFF4`                | `#090B0F`                | Vùng bàn dựng bao quanh khung xem trước video        |
| `--line` / `--border-subtle`   | `#E6E8EE`                | `rgba(255,255,255,0.08)` | Viền mảnh `1px` sắc nét                              |
| `--text` / `--text-primary`    | `#111318`                | `#F4F6FA`                | Tiêu đề, chữ nội dung chính (WCAG >= 12:1)           |
| `--muted` / `--text-secondary` | `#5E6675`                | `#96A0B2`                | Nhãn phụ, mô tả ngắn (WCAG >= 5.0:1)                 |
| `--brand` / `--accent-primary` | `#D9232E`                | `#D9232E`                | Nút CTA chính (`Xuất video`, `Tạo mới`), điểm active |
| `--accent-soft`                | `#FDF2F2` (`#B91C1C`)    | `#2D1418` (`#FCA5A5`)    | Nền pill trạng thái / mục menu đang chọn             |
| `--primary` / `--ink-action`   | `#111318` (`#FFFFFF`)    | `#F4F6FA` (`#111318`)    | Nút hành động thứ cấp sang trọng chuẩn VEED          |

---

## 4. KIẾN TRÚC THÔNG TIN TINH GỌN (`StudioShell.tsx`)

- **Sidebar tự động thu gọn thành Icon Rail** khi bước vào Không gian Dựng phim (`/stickv`, `/core`, `/postv`, `/chatting`).
- **Topbar 56px (`StudioTopBar.tsx`):** Quay lại · Huy hiệu động cơ · Tên dự án · Chọn tỷ lệ `9:16 | 16:9` · Xem nhanh · Nút **`Xuất video`** mở **`ExportPopover.tsx`** (gom gọn Độ phân giải, Watermark HBT, Outro 4s, Xem nhanh / Xuất bản đẹp và Live Progress View).
- **Cột công cụ trái chia 3–4 Tab rõ ràng:** Tại một thời điểm chỉ hiện duy nhất 1 nhóm chức năng và chỉ mount form chỉnh sửa cho **duy nhất 1 cảnh/beat đang chọn** (giảm >80% phần tử DOM và nút bấm lộ thiên).
- **Sân khấu Xem trước trung tâm (`StageCanvas.tsx`)** & **Dải phân cảnh ngang ở đáy (`SceneTimelineStrip.tsx`)** memo hóa từng thẻ cảnh.
