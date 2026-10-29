# PostV — Bổ sung bối cảnh cho HBT Studio

Ngày 23/10/2026 · Đính kèm cùng `01-nghien-cuu.md`.
Mục đích: để chat quản lý đối chiếu với `IMPLEMENT.md` v1.4 và `PLAN.md` v1.4, rà rủi ro, rồi soạn lệnh cho Claude Code.
Ký hiệu: **[KC]** đã kiểm chứng · **[SL]** suy luận · **[?]** chưa biết.

---

## 1. PostV là gì

Dạng video mới trong HBT Studio, kiểu "Hooked – Reddit Post to Video" cho nội dung Threads, **người dùng tự dán nội dung**.
Video 9:16: thẻ bài đăng ẩn danh vẽ bằng Pillow + video nền gameplay (Minecraft parkour do người dùng nạp) + giọng đọc + karaoke sáng dần + nhạc + outro 4 giây + ảnh bìa + `publish.txt`.
Dùng riêng một người, chạy local, tiếng Việt, chi phí 0 là mặc định.

## 2. Quyết định đã chốt

| #   | Quyết định                                                                                                                                                                 | Nguồn                                 |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| 1   | Gộp vào HBT Studio với tên **PostV**, không làm web riêng                                                                                                                  | Chủ dự án 23/10                       |
| 2   | Nhập nguồn: **dán thủ công là đường chính**. Dán cả trang (Ctrl+A, Ctrl+C) vào một khung, app tự tách bài + bình luận + số like (nếu có), cho sửa tay                      | Chủ dự án + nghiên cứu                |
| 3   | Link chỉ **lưu làm dòng dẫn nguồn** + nút mở bài. Không tự truy cập Threads                                                                                                | Nghiên cứu (mục 4)                    |
| 4   | Thẻ bài: chữ đã dán → **vẽ lại bằng Pillow**, kiểu mạng xã hội chung chung, tên ẩn danh. Tuỳ chọn (Should): OCR từ ảnh chụp; giữ ảnh chụp thì bắt buộc che tên/avatar      | Mình đề xuất, chủ dự án chưa xác nhận |
| 5   | Nền: thư viện do người dùng nạp, **mỗi clip có nguồn + giấy phép**, thiếu thì chặn xuất                                                                                    | Nghiên cứu                            |
| 6   | Kịch bản = lời dẫn + trích bình luận + **góc nhìn riêng của kênh (bắt buộc)**. Đích 35–75 giây                                                                             | Yêu cầu ban đầu                       |
| 7   | Giọng: Vbee (nhập file) trước; VieNeu-TTS local sau (Should). Karaoke bằng Whisper căn theo kịch bản đã biết                                                               | Chủ dự án                             |
| 8   | AI mặc định nhập tay hoặc dán kịch bản; Claude/Gemini API là tuỳ chọn, qua `ScriptProvider` ở `IMPLEMENT.md` §12                                                           | Chủ dự án                             |
| 9   | Ba điểm duyệt của con người: nguồn → đoạn/kịch bản → video cuối. Không tự đăng                                                                                             | Theo nguyên tắc PLAN §3               |
| 10  | Lịch: **thiết kế viết ngay, build sau `v1.0.0`**                                                                                                                           | Mình đề xuất                          |
| 11  | **Nền gameplay chạy liền suốt video, không có hiệu ứng chuyển cảnh.** Chỉ thẻ bài (ảnh bài/bình luận) có hiệu ứng vào/ra khi đổi cảnh                                      | Chủ dự án 23/10                       |
| 12  | **Phong cách PostV theo Hooked, không theo video HBT** (không phóng ảnh, không thẻ kem, không trượt cả khung). Bố cục chi tiết **chờ video mẫu** của chủ dự án             | Chủ dự án 23/10                       |
| 13  | Mặc định tạm (chủ dự án không chọn, đổi được): phụ đề **kiểu Hooked** (chữ to giữa màn hình, 1–3 từ mỗi lần, từ đang đọc đổi màu); outro HBT là **công tắc**, mặc định bật | Mình đề xuất                          |

### 2b. Video mẫu chủ dự án gửi (phân tích 23/10, đo trên khung hình)

