# HBT STUDIO WEB — ĐẶC TẢ TỔNG REFACTOR KIẾN TRÚC, TỐI ƯU CPU/RAM & THANH TIẾN TRÌNH SIDEBAR CỐ ĐỊNH

> **Mốc xuất phát:** `main` @ `2ef40cf` · **Mục tiêu chất lượng:** Giảm rõ rệt Peak RAM & CPU khi dựng video 60fps trên `i5-10400` / 16 GB RAM (0 GPU rời) mà **giữ nguyên 100% chất lượng đầu ra**, chuẩn hóa **1 Thanh Tiến Trình Cố Định duy nhất tại Sidebar trái** cho cả 4 động cơ (bao gồm StickV), và xóa sạch file chết/code thừa.

---

## 0. LUẬT BẤT BIẾN & GIỚI HẠN AN TOÀN (KHÔNG ĐƯỢC PHÁ)

1. **Git & Tài sản cục bộ:**
   - Thực hiện trên nhánh tạm `refactor/system-perf-cleanup` tách từ `main` (`2ef40cf`); sau khi merge `--no-ff` vào `main` và xanh CI thì xóa nhánh tạm để giữ đúng **6 nhánh cố định** (`main`, `GD-Config`, `GD1-HBT`, `GD2-PostV`, `GD3-Chatting`, `GD4-StickV`).
   - Bảo toàn tuyệt đối: **4 tag lịch sử `v1`, `v2`, `v3`, `v4`**, **3 stash cũ (`stash@{0..2}`)**, `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`), `STICKV_MP4_COMPAT_FLAGS`, chống khóa file `WinError 32`, và dữ liệu local (`library/`, `workspace/`, `assets/`, `brand/`, `.env`).
