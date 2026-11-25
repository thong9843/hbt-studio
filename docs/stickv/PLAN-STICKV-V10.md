# HBT STUDIO — ĐẶC TẢ NÂNG CẤP STICKV V10 (ZERO-LATENCY KARAOKE · ẢNH MINH HỌA 3 TẦNG · HYBRID 2D IK PUPPET)

> **Mốc nền tảng:** `main` @ `a7ed925` (hoặc mới hơn sau khi merge `GD3-Chatting`). Đã có sẵn `backend/hbt/shared/image_gen/cloudflare_flux.py`, `backend/hbt/shared/online_sources/reference_images.py` và bộ `whisper_worker` trong `pipeline/`.
> **Nhánh triển khai:** `GD4-StickV` (đồng bộ từ `main` trước khi code).
> **Phần cứng ưu tiên:** Máy local Windows chạy CPU (`i5-10400`, 16 GB RAM, không GPU rời). Giữ nguyên `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`), `STICKV_MP4_COMPAT_FLAGS` (`yuv420p`, `aac 48000Hz`), chống khóa file `WinError 32` (`deleted_renders.json`), Watermark `brand/hbt-logo-mark.png` và Outro 4s.

---

## 0. BẤT BIẾN HỆ THỐNG & VÙNG CẤM

1. **6 vùng cấm khóa tuyệt đối (chỉ được import đọc, KHÔNG sửa bất kỳ dòng nào):**
   - `backend/hbt/pipeline/`
   - `backend/hbt/models.py`
   - `reference/`
   - `backend/hbt/api/projects.py`
   - `backend/hbt/postv/`
   - `backend/hbt/chatting/`
2. **Bảo toàn dữ liệu & lịch sử Git:**
   - Giữ nguyên `library/` (chỉ ghi thêm cache ảnh mới vào `library/reference_images/`), `workspace/`, `assets/`, `brand/`, `.env`, các stash cũ và **không dời 4 tag lịch sử `v1`, `v2`, `v3`, `v4`**.
3. **Kiểm thử cuối đợt (chạy duy nhất 1 lần qua Git Bash):**
   - `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`
   - Không chạy nhóm `@pytest.mark.slow` hay Playwright E2E; chủ dự án nghiệm thu trực tiếp bằng video xuất thật.

---

## 1. CHẨN ĐOÁN 4 VẤN ĐỀ THỰC TẾ TỪ VIDEO NGHIỆM THU (`43,3s`)

Đối chiếu khung hình 60fps và sóng âm thực tế của video _Nghịch lý thể hình cầu thủ_:

1. **Karaoke & chuyển bảng bị trễ `0,35s - 0,50s` so với giọng đọc:** Tại `00:00.50` giọng đã đọc tới _"cầu thủ bóng đá"_ nhưng Karaoke mới sáng _"người"_; tại `00:04.50` và `00:09.00` giọng Beat 2 / Beat 3 đã phát nhưng màn hình vẫn giữ bảng cũ thêm `0,45s - 0,50s`.
2. **Thiếu ảnh minh họa & Polaroid trống rỗng:** 8/9 beat là bảng chữ; beat duy nhất dùng ảnh (`00:18 - 00:21`, _"Sợi cơ chịu đựng bền bỉ"_) ra khung xanh đen trống rỗng với 1 chấm icon nhỏ ở giữa.
3. **3 lỗi hiển thị bảng chữ:**
   - `00:00 - 00:04`: ô `myth_vs_fact` in thô chuỗi dict Python `{'title': 'LẦM TƯỞNG CƠ BẮP', 'text': '...'}` lên màn hình.
   - Dòng `CHỐT LẠI:` ở hầu hết các beat bị chặt cụt giữa chữ bằng `...` (vd `"...trong b..."`).
   - `00:39 - 00:42`: beat CTA cuối hiện 1 dải băng trống `CHƯƠNG 1 — TÓM TẮT 3 Ý CỐT LÕI` lặp lại bảng vừa chiếu ở `00:35`.
4. **Stickman vừa đơ vừa gãy khớp tay:** Đứng giữ 1 tư thế suốt 4–5 giây; riêng `00:18 - 00:21` hai cánh tay cụp gập chéo dị dạng trước bụng và `00:39 - 00:42` cả hai tay vắt dồn sang cùng bên trái như trật khớp do giới hạn của ảnh cắt mảnh tĩnh.

---