|                  | **Mẫu A: "Reddit story"** (45,9 s, 720×1280, 25 fps)                             | **Mẫu B: "Câu chuyện Threads"** (26,7 s, 1080×1920, 30 fps)                                                                     |
| ---------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Nền              | Gameplay Minecraft parkour **chạy liền**; đổi clip 1 lần (~24 s, cắt thẳng)      | Ảnh/video phong cảnh "aesthetic", **đổi nền theo từng bình luận** (chuyển có nhoè)                                              |
| Thẻ bài          | **Một thẻ bài gốc cố định** ở trên (y ≈ 5–25 % chiều cao, rộng ~92 %) suốt video | **Mỗi đoạn một thẻ**: bài gốc → từng bình luận; bình luận có trả lời thì hiện dạng chuỗi lồng (đường kẻ dọc). Thẻ ở y ≈ 20–35 % |
| Vào/ra thẻ       | Thẻ phóng từ nhỏ ra trong ~0,25 s; cuối video mờ dần                             | Thẻ hiện, đổi thẻ khi sang bình luận mới                                                                                        |
| Số liệu trên thẻ | Lượt thích/bình luận **chạy số tăng dần** lúc đầu (53,9k → 68,9k)                | Lượt thích, trả lời, đăng lại, chia sẻ; cũng chạy số                                                                            |
| Phụ đề           | Chữ thường, trắng viền đen, 1–4 từ, **từ đang đọc có hộp đỏ bo góc**, y ≈ 77 %   | **CHỮ HOA**, trắng, 3–5 từ, **từ đang đọc đổi màu xanh lá** (không hộp), y ≈ 83 %                                               |
| Mở đầu           | Không có tiêu đề riêng                                                           | Giây đầu có **dòng tiêu đề hook** chữ to giữa màn hình                                                                          |
| Meme/sticker     | Không                                                                            | **Có**: mèo meme đặt cạnh phụ đề, đổi theo đoạn                                                                                 |

**Rủi ro thấy ngay trong mẫu (không làm theo):** mẫu B hiện **tên tài khoản thật** và **biểu tượng Threads** trên thẻ; cả hai mẫu chép giao diện Reddit/Threads; meme mèo là nội dung của người khác. PostV giữ: tên ẩn danh, thẻ kiểu chung không logo, meme/sticker chỉ từ thư viện có giấy phép.

**Đề xuất [SL]:** PostV có **2 mẫu dựng** chọn trong bước Xuất:

- **"Thẻ cố định"** (theo mẫu A): khớp quyết định 11, làm trước (đơn giản nhất).
- **"Chuỗi bình luận"** (theo mẫu B): thẻ đổi theo đoạn, tuỳ chọn đổi nền theo đoạn, sticker. Làm sau.
  Mọi thông số đo ở trên (vị trí, số từ, màu từ đang đọc, kiểu hộp) đặt trong cấu hình mẫu, không cứng trong mã.
  **Về Hooked:** đã kiểm chứng từ trang công khai: có thẻ mở đầu (tuỳ chọn hiện tên tác giả), chữ sáng theo từ hoặc theo câu, nền gameplay, bình luận hay được lồng vào lời đọc, nhiều kiểu phụ đề, thời lượng 15–180 s. **Chưa biết:** thẻ hiện lúc nào, vị trí, cỡ chữ cụ thể → lấy theo video mẫu.

## 3. Ràng buộc pháp lý và an toàn (Must)

