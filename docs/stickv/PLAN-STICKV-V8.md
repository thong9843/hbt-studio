# HBT STUDIO — KẾ HOẠCH KIẾN TRÚC & TRIỂN KHAI `STICKV` v8 (LONG-FORM & ARTICULATED PUPPET)

> **Tài liệu đặc tả dành cho Agent thực thi (Antigravity):** Đọc kỹ toàn bộ kế hoạch này cùng `CLAUDE.md`, `GEMINI.md` và trạng thái hiện tại trên nhánh `feat/stickv-v7-automation` trước khi sửa mã nguồn.
> **Mục tiêu cốt lõi:** Khắc phục triệt để 3 điểm nghẽn của bản thử nghiệm 45s (tay gậy cứng đờ chỉ nhún lên xuống, còn khúc cắt & khoảng trống màn hình, chưa đáp ứng video khám phá cổ đại dài 5–10 phút), đồng thời bổ sung cấu hình **`VOICEMOD_TUNA_API_KEY`** vào `.env.example`, trang Cài đặt và cổng tìm kiếm SFX.

---

## 0. RÀNG BUỘC BẤT BIẾN & QUY TRÌNH LÀM VIỆC

1. **Vùng cấm tuyệt đối:** Không sửa `backend/hbt/pipeline/`, `backend/hbt/models.py` (gốc), `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
2. **Bảo toàn các tính năng đã nghiệm thu:**
   - Giữ nguyên `FFMPEG_RESOURCE_CLAMP` (`-threads 2`) cho CPU `i5-10400`.
   - Giữ nguyên `STICKV_MP4_COMPAT_FLAGS` (`-c:v libx264 -pix_fmt yuv420p -profile:v high -level 4.1 -c:a aac -b:a 192k -ar 48000 -movflags +faststart`) để tương thích 100% Windows Media Player.
   - Giữ nguyên cơ chế chống khóa file `WinError 32` (`releaseVideoElementLocks` + `deleted_renders.json`), Watermark (`brand/hbt-logo-mark.png`), và Outro 4s (`@HayBietTuot`) cho cả `9:16` và `16:9`.
3. **Quy trình Kickoff & Kiểm thử Windows:**
   - **Bước 1 (Review trước):** Khi nhận lệnh `kickoff`, chỉ rà soát repo, xuất Bảng kế hoạch (Commit | File thêm/sửa | Test nhanh | Ước lượng dòng) và chờ chủ dự án duyệt rồi mới code.
   - **Kiểm thử nhanh cuối đợt (duy nhất 1 lần qua Git Bash):**
     `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`

---

## 1. BỔ SUNG CẤU HÌNH VOICEMOD TUNA API KEY (`.env.example` & `/settings`)

1. **Cập nhật `.env.example`:**
   - Thêm biến `VOICEMOD_TUNA_API_KEY=` ngay cạnh `PIXABAY_API_KEY=` và `FREESOUND_API_KEY=` kèm chú thích hướng dẫn dùng cho tìm & tải Meme SFX trong `/library`.
2. **Cập nhật Backend (`config.py`, `app_settings.py`, `asset_hub.py`, `shared/online_sources/`):**
   - Thêm `voicemod_tuna_api_key: str = ""` vào `Settings` và `AppSettingsStore` (`workspace/settings.json`), hỗ trợ `resolve_online_api_key("tuna")` đọc động đè `.env` rỗng ngay khi lưu từ `/settings` (không cần khởi động lại server) và xóa `_ONLINE_SEARCH_CACHE`.
   - Cập nhật client Voicemod Tuna trong `backend/hbt/shared/online_sources/` để gửi header xác thực (`x-api-key` / `Authorization: Bearer {key}`) khi người dùng đã nhập `VOICEMOD_TUNA_API_KEY` (vẫn giữ fallback công khai nếu để trống).
3. **Cập nhật Frontend (`SettingsPage.tsx`, `i18n/vi.ts`):**
   - Thêm ô nhập **Voicemod Tuna API Key** kèm badge trạng thái **`Đã cấu hình` / `Chưa cấu hình`** đồng bộ với Pixabay và Freesound.

---

## 2. NÂNG CẤP XƯƠNG TAY 2 ĐOẠN (KHỚP KHUỶU TAY) & 12 HÀNH ĐỘNG (`puppet.py`)

### 2.1 Tách Khớp Khuỷu Tay Tự Động (`auto_segment_puppet` v2)

- Nâng phiên bản cache phân mảnh lên `SEG_CACHE_VERSION = "v2_elbow"` trong `assets/stickman/puppet/.segments/` để tự động tách lại từ `base_character.png` hiện có.
- Từ mỗi cánh tay (`arm_left`, `arm_right`), xác định trục chính từ tâm vai (`shoulder_pivot`) tới đầu bàn tay găng trắng (`hand_tip`) và chia tại mốc **`52%` chiều dài** thành 2 lớp RGBA độc lập:
  1. **`upper_arm_left` / `upper_arm_right`:** Phần bắp tay đen xoay quanh **`shoulder_pivot`**.
  2. **`forearm_left` / `forearm_right`:** Phần cẳng tay đen + bàn tay găng trắng xoay quanh **`elbow_pivot`** (gắn tại đầu mút dưới của `upper_arm` sau khi đã xoay vai).
- **Vá khớp tròn kép (`#0B0E14`):** Vẽ hình tròn đặc màu đen mực (bán kính `0.52 * độ dày nét tay`) tại cả **`shoulder_pivot`** lẫn **`elbow_pivot`** để khi cánh tay gập góc nhọn (`-118°`) nét vẽ luôn liền khối, không bao giờ hở khe trắng hay gãy khúc.

