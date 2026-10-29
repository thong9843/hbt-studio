# 02 — PRD PostV

Ngày 29/10/2026 · Nguồn: `POSTV-BRIEF.md`, `01-nghien-cuu-POSTV.md` (23/10, viết từ mã cũ hơn `v0.4.0`), mã `main` `b086d06` (`v1.1.0`), các câu chủ dự án chốt 29/10.
Ký hiệu: **[KC]** đã kiểm chứng · **[SL]** suy luận · **[?]** chưa biết.
Tài liệu đi kèm: `IMPLEMENT-POSTV.md` (đặc tả), `06-cau-hoi-mo.md` (câu cần chốt).

## 1. Mục tiêu

| #   | Mục tiêu                                                                                                              | Số đo                                              |
| --- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| G1  | Dựng video 9:16 kiểu "đọc bài mạng xã hội trên nền gameplay" từ chữ **người dùng tự dán**, có góc nhìn riêng của kênh | 1 video 35–75 s làm trọn trong app, không terminal |
| G2  | Dùng lại tối đa phần đã chạy thật của HBT Studio (căn chữ, nhạc, outro, bìa, lint, `publish.txt`, job)                | Không sửa `backend/hbt/pipeline/` ở mốc nào        |
| G3  | Không làm hỏng video kiểu cũ                                                                                          | Dựng lại "muỗi": framemd5 giống `v1.1.0`           |
| G4  | An toàn pháp lý: không cào, không gửi yêu cầu tới Threads/Meta, ẩn danh mặc định, dẫn nguồn, có bước duyệt của người  | Test chặn mạng; thẻ không có tên/avatar thật       |
| G5  | Chạy local, một người dùng, hai máy, **không giả định GPU**                                                           | Đủ chạy trên máy cũ (CPU)                          |

## 2. Quyết định đã chốt