## 2. TRỤ CỘT 1 — KHÓA ĐỒNG BỘ KARAOKE & BẢNG **0 ĐỘ TRỄ** (SAI SỐ `<= 16ms` / 1 FRAME @ 60FPS)

### 2.1. Kiến trúc Trục Âm Thanh Chủ (Audio-First Master Clock)

Thay đổi triệt để nguyên lý đồng bộ trong `backend/hbt/stickv/audio.py`, `audio_director.py` và `render.py`:

1. **Chốt file giọng tổng bất biến trước khi dựng hình (`build/stickv_voice_full.wav`):**
   - Tổng hợp giọng VieNeu-TTS từng beat, làm sạch xung nhiễu đầu/đuôi, ghép nối thành **duy nhất 1 file `build/stickv_voice_full.wav`** có đủ `GLOBAL_LEAD_SILENCE_S = 0.18s` (chống bộ mã hóa AAC nuốt âm đầu) và khoảng thở giữa các beat.
   - Ghi nhận chính xác bảng mốc `beat_timeline = [(beat_idx, beat_start_s, beat_end_s, speech_start_s, speech_end_s)]` tính trực tiếp từ số mẫu PCM (`sample_count / 48000.0`).
   - **Luật bất biến:** Từ sau khi chốt `stickv_voice_full.wav`, **cấm tuyệt đối mọi bước trim, siết khoảng lặng hoặc J-Cut làm thay đổi độ dài hay dịch trục thời gian** của kênh giọng đọc. Bước trộn BGM/SFX cuối cùng chỉ mix song song lên đúng `stickv_voice_full.wav` (giữ nguyên độ dài 1:1).

2. **Căn mốc từng từ bằng Whisper thật trực tiếp trên `stickv_voice_full.wav`:**
   - Tái sử dụng trực tiếp tiến trình con Whisper sẵn có của dự án (`hbt.pipeline.whisper_worker` / bộ căn chữ của `pipeline/` — chỉ import đọc, không sửa `pipeline/`).
   - **Tham số chuẩn đã chứng minh trên máy CPU `i5-10400`:**
     - Model: `small` + `int8` trên CPU (hoặc theo cấu hình `workspace/settings/app.json`).
     - **Tuyệt đối KHÔNG truyền `initial_prompt`** (tăng tỷ lệ khớp từ 61% lên ~90%).
     - Chạy trong tiến trình con có timeout (`whisper_timeout_seconds`, hỗ trợ hủy job tức thì qua `CancelToken`).
     - **Cache bền vững tại `build/stickv_timing.json`:** khóa theo `sha256(stickv_voice_full.wav + beat_texts + whisper_config_key)` — chỉ căn lại khi lời thoại hoặc giọng đọc thay đổi.
     - **Fallback an toàn:** Trong môi trường `PYTEST_CURRENT_TEST` hoặc khi Whisper chưa cài / timeout, tự rơi êm về bộ căn **năng lượng RMS khung `20ms` + trọng số âm tiết tiếng Việt** (thu hẹp đúng vùng có tiếng nói thật trong `[speech_start_s, speech_end_s]` của từng beat) và ghi rõ phương pháp đã dùng vào log/meta.

3. **Bù trễ quang học & AAC (`KARAOKE_LEAD_OFFSET_S = -0.025`):**
   - Áp dụng độ dịch sớm siêu nhỏ **`-25ms`** (~1.5 frame ở 60fps) lên mốc hiển thị chữ sáng vàng (`effective_start = max(beat_start_s, word.start_s - 0.025)`) để triệt tiêu độ trễ priming ~21ms của AAC và độ trễ thị giác — mắt người cảm nhận **0 độ trễ tuyệt đối** (âm bật ra là chữ sáng vàng đúng tích tắc đó).

4. **Khóa mốc chuyển Bảng & Kiểm toán Zero-Drift:**
   - Phân bổ số frame của từng Beat `k` theo mốc tích lũy tuyệt đối của `stickv_voice_full.wav`:
     `frame_start = round(beat_start_s * fps)`, `frame_end = round(beat_end_s * fps)`.
   - Mọi từ Karaoke của Beat `k` bị kẹp chặt trong `[beat_start_s, beat_end_s]` (không bao giờ tràn sang beat sau hay kéo dài vào khoảng lặng).
   - Chuyển bảng mới bắt đầu trượt vào ngay tại `beat_start_s` với tốc độ chốt dứt khoát (`0.22s` ease-out) để chữ bảng hiện rõ ngay khi âm đầu vang lên.
   - **Zero-Drift Self-Check:** Sau khi chốt timeline, kiểm tra bắt buộc `abs(total_video_duration_s - voice_full_duration_s) <= 0.03s` và mảng `word_timings` đơn điệu tăng, không chồng lấn.

