# HBT Studio — Kế hoạch tổng thể

> Web app chạy **local** sản xuất video ngắn cho kênh **Hay Biết Tuốt** (TikTok, YouTube Shorts, Facebook Reels).
> Phiên bản kế hoạch: **v2.0 · 09/11/2026** — Kế hoạch & lộ trình duy nhất cho toàn bộ hệ thống HBT Studio.
> Quy tắc tài liệu: **Đặc tả chỉ ở IMPLEMENT.md, kế hoạch chỉ ở PLAN.md**. File cũ lưu tại `docs/archive/`.

---

## 1. Bài toán & Mục tiêu

Quy trình sản xuất nội dung video ngắn chuyển từ thủ công phân tán sang tự động hoá local trong một web app duy nhất:
- **Dạng 1 · HBT Video (GĐ1):** Video thông tin khoa học/đời sống 8 cảnh, 50fps, phụ đề karaoke Whisper chính xác, zoompan chuyển cảnh mượt mà, ducking nhạc tự động, xuất bản kèm ảnh bìa và mô tả.
- **Dạng 2 · GĐ2 Bán tự động:** Claude chat sinh JSON nháp `hbt_draft: 1` → ComfyUI local hoặc đường tay vẽ ảnh → VieNeu-TTS đọc tiếng Việt → tự chọn nhạc theo mood.
- **Dạng 3 · PostV (Mạng xã hội):** Video chuyển thể bài viết/bình luận ngắn (Threads/FB/Reddit) trên nền gameplay dọc 60fps, giọng đọc đa nhân vật VieNeu, thẻ Pillow bo góc, che từ nhạy cảm K-41, meme phông xanh PV7b, Quick UI 1 chạm PV9.
- **Dạng 4 · Chatting (Tin nhắn hội thoại):** Video chat đối thoại 2–4 người kiểu Messenger/Zalo trên nền gameplay dọc 60fps, Ollama `qwen2.5:3b-instruct` viết kịch bản, sticker 10 tag cảm xúc, âm thanh pop/typing, giọng VieNeu.

## 2. Nguyên tắc bất biến

1. **Chạy local, dữ liệu tại máy người dùng:** Server chỉ lắng nghe tại `127.0.0.1`.
2. **Con người duyệt ở các điểm kiểm soát:** Kịch bản → Hình ảnh/Sticker → Video xuất xưởng.
3. **Kịch bản là nguồn chữ chuẩn:** Phụ đề/bong bóng lấy chữ từ kịch bản, Whisper/VieNeu lấy mốc thời gian.
4. **Không làm vỡ logic đã kiểm chứng:** Vùng cấm `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`.
5. **Mã nguồn trên Git, media không lên Git:** `workspace/`, `models/`, media file đều nằm ngoài git.

## 3. Lộ trình tổng hợp các giai đoạn (HBT · PostV · GĐ2 · Chatting · GĐ4)

