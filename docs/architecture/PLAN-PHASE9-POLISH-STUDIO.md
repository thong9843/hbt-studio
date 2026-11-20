# HBT STUDIO — ĐẶC TẢ GIAI ĐOẠN 9: TRIỆT TIÊU KHỰNG VOICE/VIDEO, BẢNG TRI THỨC CHUẨN MỰC, PERSISTENT JOB STICKV & GIAO DIỆN PRO CRAFT

> **Mục tiêu:** Giải quyết dứt điểm 100% các lỗi thực chiến phát hiện qua nghiệm thu `video_1.mp4` và ảnh UI thực tế:
>
> 1. Khôi phục tiến độ render StickV liên tục khi chuyển trang qua lại (`Persistent SSE Reconnect`).
> 2. Nâng tầm giao diện lên chuẩn **HBT Studio Pro Craft** với custom controls (thay toàn bộ `<select>` gốc), sửa vỡ màu Dark Mode ở `WatermarkControl`, và hệ thống micro-animations GPU-composited (`0%` CPU khi rảnh, không lag).
> 3. Triệt tiêu tận gốc lỗi khựng giọng/khựng hình đầu beat, tiếng thừa bị cắt cụt, mất âm đầu câu, dính chữ Karaoke, lộ markdown `**...**`, bảng thưa chữ/lặp lời thoại và lặp bảng tóm tắt cuối video.

---

## 1. BẤT BIẾN HỆ THỐNG & VÙNG CẤM