### 2.2 Thư viện 12 Hành Động Có Ngữ Nghĩa Kể Chuyện (`POSE_PRESETS`)

Mỗi hành động điều khiển đồng bộ `(shoulder_L, elbow_L, shoulder_R, elbow_R, head_deg, torso_deg, dy_px, eye_override, eye_gaze)` qua bộ lọc lò xo giảm chấn tới hạn (`_SpringChannel`) + nội suy mượt `0.45s`:

| Tên hành động (`pose`) | Mô tả tư thế & ngữ cảnh sử dụng                | Động học khớp (Vai · Khuỷu · Đầu · Thân)                                                                                                                                   |
| :--------------------- | :--------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`point_up`**         | Giơ tay chỉ thẳng lên bảng minh họa            | Vai phải `-48°`, khuỷu phải gập `-58°` chỉ lên trên; tay trái thả tự nhiên `12°`; đầu nghiêng `-6°` nhìn lên bảng (`gaze: 0, -4`).                                         |
| **`think_chin`**       | Vắt tay lên cằm suy nghĩ / đặt nghi vấn        | Tay trái gập ngang ngực đỡ khuỷu (`shoulder -28°, elbow -68°`); tay phải gập ngược đưa găng tay chạm cằm (`shoulder 18°, elbow -118°`); đầu nghiêng `+9°` (`gaze: 3, -3`). |
| **`arms_crossed`**     | Khoanh tay trước ngực phân tích / phản biện    | Hai vai khép nhẹ (`±22°`), hai cẳng tay gập chéo ngang ngực (`L: +78°, R: -78°`); thân thẳng vững vàng.                                                                    |
| **`hands_on_hips`**    | Chống nạnh tự tin khẳng định kết luận          | Hai vai mở ngang (`±34°`), hai khuỷu gập ngược chống vào hông (`L: -72°, R: +72°`).                                                                                        |
| **`shrug_ask`**        | Nhún vai dang hai tay đặt câu hỏi tu từ        | Vai nhún lên (`dy: -4px`), hai bắp tay mở `±28°`, hai cẳng tay xòe ra ngoài (`L: -48°, R: +48°`); đầu nghiêng nhẹ `±7°`.                                                   |
| **`present_board`**    | Một tay chống hông, tay kia xòe giới thiệu     | Tay trái chống hông (`30°, -68°`); tay phải mở rộng (`-38°, -24°`) vung nhẹ theo nhịp RMS giọng nói.                                                                       |
| **`emphatic_chop`**    | Chặt/nhấn nhịp cẳng tay theo từ khóa           | Cẳng tay phải đánh nhịp dứt khoát (`elbow: -65° -> -15°`) khớp đỉnh RMS khi nhấn số liệu/sự thật.                                                                          |
| **`shock_hands_up`**   | Giơ hai tay lên cạnh đầu ngạc nhiên / sốc      | Hai vai nâng cao (`±52°`), hai khuỷu gập hướng về đầu (`L: -62°, R: +62°`), mắt `eyes_shock`, nảy nhẹ `-18px` trong `0.4s` đầu.                                            |
| **`lean_secret`**      | Nghiêng người đưa tay cạnh miệng bật mí bí mật | Thân nghiêng tới `+4.5°`, cẳng tay phải gập `-105°` đặt cạnh miệng thì thầm, mắt liếc ngang (`gaze: 5, 0`).                                                                |
| **`count_points`**     | Đếm từng luận điểm trên bàn tay                | Cẳng tay trái đưa ngang ngực (`-15°, -75°`), cẳng tay phải gõ nhịp đếm (`elbow: -55° -> -25°`) theo từng ý.                                                                |
| **`walk_explore`**     | Đánh tay sải bước dẫn dắt hành trình khám phá  | Hai tay đánh chéo trước–sau ngược pha (`±24°`) kết hợp nhịp bước `abs(sin(3.4t)) * 5px`.                                                                                   |
| **`idle_breathe`**     | Đứng thở tự nhiên khi chuyển ý                 | Tay buông lỏng tự nhiên (`±14°`, khuỷu `±12°`), thở phồng nhẹ `scale_y ±1.2%`.                                                                                             |