| Mốc | Tên & Phạm vi | Kết quả & Kiểm chứng | Phiên bản / Tag |
|---|---|---|---|
| **M0** | Khởi tạo repo, môi trường, FastAPI + React Vite | Mở được web app và gọi `/health` | `v0.1.1` |
| **M1** | Port bộ dựng video từ `reference/pipeline/` | Dựng video "muỗi" 50fps, chuẩn hoá −14 LUFS | `v0.2.0` |
| **M2** | Backend API CRUD, tải media, SSE progress | Gọi API curl dựng được video trọn vẹn | `v0.3.0` |
| **M3** | Web UI soạn thảo cảnh, nhạc, xuất video | Làm trọn 1 video bằng giao diện web | `v0.4.0` |
| **M4** | Whisper phụ đề karaoke, lint từ nhạy cảm, publish | Căn chữ chính xác, cảnh báo từ nhạy cảm | `v0.5.1` |
| **M5** | Giao diện mới v2 + Hộp dán JSON kịch bản | 6 màn hình mockup v2, dán JSON thẻ chữ | `v0.6.0` |
| **v1.0** | Polish: Bộ đếm ký tự trong ô, dọn file tạm | Đóng gói Giai đoạn 1 | `v1.0.0` |
| **v1.1** | Tải ảnh bìa riêng, cắt ảnh cover tự động | Hỗ trợ ảnh bìa tuỳ chỉnh | `v1.1.0` |
| **PV0** | Đo lường hiệu năng VieNeu, Whisper, PostV | Khảo sát tính khả thi trên máy cũ | — |
| **PV1** | Schema `kind: "postv"`, lưu trữ và API cơ bản | Hỗ trợ 2 loại dự án song song trong app | `v1.2.0` |
| **PV2** | Nhập nguồn & bóc tách bài viết/bình luận, từ che | Thanh bước ngang, phân tích chữ dán | `v1.3.0` |
| **PV3** | Thẻ bài Pillow & Thư viện nền gameplay dọc | Thẻ bo góc, clip nền gameplay dọc | `v1.4.0` |
| **PV4** | Giọng đọc VieNeu-TTS (đa nhân vật) | Phân vai người dẫn + người bình luận | `v1.5.0` |
| **PV5** | Bộ dựng PostV FFmpeg 60fps, che từ nhạy cảm K-41 | Dựng 1 lệnh FFmpeg duy nhất, bíp + mờ | `v1.6.0` |
| **PV6** | UI bước 4–5, xem trước tĩnh, bìa gameplay | Hoàn thiện giao diện 5 bước PostV | `v1.7.0` |
| **PVA** | Tự động hoá 7 pha (PVA Auto) | Dán chữ → video Xem nhanh 10 s | `v1.8.0` |
| **PV8** | Hoàn thiện PostV, nới lỏng metadata clip nền | Tối ưu trải nghiệm sử dụng thư viện nền | `v1.9.0` |
| **PV7** | Sửa thả ảnh bìa, bình luận lồng, thẻ cố định | `cli pack-media`/`unpack-media` | `v1.10.0` |
| **G0** | Đặc tả GĐ2 (PRD, IMPLEMENT-GD2, Prompt) | Tài liệu thiết kế Giai đoạn 2 | — |
| **G1** | JSON nháp `hbt_draft: 1`, tạo dự án từ nháp | Tạo dự án 1 click, tự chọn nhạc theo mood | `v1.11.0` |
| **G2+G3**| Duyệt ảnh dấu ảnh + Giọng VieNeu cho HBT | `{}` và `|`, nhớ giọng gần nhất | `v1.13.0` |
| **PV7b** | Meme phông xanh & bóc tách link Threads | `greenscreenmemes.com`, Meta Bot SSR | `v1.14.0` |
| **PV9** | Giao diện Quick UI PostV ("Dán link/chữ → Video") | SSE 6 pha, khung chat hiện đại | `v1.15.0`–`v1.15.2`|
| **CH0** | Chuẩn bị Chatting: Ollama Qwen2.5-3B, Stickers | Cài đặt Ollama local, nạp 10 tag sticker | — |
| **CH1** | Backend Core Chatting (Models, Sources, LLM, API) | Pydantic v2, Ollama client, parse Reddit | — |
| **CH2** | Theme Messenger/Zalo, Pillow draw, Timeline, Render | Dựng video chat 9:16, âm thanh pop/typing | — |
| **CH3** | Frontend Chatting UI (Trang chủ & Editor 3 cột) | UI hiện đại, SSE đếm giây, e2e test | — |
| **CH4** | Benchmark Ollama, gộp tài liệu IMPLEMENT/PLAN | Bench 3 runs (~91s), tài liệu hợp nhất | `v1.16.0` |
| **G4** | ComfyUI SDXL local tạo ảnh HBT tự động | Chạy trên máy mới có GPU rời (chờ máy mới) | `v1.17.0` (dự kiến) |
| **GĐ4** | Threads API chính thức & Tối ưu hàng loạt | Mở rộng quy mô sản xuất đa kênh | Tương lai |

## 4. Nhật ký quyết định (Thu gọn 1 dòng/quyết định)

### 4.1 HBT Studio (M0–M5, v1.0, v1.1)
- **20/10/2026:** Web app local 127.0.0.1, mã nguồn trên Git, media ignore; 3 điểm duyệt kịch bản → ảnh → video.
- **20/10/2026:** Tái sử dụng logic pipeline `reference/`; kiểm tra `/health` yêu cầu đủ FFmpeg và các filter cần thiết.
- **21/10/2026:** Mặc định 50fps + easing + phóng 3 lần + xfade; thêm outro 4s; lời đọc giới hạn 750 ký tự; ảnh bìa 9:16 & 3:2.
- **21/10/2026:** Cắt đuôi giọng Vbee (silence aligner) tự động khi có đoạn thừa; đệm 1.6s sau câu cuối; chuẩn hoá −14 LUFS.
- **21/10/2026:** Nhận diện ký hiệu `{cách đọc}` trong lời thoại; outro dùng clip 4s cố định và âm thanh ting 0.30.
- **22/10/2026:** Quy định hồ sơ 2 máy: Máy cũ (i5-10400 CPU) và Máy mới (i5-14400F, RTX 2060 Super 8GB).
- **24/10/2026:** Whisper chạy tiến trình con độc lập; bậc rơi CUDA → CPU small int8 → khoảng lặng; bỏ `initial_prompt`.
- **26/10/2026:** Phụ đề karaoke: từ đang đọc đổi màu vàng `#FFD43B`, bỏ viên thuốc nền; nạp DLL CUDA Windows an toàn.
- **27/10/2026:** Đóng M4 theo phạm vi máy cũ (golden test đạt bằng mắt/tai); M5 duyệt thiết kế v2 (mockup v2 + DESIGN-HBT v2).
- **27/10/2026:** Khối JSON kịch bản: nhận dạng đầy đủ hoặc mảng ngắn, kiểm tra K1–K12, hỗ trợ 10 bản sao lưu và hoàn tác.
- **28/10/2026:** Đợt v1.0.0: Bộ đếm ký tự đặt trong ô input; Storage dọn file tạm; fix lỗi e2e xoá dự án và menu bị che.
- **28/10/2026:** Đợt v1.1.0: Thêm ảnh bìa tải lên `thumbnail.image` (`POST /assets kind=cover`), cắt giữa cover, giữ nguyên pipeline cũ.

