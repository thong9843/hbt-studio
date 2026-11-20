# HBT STUDIO — ĐẶC TẢ TÁCH BẢN SẮC HÌNH ẢNH (HBT CORE AI 2D + STICKV POLAROID) & NÂNG CẤP DIỄN HOẠT NGƯỜI QUE MƯỢT

## 1. QUY TẮC GIT, VÙNG CẤM & BẢO TOÀN

- **Phân nhánh thực thi (theo quy ước 6 nhánh cố định):**
  - **Phần A (HBT Core):** Làm trên nhánh `GD1-HBT` (bắt buộc đồng bộ `git merge --no-ff main` vào `GD1-HBT` trước khi code để thừa hưởng giao diện VEED & Ponytail mới nhất; **KHÔNG dời tag `v1`**).
  - **Phần B (StickV):** Làm trên nhánh `GD4-StickV` (bắt buộc đồng bộ `git merge --no-ff main` vào `GD4-StickV` trước khi code; **KHÔNG dời tag `v4`**).
  - Cuối ngày (16:00+ VN) mới hợp nhất cả 2 nhánh về `main`.
- **Vùng cấm tuyệt đối (Cấm sửa dù 1 dòng):** `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
- **Môi trường:** Máy cũ Windows `i5-10400`, 16 GB RAM, không GPU rời. Giữ nguyên `FFMPEG_RESOURCE_CLAMP`, dữ liệu local (`library/`, `workspace/`, `assets/`, `brand/`), 2 stash cũ và `AGENTS.md` (Ponytail `full`).
- **Kiểm thử cuối mỗi nhánh (1 lần qua Git Bash):**
  `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`

---

## 2. PHẦN A (`GD1-HBT`) — HBT CORE: TỰ ĐỘNG VẼ 10–12 ẢNH HOẠT HÌNH 2D BẰNG CLOUDFLARE WORKERS AI

### 2.1. Cấu hình khóa an toàn (`.env`, `app_settings.py`, `/settings`)

- Thêm 2 trường tùy chọn vào `AppSettings` (`backend/hbt/app_settings.py`, `config.py`, `.env.example`):
  - `cloudflare_account_id` (`CLOUDFLARE_ACCOUNT_ID`)
  - `cloudflare_api_token` (`CLOUDFLARE_API_TOKEN`)
  - `cloudflare_image_model`: mặc định `"@cf/black-forest-labs/flux-2-klein-4b"` (tùy chọn dự phòng tiết kiệm: `"@cf/black-forest-labs/flux-1-schnell"`).
- Bổ sung thẻ nhập gọn trong `SettingsPage.tsx` (có nút kiểm tra kết nối nhanh & badge trạng thái Đã cấu hình / Chưa cấu hình).

### 2.2. Client sinh ảnh 2D đồng nhất phong cách (`backend/hbt/shared/image_gen/cloudflare_flux.py`)

- **Endpoint Cloudflare:** `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}` (Header `Authorization: Bearer {token}`, timeout `45s`, retry nhẹ `1` lần khi `5xx`).
- **Khóa `Style Anchor` đồng bộ (chất tranh editorial 2D phẳng như video mẫu Đảo Phục Sinh):**
  - Tự động gắn tiền tố phong cách vào `image_prompt` nếu chưa có:
    `"2D flat editorial storybook illustration, crisp dark ink outlines, subtle warm paper grain texture, cohesive muted color palette, clean visual storytelling composition, vertical 9:16, no text, no letters, no watermark."`
- **Tối ưu Neuron & Giữ mạch truyện liền mạch:**
  - Sinh ở kích thước `768×1344` (`9:16`, 4 bước) rồi phóng nét bằng `PIL.Image.Resampling.LANCZOS` lên `1080×1920` (giảm ~45% neuron tiêu thụ, giữ sắc nét tranh 2D).
  - Với `flux-2-klein-4b`: gửi `multipart/form-data`, khóa chung `seed` theo dự án và hỗ trợ truyền ảnh Cảnh 1 làm `input_image_0` (tùy chọn `consistency=True`) để giữ bảng màu & nét vẽ xuyên suốt 10–12 cảnh.
  - Tự động fallback sang `flux-1-schnell` nếu người dùng bật chế độ Tiết kiệm hoặc khi `flux-2-klein-4b` gặp lỗi định dạng.
- **Tích hợp HBT Core API & UI:**
  - Endpoint `POST /api/hbt-core/{slug}/generate-images` (chạy job SSE nền sinh tuần tự 10–12 ảnh, lưu thẳng vào `images/scene-01.png ...`, báo tiến độ từng cảnh `1/12 → 12/12`) và `POST /api/hbt-core/{slug}/scenes/{index}/generate-image` (vẽ lại riêng 1 cảnh).
  - Trên `HbtCoreWorkspace.tsx`: thêm đúng 1 nút gọn **`Tự vẽ ảnh`** (cạnh thanh công cụ kịch bản) và 1 nút nhỏ **`Vẽ lại`** trong từng cảnh (khi chưa nhập key Cloudflare, hiện thông báo dẫn gọn sang `/settings`).

---

## 3. PHẦN B (`GD4-StickV`) — ẢNH TƯ LIỆU POLAROID & DIỄN HOẠT NGƯỜI QUE MƯỢT (TAY CHÂN + KHUÔN MẶT)

### 3.1. Kho Ảnh Tư Liệu Tự Động & Thẻ Ghim Bảng (`Pinned Polaroid Evidence`)

- **Client nguồn ảnh miễn phí (`backend/hbt/shared/online_sources/evidence_images.py`):**
  - **Nguồn 1 — Wikimedia Commons API** (miễn phí 100%, không cần API key, dùng `User-Agent: HBTStudio/1.0`): cực mạnh cho ảnh thật về lịch sử, di tích, giải phẫu, khoa học, thiên văn. Lọc bỏ `.svg`/ảnh quá nhỏ (`< 400px`) và lấy ảnh `.jpg`/`.png` sắc nét.
  - **Nguồn 2 — Pixabay Images API** (tái sử dụng `PIXABAY_API_KEY` đang có): dùng làm nguồn bổ sung cho ảnh đời sống, tâm lý, minh họa.
  - **Cache cục bộ:** Lưu ảnh đã tải vào `library/evidence/<hash>.jpg` (có TTL & giới hạn kích thước) để tái sử dụng không cần gọi mạng lại.
- **Vẽ Thẻ Ảnh Ghim Bảng (`stage.py`):**
  - Giữ nguyên **5 phông nền động** của StickV (không phủ kín nền để tách biệt hoàn toàn với HBT Core).
  - Bổ sung kiểu hiển thị **`evidence_card`** (hoặc tự động kích hoạt khi beat có `evidence_query` / `prop_query` cần ảnh thật): đóng khung ảnh trong **thẻ Polaroid trắng** (viền trắng sạch, đáy thẻ in chú thích ngắn 2–4 từ, ghim đỏ `#D9232E` hoặc miếng băng dính mờ ở cạnh trên, nghiêng nhẹ `-2.5°` hoặc `+2.5°`, bóng đổ mềm), vào/ra bằng hiệu ứng trượt + xoay nhẹ mượt mà `0.35s`.