---

## 3. SÂN KHẤU LIỀN MẠCH KHÔNG KHÚC CẮT & PHỦ KÍN 100% MINH HỌA (`stage.py`, `audio.py`)

1. **Phủ kín 100% thời lượng (Xóa bỏ nửa trên màn hình trống trơn):**
   - Mọi beat đều phải hiển thị nội dung minh họa ở vùng sân khấu (`StageZone`). Nếu beat có `board_type == "none"`, `stage.py` tự động tạo **Thẻ Minh Họa Tự Động** gồm: Icon màu lớn tải từ **Iconify API** (`prop_query` hoặc từ khóa trích xuất tự động từ câu thoại) + cụm từ khóa nổi bật + thanh tiến trình chương hiện tại.
   - Bổ sung 3 mẫu đồ họa chuyên dụng cho chủ đề **Khám phá cổ đại & Khoa học**:
     - `timeline_era`: Trục thời gian phát sáng kèm mốc niên đại (ví dụ: `2560 TCN`, `66 Triệu Năm Trước`) và sự kiện.
     - `location_map`: Thẻ bản đồ tọa độ / la bàn định vị địa danh cổ đại kèm icon di tích.
     - `myth_vs_fact`: Thẻ đối chiếu 2 tầng (`LẦM TƯỞNG` đỏ vs `SỰ THẬT` vàng/xanh ngọc).
2. **Chuyển tiếp mượt 100% (Zero Hard-Cut):**
   - Mọi thẻ minh họa vào sân khấu bằng `slide_up (28px) + scale (0.94 -> 1.0) + fade_in (0.35s ease_out_cubic)` và rời sân khấu bằng `slide_up (-18px) + fade_out (0.30s ease_in_cubic)`.
   - Nếu 2 beat liên tiếp dùng cùng thẻ chủ đề (`board_title` trùng nhau), giữ nguyên khung thẻ ngoài và chỉ `cross-fade (0.25s)` phần chữ/số liệu bên trong.
3. **Nhịp kể liên tục (`audio.py` & Karaoke):**
   - Rút ngắn khoảng nghỉ nhân tạo trong `_assemble_padded_beat_wav` xuống mức tự nhiên như người kể chuyện: `lead_pad = 0.06s`, `inter_sentence_pad = 0.16s`, `tail_pad = 0.14s`.
   - Khung phụ đề Karaoke giữ nền mờ ổn định qua các khoảng ngắt hơi ngắn (`<= 0.22s`), không nhấp nháy tắt bật liên tục.

---

## 4. GÓC MÁY ẢO (_VIRTUAL CAMERA_) & KHỔ KHUNG HÌNH `9:16` / `16:9` (`stage.py`, `render.py`, `StickvPage.tsx`)

1. **Hỗ trợ 2 tỷ lệ khung hình (`aspect_ratio: Literal["9:16", "16:9"] = "9:16"`):**
   - **`9:16` (`1080×1920` — Shorts/TikTok/Reels):** Vùng minh họa nửa trên (`y: 9% -> 51%`), Karaoke (`y: 57%`), Stickman (`x: 50%, y: 78%`).
   - **`16:9` (`1920×1080` — YouTube Khám phá dài 5–10 phút):** Stickman đứng bên trái (`x: 22%, y: 82%, cao 64%`), sân khấu minh họa màn ảnh rộng bên phải (`x: 38% -> 94%, y: 12% -> 76%`), Karaoke ở cạnh dưới (`y: 86%`). Outro 4s tự chọn đúng bản `9:16` hoặc `16:9`.
2. **3 Góc Máy Ảo (`camera_shot: Literal["wide_stage", "focus_board", "closeup_react"] = "wide_stage"`):**
   - Nội suy mượt `(zoom, pan_x, pan_y)` trong `0.55s` (`ease_in_out_cubic`) khi đổi beat:
     - `wide_stage` (`zoom = 1.00`): Toàn cảnh cân đối nhân vật và minh họa.
     - `focus_board` (`zoom = 1.15`): Phóng nhẹ vào bản đồ/biểu đồ/di vật trong khi Stickman lùi về góc chỉ tay (`point_up`).
     - `closeup_react` (`zoom = 1.28`): Cận cảnh biểu cảm Stickman khi đặt câu hỏi tu từ (`shrug_ask`, `think_chin`) hoặc tung bí mật (`lean_secret`, `shock_hands_up`).

---