### 4.2 Giai đoạn 2 (GĐ2)
- **E1–E2 (02/11/2026):** Dữ liệu nháp lưu `draft.json` cạnh `project.json`; định dạng phẳng `hbt_draft: 1`; tạo dự án từ nháp.
- **E2b–E3 (02/11/2026):** Khoá tâm trạng `music_mood`; kiểm tra nháp K13–K18 (K16 so theo số liệu, K17 chặn từ cấm vẽ bản đồ/chữ).
- **E4–E4b (02/11/2026):** VieNeu cho HBT: `{cách đọc}` đọc trong ngoặc, `|` nghỉ 0.25s; nhớ lựa chọn giọng gần nhất vào settings.
- **E5–E6 (02/11/2026):** Tự chọn nhạc theo mood khớp trường `moods[]` trong index; ComfyUI local cổng 8188 (fallback đường tay).
- **E7 (02/11/2026):** Module GĐ2 tách riêng tại `backend/hbt/gd2/` và `api/gd2.py`, không sửa `api/projects.py`.

### 4.3 PostV (K-01 đến K-48)
- **K-01–K-03 (29/10/2026):** Bộ dựng `postv/render.py` độc lập; fps hỗ trợ 60/50/30 (mặc định 60); thời lượng tự do dưới 120s.
- **K-04–K-06 (29/10/2026):** Giọng VieNeu local thay Vbee; nền gameplay dọc ≥ 720×1280; bìa ưu tiên ảnh tải lên hoặc cắt gameplay.
- **K-10–K-12 (29/10/2026):** Chỉ nhận video nền dọc; mặc định 60fps; outro 60fps dùng `outro_4s_60fps.mp4` dựng sẵn.
- **K-23–K-26 (29/10/2026):** Thẻ bài bo góc 90%; phụ đề 1–3 từ karaoke; hiển thị 3 số liệu (like, cmt, share) trên thẻ bài.
- **K-27, K-41 (29/10/2026):** Che từ nhạy cảm riêng PostV (`censor_words.json` + từ cấm HBT); bíp 1kHz 0.35 + mờ thẻ/phụ đề.
- **K-33–K-35 (29/10/2026):** Không dùng `{}` hay `|` cho PostV; tách riêng mã PostV (N8); người dẫn mặc định Adam bựa.
- **K-36–K-38 (29/10/2026):** Thanh 5 bước ngang ở đầu màn `/postv/:slug`; trang danh sách `/postv` và nav PostV riêng.
- **K-42–K-48 (29/10/2026):** Không AI viết lời trong app (dán JSON hoặc Claude code); PVA tự động 7 pha dừng ở Xem nhanh 10s.
- **PV7b (06/11/2026):** Meme phông xanh greenscreenmemes.com lọc `colorkey`; bóc tách link Threads tự động bằng Meta Bot SSR.
- **PV9 (06/11/2026):** Giao diện Quick UI "Dán link/chữ → Video" tại `/postv`, pipeline 6 pha SSE stream, tuỳ chọn chip nhanh.