### 3.2. Nâng Cấp Cử Động Tay Chân Hướng Dẫn / Điều Hướng (Xóa Cứng — `puppet.py`)

Khắc phục cảm giác "cứng, ngoe nguẩy đều theo `sin(t)`" bằng **3 nguyên lý hoạt hình 2D** tính toán trực tiếp bằng NumPy/Pillow (nhẹ CPU):

1. **Độ trễ nối tiếp khớp (Overlapping Action & Follow-Through):**
   - Tách riêng bộ lò xo giảm chấn (_critically damped spring_) cho từng khớp thay vì di chuyển đồng loạt trong 1 frame:
     - Thân (`torso`) dẫn động trước (`t + 0.00s`)
     - Bắp tay (`upper_arm`) theo sau (`trễ 0.04s`)
     - Cẳng tay + bàn tay (`forearm_hand`) theo sau (`trễ 0.09s`, có độ vẫy nhẹ cuối nhịp _follow-through_)
     - Đầu (`head`) và cà vạt (`tie_sway`) trễ nhẹ `0.06s–0.11s`.
   - Thêm bước **lấy đà ngắn (`Anticipation`, `0.08s`)** ngược hướng ~`6°` trước khi thực hiện các động tác chỉ tay hoặc giơ tay mạnh.

2. **Chuyển trọng tâm thân & chân (`Weight Shift & Lower-Body Motion`):**
   - Không để 2 chân đứng đóng đinh bất động: thêm dao động chuyển trọng tâm hông (`hip_sway_x` ±`6–12px`), độ nhún đầu gối tinh tế (`knee_dip_y` khi nhấn trọng âm câu nói), và nghiêng trục thân (`torso_tilt` ±`4°–7°`) hướng về phía bảng minh họa khi nhân vật đang dẫn dắt người xem.