## 5. KIẾN TRÚC VIDEO DÀI 5–10 PHÚT ĐA CHƯƠNG & RENDER PHÂN ĐOẠN (`llm.py`, `render.py`, `StickvPage.tsx`)

1. **Chọn Thời lượng Mục tiêu (`target_duration_min: Literal[1, 3, 5, 8, 10] = 1`):**
   - `1 phút` (`8–12` beats) · `3 phút` (`22–28` beats) · `5 phút` (`36–45` beats) · `8 phút` (`56–68` beats) · `10 phút` (`70–85` beats).
2. **Sinh Kịch Bản Đa Chương 2 Tầng (`llm.py`):**
   - Với video `3–10 phút`, Gemini lập **Dàn ý 4–8 Chương (`chapters`)** trước, sau đó sinh chi tiết từng chương (mỗi lần 1–2 chương) để tránh cắt cụt token và đảm bảo chiều sâu kiến thức lịch sử/khoa học.
   - Bổ sung trường `chapter_title` trên `StickvBeat`: khi bắt đầu chương mới, hiển thị dải băng tiêu đề chương (`CHƯƠNG 1: ...`) trượt mượt ở góc trên trong `2.8s` đầu chương.
   - Ép luật đa dạng hành động: không cho phép 2 beat liền kề lặp lại cùng một `pose` trong bộ 12 hành động.
3. **Render Phân Đoạn Theo Chương (`Chunked Chapter Rendering` trong `render.py`):**
   - Chia danh sách beat thành các cụm theo chương (`~30–60s/cụm`), render từng cụm ra `build/chunks/chunk_{idx:03d}.mp4` với `STICKV_MP4_COMPAT_FLAGS` và `FFMPEG_RESOURCE_CLAMP`.
   - Truyền liên tục toàn bộ trạng thái cuối của cụm trước (`global_t`, `prev_stage_state`, `prev_puppet_state`, `prev_camera_state`) sang cụm sau nên giữa các cụm **liền mạch 100% không vết nối**, đồng thời giữ RAM ổn định trên máy `i5-10400` khi xuất video 10 phút (`18.000` frames).
   - Nối các cụm bằng FFmpeg `concat` demuxer (`-c copy`) và gắn Outro 4s.

---

## 6. KẾ HOẠCH CHIA COMMIT & KIỂM THỬ NHANH (TRÊN `feat/stickv-v7-automation`)

1. **`feat(settings): add VOICEMOD_TUNA_API_KEY to .env.example, settings store and online SFX`**
   - Cập nhật `.env.example`, `config.py`, `app_settings.py`, `online_sources/` (Tuna client), `SettingsPage.tsx` và `i18n/vi.ts`.
   - Unit test: kiểm tra đọc động `VOICEMOD_TUNA_API_KEY` từ `workspace/settings.json` và header xác thực Tuna.
2. **`feat(stickv-puppet): upgrade to 2-segment elbow arm rig and 12 expressive storytelling poses`**
   - Cập nhật `backend/hbt/stickv/puppet.py` (`SEG_CACHE_VERSION = "v2_elbow"`, tách `upper_arm` + `forearm`, vá khớp vai & khuỷu `#0B0E14`, 12 hành động `point_up`, `think_chin`, `arms_crossed`, `hands_on_hips`, `shrug_ask`, `present_board`, `emphatic_chop`, `shock_hands_up`, `lean_secret`, `count_points`, `walk_explore`, `idle_breathe`).
   - Unit test: kiểm tra tách bắp tay/cẳng tay, xoay khớp khuỷu không gãy nét, đủ 12 preset hành động.
3. **`feat(stickv-stage): eliminate hard cuts with 100% visual coverage, virtual camera and 16:9/9:16`**
   - Cập nhật `stage.py`, `backdrops.py`, `audio.py`, `models.py` (thẻ minh họa tự động 100% beat, `timeline_era` / `location_map` / `myth_vs_fact`, chuyển tiếp fade/slide `0.35s`, nhịp đọc `0.16s`, `camera_shot`, `aspect_ratio` `9:16` & `16:9`).
   - Unit test: kiểm tra chuyển tiếp mượt không hard-cut, layout `16:9` vs `9:16`, nội suy `camera_shot`.
4. **`feat(stickv-longform): add multi-chapter 5-10 min script generator, chunked renderer and UI controls`**
   - Cập nhật `llm.py` (sinh kịch bản đa chương 1–10 phút), `render.py` (chunked rendering nối tiếp trạng thái không tràn RAM), `StickvPage.tsx` và `i18n/vi.ts` (bộ chọn `9:16` / `16:9`, thời lượng `1 / 3 / 5 / 8 / 10 phút`, 12 hành động, góc máy ảo).
   - Chạy kiểm thử nhanh 1 lần qua Git Bash:
     `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`
