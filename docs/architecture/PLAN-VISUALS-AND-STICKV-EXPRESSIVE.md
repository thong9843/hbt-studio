# HBT STUDIO — ĐẶC TẢ PHẦN B (`GD4-StickV`): ẢNH TƯ LIỆU POLAROID & DIỄN HOẠT NGƯỜI QUE MƯỢT

## 1. Phạm vi & Quy tắc bảo toàn

- **Nhánh thực thi:** `GD4-StickV` (đồng bộ `main` bằng `git merge --no-ff main`, giữ nguyên tag `v4`).
- **Vùng cấm:** `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
- **Bảo toàn:** `library/`, `workspace/`, `assets/`, `brand/`, `.env`, 2 stash cũ, `FFMPEG_RESOURCE_CLAMP` và `STICKV_MP4_COMPAT_FLAGS`.

## 2. Kho Ảnh Tư Liệu Tự Động & Thẻ Polaroid Ghim Bảng (`pinned_photo`)

- **Module:** `backend/hbt/shared/online_sources/reference_images.py` (cache cục bộ `library/reference_images/`):
  1. **Wikimedia Commons API** (`commons.wikimedia.org/w/api.php`, `User-Agent: HBTStudio/1.0`, 0 API key): lọc JPEG/PNG kích thước `>= 300px`.
  2. **Pixabay Images API** (tái sử dụng `PIXABAY_API_KEY`, `image_type=illustration` fallback `all`, `safesearch=true`).
  3. **Fallback:** `iconify_props.py` khi không tìm được ảnh phù hợp.
- **Sân khấu (`stage.py`):**
  - Kiểu bảng `pinned_photo`: khung Polaroid trắng `#FFFFFF`, bóng đổ mềm, chú thích ngắn 3–6 từ ở mép dưới, đinh ghim đỏ `#D9232E` hoặc băng dính mờ ở đỉnh, nghiêng nhẹ `±2.2°`, đặt trên 5 phông nền động sẵn có (không phủ kín nền), vào/ra mượt `0.35s` cubic ease-out.
- **API & UI (`api/stickv.py`, `StickvPage.tsx`):**
  - Endpoint tìm ảnh tư liệu `GET /api/stickv/reference-images/search` và gán nhanh ảnh cho beat `POST /api/stickv/{slug}/beats/{beat_id}/reference-image`.
  - Nút gọn **`Đổi ảnh`** trong tab `Hình ảnh` của `StickvPage.tsx`.

## 3. Diễn Hoạt Tay Chân Hướng Dẫn & Biểu Cảm Khuôn Mặt (`puppet.py`)

- **Động học liên khớp có độ trễ tự nhiên (Follow-through & Arcs):**
  - `Torso Lean (lead)` → `Head (+1–2 frames)` → `Shoulder (+2 frames)` → `Elbow/Forearm (+4 frames)` với lò xo giảm chấn nhẹ tạo overshoot/settle `8–12%`.
  - **Weight Shift:** dao động thân/hông `±4–7px`, nghiêng thân `±3.5°`, nhún gối `1.5–2.5%` trong khi chân vẫn bám chặt mặt đất; nhịp bước và đánh tay mượt ở `walk_explore`.
- **6 cử chỉ hướng dẫn & điều hướng mới** (tương thích ngược toàn bộ preset & alias cũ):
  - `guide_sweep_board`, `guide_two_sides`, `guide_step_count`, `guide_zoom_focus`, `welcome_open`, `lean_curious`.
- **Biểu cảm khuôn mặt & Lip-Sync 4 mức:**
  - **Prosody Micro-Brows:** nhướng cụm mắt/mày `2–3px` (scale `1.04x`) khi `env > 0.65`.
  - **Gaze Target:** dịch cụm mắt `+5px` hướng lên bảng khi làm cử chỉ hướng dẫn, quay lại nhìn khán giả ở cuối câu.
  - **Chớp mắt biến thiên tự nhiên** chu kỳ `2.4s – 4.2s`.
  - **6 `face_mood`:** `explaining`, `curious`, `excited`, `skeptical`, `shocked`, `warm_cta`.
  - **Lip-Sync 4 mức:** `closed` (`< 0.12`), `narrow` (`0.12–0.32`), `medium` (`0.32–0.60`), `wide_emphasis` (`> 0.60`, Squash & Stretch).