---

## 3. TRỤ CỘT 2 — HỆ THỐNG ẢNH MINH HỌA 3 TẦNG (50–60% BEAT CÓ ẢNH · 0% POLAROID TRỐNG)

### 3.1. Cân bằng tỷ lệ Hình ảnh vs. Bảng số liệu (`backend/hbt/stickv/llm.py`)

- Yêu cầu Gemini bố trí **50% - 60% số beat** có hình minh họa trực quan (`board_type = "pinned_photo"`), xen kẽ nhịp nhàng với các bảng phân tích (`myth_vs_fact`, `comparison`, `counter_grow`, `flow_steps`, `timeline_era`, `recap_card`) — tránh 8 beat liên tiếp toàn bảng chữ.
- Quy định chặt trường tìm ảnh trên mỗi beat `pinned_photo`:
  - `prop_query`: **2 - 4 từ khóa tiếng Anh cụ thể, nhìn thấy được ngoài đời thật** (vd: `"soccer player sprint"`, `"football stadium pitch"`, `"marathon runner legs"`), **cấm** cụm từ trừu tượng kiểu _"sợi cơ bền bỉ"_ hay _"tư duy chiến thuật"_.
  - `image_prompt` _(tùy chọn mới trên `StickvBeat`, tương thích ngược kịch bản cũ)_: 1 câu tiếng Anh ngắn mô tả hình minh họa 2D trực quan dùng khi cần tầng 3 (Cloudflare Flux) vẽ các khái niệm trừu tượng (vd: cấu trúc sợi cơ, lực vật lý, nơ-ron thần kinh).

### 3.2. Bộ phân giải ảnh 3 tầng có Cloudflare Flux Fallback (`reference_images.py` + `cloudflare_flux.py`)

Luồng `resolve_reference_image(query, illustration_prompt, allow_ai_fallback=True)` lưu cache lâu dài vào `library/reference_images/<sha1>.jpg`:

```text
[Beat cần ảnh (pinned_photo)]
   |
   +--> Tầng 1: Wikimedia Commons (0 API key)
   |      |-- Thử query đầy đủ (vd: "soccer player sprint")
   |      `-- Nếu rỗng -> tự rút gọn xuống 2 từ cốt lõi (vd: "soccer player")
   |
   +--> Tầng 2: Pixabay Photos / Illustrations (dùng PIXABAY_API_KEY sẵn có)
   |      `-- Thử query đầy đủ -> fallback query rút gọn
   |
   +--> Tầng 3: Cloudflare Workers AI (tái dùng hbt.shared.image_gen.cloudflare_flux)
   |      |-- Chỉ kích hoạt khi Tầng 1 & 2 không có ảnh đạt chuẩn VÀ đã cấu hình Cloudflare key
   |      |-- Mặc định dùng @cf/black-forest-labs/flux-1-schnell (~58 neurons/ảnh, 768x512)
   |      |-- Style Anchor riêng cho StickV:
   |      |   "Clean 2D flat editorial infographic illustration, crisp dark ink outlines,
   |      |    vibrant modern educational colors, simple clear subject, no text, no letters, no watermark."
   |      `-- Lưu cache vào library/reference_images/ để dùng lại vĩnh viễn (0 tốn lại neuron)
   |
   `--> Chốt chặn cuối (Khi mất mạng & không có Cloudflare key):
          KHÔNG BAO GIỜ vẽ khung Polaroid xanh đen rỗng kèm icon nhỏ!
          Tự động chuyển mềm beat đó sang thẻ Phân Tích 2 Tầng (bullets/auto_card) đầy đặn.
```

- **Bảo vệ tốc độ & hạn mức miễn phí:** Trần tối đa **`4` ảnh Cloudflare AI / lần tạo video** (đủ lấp sạch các khái niệm trừu tượng mà chỉ tốn ~230 / 10.000 neurons mỗi ngày).
- **UI gọn trên `StickvPage.tsx` (tab `Hình ảnh`):** Bên cạnh nút **"Đổi ảnh"** (tìm Wikimedia/Pixabay), thêm 1 nút nhỏ **"Vẽ AI"** (gọi `POST /api/stickv/{slug}/beats/{beat_id}/generate-photo`) để người dùng chủ động vẽ lại minh họa 2D cho từng khung Polaroid chỉ với 1 bấm.

