# KẾ HOẠCH NÂNG CẤP STICKV V9 — CAMERA AN TOÀN BẢNG TRI THỨC, NỘI DUNG BẢNG CHUYÊN SÂU & PUPPET 18 HÀNH ĐỘNG + 10 BIỂU CẢM

> **Mục tiêu:** Khắc phục triệt để 3 hạn chế thực tế qua nghiệm thu video `StickV v8`:
>
> 1. Lỗi camera zoom quanh tâm `(W/2, H/2)` đẩy văng Bảng thông tin ra khỏi mép trên và phóng Stickman dính sát phụ đề Karaoke.
> 2. Nội dung Bảng thông tin phía trên sơ sài, chép lại nguyên văn lời thoại MC, ô icon trống mờ và beat cuối hiện lại câu kêu gọi đăng ký kênh.
> 3. Khuôn mặt Stickman giữ nguyên 1 biểu cảm suốt video và kho hành động cơ thể còn hạn chế.

---

## 1. BẤT BIẾN HỆ THỐNG & VÙNG CẤM

- **Môi trường:** Windows local (`i5-10400`, không GPU rời). Giữ nguyên `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`), `STICKV_MP4_COMPAT_FLAGS` (`yuv420p`), chống khóa file `WinError 32` (`deleted_renders.json`), Watermark `brand/hbt-logo-mark.png` và Outro 4s.
- **Vùng cấm chỉnh sửa:** `backend/hbt/pipeline/`, `backend/hbt/models.py` (gốc), `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
- **Giữ nguyên dữ liệu kho local:** `library/memes/index.json`, `library/stickers/`, `library/stickman/puppet/` (7 file gốc), và 2 stash cũ trên `feat/pv-comments-length`.
- **Kiểm thử cuối đợt (duy nhất 1 lần qua Git Bash):**
  `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`

---

## 2. HẠNG MỤC 1: SỬA TRIỆT ĐỂ CAMERA ZOOM & BỐ CỤC VÙNG AN TOÀN (`stage.py`, `render.py`)

### 2.1. Nguyên nhân lỗi cũ

Việc phóng to toàn khung hình quanh tâm `(W/2, H/2)` ở `9:16` (`1080×1920`) đẩy vùng bảng (`y = 140..780`) lên tọa độ âm (`y < 0`, bị cắt mất chữ) và đẩy đầu Stickman (`y = 1220..1760`) chạm sát dải Karaoke (`y = 920..1100`).

### 2.2. Kiến trúc Khung Hình Tách Lớp & Kẹp Biên An Toàn (Safe-Clamp Camera)

Thay vì zoom mù toàn bộ ảnh sau ghép, `stage.py` tính biến đổi tách lớp theo `camera_shot` (nội suy mượt `0.55s` cubic smoothstep) cho cả 2 khổ:

| Góc máy (`camera_shot`)                       | Khổ dọc `9:16` (`1080×1920`)                                                                                                                                                                                                                                                                                                                                                                          | Khổ ngang `16:9` (`1920×1080`)                                                                                                                                                                         |
| :-------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`wide_stage`** _(Toàn cảnh)_                | • Bảng trên: `scale = 1.00`, kẹp biên `y in [125, 830]`, `board_alpha = 1.0`.<br>• Karaoke: `y = 895..1065`.<br>• Stickman: `scale = 1.00`, chân neo tại `(0.50*W, 0.90*H)`.                                                                                                                                                                                                                          | • Stickman bên trái: `x = 0.21*W`, `y_foot = 0.91*H`, `scale = 1.00`.<br>• Bảng tri thức bên phải: `x in [680, 1840]`, `y in [115, 860]`, `board_alpha = 1.0`.<br>• Karaoke đáy: `y = 910..1030`.      |
| **`focus_board`** _(Cận bảng tri thức)_       | • Bảng trên: phóng `scale = 1.07` neo theo **đỉnh trên giữa `(W/2, 118)`**, kẹp cứng `top >= 115px` và `bottom <= 865px` (**100% chữ trên bảng nằm trọn trong khung hình, không bao giờ bị cắt**).<br>• Stickman: thu nhẹ `scale = 0.82`, dịch sang `(0.36*W, 0.91*H)` và tự động ưu tiên dáng `point_board_high` (nếu beat đang ở dáng tĩnh `idle_breathe`/`present_board`).                         | • Bảng bên phải: phóng `scale = 1.08` kẹp cứng trong `x in [650, 1860], y in [95, 900]`.<br>• Stickman bên trái: dịch nhẹ sang `x = 0.16*W`, `scale = 0.88`, ưu tiên dáng `point_board_high`.          |
| **`closeup_react`** _(Cận biểu cảm Stickman)_ | • Bảng lớn phía trên **mờ dần mượt về `board_alpha = 0.0` trong `0.30s`** (chỉ giữ lại thanh pill tên Chương/Chủ đề nhỏ gọn tại `y = 125px`), tuyệt đối không để bảng bị cắt ngang lơ lửng ở mép trên.<br>• Karaoke: giữ ổn định tại `y = 820..990`.<br>• Stickman: phóng `scale = 1.22` neo chân tại `(0.50*W, 0.93*H)` (đỉnh đầu đạt `~1060px`, cách Karaoke tối thiểu `70px`, không dính sát mặt). | • Stickman bên trái: phóng `scale = 1.22` tại `(0.24*W, 0.93*H)`.<br>• Bảng bên phải: thu nhẹ `scale = 0.94`, giảm độ nổi `board_alpha = 0.35` để dồn thị giác vào biểu cảm nhân vật mà không cắt chữ. |

---

## 3. HẠNG MỤC 2: NÂNG CẤP PROMPT AI & THẺ BẢNG TRI THỨC CHUYÊN SÂU (`llm.py`, `models.py`, `stage.py`)

### 3.1. Luật Kịch Bản Song Song: Lời Thoại Kể Chuyện vs. Bảng Tri Thức (`llm.py`)

Cập nhật cả **Prompt gọi Gemini API** lẫn **Prompt Đạo diễn (`build_director_prompt`)**:

1. **Luật Cấm Chép Lời Thoại (Anti-Parrot Rule):**
   - Nghiêm cấm sao chép hoặc viết lại y nguyên câu thoại `text` lên `board_title` / `board_bullets`.
   - **`text` (Giọng VieNeu-TTS):** Kể chuyện tự nhiên, gợi tò mò, dẫn dắt cảm xúc.
   - **`board_data` (Bảng trên màn hình):** Đóng vai trò **"Tấm Bảng Bằng Chứng & Ghi Chú Khoa Học"** — bắt buộc cung cấp giá trị thông tin bổ sung mà tai nghe chưa đủ:
     - **Số liệu định lượng thực tế** (ví dụ: `Amygdala phản ứng trong 12ms — nhanh gấp 20 lần vỏ não trước trán`), hoặc
     - **Chuỗi cơ chế Nguyên nhân $\rightarrow$ Cơ chế $\rightarrow$ Hệ quả**, hoặc
     - **So sánh đối chiếu 2 mặt (`Lầm tưởng` vs. `Sự thật`)**, hoặc
     - **Thuật ngữ chuyên môn + giải thích ngắn + câu chốt (`takeaway`)**.
   - Cấm các cụm sáo rỗng vô nghĩa như `"100% Mức độ cảnh báo"`, `"Thông tin quan trọng"`, `"Lưu ý đặc biệt"`.
2. **Thẻ Tóm Tắt Cuối Video (`board_type = "recap_card"`):**
   - Bắt buộc 1–2 beat cuối video (phần CTA bình luận / đăng ký kênh) phải đặt `board_type = "recap_card"` với `board_title = "TÓM TẮT 3 Ý CỐT LÕI"` và `bullets` đúc kết **3 bài học giá trị nhất** rút ra từ các beat trước đó (tuyệt đối không hiện lại câu _"Đừng quên đăng ký kênh..."_ lên bảng).
   - Bổ sung bước hậu kiểm (`_enforce_meaningful_boards`) trong `llm.py`: tự động phát hiện beat cuối là CTA hoặc bảng trùng >70% từ với `text` để chuyển sang `recap_card` hoặc trích xuất cụm từ khóa/cơ chế cô đọng.

### 3.2. Thiết Kế Lại Bố Cục Thẻ Bảng Đầy Đặn (`stage.py`)

- **Xóa bỏ ô icon trống mờ nhạt bên trái:** Nâng cấp thẻ mặc định / `bullets` / `auto_card` thành **Thẻ Phân Tích 2 Tầng** lấp đầy cân đối `84%` diện tích bảng:
  1. **Tầng Tiêu Đề (Header):** Huy hiệu Chương/Chủ đề + Iconify vector sắc nét (`54×54px`) nằm trong huy hiệu tròn nổi bật bên trái tiêu đề chính (`Be Vietnam Pro Bold`, `44–48px`).
  2. **Tầng Phân Tích (Body):** 2–3 gạch đầu dòng ngắn gọn (mỗi dòng `<= 11 từ`) có vạch nhấn màu bên trái (`#D9232E` / `#F59E0B`), hỗ trợ **tô màu từ khóa bọc trong `**...**`** (`#FACC15` trên nền tối, `#B91C1C` trên nền giấy kem) để người xem lướt mắt 1 giây là nắm được ý chính.
  3. **Tầng Chốt Ý (`takeaway`):** Hộp nổi bật ở đáy thẻ gắn nhãn `CHỐT LẠI:` tóm gọn kết luận của beat.