- **Vùng cấm tuyệt đối (Cấm sửa dù 1 dòng):** `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
- **Môi trường & Tài nguyên:** Windows local (`i5-10400`, không GPU rời). Giữ nguyên `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`), `STICKV_MP4_COMPAT_FLAGS` (`yuv420p -profile:v high -level 4.1 -c:a aac -ar 48000 -movflags +faststart`), chống khóa file `WinError 32`, Watermark HBT và Outro 4s.
- **Bảo toàn dữ liệu local:** Giữ nguyên `library/`, `workspace/`, `assets/` và 2 stash cũ trên `feat/pv-comments-length`.
- **Ngôn ngữ & Font:** Mọi nhãn giao diện bằng tiếng Việt trong `frontend/src/i18n/vi.ts`; không cài thêm thư viện animation JS nặng (`framer-motion`, `gsap`, `lottie`).
- **Kiểm thử cuối đợt (duy nhất 1 lần qua Git Bash):**
  `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`

---

## 2. HẠNG MỤC 1: KHÔI PHỤC TIẾN ĐỘ RENDER STICKV KHI CHUYỂN TRANG (`PERSISTENT JOB SYNC`)

### 2.1. Backend (`backend/hbt/jobs.py`, `backend/hbt/api/render.py`, `backend/hbt/api/stickv.py`)

- Đảm bảo mọi job StickV (cả `preview`, `final`, lẫn `cinema_full`) khi `submit` đều lưu đầy đủ metadata chuẩn trong `Job`: `kind="stickv"`, `slug=<project_slug>`, `mode="preview"|"final"`, `progress` (`0..100`), `stage` (nhãn tiếng Việt từng pha: _Sinh giọng VieNeu-TTS_, _Căn chỉnh & Kiểm định_, _Dựng khung hình_, _Trộn âm thanh -14 LUFS_, _Ghép Outro & Hoàn tất_), `current_beat`, `total_beats`, `started_at`.
- Đảm bảo `GET /api/jobs` trả về danh sách job đang chạy (`running`) / đang chờ (`queued`) và `GET /api/jobs?include_recent=true` trả kèm các job hoàn tất gần nhất (`done`/`failed`/`cancelled`), đầy đủ `slug`, `kind`, `mode`, `progress`, `stage`, `current_beat`, `total_beats`, `started_at`, `output`.

### 2.2. Frontend (`RenderJobProvider.tsx`, `GlobalJobDock.tsx`, `StickvPage.tsx`)

- **Tự động nhận diện & nối lại SSE khi quay về `/stickv`:**
  - Ngay khi `StickvPage.tsx` mount (hoặc khi người dùng chọn/đổi dự án `slug`), tự động truy vấn trạng thái từ `RenderJobProvider` + gọi `GET /api/jobs?include_recent=true` tìm job có `kind === "stickv"` (khớp `slug` hiện tại hoặc job StickV đang `running`/`queued` gần nhất).
  - Nếu có job đang chạy/chờ: **tự động khôi phục ngay giao diện thanh tiến độ chi tiết + nối lại luồng SSE `/api/jobs/{job_id}/events`**, khóa chống bấm đúp nút `Xuất bản đẹp`, hiển thị đúng % + tên bước + beat hiện tại + thời gian ước tính + nút `Hủy dựng`.
  - Nếu job vừa hoàn tất (`done`) trong lúc người dùng đang ở trang khác: ngay khi quay lại `/stickv`, tự động nạp lại danh sách render mới nhất và hiển thị video thành phẩm sẵn trong trình phát kèm toast thông báo.
- **Tăng cường `GlobalJobDock.tsx`:** Khi có job StickV đang chạy và người dùng đang đứng ở trang khác (`/`, `/library`, `/core`...), Dock góc dưới phải luôn hiện tiến độ sống + nút bấm **"Xem tiến trình StickV"** nhảy thẳng về đúng dự án `/stickv?slug=<slug>`.

---

## 3. HẠNG MỤC 2: NÂNG CẤP GIAO DIỆN "HBT STUDIO PRO CRAFT" (ĐẸP, CHI TIẾT & 0% LAG)

### 3.1. Luật Hiệu Năng Bắt Buộc (Zero-Lag Guarantee)

- **Chỉ dùng CSS thuần (`transform`, `opacity`, `background-color`, `border-color`, `color`)**, thời lượng `120ms–220ms`, đường cong `cubic-bezier(0.22, 1, 0.36, 1)`.
- **Cấm tuyệt đối:** `backdrop-filter: blur()` trên vùng lớn, `box-shadow` animate theo frame, animation vô hạn khi trang rảnh (`CPU = 0%` ở trạng thái nghỉ), hoặc thêm dependency ngoài cho animation.
- **Tôn trọng người dùng:** `@media (prefers-reduced-motion: reduce)` tắt toàn bộ `transform`/chuyển động.

### 3.2. Thay Thế Toàn Bộ Controls Thô & Sửa Vỡ Dark Mode

1. **Tạo component `frontend/src/components/ui/StudioSelect.tsx`:**
   - Thay thế **100% thẻ `<select>` gốc của trình duyệt** trong `StickvPage.tsx`, `HbtCoreWorkspace.tsx`, `PostvQuickPage.tsx`, `ChattingHome.tsx`, `ChattingEditor.tsx`, `SettingsPage.tsx`, `WatermarkControl.tsx`, `AssetHubPage.tsx`.
   - Thiết kế: Nền bề mặt nâng cao (`--bg-elevated`), viền `1px` sắc nét, focus ring tinh tế, mũi tên chevron xoay mượt `180°`, bảng menu bo góc `12px` mở theo hiệu ứng `opacity 0->1` + `translateY(-4px)->0` + `scale(0.98)->1` (`140ms`), hỗ trợ icon/mô tả phụ cho từng option, điều hướng đầy đủ bàn phím (`ArrowUp/Down`, `Home/End`, `Enter`, `Space`, `Escape`) và đóng khi click ngoài.
2. **Tạo component `frontend/src/components/ui/SegmentedControl.tsx`:**
   - Thanh chọn dạng viên thuốc trượt mượt (sliding active thumb bằng `transform: translateX()`) cho các lựa chọn ngắn: Tỷ lệ khung hình (`9:16` / `16:9`), Thời lượng (`1p` / `3p` / `5p` / `8p` / `10p`), Tab chế độ.
3. **Sửa triệt để `WatermarkControl.tsx`:**
   - Loại bỏ hoàn toàn nền trắng/tím nhạt chói gắt khi đang ở Dark Mode (`data-theme="dark"`): dùng hệ token bề mặt thích ứng 2 chế độ (`--surface-card` + viền hairline `--border-subtle`).
   - Đổi badge trạng thái sang **pill badge bo tròn `999px`** (`--wm-badge-bg`, `--wm-badge-border`, `--wm-badge-text`) 1 dòng gọn gàng.
4. **Nâng cấp Hệ Thống Nút & Thẻ (`tokens.css`, `ui.css`, `Button.tsx`):**
   - **Hệ bề mặt 3 tầng phân cấp rõ ràng:**
     - Dark Studio (`#0A0D14` nền tổng → `#111622` thẻ chính → `#182032` khối nổi/input, viền `rgba(255,255,255,0.08)` kèm cạnh sáng trên `inset 0 1px 0 rgba(255,255,255,0.05)`).
     - Light Studio (`#F4F6FA` nền tổng → `#FFFFFF` thẻ chính → `#F8FAFC` khối nổi, viền `rgba(15,23,42,0.09)` + bóng đổ đa tầng siêu nhẹ).
   - **Nút hành động chính (Primary Export / Magic AI):** Bo góc `12px` sắc sảo, viền sáng trên `1px`, hover nâng `-1.5px` kèm **vệt sáng sheen chạy 1 lượt duy nhất** chỉ kích hoạt trên `:hover`, bấm xuống `scale(0.985)` chắc tay.
   - **Nút phụ & Khối công tắc (Outro 4s, Watermark):** Dùng công tắc gạt (`Switch`) thay cho ô checkbox vuông nhỏ.
   - **Kiểm chứng WCAG:** Cập nhật `tokens.test.ts` xác nhận mọi cặp màu chữ/nền ở cả Light & Dark đều đạt `>= 4.5:1`.

---

