# HBT STUDIO — ĐẶC TẢ KỸ THUẬT DIỄN HOẠT 2D PUPPET & BIỂU CẢM TỰ ĐỘNG (`STICKV` v7.1)

> **Mục tiêu cốt lõi:** Xây dựng bộ diễn hoạt nhân vật 2D thông minh (`backend/hbt/stickv/puppet.py`) biến bộ linh kiện tĩnh 2D thành nhân vật sống động 30fps có **khẩu hình nhép theo từng âm tiết giọng VieNeu-TTS**, **mắt biểu cảm & chớp mắt tự nhiên**, **đầu gật gù** và **vung tay chỉ bảng/diễn giải mượt mà**.
> **Nguyên tắc chống chuyển động "ngớ ngẩn" (Anti-Jank Rigging Rules):** Tuyệt đối KHÔNG xoay từng bộ phận quanh tâm ảnh mặc định (gây rụng tay, bay đầu); KHÔNG dùng nhiễu ngẫu nhiên khung-qua-khung (gây giật kinh phong); MỌI chuyển động phải đi qua **Cây phân cấp khớp Cha–Con (Hierarchical Bone Tree)** với **Tâm xoay giải phẫu (Anatomical Pivot)** và **Bộ lọc làm mượt lò xo / hàm lượng giác (Damped Spring & Smooth Sine)**.

---

## 1. QUY CHUẨN BỘ LINH KIỆN ĐẦU VÀO (`assets/stickman/puppet/`)

Hệ thống đọc các tệp ảnh PNG RGBA trong suốt (đã qua `remove_white_background` và tự động crop sát viền non-transparent `getbbox()` + padding 4px) tại thư mục `assets/stickman/puppet/`:

### 1.1 Danh sách 7 linh kiện chuẩn & Linh kiện tách khớp tự động

1. **`base_character.png` (Bắt buộc để bật chế độ Puppet):**
   - Nhân vật HBT đứng thẳng đối diện, dáng A-Pose đối xứng (hai tay mở nhẹ ~30–35° tách khỏi thân), **đầu tròn trắng trơn không vẽ sẵn mắt hay miệng**.
2. **Tự động tách 4 bộ phận cơ thể từ `base_character.png` (`auto_segment_puppet`):**
   - Ngay khi người dùng tải `base_character.png` lên (và lưu cache vào `assets/stickman/puppet/.segments/` kèm mã băm SHA-256), hàm `auto_segment_puppet()` dùng phân tích hình thái học NumPy/Pillow tách chính xác thành 4 lớp RGBA độc lập (hoặc đọc trực tiếp nếu người dùng đã upload sẵn 4 file rời `body_torso.png`, `head_blank.png`, `arm_left.png`, `arm_right.png`):
     - **`head_blank.png`:** Phần đầu hình cầu trắng (từ đỉnh đầu xuống sát mép trên cổ áo trắng).
     - **`body_torso.png`:** Phần cổ áo trắng, cà vạt đỏ, thân và hai chân + giày vàng (giữ cố định làm trụ gốc `Root` để chân luôn bám mặt đất, không bao giờ bị trượt/bay chân vô lý).
     - **`arm_left.png` & `arm_right.png`:** Hai cánh tay đen + găng tay trắng bên trái và bên phải thân (tách theo vùng liên thông bên ngoài trục thân giữa `x_center ± torso_half_width`).
   - **Vá khuyết khớp (Joint Cap):** Tại điểm cắt khớp vai và khớp cổ, tự động vẽ một hình tròn đặc màu đen mực `#0B0E14` (bán kính bằng `0.5 * độ dày nét tay`) ngay tại tâm xoay để khi tay xoay góc lớn (`-60°` đến `+45°`), khớp vai luôn liền mạch, **không bao giờ bị hở khe trắng hay đứt nét**.