- **Thêm renderer cho `recap_card`:** Hiển thị 3 thẻ ngang đánh số `1` · `2` · `3` màu Vàng Hổ Phách / Đỏ HBT giúp người xem đọc lại toàn bộ kiến thức video trong 4 giây cuối.

---

## 4. HẠNG MỤC 3: MỞ RỘNG 18 HÀNH ĐỘNG (`pose`) & 10 BIỂU CẢM KHUÔN MẶT (`emotion`) (`puppet.py` v3)

> **Nguyên tắc tài nguyên:** Tái sử dụng **100% bộ 7 linh kiện PNG sẵn có** trong `library/stickman/puppet/` (`base_character`, `eyes_neutral`, `eyes_happy`, `eyes_shock`, `eyes_angry`, `mouth_closed`, `mouth_open`), KHÔNG yêu cầu người dùng tạo thêm ảnh trên Google Flow.

### 4.1. Schema Mới (`models.py` & `llm.py`)

- Thêm trường `emotion: str = "auto"` vào `StickvBeat` (tương thích ngược 100% với dự án cũ; nếu `"auto"` hoặc rỗng sẽ tự suy luận từ `pose` + từ khóa câu thoại).
- Cập nhật `enforce_pose_diversity` trong `llm.py` để ép không lặp cả `pose` lẫn `emotion` ở 2 beat liền kề.