3. **Mở rộng Bộ Cử Chỉ Hướng Dẫn & Điều Hướng (`Presenter / Guide Gestures`):**
   Cập nhật & bổ sung các hành động mang tính **MC hướng dẫn trực tiếp** (vẫn tương thích ngược 100% với 12 tên pose cũ):
   - `guide_sweep`: Tay đưa từ trước ngực mở rộng vòng cung mượt sang hướng bảng minh họa/thẻ Polaroid ("Hãy nhìn vào đây..."), vai hạ tự nhiên, thân hơi xoay mở về phía bảng.
   - `point_precise`: Tay phải nâng có lấy đà nhẹ, khuỷu gập tự nhiên `45°–65°`, bàn tay chỉ đích xác hướng khung bảng; cẳng tay nhấp nhịp nhỏ (`±4°`) ăn khớp các đỉnh trọng âm RMS của giọng nói.
   - `compare_weigh`: Hai cẳng tay gập ngang trước thân, lòng bàn tay hướng lên như cân tiểu ly, lên xuống ngược pha nhau khi so sánh hai vế (`myth_vs_fact` / `versus_split`).
   - `count_step`: Tay giữ trước ngực, cẳng tay đánh nhịp dứt khoát theo từng cụm ý/ngắt hơi (ý 1 → ý 2 → ý 3) thay vì lắc liên tục.
   - `beckon_guide`: Thân hơi rướn nhẹ tới trước, một tay vẫy mời/đưa hướng về phía người xem, tay kia đặt gọn tự nhiên khi dẫn dắt vào điểm mấu chốt.
   - `open_welcome`: Hai tay mở rộng mượt từ trung tâm ra hai bên kèm đầu gật thân thiện cho câu mở đầu (Hook) và kết bài (CTA).

### 3.3. Nâng Cấp Biểu Cảm Khuôn Mặt Sinh Động (`EyeController` & `FaceRig` trong `puppet.py`)

1. **Ánh nhìn chủ động có mục tiêu (Active Gaze & Saccade):**
   - Mắt không nhìn chết 1 chỗ: tự động đảo điểm nhìn mượt (`saccade` nhanh `0.08s`) giữa **Camera (người xem)** $\leftrightarrow$ **Bảng minh họa / Thẻ Polaroid** đúng thời điểm nhân vật đưa tay chỉ hoặc chuyển ý.
   - Hỗ trợ đồng tử/cụm mắt dịch chuyển tinh tế (`±5px` ngang, `±4px` dọc) bên trong vùng đầu trắng (kẹp chặt trong biên an toàn không bao giờ trôi khỏi viền đầu).
2. **Vi biểu cảm & Chuyển trạng thái đàn hồi (Micro-expressions & Elastic Swap):**
   - Khi đổi cảm xúc mắt (`neutral` $\rightarrow$ `shock` / `happy` / `angry`), áp hiệu ứng nảy đàn hồi nhẹ (`scale 0.88 → 1.08 → 1.00` trong `0.14s`) thay vì cắt cứng trong 1 frame.
   - Tự động **nhướn lông mày / phóng nhẹ cụm mắt (`+4%` trục Y)** ở các đỉnh nhấn giọng nói hoặc khi câu thoại kết thúc bằng dấu `?` / `!`.
   - Chớp mắt tự nhiên theo chu kỳ biến thiên giả ngẫu nhiên (`2.6s–4.2s`, đôi khi chớp đôi nhanh _double-blink_ rất có hồn).
3. **Khẩu hình đa sắc thái theo giọng đọc VieNeu-TTS (Multi-level Lip-sync):**
   - Kết hợp cường độ `RMS` và độ biến thiên `delta_rms` để tạo **4 mức khẩu hình mượt**:
     - `env < 0.12`: Miệng khép mỉm cười (`mouth_closed`).
     - `0.12 <= env < 0.30`: Miệng hé nói nhỏ (`mouth_open` co `scale_y=0.55`, `scale_x=0.85`).
     - `0.30 <= env < 0.65`: Miệng nói rõ (`scale_y=0.90`, `scale_x=1.00`).
     - `env >= 0.65`: Nhấn mạnh cảm xúc (`scale_y=1.18`, `scale_x=0.92` — tạo độ mở dọc tự nhiên) kết hợp gật nhẹ đầu ăn khớp trọng âm.

### 3.4. Cập nhật Prompt Gemini & UI StickV

- Cập nhật `backend/hbt/stickv/llm.py` và `models.py` để Gemini tự động chọn các cử chỉ hướng dẫn mới (`guide_sweep`, `point_precise`, `compare_weigh`, `count_step`, `beckon_guide`, `open_welcome`) và điền `evidence_query` (2–4 từ tiếng Anh) cho các beat cần ảnh tư liệu ghim bảng.
- Cập nhật danh sách cử chỉ (nhãn tiếng Việt ngắn gọn, không dấu `...`) trong tab `Hình ảnh` của `StickvPage.tsx` & `vi.ts`.