3. **4 Bộ Mắt (`eyes_*.png`):**
   - `eyes_neutral.png` (mặc định / giải thích / suy nghĩ)
   - `eyes_happy.png` (vui vẻ / cười tít / chiến thắng)
   - `eyes_shock.png` (sốc / ngạc nhiên / sợ hãi)
   - `eyes_angry.png` (giận dữ / nghiêm túc / âm mưu)
4. **2 Bộ Miệng (`mouth_*.png`):**
   - `mouth_closed.png` (mỉm cười khép miệng — dùng khi ngắt hơi / im lặng)
   - `mouth_open.png` (miệng mở nói — co giãn theo âm lượng từng âm tiết)

---

## 2. HỆ TỌA ĐỘ CHUẨN HÓA & CÂY PHÂN CẤP KHỚP (HIERARCHICAL RIG)

Mọi tọa độ gắn kết đều tính theo **tỷ lệ chuẩn hóa `[0.0, 1.0]` trên bounding box** của từng bộ phận (lưu cấu hình tại `assets/stickman/puppet/rig_config.json` để có thể tinh chỉnh nếu cần, mặc định tự tính chuẩn xác):

### 2.1 Cây phân cấp biến đổi (Transform Hierarchy)

```text
[1] ROOT (Bàn chân / Mặt đất — y_anchor = 1.0)
 └─ [2] BODY_TORSO (Nhún nhẹ scale_y, nghiêng thân tối đa ±2.5°)
     ├─ [3] ARM_LEFT  (Xoay quanh Pivot Vai Trái, thừa hưởng độ nhún của Torso)
     ├─ [4] ARM_RIGHT (Xoay quanh Pivot Vai Phải, thừa hưởng độ nhún của Torso)
     └─ [5] HEAD_BLANK (Xoay quanh Pivot Cổ, thừa hưởng độ nhún của Torso)
         ├─ [6] EYES_LAYER  (Gắn cố định trong hệ tọa độ cục bộ của Head, tự liếc & chớp)
         └─ [7] MOUTH_LAYER (Gắn cố định trong hệ tọa độ cục bộ của Head, co giãn theo RMS)
```

> **Quy tắc sống còn:** Vì `EYES_LAYER` và `MOUTH_LAYER` là **con trực tiếp của `HEAD_BLANK`**, khi đầu gật (`head_angle`) hoặc nghiêng sang bên, mắt và miệng **xoay cùng một khối với đầu** — tuyệt đối không bao giờ xảy ra lỗi đầu nghiêng một đường mà mắt/miệng trôi lệch ra ngoài khuôn mặt.

### 2.2 Tọa độ Neo & Tâm Xoay Chuẩn (Default Anatomical Anchors)

- **Tâm xoay Cổ (`neck_pivot`):** Nằm tại `(0.50, 0.94)` của `head_blank.png`, gắn vào điểm `(0.50, 0.04)` trên cổ áo của `body_torso.png`.
- **Tâm xoay Vai Trái (`shoulder_left_pivot`):** Nằm tại `(0.88, 0.12)` (góc trên bên phải của ảnh `arm_left.png`), gắn vào vai trái thân tại `(0.36, 0.14)` của `body_torso.png`.
- **Tâm xoay Vai Phải (`shoulder_right_pivot`):** Nằm tại `(0.12, 0.12)` (góc trên bên trái của ảnh `arm_right.png`), gắn vào vai phải thân tại `(0.64, 0.14)` của `body_torso.png`.
- **Vùng đặt Mắt trên Đầu:** Tâm đặt tại `(0.50, 0.44)` của `head_blank.png`, chiều rộng mắt tự động scale bằng `0.58 * head_width` (bảo đảm luôn nằm gọn trong mặt cầu, cách viền đầu ít nhất `18%`).
- **Vùng đặt Miệng trên Đầu:** Tâm đặt tại `(0.50, 0.72)` của `head_blank.png`, chiều rộng miệng tự động scale bằng `0.32 * head_width`.
- **Phép xoay chuẩn xác không cắt góc:** Mọi phép xoay bộ phận dùng hàm `rotate_around_pivot(layer_rgba, angle_deg, pivot_xy)` tính toán lại ma trận affine quanh đúng `pivot_xy` với `Image.Resampling.BICUBIC` để đường viền đen luôn sắc nét, không răng cưa.