| Ràng buộc                                                                                                    | Cơ sở                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Không cào, không tự gửi yêu cầu tới Threads, không headless/dịch vụ cào bên thứ ba                           | **[KC]** Meta: _"Platform APIs are the only allowable means to access data programmatically, unless you have our prior written permission"_; áp dụng cả khi không cố ý hoặc không thành công. Chạy local không đổi điều này        |
| Không dùng Threads API/oEmbed để lấy chữ làm video ở giai đoạn này                                           | **[KC]** Overview chỉ nêu mục đích đăng bài và hiển thị cho chính người tạo; oEmbed cấm trích xuất và lưu. Keyword Search cần `threads_keyword_search` được duyệt. **[?]** chưa có căn cứ rõ cho việc dựng video từ bài người khác |
| Che tên, avatar, tên tài khoản người đăng và người bình luận                                                 | Ẩn danh mặc định                                                                                                                                                                                                                   |
| Phần biến đổi chiếm tỉ lệ đáng kể; cảnh báo khi chỉ đọc lại nguyên văn                                       | Chống nội dung tái sử dụng                                                                                                                                                                                                         |
| Nội dung nhạy cảm: đời tư người thường, tố cáo, tin đồn, bạo lực, thù ghét, thuốc/rượu bia/máu me, chính trị | Mở rộng `lint.py`                                                                                                                                                                                                                  |
| Nền Minecraft: tự quay hoặc footage có giấy phép; video không quảng bá sản phẩm không liên quan Minecraft    | **[KC]** Minecraft Usage Guidelines: video phải miễn phí xem, cần nội dung riêng đủ lớn; không nói gì về footage của người khác                                                                                                    |
| Khoá API chỉ trong `.env`; dữ liệu ở lại máy                                                                 | Khớp `CLAUDE.md`                                                                                                                                                                                                                   |
| Điều khoản Threads gốc (Supplemental Terms) chưa đọc được nguyên văn                                         | **[?]** chủ dự án tự mở [help.instagram.com/769983657850414](https://help.instagram.com/769983657850414)                                                                                                                           |

## 4. Đối chiếu với HBT Studio hiện tại

### 4.1 Tái sử dụng (theo `IMPLEMENT.md` và nhật ký trong context)

| Cần                                                                 | Đã có                                                                                    | Ghi chú                                               |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Căn chữ theo Whisper, cache `timing.json`, rơi về khoảng lặng       | `pipeline/align.py` (`align_whisper` **đã có trong mã**), `scene_align.py`, `text.py` (` | `, `{}`), §5.2                                        | M4 Đợt 1 chỉ thêm chọn model theo máy, timeout, `bench-align`. PostV **không bị chặn**: thiếu Whisper thì rơi về khoảng lặng |
| Karaoke nền vàng `#FFD43B`                                          | `pipeline/captions.py` §5.3                                                              | Dùng lại nguyên                                       |
| Giọng, ducking, −14 LUFS, cắt đuôi quảng cáo Vbee, `voice.trim_end` | `pipeline/audio.py` §4d, §6                                                              | Dùng lại                                              |
| Thư viện nhạc có id, tự chọn đoạn nhạc                              | `library/music/index.json`, `POST /music`                                                | **Đã xong** (Đợt 2, 23/10)                            |
| Outro 4 giây có lời                                                 | `brand/outro/`, `library/outro/voice.wav` §4c                                            | Dùng lại                                              |
| Ảnh bìa 9:16 + cắt 3:2                                              | `pipeline/thumbnail.py` §4e                                                              | **Đã xong** (Đợt 3)                                   |
| Kiểm tra từ nhạy cảm, `block`/`warn`/`info`, cả `{}`                | `pipeline/lint.py`, `/settings/sensitive-words`                                          | **Đã xong** (Đợt 2). PostV mở rộng quét văn bản nguồn |
| `publish.txt` + sao chép                                            | §8                                                                                       | Thêm dòng dẫn nguồn                                   |
| Job một luồng, SSE, huỷ; Xem nhanh, `preview_seconds`               | `jobs.py`, `POST /render`                                                                | Dùng lại                                              |
| Quy ước API (slug, 422, 503), tải file kèm giấy phép                | §9 (`POST /music` bắt buộc tên, tác giả, nguồn, giấy phép)                               | Làm thư viện nền theo mẫu này                         |
| Interface nhà cung cấp                                              | §12: `ScriptProvider`, `VoiceProvider` (VieNeu-TTS local / Vbee / thủ công)              | Dùng lại, không tạo interface mới                     |
| Giao diện                                                           | `DESIGN-HBT.md`, `i18n/vi.ts`, `utils/scene.ts`                                          | Chữ UI tiếng Việt, đánh số cảnh qua một chỗ           |

### 4.2 Phần mới

| Phần                                                     | Ghi chú                                                                         |
| -------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Ô dán + bộ tách bài/bình luận/số like                    | **[?]** chưa biết định dạng chữ khi copy từ Threads → cần mẫu thật              |
| Chọn đoạn, xếp hạng, thanh "tỉ lệ biến đổi"              | Người dùng có thể nhập tay số like                                              |
| Kịch bản kèm `commentary`                                | Bắt buộc có                                                                     |
| Thẻ bài đăng ẩn danh (Pillow)                            | Nối với `visual.py`                                                             |
| Thư viện nền `library/backgrounds/index.json` + endpoint | Mẫu theo thư viện nhạc                                                          |
| Renderer riêng cho cảnh nền video                        | `render.py` hiện zoompan trên **ảnh** (3240×5760, chuyển cảnh numpy). Không đổi |
| Chia lượt giọng >750 ký tự rồi nối                       | Gói Vbee 3.000 ký tự/ngày → khoảng 4 video 750 ký tự/ngày                       |
| OCR tiếng Việt chạy local (Should)                       | **[?]** độ chính xác dấu                                                        |
| Nhập giọng VieNeu-TTS (Should)                           | Xem 4.4                                                                         |
| Schema `project.json` cho PostV                          | Hiện `scenes[]` bắt buộc có `image`, 3–12 cảnh                                  |
| Giao diện 5 bước                                         | Hiện có Dự án, Soạn video, Âm thanh, Xuất video, Cài đặt                        |

### 4.3 Điểm cần chủ dự án / chat quản lý quyết

| #   | Vấn đề                                                                                                                                                 | Đề xuất của mình                                                                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A   | `CLAUDE.md`: _"Chưa xong cả sáu bước thì không bắt đầu mốc kế tiếp"_ và _"làm đúng mốc đang mở"_. Viết tài liệu PostV lúc M4 đang dở có vi phạm không? | Cho phép riêng, **chỉ tài liệu**, nhánh `docs/postv-design` từ `main`, đặt trong `docs/postv/`. Không sửa `PLAN.md`/`IMPLEMENT.md` đến khi M4 đóng                                                           |
| B   | PostV nằm ở đâu trong PLAN: Giai đoạn 2? Hay "ý tưởng sau GĐ1" (dạng video khác)?                                                                      | Đặt mốc riêng **PV0…PVn**, không đánh số lẫn với M0–M4. Quyết sau `v1.0.0`                                                                                                                                   |
| C   | Schema: `scenes[]` bắt buộc `image`                                                                                                                    | Thêm trường `mode: "postv"` (hoặc kiểu project) bằng union Pydantic; project cũ `version: 1` không đổi                                                                                                       |
| D   | Renderer: dùng chung `render.py` hay riêng                                                                                                             | **Đã chốt nền liền (quyết định 11).** Dùng chung bước 2–4, 7, 8, 10; tách bước 1, 5, 6, 9 (xem 4.3b). Không động tham số bản đẹp của video ảnh. Còn cần quyết: kiểu hiệu ứng vào/ra của thẻ (đề xuất ở 4.3b) |
| E   | `CLAUDE.md` còn dòng _"đọc `DESIGN.md` (Nike)"_, trong khi M3 đã chuyển sang `DESIGN-HBT.md` và context ghi _không đọc `DESIGN.md`_                    | Chat quản lý sửa `CLAUDE.md` cho khớp                                                                                                                                                                        |
| F   | Thẻ bài: OCR vẽ lại (mặc định) hay giữ ảnh chụp kèm che tên/avatar                                                                                     | OCR vẽ lại làm mặc định                                                                                                                                                                                      |
| G   | Nền Minecraft: tự quay hay dùng footage có giấy phép                                                                                                   | Tự quay 10–20 phút là đủ ghép nhiều video                                                                                                                                                                    |

### 4.3b Đối chiếu với mã (đọc 23/10 qua bản đồng bộ GitHub của Project)

**Lưu ý:** bản đồng bộ trong Project **cũ hơn `v0.4.0`**: `App.tsx` còn trang M0, `lint.py` chỉ có quy tắc 750 ký tự, thư viện nhạc chưa có id, chưa có `thumbnail.py`. Phần M3/M4 dưới đây dựa trên tài liệu, không phải mã. Nên bấm đồng bộ lại GitHub trong cài đặt Project.

**Cách bộ dựng chạy** (`pipeline/render.py` → `render_project`):

| Bước        | Hàm                                                                                                                                           | Ý nghĩa cho PostV                                                                                                    |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 1 Kiểm tra  | `load_project`, `render_problems`, `lint_project`                                                                                             | Cảnh bắt buộc có `image` → PostV cần nhánh kiểm tra riêng                                                            |
| 2 Giọng     | `audio.prep_voice` (trễ 0,2 s, đệm 1,6 s, −14 LUFS, mono)                                                                                     | **Một file giọng/project**                                                                                           |
| 3 Căn chữ   | `parse_voice` → `run_alignment` (Whisper → khoảng lặng), cache `timing.json`; `audio.trim_tail_if_needed` chỉ cắt **sau chữ cuối**            | Xem phát hiện 2                                                                                                      |
| 4 Mốc cảnh  | `compute_offsets` (giữa khoảng nghỉ giữa 2 cảnh), `clip_durations`                                                                            | Dùng lại nguyên                                                                                                      |
| 5 Lớp hình  | `visual.build_scene_layers` → `b{i}.png` (ảnh fit) + `t{i}.png` (thẻ kem `draw_card`), trả đáy thẻ                                            | PostV thay `draw_card` bằng thẻ bài đăng; giữ cách trả đáy thẻ để `caption_y_for` tự đẩy phụ đề lên 230 khi thẻ thấp |
| 6 Clip cảnh | `scene_clip`: `zoompan` trên **ảnh tĩnh** + thẻ hiện dần, chạy song song tối đa 3                                                             | Điểm phải mở rộng: nền **video**                                                                                     |
| 7 Âm thanh  | `pick_music_start`, `mix_audio` (ducking), whoosh, `build_outro_audio`, `join_audio`                                                          | Dùng lại nguyên                                                                                                      |
| 8 Phụ đề    | `build_phrases` → `render_states` (mỗi trạng thái 1 PNG) → `write_ffconcat`, `write_srt`                                                      | Dùng lại nguyên                                                                                                      |
| 9 Ghép      | `compose`: Python đọc từng khung rgb24 của các clip, trượt có nhoè (`slide_frame`, 6 mẫu con), hoà outro 0,5 s, đẩy vào encoder đã phủ phụ đề | Mọi khung đi qua Python → nguồn chính của ~3,6 s/giây video                                                          |
| 10 Kiểm tra | ffprobe, `measure_lufs`, `build_publish_text`, `meta.json`                                                                                    | Thêm dòng nguồn vào `publish.txt`                                                                                    |

Cache: mọi khoá có `PIPELINE_VERSION` = hash mã nguồn các module pipeline. Sửa `render.py`/`visual.py` → toàn bộ cache cũ mất hiệu lực (không lỗi, chỉ dựng lại lâu một lần).
Job: `JobManager.submit` kiểm tra `render_problems()` rồi gọi `render_fn` (có thể thay) → dễ cắm bộ dựng PostV.

**Phát hiện quan trọng cho thiết kế:**

1. **Dùng lại phần lớn bộ dựng, theo quyết định 11 (nền liền):**
   - Giữ nguyên: bước 2–4 (giọng, căn chữ, mốc cảnh), 7 (âm thanh, outro), 8 (phụ đề), 10 (kiểm tra, `publish.txt`).
   - Làm riêng trong `render_postv.py`: bước 1 (kiểm tra project PostV), 5 (vẽ thẻ bài), 6 + 9 gộp lại: **không** cắt clip từng cảnh, **không** dùng `slide_frame` cho nền.
   - Cách dựng đề xuất **[SL]**: nền = một đoạn gameplay dài bằng phần có lời (cắt/scale/crop 1080×1920, lặp nếu ngắn) → phủ lớp thẻ theo mốc cảnh từ bước 4 → phủ phụ đề → nối outro. Mốc đổi thẻ dùng lại `compute_offsets`.
   - Hiệu ứng thẻ đề xuất (cần duyệt): thẻ cũ trượt ra trái, thẻ mới trượt vào từ phải, `easeInOutCubic` 0,4 s (cùng thông số chuyển cảnh hiện có), có thể kèm nhoè chuyển động chỉ trên thẻ. Phương án nhẹ hơn: thẻ hiện dần 0,35 s như `CARD_FADE` hiện tại.
   - **[SL]** Nhanh hơn video ảnh vì không có `zoompan` trên ảnh 3240×5760 và không trượt cả khung hình qua Python. Cần đo thật trên hai máy.
2. **Chia lượt Vbee >750 ký tự: mỗi file Vbee đều có thể có quảng cáo ở cuối.** Bộ cắt hiện có chỉ cắt sau chữ cuối của **cả** video. PostV phải cắt đuôi **từng file** trước khi nối (dùng lại `plan_tail_trim` theo kịch bản của từng lượt), rồi mới vào bước 2.
3. **`models.Project`**: `version: Literal[1]`, `extra="ignore"`, 3–12 cảnh. Thêm trường `mode`/`postv` không phá project cũ; nhưng `render_problems()` đòi ảnh → cần sửa theo kiểu project.
4. **Thư viện nền**: làm giống `library.py` (`MusicEntry` bắt buộc `title`, `artist`, `source`, `license`) → `BackgroundEntry` + `library/backgrounds/index.json`.
5. **Tải file**: `storage.save_asset` chỉ nhận `image|voice|music`; PostV cần thêm loại "nhiều file giọng" và "ảnh chụp để OCR".

### 4.4 VieNeu-TTS **[KC]** ([GitHub](https://github.com/pnnbao97/VieNeu-TTS))

- Mã nguồn Apache 2.0, bản v3 Turbo mã nguồn mở; v4 độc quyền (chỉ qua API). Trang **không nêu giấy phép trọng số**.
- VRAM đỉnh ~1,1 GB (benchmark RTX 3060); 48 kHz; nhân bản giọng từ mẫu 3–8 giây. Trang không nhắc mốc thời gian từng từ → cần Whisper.
- CPU: int8 cần VNNI, máy cũ i5-10400 **[SL]** nên dùng fp32 (chưa thử).

## 5. Lịch đề xuất **[SL]**

| Bước                                                          | Khi nào                          |
| ------------------------------------------------------------- | -------------------------------- |
| Viết tài liệu PostV (docs-only)                               | Ngay, máy cũ, không ảnh hưởng M4 |
| Xong M4 (Đợt 1 Whisper trên máy mới + golden test) → `v1.0.0` | Theo kế hoạch hiện tại           |
| Build PostV                                                   | Sau `v1.0.0`                     |

Ước lượng thô, sẽ được tinh chỉnh trong `05-lo-trinh.md`: khoảng 10–12 buổi (≈3 giờ/buổi) cho PV0–PV5: nhập nguồn, thẻ bài + thư viện nền, chọn đoạn + kịch bản, renderer, giao diện, giọng nhiều lượt + OCR.

## 6. Chưa kiểm chứng (thành mốc kiểm thử riêng)

1. Chữ khi copy cả trang Threads: có số like không, ranh giới bình luận. Cần 3–5 mẫu thật do chủ dự án cung cấp.
2. Whisper tiếng Việt với giọng VieNeu thật (độ lệch phụ đề < 0,05 s như golden test hiện có).
3. Giấy phép trọng số VieNeu-TTS trước khi dùng cho kênh kiếm tiền.
4. OCR dấu tiếng Việt (Tesseract `vie`).
5. VieNeu fp32 trên máy cũ.
6. Điều khoản Threads gốc và quy trình App Review.

## 7. Việc nhờ chat quản lý

1. Đối chiếu mục 4 với `IMPLEMENT.md`/`PLAN.md`; báo chỗ nào mình hiểu sai.
2. Cho ý kiến về mục 4.3 (A–G).
3. Sửa lệnh `PROMPT-CLAUDE-CODE-POSTV.md` cho khớp luật `CLAUDE.md` và `/kickoff`, rồi trả bản cuối.