### 4.4 Chatting (CH-D1 đến CH-D7)
- **CH-D1 (07/11/2026):** Backend chỉ gọi mạng khi dán link Reddit công khai (.json); Threads trả 422 yêu cầu dán chữ; chặn socket ngoài.
- **CH-D2 (07/11/2026):** Ollama local model mặc định `qwen2.5:3b-instruct`; luôn gửi `keep_alive: 0` nhả RAM ngay; format JSON schema; đo `timings`.
- **CH-D3 (07/11/2026):** Lưu trữ riêng tại `workspace/chatting/<slug>/chat.json` + `source.json`; không DB, không đụng `api/projects.py`.
- **CH-D4 (07/11/2026):** Vẽ giao diện chat bằng Pillow (1080×1920) kiểu Messenger/Zalo; không in logo/tên app lên video.
- **CH-D5 (07/11/2026):** Avatar nhân vật kéo thả người dùng hoặc vẽ tròn chữ cái đầu của tên nhân vật.
- **CH-D6 (07/11/2026):** Sticker từ thư viện local `library/stickers/<tag>/` (10 tag cảm xúc); index.json, chọn ngẫu nhiên theo seed.
- **CH-D7 (07/11/2026):** 2 Theme ban đầu: Messenger và Zalo; cấu trúc mở rộng ThemeBase hỗ trợ thêm theme sau.
- **Quyết định 09/11/2026 (Threads Chatting & Sanitize):** Threads trong Chatting dùng chung PV7b (`extract_threads_post`), rủi ro bị chặn; có đường dán chữ; chuyển API chính thức khi xong GĐ4. Tự động sanitize kịch bản LLM (cắt tin $\le$ 900 ký tự ưu tiên giữ tin đầu + 2 tin cuối, lọc sticker dư), trả cảnh báo số tin cắt và sticker bỏ trên UI.
- **CH5 (10/11/2026):** Tách sạch lời thoại TTS (lọc mốc giờ 20:15, đã xem, mô tả sticker sang divider mờ giữa màn hình); hybrid sub-frames 60fps mượt mà ở các pha động (typing sóng sin, popup spring ease-out, cuộn trượt êm), giữ 1 frame tĩnh ở pha thoại; thiết kế UI Messenger chuẩn (header avatar kèm active dot xanh #31A24C, grouped bubble bo góc bất đối xứng 8px).

---

## 5. Tiến độ thực hiện & Số lượng kiểm thử

| Mốc | Trạng thái | Phiên bản | Ghi chú & Kết quả kiểm thử |
|---|---|---|---|
| M0–M4 | ☑ | `v0.5.1` | Hoàn thiện pipeline HBT cốt lõi, Whisper, Lint, Publish |
| M5 | ☑ | `v0.6.0` | Giao diện v2, dán JSON kịch bản (757 pytest, 761 vitest, 7 e2e) |
| v1.0.0 | ☑ | `v1.0.0` | Bộ đếm trong ô, dọn file tạm (760 pytest, 764 vitest, 8 e2e) |
| v1.1.0 | ☑ | `v1.1.0` | Ảnh bìa tải lên (814 pytest, 774 vitest, 9 e2e) |
| PV1–PV6 | ☑ | `v1.7.0` | Toàn bộ quy trình PostV 5 bước (1118 pytest, 930 vitest, 14 e2e) |
| PVA–PV8 | ☑ | `v1.9.0` | PVA tự động, clip nền linh hoạt (1136 pytest, 945 vitest, 16 e2e) |
| PV7 | ☑ | `v1.10.0`| Fix cover drop, thẻ cố định, pack-media (1153 pytest, 947 vitest, 17 e2e) |
| G1–G3 | ☑ | `v1.13.0`| JSON nháp HBT, duyệt ảnh, VieNeu HBT (1241 pytest, 993 vitest, 21 e2e) |
| PV7b | ☑ | `v1.14.0`| Meme phông xanh, bóc link Threads tự động |
| PV9 | ☑ | `v1.15.2`| Quick UI PostV dán link 1 chạm (e2e baseline 22 passed) |
| **CH0–CH4**| ☑ | **`v1.16.0`**| **Chatting hoàn chỉnh (Ollama Qwen2.5-3B, Messenger/Zalo, stickers, UI 3 cột, bench ~91s, gộp tài liệu)** |
| **Fix Chatting** | ☑ | **`v1.16.1`** | **Sanitize LLM (cắt tin $\le$ 900 ký tự giữ đầu + 2 cuối, lọc sticker), cảnh báo UI, hỗ trợ Threads** |
| **CH5** | ☑ | **`v1.18.1`** | **Cải tiến Chatting: Tách sạch lời thoại TTS (bỏ mốc giờ/mô tả), hybrid sub-frames 60fps mượt (typing sine wave, pop spring, cuộn mượt), UI Messenger chuẩn (header avatar active, grouped bubble)** |
| **Phase 6** | ☑ | **`v2.1.0`** | **Creator Workstation: PostV video/gif & meme cap, SQLite Media Index (`workspace/studio.db`), Kanban 4 cột, Clipper 9:16, OpenCut-style Video Editor + Safe-Zone, Scheduler UI (CI run 43399203837 xanh)** |
| G4 | ☐ | `v1.19.0` | ComfyUI SDXL local (chờ setup trên máy mới có GPU) |
| GĐ4 | ☐ | — | Threads Graph API chính thức, mở rộng xuất video đa kênh |