---

## 4. TRỤ CỘT 3 — VÁ DỨT ĐIỂM 3 LỖI BẢNG CHỮ SOI TỪ VIDEO THẬT (`stage.py`, `llm.py`)

1. **Diệt 100% lỗi in thô dict Python `{'title': ..., 'text': ...}`:**
   - Thêm hàm chuẩn hóa `_unwrap_board_text(value) -> tuple[str, str]` và áp dụng thống nhất cho `myth_vs_fact`, `comparison`, `bullets`, `flow_steps`, `timeline_era`, `recap_card`:
     - Nếu `value` là `dict` -> tách sạch `title` và `text` / `body` / `desc` / `content`.
     - Nếu `value` là chuỗi lỡ bị `str(dict)` hóa (bắt đầu bằng `{` và chứa `'title'` hoặc `"title"`) -> giải mã an toàn bằng `json.loads` / `ast.literal_eval` rồi lấy chữ sạch.
     - Kèm kiểm tra ở `llm.py` lúc parse JSON từ Gemini để `board_data` luôn được lưu sạch từ gốc.
2. **Hết cắt cụt chữ ở hộp `CHỐT LẠI:` (`...`):**
   - Trong `stage.py`: nâng hộp `CHỐT LẠI:` cho phép tự động xuống tối đa **2 dòng sạch** (`_draw_rich_autofit_text`, cỡ chữ tự co từ `24px` xuống `20px`) và tăng nhẹ chiều cao thanh đáy hộp khi cần.
   - Trong `llm.py`: ràng buộc `takeaway` dài tối đa **`10 - 13 từ`** ngắn gọn, súc tích để đọc lướt trong 1 giây không bao giờ phải cắt cụt giữa từ.
3. **Bỏ dải băng lặp `CHƯƠNG 1 — TÓM TẮT 3 Ý CỐT LÕI` ở beat CTA cuối:**
   - Với video ngắn 1 chương (`<= 90s` hoặc tổng số chương `<= 1`), không hiển thị dải băng `CHƯƠNG 1` rỗng ở beat CTA cuối.
   - Nếu beat liền trước đã là `recap_card` và beat cuối là lời kêu gọi đăng ký/bình luận (CTA), **giữ nguyên thẻ `recap_card` ổn định trên màn hình** (chỉ bật thêm dải huy hiệu CTA nhỏ gọn phía dưới thẻ) để người xem kịp đọc lại 3 ý cốt lõi trong 3–4 giây cuối.

---

## 5. TRỤ CỘT 4 — HYBRID 2D IK STICKMAN RIG & DIỄN HOẠT ĐA PHA (`puppet.py` v4, `animator.py`)

### 5.1. Tại sao cần chuyển sang Hybrid 2D IK (`SEG_CACHE_VERSION = "v4_hybrid_ik"`)

Cắt mảnh cánh tay từ ảnh tĩnh PNG gốc không thể gập sâu tự nhiên và dễ gây biến dạng/chồng chéo khi xoay góc lớn (lỗi tay cụp chéo `00:18` và hai tay dồn sang một bên `00:39`). Kiến trúc **Hybrid 2D IK** giữ trọn diện mạo nhân vật HBT nhưng thay tứ chi bằng hệ xương 2 khớp tính toán hình học chuẩn xác:

1. **Giữ nguyên linh kiện nhận diện từ `library/stickman/puppet/` (không cần vẽ ảnh mới):**
   - **Đầu & Khuôn mặt (`head_blank`, 4 bộ `eyes_*`, 2 bộ `mouth_*`)**: giữ nguyên hệ biểu cảm, lông mày theo nhấn giọng RMS, liếc mắt, chớp mắt và Lip-Sync 4 mức.
   - **Thân áo sơ mi & Cà vạt đỏ (`body_torso`)**: tách sạch phần thân giữa không dính cánh tay cũ, thêm dao động nhẹ cho đuôi cà vạt khi thân nghiêng/nhún.
   - **Đôi giày vàng HBT (`shoe_left`, `shoe_right`)**: cắt sạch 2 chiếc giày vàng từ `base_character.png` và neo cứng bám mặt đất (kèm bóng bầu dục mềm dưới chân, **0% trượt chân**).