### 4.2. Danh Sách 10 Biểu Cảm Khuôn Mặt (`SEG_CACHE_VERSION = "v3_expressive"`)

Lắp ráp trên `Head` trong hệ tọa độ cục bộ trước khi xoay theo cổ (`neck_pivot`):

| Mã `emotion`    | Linh kiện mắt/miệng gốc              | Biến đổi hình học & Ký hiệu cảm xúc Pillow vẽ thêm                                                                       |
| :-------------- | :----------------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| **`neutral`**   | `eyes_neutral`                       | Lông mày cong tự nhiên bình tĩnh.                                                                                        |
| **`confident`** | `eyes_neutral`                       | Nhếch cao một bên lông mày (`+6px`), đầu ngẩng tự tin (`-3°`).                                                           |
| **`curious`**   | `eyes_neutral`                       | Đầu nghiêng `10°`, một bên mày nhướn cao + **dấu hỏi `?` màu vàng `#F59E0B`** nhún nhẹ cạnh đầu.                         |
| **`idea`**      | `eyes_happy`                         | **Bóng đèn vàng `#FACC15` tỏa tia sáng** bật sáng phía trên đỉnh đầu (`y - 56px`, scale pop-in `0.25s`).                 |
| **`shock`**     | `eyes_shock`                         | Miệng mở rộng hơn (`1.18x`) + **2 dấu chấm than `!` màu đỏ `#D9232E`** rung nhẹ hai bên đầu.                             |
| **`skeptical`** | `eyes_neutral` (nheo `scale_y=0.72`) | Vẽ thêm cặp lông mày bất đối xứng (1 bên nhíu thấp, 1 bên nhướn cao), đầu nghiêng `-5°`.                                 |
| **`serious`**   | `eyes_neutral`                       | Vẽ cặp lông mày chữ V hạ thấp nghiêm nghị (`#0B0E14`), đầu giữ thẳng vững vàng.                                          |
| **`sad`**       | `eyes_neutral`                       | Xoay nhẹ mắt/mày cụp đuôi (`±8°`), đầu cúi nhẹ `+7°` + **giọt mồ hôi/nước mắt xanh `#38BDF8`** trượt nhẹ bên thái dương. |
| **`happy`**     | `eyes_happy` (`^ ^`)                 | Nhịp nhún đầu vui tươi đồng bộ theo giọng nói.                                                                           |
| **`excited`**   | `eyes_shock` + `mouth_open` rộng     | **Tia lấp lánh vàng `#FACC15`** quanh đầu + độ nảy thân cao hơn `1.3x`.                                                  |