---

## 3. ĐỒNG BỘ KHẨU HÌNH (LIP-SYNC) & BIỂU CẢM MẮT TỰ ĐỘNG

### 3.1 Đường bao Âm lượng RMS Làm mượt (`compute_smoothed_rms`)

- Đọc tệp WAV giọng đọc **VieNeu-TTS** của beat hiện tại ở tần số lấy mẫu gốc, chia thành các cửa sổ khớp từng khung hình video (`fps = 30`).
- Tính giá trị `rms[i]` cho từng frame `i`, chuẩn hóa về `[0.0, 1.0]` theo phân vị thứ 92 (`P92`) của chính beat đó.
- **Lọc thông thấp (Exponential Moving Average — EMA):**
  `env[i] = 0.55 * rms_norm[i] + 0.45 * env[i - 1]`
  _(Giúp miệng đóng mở uyển chuyển như người thật đang phát âm, loại bỏ hiện tượng miệng rung giật liên hồi 30 lần/giây)._
- **Quy tắc đóng/mở miệng từng frame:**
  - Nếu `env[i] < 0.14` (đang trong khoảng nghỉ `0.10s` đầu câu, `0.28s` giữa hai câu, hoặc `0.45s` cuối beat): hiển thị **`mouth_closed.png`** (`scale_x = 1.0, scale_y = 1.0`).
  - Nếu `env[i] >= 0.14`: hiển thị **`mouth_open.png`**, co giãn theo biên độ nói:
    - `mouth_scale_y = 0.55 + 0.75 * min(1.0, (env[i] - 0.14) / 0.70)` (dao động tự nhiên từ `0.55` đến `1.30`).
    - `mouth_scale_x = 1.04 - 0.12 * (mouth_scale_y - 0.55)` (nguyên tắc _Squash & Stretch_ trong hoạt hình: miệng mở càng cao theo chiều dọc thì hơi thu gọn chiều ngang).

### 3.2 Tự động Chọn Mắt, Chớp Mắt & Hướng Nhìn (`EyeController`)

- **Ánh xạ biểu cảm từ `pose` / `anim_oneshot` của beat:**
  - `shock`, `scared`, `shock_jump`, `confused` $\rightarrow$ `eyes_shock.png`
  - `happy`, `laugh`, `winner`, `love`, `idea`, `idea_bulb`, `celebrate`, `rich` $\rightarrow$ `eyes_happy.png`
  - `angry`, `evil_grin`, `run`, `stop`, `stop_hand` $\rightarrow$ `eyes_angry.png`
  - Tất cả các dáng còn lại (`explain`, `think`, `detective`, `nerd`, `secret`, `present`...) $\rightarrow$ `eyes_neutral.png`
- **Chớp mắt sinh học tự nhiên (Natural Blinking):**
  - Chu kỳ mỗi `3.2s` (`96` frames ở 30fps, có độ lệch ngẫu nhiên có hạt giống `±0.4s` theo `beat.id`):
  - Trong 3 khung hình liên tiếp (`f = 0, 1, 2`), ép chiều cao lớp mắt `eye_scale_y` theo đường cong `[0.45, 0.12, 0.50]` (không bao giờ chớp mắt khi đang dùng `eyes_happy` vì mắt cười đã nhắm cong sẵn).
- **Hướng nhìn thông minh theo `interaction`:**
  - Khi `interaction == "hold_prop"`: dịch nhẹ cặp mắt về phía vật thể trên tay (`eye_offset_x = ±4px`, `eye_offset_y = -2px`).
  - Khi `interaction == "point_chart"`: dịch nhẹ cặp mắt hướng lên phía bảng biểu đồ.

---

## 4. THƯ VIỆN HÀNH ĐỘNG ĐỘNG HỌC (PROCEDURAL MOTION CURVES)