| #   | Quyết định                                                                                                       | Nguồn                          |
| --- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| D1  | Gộp vào HBT Studio, tên **PostV**; dùng chung job, thư viện nhạc, outro, bìa, lint, `publish.txt`                | Brief #1                       |
| D2  | Dán tay là đường chính; link chỉ lưu làm dòng dẫn nguồn + nút mở bài                                             | Brief #2, #3                   |
| D3  | Cấm cào, headless, dịch vụ cào, Threads API, oEmbed                                                              | Brief mục 3                    |
| D4  | Thẻ bài vẽ bằng Pillow, tên ẩn danh, không logo/tên/giao diện Threads, Meta, Reddit                              | Brief #4                       |
| D5  | Commentary (góc nhìn kênh) **bắt buộc**; thời lượng đích 35–75 s                                                 | Brief #6                       |
| D6  | Nền gameplay chạy liền; chỉ thẻ có hiệu ứng vào/ra                                                               | Brief #11                      |
| D7  | Phong cách Hooked; mẫu A "Thẻ cố định" làm trước, mẫu B "Chuỗi bình luận" sau                                    | Brief #12, 2b                  |
| D8  | Ba điểm duyệt của người: nguồn → đoạn/kịch bản → video cuối; không tự đăng                                       | Brief #9                       |
| D9  | Không đổi tham số bản đẹp HBT (`PIPELINE_VERSION` giữ nguyên)                                                    | CLAUDE.md                      |
| D10 | **Giọng: VieNeu-TTS chạy local thay Vbee** cho PostV. Nhập file giọng vẫn là đường dự phòng (rẻ, đã có)          | Chủ dự án 29/10 (đổi Brief #7) |
| D11 | PostV **bỏ giới hạn 750 ký tự** (đó là giới hạn gói Vbee). Cảnh báo theo **giây** 35–75 s                        | Chủ dự án 29/10 + đề xuất đợt  |
| D12 | fps xuất hỗ trợ **30, 50, 60**; mặc định 50 (đề xuất, còn câu mở C-05 về 60)                                     | Chủ dự án 29/10                |
| D13 | Nền: chủ dự án có **nhiều video gameplay full HD 60 fps, đủ giấy phép**; ngắn hơn lời thì **nối thêm clip khác** | Chủ dự án 29/10                |
| D14 | Bìa: ưu tiên `thumbnail.image`; không có thì lấy **khung gameplay**                                              | Chủ dự án 29/10                |
| D15 | Bước chép 2–4 của `_render_project` vào `backend/hbt/postv/` ở PV đầu (không sửa `render.py`)                    | Đề xuất đợt, chủ dự án duyệt   |
| D16 | Đợt fix/cover-drop hoãn đến khi xong hết PostV                                                                   | Chủ dự án 29/10                |
| D17 | CUDA (VieNeu, Whisper lớn) chỉ cần máy mới khi kiểm đường CUDA; còn lại làm trên máy cũ                          | Chủ dự án 29/10                |

## 3. User story và tiêu chí chấp nhận

| #    | Người dùng muốn…                                                         | Chấp nhận khi…                                                                                                                                                                   |
| ---- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| US1  | Dán cả trang Threads vào một ô, app tách bài + bình luận (+ like nếu có) | Với 3–5 mẫu thật (PV0) tách đúng bài gốc và từng bình luận; sửa tay được từng khối; nhập link chỉ lưu `source.url`; **không có request ra ngoài** (test chặn mạng)               |
| US2  | Chọn bài gốc và 1–5 bình luận làm nội dung                               | Chọn/bỏ/đổi thứ tự được; hiện ước lượng thời lượng theo giây; số like nhập tay được                                                                                              |
| US3  | Viết kịch bản gồm lời dẫn + trích bình luận + **góc nhìn riêng**         | Thiếu commentary → chặn xuất; trích nguyên văn quá ngưỡng → cảnh báo; ngoài 35–75 s → cảnh báo (không chặn)                                                                      |
| US4  | Có giọng đọc cho kịch bản                                                | Sinh bằng VieNeu local (CPU được) hoặc nhập file; nghe thử trong app; lời đọc dùng cú pháp `\|` và `{}` như video HBT                                                            |
| US5  | Thẻ bài đăng đẹp, ẩn danh                                                | Pillow, tên ẩn danh sửa được, không logo/giao diện nền tảng nào, dấu tiếng Việt đúng (font trong `backend/hbt/fonts/`); xem trước PNG                                            |
| US6  | Chọn nền từ thư viện gameplay của mình                                   | Mỗi clip có nguồn + giấy phép, thiếu thì chặn xuất; nền ngắn hơn lời thì tự nối clip khác; nền chạy liền suốt video                                                              |
| US7  | Xem nhanh trước khi xuất                                                 | Xem nhanh 540×960, 30 fps, ≤ 10 s đầu, dùng lại cache                                                                                                                            |
| US8  | Xuất video hoàn chỉnh                                                    | 1080×1920 ở 30/50/60 fps; thẻ hiện dần 0,35 s (phóng 0,25 s là tuỳ chọn); phụ đề kiểu Hooked; nhạc ducking −14 LUFS (±1); outro 4 s (công tắc); bìa; `publish.txt` có dòng nguồn |
| US9  | Được cảnh báo từ nhạy cảm và nội dung rủi ro                             | Quét nguồn + kịch bản + hook bằng danh sách hiện có; mức `block` chặn xuất; đời tư người thường/tố cáo/tin đồn có nhóm từ riêng [SL]                                             |
| US10 | Video HBT cũ không bị ảnh hưởng                                          | `project.json` cũ đọc nguyên; "muỗi" dựng nguội: framemd5 hình + tiếng giống `v1.1.0`; `git diff v1.1.0 -- backend/hbt/pipeline/ reference/` rỗng                                |
| US11 | Gỡ nguồn/video khi chủ bài yêu cầu                                       | Nút **Xoá nguồn** xoá chữ nguồn trong project (giữ kịch bản đã biến đổi); xoá lần xuất có sẵn                                                                                    |

## 4. Ưu tiên

| Mức        | Nội dung                                                                                                                                                               |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Must**   | US1–US6, US8–US11 · mẫu A "Thẻ cố định" · schema `kind:"postv"` · thư viện nền có giấy phép · VieNeu local hoặc nhập file · lint nguồn · màn 5 bước theo DESIGN-HBT v2 |
| **Should** | Xem nhanh (US7) · số like chạy tăng dần trên thẻ · nhập `.txt/.md` · OCR ảnh chụp (vẽ lại, che tên/avatar) · VieNeu qua CUDA · chọn tên ẩn danh tự động                |
| **Could**  | Mẫu B "Chuỗi bình luận" (thẻ đổi theo đoạn, đường kẻ lồng) · sticker từ thư viện có giấy phép · đổi nền theo đoạn · `ScriptProvider` gợi ý chọn đoạn (GĐ2)             |
| **Won't**  | Xem mục 5                                                                                                                                                              |

## 5. Ngoài phạm vi

| Hạng mục                                                  | Lý do                                                              |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| Cào, headless, dịch vụ cào bên thứ ba, tải trang từ link  | Meta cấm truy cập dữ liệu ngoài API [KC]                           |
| Threads API, oEmbed lấy chữ                               | Không có căn cứ rõ cho việc dựng video; oEmbed cấm trích xuất [KC] |
| Tự đăng lên nền tảng                                      | Giữ 3 điểm duyệt của người                                         |
| AI tự bịa bài/bình luận                                   | Rủi ro "nội dung giả" (bài học từ Hooked)                          |
| Tên/avatar thật, logo hay giao diện Threads, Meta, Reddit | Thương hiệu duy nhất trong app là HBT                              |
| Meme/sticker của người khác                               | Chỉ nhận từ thư viện có giấy phép                                  |
| Vbee API, chia lượt Vbee, cắt quảng cáo từng file Vbee    | Chủ dự án bỏ Vbee cho PostV (D10)                                  |
| Đăng nhập, nhiều người dùng, gửi dữ liệu ra ngoài         | CLAUDE.md                                                          |
| Sửa `backend/hbt/pipeline/`, `reference/`                 | D9; ngoại lệ chỉ khi chủ dự án duyệt riêng                         |

## 6. Ràng buộc pháp lý và an toàn (Must)

| Ràng buộc                                                       | Cách đáp ứng                                                         |
| --------------------------------------------------------------- | -------------------------------------------------------------------- |
| Không gửi yêu cầu tới Threads/Meta                              | Link chỉ lưu chuỗi; nút "Mở bài" mở tab trình duyệt của người dùng   |
| Che danh tính người đăng và người bình luận                     | Thẻ vẽ lại, tên ẩn danh; không lưu avatar                            |
| Phần biến đổi chiếm tỉ lệ đáng kể                               | Commentary bắt buộc + thanh tỉ lệ biến đổi + cảnh báo đọc nguyên văn |
| Nội dung nhạy cảm                                               | Mở rộng `sensitive.py`/`lint` quét nguồn và kịch bản                 |
| Nền: nguồn + giấy phép từng clip                                | `BackgroundEntry` bắt buộc `source`, `license`                       |
| Giấy phép trọng số VieNeu-TTS trước khi dùng cho kênh kiếm tiền | **[?]** kiểm ở PV0 (xem C-03)                                        |
| Điều khoản Threads gốc chưa đọc được nguyên văn                 | **[?]** chủ dự án tự mở `help.instagram.com/769983657850414`         |

## 7. Brief ↔ mã

Đối chiếu ngày 29/10/2026 trên `main` `b086d06`. Brief viết 23/10 từ bản đồng bộ cũ hơn `v0.4.0`.

| #   | Brief ghi                                                             | Mã thật                                                                                                                                                                                                                     | Hệ quả cho PostV                                                                                                        |
| --- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| B1  | Bước 2–4 (giọng, căn chữ, mốc cảnh) "dùng lại nguyên"                 | Ba bước nằm thẳng trong `_render_project` (`pipeline/render.py`), không có hàm riêng. Import được: `tokens_of`, `run_alignment`, `scene_offsets`, `compute_offsets`, `clip_durations`                                       | Chép phần điều phối sang `postv/` (D15); tách hàm ở `render.py` là ngoại lệ, để sau                                     |
| B2  | `render.py` chỉ cần "điểm cắm tối thiểu"                              | `PIPELINE_VERSION` băm cả file `render.py` → sửa một dòng cũng làm nguội cache. `JobManager(render_fn=…)` trong `jobs.py` đã là điểm cắm; `jobs.submit` gọi `render_problems()` và `lint_project()` nên phải rẽ theo `kind` | Không sửa `render.py`; rẽ nhánh ở `jobs.py`                                                                             |
| B3  | Karaoke "nền vàng `#FFD43B`"                                          | Từ 26/10: chữ đang đọc đổi **màu** vàng, đã bỏ nền viên thuốc (`visual.render_caption`, `HIGHLIGHT`)                                                                                                                        | Hooked cần kiểu riêng (xem B5)                                                                                          |
| B4  | Thư viện nhạc "chưa có id" (bản cũ)                                   | Đã có `id`, `MusicLibrary.find`, `POST /music` bắt buộc tên, tác giả, nguồn, giấy phép (`library.py`)                                                                                                                       | `BackgroundLibrary` copy mẫu này                                                                                        |
| B5  | Phụ đề dùng lại `captions.py`                                         | `MAX_TOKENS = 7`, `render_caption` cố định ExtraBold 70, 2 màu, `maxw` 900. `Phrase`, `write_ffconcat`, `write_srt` dùng lại được                                                                                           | PostV có bộ tách cụm 1–3 từ và bộ vẽ trạng thái riêng                                                                   |
| B6  | Thêm `mode`/union Pydantic là đủ                                      | `Project.version: Literal[1]`; `Storage.load` gọi thẳng `Project.model_validate` rồi lặp `scenes`; `list_projects` đọc `scenes[0].image`; `models.load_project`; `render_problems` đòi ảnh                                  | Đặt `PostvProject` ở `postv/models.py`, dispatch theo `kind` ở `storage.py` (`load_any`); **không cần sửa `models.py`** |
| B7  | `publish.txt` chỉ thêm dòng nguồn                                     | `build_publish_text(project: Project)` nằm trong `pipeline/`. Bìa: `make_covers` đọc `project.scenes`, nhưng `render_cover` + `save_covers` nhận đường dẫn ảnh                                                              | `postv/publish.py` riêng; bìa gọi `render_cover` trực tiếp                                                              |
| B8  | `ScriptProvider`, `VoiceProvider` "dùng lại, không tạo interface mới" | `ScriptProvider.draft(topic, series, n_scenes) -> ProjectDraft` theo cảnh ảnh, không có `commentary`. `VoiceProvider.synthesize(text, voice_id) -> bytes` dùng được                                                         | Mở rộng `ScriptProvider` (Could) hoặc thêm `PostvDraft`; VieNeu cắm vào `VoiceProvider`                                 |
| B9  | Điểm A (viết tài liệu lúc M4 dở) và E (CLAUDE.md còn Nike)            | M4 đã đóng (27/10); CLAUDE.md đã trỏ `DESIGN-HBT.md` và cấm Nike                                                                                                                                                            | Hết hiệu lực                                                                                                            |
| B10 | IMPLEMENT §9 ghi ảnh `scene-NN`                                       | `storage.py`: `images/<sha256-16>.<ext>`; project cũ dạng `scene-NN` tự đổi khi `load`; ngoại lệ `images/cover.<ext>`                                                                                                       | PostV không dùng `images/` cho cảnh; nền ở `library/backgrounds/`                                                       |

### 7b. Thay đổi do chốt 29/10 (VieNeu thay Vbee)

| Brief ghi                                                                        | Nay                                                                                                  |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| #7 "Vbee trước, VieNeu sau (Should)"                                             | VieNeu local là đường chính của PostV; nhập file giọng là dự phòng                                   |
| 4.2 "Chia lượt giọng > 750 ký tự rồi nối"; phát hiện 2 (cắt đuôi từng file Vbee) | Bỏ. VieNeu không chèn quảng cáo; một lần sinh cho cả kịch bản                                        |
| 4.1 giới hạn 750 ký tự (gói Vbee 3.000 ký tự/ngày)                               | Bỏ cho PostV; cảnh báo theo giây 35–75 s. `lint.VOICE_CHAR_LIMIT` giữ nguyên cho video HBT           |
| 4.4 VieNeu "Should"                                                              | **Must** (D10); thêm rủi ro giấy phép trọng số, tốc độ CPU, độ lệch Whisper trên giọng VieNeu        |
| 2b/4.3b nền "gameplay cắt/scale/crop"                                            | Nguồn 60 fps full HD; khung ngang 16:9 hay dọc **[?]** (C-01) quyết định cách cắt; fps xuất 30/50/60 |

## 8. Chỉ số thành công

| Chỉ số                                             | Ngưỡng                                                          |
| -------------------------------------------------- | --------------------------------------------------------------- |
| Thời gian làm 1 video PostV (từ dán đến file xuất) | ≤ 20 phút thao tác + thời gian dựng                             |
| Thời gian dựng bản đẹp 50 fps, ~60 s, máy cũ       | **[?]** đo ở PV5; mục tiêu ≤ video "muỗi" (≈ 145–170 s) [SL]    |
| Chữ phụ đề lệch lời đọc                            | Xem bằng mắt/tai, không cụm nào lệch (cùng tiêu chí golden HBT) |
| Video HBT cũ                                       | Không đổi (US10)                                                |