2. **6 Vùng cấm mặc định:**
   - Khóa cứng trong suốt đợt này: `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
   - Nếu BA phát hiện file chết hoặc điểm tối ưu nằm trong 6 vùng cấm, **KHÔNG tự ý sửa/xóa** — ghi vào mục **"Đề xuất mở khóa sau (Deferred Unlock)"** trong báo cáo Audit để chủ dự án quyết định riêng.
3. **Model AI & Bất biến chống hồi quy:**
   - Giữ cứng `gemini-3.1-flash-lite` mặc định (cấm hạ về dòng 2.x).
   - Bảo toàn toàn bộ **`INV-01` → `INV-09`** trong `docs/REGRESSION-LEDGER.md` và bổ sung 2 bất biến mới:
     - **`INV-10`:** Thanh tiến trình tổng cố định ở Sidebar trái hiển thị sống cho **cả 4 động cơ** (`core`, `postv`, `chatting`, `stickv`) ở mọi route, không trùng lặp, không làm lag chuyển tab.
     - **`INV-11`:** Ngân sách CPU/RAM khi render StickV 60fps phải thấp hơn rõ rệt so với mốc Baseline đo trước refactor, giữ nguyên 100% độ nét, 60fps, `drift_ms <= 30ms`, `alignment_source=whisper`.

---

## 1. HẠNG MỤC 1: THANH TIẾN TRÌNH CỐ ĐỊNH TỔNG TẠI SIDEBAR TRÁI (`INV-10`)

### 1.1. Nguyên tắc "Single Source of Truth" (Xóa cảnh thiếu ở StickV & trùng lặp 3 nơi)
- **Vị trí cố định duy nhất:** Đặt 1 khối **`SidebarRenderStatus`** ghim cố định ngay phía trên khu vực chân Sidebar trái (trên nút Cài đặt / Sáng-Tối), luôn hiển thị xuyên suốt bất kể người dùng đang đứng ở `/`, `/core`, `/postv`, `/chatting`, `/stickv`, `/library` hay `/settings`.
- **Xóa bỏ hiển thị tiến độ trùng lặp/rời rạc:** Gỡ bỏ hoàn toàn hộp nổi `GlobalJobDock` góc dưới phải (và dải banner tiến độ phụ trên Topbar nếu gây lặp) — chỉ giữ **Sidebar trái** làm đồng hồ tổng toàn ứng dụng.
- **Tương thích 2 trạng thái Sidebar:**
  - **Sidebar mở rộng (`~220px`):** Hiện rõ tên động cơ (badge màu riêng: Core Đỏ, PostV Tím, Chatting Xanh, StickV Vàng) + tên dự án cắt gọn 1 dòng + thanh bar `transform: scaleX()` + `%` + tên bước tiếng Việt hiện tại + nút **Đi tới dự án** (nhảy thẳng về `/stickv?slug=...`, `/core?slug=...`...) + nút **Hủy**.
  - **Sidebar thu gọn Icon Rail (`~60px`):** Hiện vòng tròn tiến độ SVG (`stroke-dashoffset`) kèm chữ `%` ở tâm + hover tooltip hiện chi tiết bước đang chạy, bấm vào nhảy thẳng về đúng dự án.
  - **Khi rảnh (không có job chạy):** Thu gọn gọn gàng hoặc hiện trạng thái nhẹ 1 dòng không chiếm chỗ (`0%` CPU idle animation).

### 1.2. Chuẩn hóa Hợp đồng Backend (`jobs.py`, `api/jobs.py`, `api/stickv.py`)
- Mọi loại job nền của cả 4 động cơ (`core`, `hbt_core_images`, `postv`, `chatting`, `stickv`) bắt buộc đăng ký chung qua **`JobManager`** với schema `JobSnapshot` đồng nhất 100%:
  ```json
  {
    "job_id": "string",
    "engine": "core | postv | chatting | stickv",
    "kind": "render | preview | images | auto",
    "slug": "string",
    "title": "string",
    "route": "/stickv?slug=...",
    "status": "queued | running | done | failed | cancelled",
    "progress": 0,
    "stage": "Đang dựng khung hình (Beat 4/10)",
    "started_at": 1732670000.0,
    "updated_at": 1732670012.5,
    "error": null
  }
  ```
- **Khắc phục triệt để lỗi StickV bị mất/chậm tiến trình:**
  - Ngay khi `POST /api/stickv/{slug}/render` (hoặc bất kỳ động cơ nào) trả về `job_id`, frontend ghi tức thì bản ghi `optimistic queued/running` vào store trước khi luồng SSE gửi gói đầu tiên.
  - Khi reload trang (`F5`) hoặc mở từ trang khác, store tự gọi `GET /api/jobs?active_only=true` một lần khi boot app và tự mở **1 kết nối SSE duy nhất** (`/api/jobs/{job_id}/events`) nếu có job đang `queued`/`running`.

### 1.3. Chống Lag Trình Duyệt (Isolated External Store)
- **Cấm** đặt `progress` (nhảy liên tục) trong React Context cấp gốc bọc cả `<App/>` (nguyên nhân khiến toàn bộ trang Studio + `<video>` re-render mỗi khi `%` tăng).
- Dùng **`useSyncExternalStore`** (module `frontend/src/stores/jobProgressStore.ts`) + **throttle 250ms**:
  - Chỉ duy nhất component `SidebarRenderStatus` (và nút khóa Export của đúng trang đang chạy job đó) đăng ký subscribe vào `progress`.
  - Chuyển giữa 6 route không làm ngắt kết nối SSE và không gây re-render cây DOM chính.

---

## 2. HẠNG MỤC 2: TỐI ƯU HÓA CPU & RAM KHÔNG GIẢM CHẤT LƯỢNG (`INV-11`)

> **Mục tiêu định lượng trên `i5-10400` / 16 GB RAM (đo thật trên dự án Pisa 41.5s 60fps):**
> - **Peak RAM backend:** Giảm ít nhất **25–40%** (mục tiêu duy trì `< 1.8 GB` tổng tiến trình Python + FFmpeg khi dựng video ngắn/trung bình).
> - **Thời gian render (Wall-Clock) & Tải CPU:** Giảm thời gian dựng ít nhất **25–40%** hoặc ổn định tải CPU không kéo đơ máy Windows (`BELOW_NORMAL_PRIORITY_CLASS`), trong khi pixel & audio thành phẩm **giữ nguyên chuẩn 60fps, `yuv420p`, `-14 LUFS`, `drift_ms <= 30ms`**.

### 2.1. Mũi nhọn 1 — Tách Lớp Tĩnh / Lớp Động trong Vòng lặp Render 60fps (Giảm 60–75% CPU Pillow)
- **Vấn đề hiện tại:** Trong `stickv/stage.py`, `stickv/render.py` (và các hàm vẽ khung tương tự), nhiều thành phần tĩnh của beat (nền động hoặc lưới tĩnh, khung bảng thông tin, toàn bộ chữ trên bảng, khung Polaroid + ảnh đã resize, watermark tĩnh) đang bị vẽ lại / resize lại / tải font lại hàng trăm lần mỗi beat ở 60fps.
- **Giải pháp không mất 1 pixel chất lượng:**
  1. **Font & Sprite LRU Cache cố định:** Tải `ImageFont.truetype` đúng 1 lần duy nhất (cache theo `(font_path, size)`), cấm gọi `ImageFont.truetype()` trong vòng lặp frame.
  2. **Pre-render Static Beat Layer:** Trước khi chạy vòng lặp frame của beat `k`, vẽ sẵn **1 ảnh RGBA `static_board_layer`** (khung bảng + chữ Rich Text + ảnh Polaroid đã dán) và **`watermark_layer`** đúng 1 lần.
  3. **Trong vòng lặp 60fps:** Chỉ alpha-composite `backdrop(t)` + `static_board_layer` (áp alpha crossfade nếu đang ở 0.28s đầu/cuối beat) + `puppet_layer(t)` + `karaoke_strip(t)`.
  4. **Đóng tài nguyên tức thì (`with Image.open(...)` / `.close()`):** Mọi ảnh tạm của frame phải đóng rõ ràng ngay sau khi đẩy byte sang FFmpeg; giữa mỗi beat xóa cache `static_board_layer` của beat cũ và gọi `gc.collect()` nhẹ theo chu kỳ (mỗi 2–3 beat hoặc cuối mỗi chapter).

### 2.2. Mũi nhọn 2 — Không Chồng Chéo Bộ Nhớ Giữa 4 Giai Đoạn Nặng (Phase Memory Isolation)
- **Vấn đề hiện tại:** VieNeu-TTS ONNX + Faster-Whisper `small int8` + Pillow 60fps + FFmpeg dễ giữ nguyên trọng số/buffer trong RAM cùng lúc khiến tổng RAM vọt lên 6–12 GB.
- **Giải pháp tuần tự giải phóng sạch RAM theo Pha:**
  1. **Pha 1 (TTS):** Sinh WAV từng beat → lưu ra đĩa `build/voice/` → giải phóng mảng audio khỏi RAM (không giữ danh sách numpy WAV của toàn bộ video trong bộ nhớ).
  2. **Pha 2 (Whisper Alignment):** Chạy căn chữ xong → lưu `.segments.json` ra đĩa → **hủy tham chiếu model Whisper / giải phóng bộ nhớ (`unload_whisper_model()` + `gc.collect()`)** TRƯỚC KHI khởi chạy Pha 3 (Render Video).
  3. **Pha 3 (Video Streaming Pipe):** Xuất từng khung RGB24 trực tiếp qua `stdin` của FFmpeg (`rawvideo`, **cấm xuất hàng nghìn file `.png` trung gian ra ổ cứng**), luôn giữ `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2 -filter_complex_threads 2`) và đặt tiến trình con FFmpeg ở mức ưu tiên thấp trên Windows (`creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS`) để Windows & trình duyệt không bị khựng đơ khi render.
  4. **An toàn Pipe FFmpeg:** Đọc `stderr` bằng luồng nền ghi vào ring-buffer tối đa 200 dòng (không tích tụ hàng chục MB log trong RAM và không bao giờ deadlock).

### 2.3. Mũi nhọn 3 — Beat-Level Hash Cache (Tái sử dụng Beat Không Đổi)
- Tính `beat_hash = sha256(narration, voice_id, board_type, board_title, board_data, prop_asset_hash, visual_mode, aspect, puppet_version, stage_version)`.
- Lưu chunk beat đã dựng vào `workspace/<engine>/<slug>/build/beat_cache/<beat_hash>.mp4` (kèm `.meta.json`).
- Khi người dùng chỉ sửa lời thoại hoặc đổi ảnh của 1–2 beat rồi bấm xuất lại: các beat không đổi nối thẳng bằng `concat -c copy` (**0% CPU render lại**), chỉ render đúng beat thay đổi. Tự động dọn file cache cũ quá hạn (LRU theo dung lượng/số dự án).

### 2.4. Mũi nhọn 4 — Tối Ưu RAM & CPU Frontend
- Trong Thư viện (`/library`) và Trang chủ (`/`): mọi thẻ `<video>` đặt `preload="none"` hoặc dùng ảnh bìa tĩnh `cover_url`/`thumb_url`, chỉ khởi tạo `<video src>` khi người dùng mở Modal xem hoặc hover chủ động; hủy `src` (`video.removeAttribute('src'); video.load()`) khi đóng Modal (vừa giảm hàng trăm MB RAM Chrome vừa chống lỗi `WinError 32` trên Windows).
- Dọn sạch mọi `setInterval` / CSS animation chạy ngầm khi trang đứng yên (`0%` idle CPU).

---

## 3. HẠNG MỤC 3: TỔNG RÀ SOÁT, XÓA FILE THỪA & TÁI CẤU TRÚC THƯ MỤC

### 3.1. Quy trình Quét Mã Chết (Reachability Audit — Bắt buộc làm trước khi xóa)
- **Backend (`backend/hbt/` & `scripts/`):**
  - Quét đồ thị import từ `backend/hbt/main.py`, `backend/tests/`, `scripts/`.
  - Phân loại rõ từng file/hàm thành 3 nhóm:
    1. **DEAD (0 tham chiếu, ngoài 6 vùng cấm):** Lên danh sách xóa hẳn.
    2. **DUPLICATE (viết lặp ở 2+ nơi, vd helper FFmpeg/audio/text/cache/media):** Lên kế hoạch gộp về 1 điểm duy nhất trong `backend/hbt/shared/`.
    3. **OVERLAP (`backend/hbt/cinema/` vs `backend/hbt/stickv/`):** Kiểm tra chính xác file nào trong `cinema/` đang thực sự được gọi từ production vs file tạo ra từ đợt cũ nay đã bỏ trống → tinh gọn hoặc xóa phần chết.
- **Frontend (`frontend/src/`):**
  - Quét đồ thị import từ `main.tsx` và `App.tsx`.
  - Liệt kê toàn bộ component, hook, CSS file, type, i18n key không còn nơi nào dùng (ví dụ `GlobalJobDock` cũ sau khi thay bằng `SidebarRenderStatus`, các file UI/style dư thừa từ các đợt redesign v3/v4/v5/v10).
- **Root Repo & `docs/`:**
  - Gom các file `.md` kế hoạch/đặc tả cũ nằm vương vãi ở thư mục gốc vào `docs/archive/` (giữ nguyên đúng bộ file cốt lõi ở root: `README.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PLAN.md`, `IMPLEMENT.md`).

### 3.2. Cấu trúc Thư mục Đích Chuẩn Hóa (Sạch · Rõ Ranh Giới · Dễ Bảo Trì)

```text
backend/hbt/
├─ main.py & config.py & app_settings.py
├─ jobs.py                       # JobManager duy nhất + chuẩn JobSnapshot cho cả 4 động cơ
├─ api/                          # CHỈ chứa thin routers (nhận request → gọi service → trả response)
│  ├─ system.py / jobs.py / asset_hub.py
│  ├─ core.py / postv.py / chatting.py / stickv.py
│  └─ projects.py                # [KHÓA - VÙNG CẤM]
├─ shared/                       # HẠ TẦNG DÙNG CHUNG (1 nguồn sự thật duy nhất)
│  ├─ llm/                       # Gemini 3.1 client, schema helpers
│  ├─ tts/                       # VieNeu-TTS worker + cache + audio duration
│  ├─ media/                     # FFmpeg clamp/runner, aspect, watermark, audio mix (-14 LUFS)
│  ├─ online_sources/            # Wikimedia, Pixabay, Giphy, GreenMeme, Tuna, Cloudflare Flux
│  ├─ asset_director/            # Smart Asset Director (cooldown, pacing, resolver)
│  └─ db/                        # studio.db media_index + deleted_renders guard
├─ core/                         # Động cơ 1: HBT Core
├─ stickv/                       # Động cơ 4: StickV (models, llm, puppet, stage, audio, render, beat_cache)
├─ pipeline/ & models.py         # [KHÓA - VÙNG CẤM]
├─ postv/                        # [KHÓA - VÙNG CẤM]
└─ chatting/                     # [KHÓA - VÙNG CẤM]