## 4. HẠNG MỤC 3: TRIỆT TIÊU KHỰNG GIỌNG/HÌNH, DÍNH CHỮ KARAOKE, LỘ `**...**` & NÂNG CẤP ĐỘ ĐẦY ĐẶN BẢNG TRI THỨC

### 4.1. Sửa Tận Gốc Lỗi Khựng Giọng Đọc & Mất Âm Đầu (`audio.py` & `audio_director.py`)

1. **Tiền xử lý văn bản (`sanitize_tts_text`):** Xóa sạch markdown (`**`, `__`, `` ` ``, `#`), chuẩn hóa dấu câu, không chia câu vụn `< 5` từ thành lượt TTS độc lập.
2. **Envelope + ZCR Gate (`clean_tts_wav`):** Giữ `pre_roll_ms = 35 ms`, `post_roll_ms = 75 ms`, loại bỏ xung nhiễu đuôi tách biệt `< 80ms` sau khoảng lặng `>= 220ms`, áp cosine fade-in `18 ms` và fade-out `25 ms`.
3. **AAC Priming Guard & Nhịp thở:** Chèn `global_lead_s = 0.18s` đầu video, `200ms` giữa các câu trong beat, `240ms` cuối beat, BGM liên tục ducking `attack=25ms, release=220ms`, chuẩn đầu ra `48000 Hz` stereo.

### 4.2. Sửa Lỗi Khựng Hình Đầu Beat & Khóa Đồng Bộ A/V Tuyệt Đối (`stage.py`, `render.py`)

- **Đồng hồ audio tích lũy (`allocate_beat_frame_counts`):** `end_frame_i = round(cumulative_audio_sec * fps)`, tổng lệch hình-tiếng `<= 1 frame`.
- Chuyển bảng vào mượt (`0.30s`, `+18px -> 0` theo `ease_out_cubic`), thoát mượt (`0.22s`, `-14px`), giữ nguyên bảng khi 2 beat cuối chia sẻ cùng 1 `recap_card`.

### 4.3. Sửa Lỗi Dính Chữ Karaoke & Lộ Dấu Sao Markdown `**...**` (`stage.py`, `shots.py`)

- Thống nhất `parse_rich_spans` / `draw_rich_text_line` / `_draw_rich_wrapped_text` cho toàn bộ mẫu thẻ (0% lọt `**` thô).
- Tính trước `pad_x = 12px` và `space_w >= 14px` trong `compute_karaoke_word_boxes` -> khoảng hở giữa hộp highlight và từ kế cận luôn `>= 10px`.

### 4.4. Nâng Cấp Độ Đầy Đặn & Luật Anti-Parrot (`llm.py`, `stage.py`, `preflight.py`)

- Hạ ngưỡng Anti-Parrot xuống `<= 0.55` trên cả `board_title` và từng `item`.
- Nâng mật độ `myth_vs_fact` / `comparison` / `bullets` / `flow_steps`, hiển thị dải Quote/Keyword nổi bật ở vùng trên khi `closeup_react`, và khóa **duy nhất 1 `recap_card` nhất quán** cho 1–2 beat tổng kết/CTA cuối video.

---

## 5. KẾ HOẠCH 4 COMMIT & CỔNG KIỂM TOÁN ĐỐI KHÁNG NEON ↔ HYDROGEN

| #      | Commit                                                                                                           | Phạm vi File                                                                                                                                                                                              |
| :----- | :--------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **C1** | `feat(stickv-audio-smooth): eliminate TTS onset clipping, ghost tail, clicks & lock A/V sync`                    | `backend/hbt/stickv/audio.py`, `backend/hbt/stickv/render.py`, `backend/hbt/cinema/audio_director.py`, `backend/tests/test_stickv_audio_smooth.py`, `backend/tests/test_stickv_stage.py`                  |
| **C2** | `feat(stickv-boards-rich): fix raw markdown leak, karaoke spacing, rich board density & single recap`            | `backend/hbt/stickv/stage.py`, `backend/hbt/stickv/llm.py`, `backend/hbt/cinema/shots.py`, `backend/hbt/cinema/preflight.py`, `backend/tests/test_stickv_stage.py`, `backend/tests/test_stickv_models.py` |
| **C3** | `feat(stickv-job-persist): restore live StickV render progress across route changes`                             | `backend/hbt/jobs.py`, `backend/hbt/api/render.py`, `frontend/src/components/RenderJobProvider.tsx`, `frontend/src/components/layout/GlobalJobDock.tsx`, `frontend/src/pages/StickvPage.tsx`, tests       |
| **C4** | `feat(ui-pro-craft): custom StudioSelect, SegmentedControl, Dark Mode Watermark fix & zero-lag micro-animations` | `StudioSelect.tsx`, `SegmentedControl.tsx`, `Button.tsx`, `ui.css`, `tokens.css`, `WatermarkControl.tsx`, studio pages, `i18n/vi.ts`, `tokens.test.ts`, `StudioSelect.test.tsx`, spec archive             |