2. **Cánh tay & Chân 2 khớp giải tích (2-Bone Analytical IK, 3x Supersampled AA):**
   - Giải bài toán IK 2 khớp (`solve_2bone_ik(root, target, L1, L2, bend_dir)`) cho:
     - **Tay trái & Tay phải:** `Shoulder -> Elbow -> Wrist` với độ dày nét mực `#0B0E14` đo khớp tự động theo ảnh gốc, vẽ ở tỷ lệ `3x` rồi thu nhỏ `LANCZOS` để đường cong mượt sắc không răng cưa.
     - **Chân trái & Chân phải:** `Hip -> Knee -> Ankle` nối liên tục từ hông (đang nhún/chuyển trọng tâm) xuống đúng cổ giày đang bám đất -> khi nhân vật nhún gối, bước chân hoặc nghiêng người, đầu gối tự động cong thực tế như người thật.
   - **4 hình bàn tay găng trắng vector (`hand_shape`) xoay tự động theo góc cẳng tay:**
     - `open_palm` (xòe tay thuyết trình thân thiện)
     - `point_index` (ngón trỏ chỉ thẳng chính xác vào tọa độ `(x, y)` trên bảng)
     - `fist_punch` (nắm tay nhấn mạnh cao trào / bất ngờ)
     - `count_fingers` (đếm ý `1 / 2 / 3`)
   - **Khóa giải phẫu chống gãy/chéo khớp (Anatomical Constraints):**
     - Ràng buộc cứng giới hạn chiều gập khuỷu tay (`bend_dir` luôn theo hướng tự nhiên), khoảng cách mục tiêu `target` kẹp trong `[0.25*(L1+L2), 0.98*(L1+L2)]`, và cấm tay bên này vắt chéo sâu sang vùng tay bên kia trừ các pose chủ đích hợp lệ (`arms_crossed`, `think_chin`) đã được tính tọa độ đối xứng sạch sẽ.

### 5.2. Diễn hoạt đa pha trong cùng 1 Beat (3-Phase Beat Choreography)

Xóa bỏ hoàn toàn cảnh nhân vật đứng đóng băng suốt 4–5 giây trong 1 beat:

- **Pha 1 — Vào nhịp (`0.0s -> 0.55s`):** Chuyển trọng tâm hông nhẹ (`±10px`), nhún gối tự nhiên (`2–4%`), mắt liếc nhanh lên bảng/ảnh Polaroid, bàn tay vẽ đường cung mượt (Cubic Ease-Out + follow-through khuỷu tay) vào tư thế chính.
- **Pha 2 — Nhấn giọng & Tương tác bảng (`0.55s -> end - 0.55s`):**
  - Bám trực tiếp theo các đỉnh năng lượng **RMS** của giọng nói (từ `stickv_voice_full.wav`): mỗi khi gặp đỉnh nhấn (`env > 0.62`, cách nhau `>= 0.75s`), tự động tạo nhịp đánh tay phụ (_gesture beat_), đổi luân phiên tay trái/phải khi so sánh (`comparison` / `myth_vs_fact`), hoặc **dịch mục tiêu ngón tay trỏ lần lượt theo từng mục** (`Ý 1 -> Ý 2 -> Ý 3` trên bảng `bullets` / `flow_steps` / `recap_card`).
  - Thân trên thở nhẹ + đầu gật khẽ đồng pha với nhịp nhấn âm tiết.
- **Pha 3 — Thu thế chuyển cảnh (`0.55s` cuối beat):** Thu tay mềm mại, ánh mắt quay về nhìn khán giả và nối mượt bằng lò xo giảm chấn sang beat tiếp theo (`0.38s`).

### 5.3. Tối ưu tốc độ render trên CPU `i5-10400`

- Giữ nguyên chế độ `animation_mode` (`auto` ưu tiên Hybrid IK Puppet v4 -> fallback `.webm`/PNG; `static` dùng ảnh pose tĩnh) và tương thích ngược toàn bộ tên 18 `pose` + 10 `emotion` + `face_mood` hiện có.
- **Pre-bake & Local Compositing:** Vẽ sẵn lớp ảnh bảng tĩnh của beat 1 lần (sau khi xong pha vào `0.22s`), và chỉ vẽ lớp Puppet IK trên khung canvas cục bộ ôm sát nhân vật (thay vì vẽ lại toàn màn hình `1080×1920` ở 3x) để tốc độ dựng 60fps trên `i5-10400` không bị chậm đi.