Mỗi hành động được định nghĩa bằng công thức điều hòa mượt (tính theo giây `t` và đường bao giọng nói `env[i]`), bảo đảm **góc xoay nằm trong giới hạn giải phẫu người thật**:

| Tên hành động (`anim_oneshot` / `anim_loop`)   | Đầu (`head_angle`)                                 | Tay trái (`arm_L`)                       | Tay phải (`arm_R`)                                | Thân (`dy`, `scale_y`)                                                              |
| :--------------------------------------------- | :------------------------------------------------- | :--------------------------------------- | :------------------------------------------------ | :---------------------------------------------------------------------------------- |
| **`idle_breathe`** _(Lúc im lặng / chờ)_       | Nghiêng êm `2.0° * sin(1.8t)`                      | Đung đưa nhẹ `4° * sin(1.8t)`            | Đung đưa ngược pha `-4° * sin(1.8t)`              | Thở phồng `scale_y = 1.0 + 0.012 * sin(2.2t)`, chân cố định `dy = 0`                |
| **`talk_explain`** _(Mặc định lúc nói)_        | Gật theo giọng nói `-5.5° * env[i] + 2° * sin(3t)` | Hạ tự nhiên `8° + 5° * sin(2.5t)`        | Vung giải thích `-28° + 14° * sin(4.2t) * env[i]` | Nhún nhẹ `-3px * env[i]`                                                            |
| **`point_board`** _(Chỉ bảng / biểu đồ)_       | Nghiêng nhìn bảng `-6°` + gật nhẹ theo `env[i]`    | Hạ tự nhiên `10°`                        | Giơ cao chỉ bảng `-52° + 6° * sin(5t)`            | Nghiêng thân `2°` về phía bảng                                                      |
| **`hold_prop`** _(Cầm / triệu hồi icon)_       | Nhìn về phía icon `5°`                             | Hạ tự nhiên `10°`                        | Đưa tay đỡ icon `-42° + 4° * sin(3t)`             | Nhún nhẹ `-2px * env[i]`                                                            |
| **`talk_excited` / `celebrate`**               | Gật mạnh `-7° * env[i]`                            | Vung cao `-45° + 18° * sin(6t)`          | Vung cao `45° - 18° * sin(6t)`                    | Nhún nhịp `dy = -8px * abs(sin(5t))`                                                |
| **`think_loop`** _(Suy nghĩ / phân tích)_      | Nghiêng đầu suy tư `9° + 1.5° * sin(1.5t)`         | Khoanh ngang `-18°`                      | Đưa tay lên cằm `-62° + 3° * sin(2t)`             | Thở chậm `1.5 Hz`                                                                   |
| **`shock_jump`** _(One-shot `0.55s` đầu câu)_  | Ngửa nhẹ `-8°` + rung ngang `±4px`                 | Dang rộng `-48°` (giảm dần theo damping) | Dang rộng `48°` (giảm dần theo damping)           | Bật nhảy parabol `dy = -26px * sin(π * t / 0.45)` trong `0.45s` đầu rồi tiếp đất êm |
| **`nod_agree`** _(One-shot gật đầu đồng ý)_    | Gật 2 nhịp rõ ràng `-12° * sin(2π * t / 0.6)`      | Đung đưa nhẹ `5°`                        | Đung đưa nhẹ `-5°`                                | Nhún nhẹ khớp nhịp gật                                                              |
| **`shake_head`** _(One-shot lắc đầu phủ nhận)_ | Dịch ngang `dx = 7px * sin(3π * t / 0.7)`          | Hạ nhẹ `6°`                              | Hạ nhẹ `-6°`                                      | Giữ vững thân                                                                       |

### 4.1 Chuyển tiếp mượt giữa `oneshot` $\rightarrow$ `loop` $\rightarrow$ `idle` (Cross-Fade Pose Blending)

- Khi kết thúc pha `anim_oneshot` (ví dụ tại `t = 0.65s`) để chuyển sang `anim_loop`, không nhảy cóc góc xoay ngay lập tức mà **nội suy tuyến tính mượt (Lerp) trong `0.15s` (5 frames)**:
  `angle_final = (1 - alpha) * angle_oneshot + alpha * angle_loop` (`alpha: 0 -> 1`).