### 4.3. Danh Sách 18 Hành Động Cơ Thể (`POSE_PRESETS` — 12 hành động v8 + 6 hành động mới)

Giữ nguyên 12 hành động v8 (`point_up`, `think_chin`, `arms_crossed`, `hands_on_hips`, `shrug_ask`, `present_board`, `emphatic_chop`, `shock_hands_up`, `lean_secret`, `count_points`, `walk_explore`, `idle_breathe`) và bổ sung **6 hành động kể chuyện mới** trên hệ xương vai–khuỷu 2 đoạn: 13. **`point_board_high` (Chỉ thẳng lên bảng trên):** Tay phải nâng vai `-138°`, duỗi cẳng tay `-152°` chỉ thẳng lên vùng Bảng tri thức phía trên, thân nghiêng nhẹ `-4°`, đầu ngước `-8°` nhìn theo hướng chỉ. 14. **`wave_hello` (Vẫy tay chào):** Tay phải giơ cao `-115°`, cẳng tay vẫy qua lại mượt (`-135° ± 22°`, tần số `3.2 Hz`) ở câu mở đầu hoặc câu chào tạm biệt cuối video. 15. **`scratch_head` (Gãi đầu bối rối):** Tay phải đưa lên `-128°`, gập khuỷu `+115°` đặt bàn tay ra sau gáy gãi nhẹ (`±8°`) kết hợp nghiêng đầu `10°`. 16. **`facepalm_light` (Vỗ trán cạn lời):** Tay phải nâng `-95°`, gập khuỷu `+118°` đặt bàn tay lên trán, đầu cúi `+9°` biểu thị sự bất lực hài hước trước lầm tưởng. 17. **`nod_yes` (Gật đầu xác nhận):** Chu kỳ gật đầu dứt khoát (`+9° -> -3° -> +9°` ở `2.2 Hz`) kết hợp cẳng tay mở ra xác nhận (`-42°`). 18. **`shake_no` (Lắc đầu & Xua tay phủ nhận):** Đầu lắc ngang/nghiêng luân phiên (`±10°` ở `2.8 Hz`) kết hợp bàn tay giơ thẳng đứng (`-85°`) xua qua lại (`±18°`).

_(Hỗ trợ đầy đủ `POSE_ALIASES` để tương thích ngược: `wave` $\rightarrow$ `wave_hello`, `facepalm` $\rightarrow$ `facepalm_light`, `confused` $\rightarrow$ `scratch_head`, `nod` $\rightarrow$ `nod_yes`, `stop` $\rightarrow$ `shake_no`, `point_high` $\rightarrow$ `point_board_high`.)_

---

## 5. KẾ HOẠCH TRIỂN KHAI THEO COMMIT (3 COMMIT)

1. **`feat(stickv-puppet-v3)`:** Nâng cấp `backend/hbt/stickv/puppet.py` (`SEG_CACHE_VERSION = "v3_expressive"`) với **18 hành động cơ thể** + **10 biểu cảm khuôn mặt** (vẽ lông mày, `?`, `!`, bóng đèn, mồ hôi, tia sáng trên `Head`), cập nhật `models.py` (`emotion`, `takeaway`, `recap_card`) và `test_stickv_puppet.py`.
2. **`feat(stickv-stage-v9)`:** Sửa triệt để logic `camera_shot` (`wide_stage`, `focus_board`, `closeup_react`) trong `stage.py` & `render.py` (kẹp biên bảng `top >= 115px`, ẩn mượt bảng khi `closeup_react`, tránh va chạm Karaoke); nâng cấp thiết kế **Thẻ Phân Tích 2 Tầng** (tiêu đề + từ khóa tô màu + hộp `CHỐT LẠI`) và thẻ `recap_card` 3 điểm đúc kết; cập nhật `test_stickv_stage.py`.
3. **`feat(stickv-llm-ui-v9)`:** Nâng cấp prompt AI trong `llm.py` (cấm chép lời thoại lên bảng, ép số liệu/cơ chế/ví dụ + tự chuyển beat CTA cuối thành `recap_card`), cập nhật dropdown **18 Hành động** + **10 Biểu cảm** trên `StickvPage.tsx` (`frontend/src/api/types.ts`, `frontend/src/i18n/vi.ts`), di chuyển `PLAN-STICKV-V9.md` vào `docs/stickv/PLAN-STICKV-V9.md` và chạy kiểm thử nhanh cuối đợt.