---

## 6. KẾ HOẠCH TRIỂN KHAI 4 COMMIT TRÊN NHÁNH `GD4-StickV`

| #      | Commit                                                                                                | Phạm vi File                                                                                                                                                                                                                     | Kiểm thử nhanh (bắt buộc)                                                                                                                                                                                                                                                                                                                    |
| :----- | :---------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **C1** | `fix(stickv-sync): audio-first master clock & zero-latency Whisper karaoke alignment`                 | `backend/hbt/stickv/audio.py`, `audio_director.py`, `render.py`, `stage.py`                                                                                                                                                      | `test_stickv_audio_smooth.py`, `test_stickv_stage.py` (test `stickv_voice_full.wav` không bị drift `<= 0.03s`, test cache `stickv_timing.json`, test lead offset `-25ms`, test không J-Cut lệch timeline, test word clamping trong beat)                                                                                                     |
| **C2** | `fix(stickv-boards-visuals): sanitize board dicts, 2-line takeaway, 3-tier Cloudflare photo fallback` | `backend/hbt/shared/online_sources/reference_images.py`, `backend/hbt/stickv/stage.py`, `llm.py`, `models.py`, `render.py`, `backend/hbt/api/stickv.py`, `frontend/src/pages/StickvPage.tsx`, `frontend/src/api/*`, `i18n/vi.ts` | `test_reference_images.py`, `test_stickv_stage.py`, `test_stickv_models.py`, `StickvPage.test.tsx` (test 0% chuỗi `{`/`'title':` lọt lên ảnh, test `CHỐT LẠI:` 2 dòng không cắt cụt, test ẩn `CHƯƠNG 1` lặp ở CTA, test fallback Wikimedia -> Pixabay -> Cloudflare Flux mock -> auto_card không bao giờ ra Polaroid rỗng, test nút `Vẽ AI`) |
| **C3** | `feat(stickv-ik-puppet): hybrid 2D IK limb rig, anatomical clamps & 3-phase RMS choreography`         | `backend/hbt/stickv/puppet.py`, `animator.py`                                                                                                                                                                                    | `test_stickv_puppet.py` (test `solve_2bone_ik` hội tụ chính xác & kẹp góc giải phẫu không gãy/chéo tay, test 4 `hand_shape`, test chân bám đất không trượt, test 3-phase choreography có biến thiên cử chỉ trong beat 4s, test đủ 18 pose + 10 emotion + tương thích ngược)                                                                  |
| **C4** | `test(stickv-v10): audit, ponytail review, docs & full fast verification`                             | `docs/stickv/PLAN-STICKV-V10.md`, dọn dead code, bổ sung test hồi quy                                                                                                                                                            | Chạy duy nhất 1 lần: `npm run lint && npm run test:fast && npm run build` + xác nhận `git diff` 6 vùng cấm rỗng                                                                                                                                                                                                                              |

---

## 7. TIÊU CHÍ NGHIỆM THU THỰC TẾ TRÊN `/stickv`

Sau khi hoàn thành, xuất lại thử đúng chủ đề **Nghịch lý thể hình cầu thủ** (`~45 - 60s`, 60fps) và đối chiếu 4 tiêu chí:

1. **Tai & Mắt đồng bộ 0 độ trễ:** Âm phát ra đến đâu chữ Karaoke sáng vàng đúng mili-giây đó, bảng Beat mới lên đúng nhịp không còn trễ `0.45s`.
2. **Ảnh minh họa sống động:** Ít nhất 50% số beat có ảnh Polaroid thật/tranh 2D sắc nét, **0 khung Polaroid trống rỗng**.
3. **Bảng chữ sạch tuyệt đối:** 0% ký tự code `{'title': ...}`, dòng `CHỐT LẠI:` hiển thị trọn vẹn ý, kết video giữ bảng tóm tắt 3 ý sạch sẽ không lặp dải `CHƯƠNG 1`.
4. **Stickman có hồn:** Tay chân cong mượt tự nhiên không gãy/chéo khớp, chân bám đất có nhún gối và trong mỗi beat 4–5 giây nhân vật chủ động chuyển cử chỉ, chỉ bảng theo từng ý thay vì đứng đóng băng.