- Nhờ vậy mọi chuyển động nối tiếp nhau đều có quán tính tự nhiên như phim hoạt hình vẽ tay.

---

## 5. LUỒNG RƠI DỰ PHÒNG (FALLBACK) & TÍCH HỢP VÀO `STICKV`

1. **Thứ tự ưu tiên khi `StickmanAnimator` render một beat:**
   - **Mức 1 (Ưu tiên cao nhất — 2D Procedural Puppet):** Nếu `assets/stickman/puppet/base_character.png` (và tối thiểu 1 file mắt + 1 file miệng) tồn tại $\rightarrow$ dùng `puppet.py` dựng chuỗi khung hình 30fps có lip-sync RMS + chớp mắt + vung tay.
   - **Mức 2 (Clip 3D/2D `.webm` Alpha):** Nếu chưa có bộ `puppet/`, kiểm tra `animations/oneshot/` và `animations/loop/` lấy clip `.webm`/`.mov` trong suốt.
   - **Mức 3 (Bộ 27+ ảnh PNG biểu cảm tĩnh):** Nếu cả hai chưa có, dùng ảnh PNG tương ứng trong `assets/stickman/` kèm chuyển động nhún RMS + lật hướng.
2. **Tích hợp trên `StickvPage.tsx` & `AssetHubPage.tsx`:**
   - Trong `/library` $\rightarrow$ tab **Nhân vật Stickman**: Thêm thẻ trạng thái **"Bộ Linh Kiện Puppet 2D (7 mảnh)"** hiển thị ô thả nhanh cho từng mảnh (`base_character`, `eyes_neutral`, `eyes_happy`, `eyes_shock`, `eyes_angry`, `mouth_closed`, `mouth_open`), tự động tách nền trắng khi upload và hiển thị thanh trạng thái _"Sẵn sàng diễn hoạt tự động (7/7 mảnh)"_.
   - Trên `StickvPage.tsx`: Thêm công tắc chọn chế độ diễn hoạt nhân vật (`Tự động (Puppet 2D -> WebM -> PNG)` / `Chỉ dùng Ảnh Pose tĩnh`) và hiển thị khung xem trước nhân vật đã lắp ráp đủ mặt trên sân khấu.

---

## 6. KẾ HOẠCH TRIỂN KHAI & KIỂM THỬ NHANH

1. **`feat(stickv-puppet): implement hierarchical 2D puppet rig, auto-segmentation and RMS lip-sync`**
   - Tạo `backend/hbt/stickv/puppet.py` (tự tách 4 phần từ `base_character.png` + vá khớp tròn, cây khớp cha–con, xoay quanh pivot không cắt nét, lip-sync RMS làm mượt EMA, chớp mắt sinh học 3.2s, 9 đường cong chuyển động + Lerp 0.15s).
   - Nối vào `backend/hbt/stickv/animator.py` làm ưu tiên Mức 1 (giữ nguyên fallback Mức 2 `.webm` và Mức 3 `27+ PNG`).
2. **`feat(stickv-puppet-ui): add 7-slot Puppet 2D uploader in /library and stage preview`**
   - Cập nhật `backend/hbt/api/asset_hub.py`, `backend/hbt/api/stickv.py`, `frontend/src/pages/AssetHubPage.tsx`, `frontend/src/pages/StickvPage.tsx` và `frontend/src/i18n/vi.ts`.
   - Viết unit test đầy đủ tại `backend/tests/test_stickv_puppet.py` (kiểm tra tách khớp không lỗi, mắt/miệng không vượt ra ngoài đầu khi đầu xoay, miệng khép khi im lặng và mở theo RMS, chớp mắt chu kỳ, chuyển tiếp Lerp `oneshot -> loop`, và fallback khi thiếu linh kiện).
   - Chạy kiểm thử nhanh 1 lần qua Git Bash:
     `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`