frontend/src/
├─ app/                          # App.tsx, Router, AppShell, Sidebar (chứa SidebarRenderStatus cố định)
├─ stores/                       # jobProgressStore.ts (useSyncExternalStore, throttle 250ms)
├─ api/                          # Typed API clients tách gọn theo domain
├─ components/ui/                # UI primitives dùng chung (Button, StudioSelect, SegmentedControl, Modal...)
├─ features/                     # Hoặc pages/ quy hoạch 1-1 gọn gàng theo 6 mục Sidebar:
│  ├─ home/ · core/ · postv/ · chatting/ · stickv/ · library/ · settings/
├─ styles/                       # tokens.css, ui.css (đã cắt sạch selector chết)
└─ i18n/vi.ts                    # Toàn bộ nhãn tiếng Việt
```

*(Lưu ý: Không đổi đường dẫn import bừa bãi nếu chỉ đổi tên cho đẹp mà không giảm độ phức tạp; chỉ di chuyển/gộp những nơi thực sự bị trùng lặp hoặc rối cấu trúc, ưu tiên xóa mã chết và tách logic nặng ra khỏi file khổng lồ).*

---

## 4. CÔNG CỤ ĐO KIỂM HIỆU NĂNG BẮT BUỘC (`scripts/benchmark_render_resources.py`)

Cấm tuyên bố "đã tối ưu CPU/RAM" bằng cảm tính. Phải có script đo thật lưu lại bằng chứng trước và sau refactor:
- Chạy render thật 1 dự án chuẩn (`bi-mat-dang-sau-thap-nghieng-pisa`, 60fps, đầy đủ audio + video).
- Lấy mẫu mỗi `0.25s` toàn bộ cây tiến trình (Python backend + các tiến trình con FFmpeg/TTS/Whisper) bằng `psutil` (hoặc PowerShell `Get-Process` nếu chưa cài `psutil`):
  - **Wall-clock time (s)**
  - **Peak RSS RAM (MB)** & **Avg RSS RAM (MB)**
  - **Peak CPU (%)** & **Avg CPU (%)**
  - **Số lượng file tạm lớn nhất phát sinh trong `build/`**
- Lưu kết quả JSON vào `workspace/stickv/_checks/perf_baseline.json` (trước refactor) và `workspace/stickv/_checks/perf_after.json` (sau refactor), in bảng so sánh `Trước vs Sau` kèm kiểm chứng `verify_stickv_smoke.py` (`RESULT: PASS`).

---

## 5. KẾ HOẠCH TRIỂN KHAI THEO 6 CỔNG (SINGLE-CONCERN PACKETS)

| Packet | Chủ trì | Mục tiêu Single-Concern | Tiêu chí Nghiệm thu Thật (Artifact Gate) |
| :--- | :--- | :--- | :--- |
| **P0 (Audit & Baseline)** | BA + QA | Quét toàn bộ repo tìm file chết/trùng lặp/điểm nghẽn; chạy `benchmark_render_resources.py` lấy mốc `perf_baseline.json`. **CHƯA SỬA CODE.** | Báo cáo `AUDIT-REPORT.md` + bảng số đo Baseline thật → **DỪNG CHỜ CHỦ DỰ ÁN DUYỆT (Gate 0)**. |
| **P1 (Sidebar Progress)** | Dev + QA | Chuẩn hóa `JobSnapshot` backend + `jobProgressStore` (`useSyncExternalStore`) + `SidebarRenderStatus` cố định ở Sidebar trái cho cả 4 động cơ (đặc biệt StickV), gỡ `GlobalJobDock` trùng. | Test Vitest chuyển 6 route khi job StickV đang chạy vẫn giữ tiến độ + 0 re-render thừa; chụp/kiểm chứng UI cả Sidebar mở rộng & thu gọn. |
| **P2 (Dead-Code Pruning)** | Dev + QA | Xóa sạch file/code/CSS chết ngoài 6 vùng cấm theo danh sách đã được duyệt ở Gate 0; gộp các helper trùng lặp về `shared/`. | Diff xóa ròng rõ ràng; 0 import gãy; `ruff` + `tsc` + `pytest` + `vitest` xanh. |
| **P3 (CPU/RAM Engine Opt)** | Dev + QA | Pre-render static beat layer (StickV/Stage), font LRU cache, giải phóng Whisper/Pillow giữa các pha, `BELOW_NORMAL_PRIORITY_CLASS`, stream raw pipe không đẻ PNG, Beat-Level Hash Cache. | Chạy lại `benchmark_render_resources.py` → so sánh `perf_after.json` vs `perf_baseline.json` (RAM & Time giảm thật) + `verify_stickv_smoke.py` `RESULT: PASS`. |
| **P4 (Frontend RAM & Hygiene)** | Dev + QA | Tối ưu `<video preload="none">` ở `/library` & `/`, giải phóng media handle chống `WinError 32`, dọn sạch CSS/component thừa, cập nhật `REGRESSION-LEDGER.md` (`INV-10`, `INV-11`). | Bundle size giảm hoặc không tăng; test unmount video & leak-free pass. |
| **P5 (Final Gate & Release)** | Release (Neon) | Kiểm toán 6 vùng cấm rỗng diff, chạy 1 lần `npm run lint && npm run test:fast && npm run build`, tổng hợp báo cáo `Trước vs Sau`. | Chờ chủ dự án nghiệm thu trực tiếp trên trình duyệt & video thật rồi mới merge `--no-ff` vào `main`. |