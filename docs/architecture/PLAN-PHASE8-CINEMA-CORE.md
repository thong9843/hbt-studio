# HBT STUDIO — ĐẶC TẢ KIẾN TRÚC GIAI ĐOẠN 8: UNIFIED EDITORIAL CINEMA CORE (v10.0)

> **Mục tiêu cốt lõi:** Chuyển đổi toàn hệ thống HBT Studio từ các bộ ghép video rời rạc sang **1 Lõi Dựng Phim Độc Bản Hợp Nhất (`backend/hbt/cinema/`)** đạt chuẩn YouTuber triệu sub (_HBT Tactile Desk_), chặn 100% lỗi bố cục trước khi render, tối ưu triệt để CPU/RAM trên máy `i5-10400` và tự động mở khóa tăng tốc GPU trên `RTX 2060 Super` mà **không phá vỡ bất kỳ tính năng hay vùng đóng băng nào hiện có**.

---

## 1. BẤT BIẾN HỆ THỐNG & LUẬT CHỐNG LỖI TUYỆT ĐỐI (ZERO-REGRESSION)

### 1.1. Vùng cấm tuyệt đối (Không sửa dù chỉ 1 dòng)

- `backend/hbt/pipeline/`
- `backend/hbt/models.py`
- `reference/`
- `backend/hbt/api/projects.py`
- `backend/hbt/postv/`
- `backend/hbt/chatting/`
- Không đọc, không chạy lệnh, không commit `DESIGN.md` của bên thứ ba; thương hiệu duy nhất là **HBT** (`brand/hbt-logo-mark.png`, `brand/outro/`).
- Giữ nguyên toàn bộ dữ liệu local trong `library/`, `workspace/`, `assets/` và 2 stash cũ trên `feat/pv-comments-length`.
- Mọi chữ hiển thị trên UI phải bằng tiếng Việt đặt trong `frontend/src/i18n/vi.ts`; chữ trên video vẽ bằng Pillow dùng font local trong `backend/hbt/fonts/` (`Be Vietnam Pro`), không sinh chữ bằng AI tạo ảnh.

### 1.2. 6 Bẫy Kỹ Thuật Bắt Buộc Phải Khóa Chặt Ngay Từ Thiết Kế

1. **Bẫy thiếu media trên GitHub Actions CI (Ubuntu):** Các tệp `.mp3`, `.wav`, `.mp4`, `.png` trong `library/` bị `.gitignore` không tồn tại trên CI. Mọi bộ nạp SFX/BGM/Puppet/Texture trong `cinema/` **phải có fallback an toàn** (tạo tín hiệu im lặng/Foley/Stickman thủ tục bằng NumPy/Pillow) — tuyệt đối không ném `FileNotFoundError` làm đỏ CI.
2. **Bẫy giới hạn lệnh 32KB của Windows (`CreateProcess`):** Video dài 5–10 phút có hàng chục lớp audio/SFX nếu truyền trực tiếp vào tham số `-filter_complex` sẽ vỡ trên Windows. Bắt buộc ghi filtergraph ra tệp tạm `filtergraph.txt` (UTF-8) và truyền bằng `-filter_complex_script <path>`.
3. **Bẫy khóa tệp Windows (`WinError 32`):** Mọi thao tác ghi tệp cache, `contact_sheet.jpg`, `beat_*.mp4` phải ghi ra tệp `.tmp` rồi đổi tên nguyên tử (`os.replace`); mọi `subprocess.Popen` phải đóng `stdin`/`stdout`/`stderr` trong khối `try...finally` và gọi `wait()`.
4. **Bẫy tràn RAM / rò rỉ đối tượng Pillow:** Cấm tuyệt đối gọi `ImageFont.truetype()` hoặc vẽ lại thẻ/bóng đổ/nền tĩnh bên trong vòng lặp `for frame_idx in range(...)`. Mọi thành phần tĩnh phải được **pre-bake đúng 1 lần mỗi beat** vào `LayerCache` có trần bộ nhớ cứng (`256 MB` trên CPU, `512 MB` trên GPU) và gọi `.close()` tường minh khi evict hoặc hết beat.
5. **Bẫy sai chuẩn MP4 trên Windows Media Player (`0x80004005`):** Mọi file xuất ra bắt buộc gắn `STICKV_MP4_COMPAT_FLAGS` (`-pix_fmt yuv420p -profile:v high -level 4.1 -c:a aac -movflags +faststart`). Khi dùng `h264_nvenc`, bắt buộc chạy 1-frame encoder probe lúc khởi động; nếu probe lỗi lập tức rơi về `libx264` kèm `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`).
6. **Bẫy đè chữ / cắt bảng / lặp khung hình:** Mọi `TimelineSpec` bắt buộc đi qua `PreflightQualityGate` trước khi render để kiểm tra va chạm hộp hình học (AABB) và tự động nắn tọa độ (Auto-Reflow) — cấm tuyệt đối xuất khung hình có `y < 0`, đè Karaoke hoặc đè Safe-Zone.

---

## 2. KIẾN TRÚC MÔ-ĐUN MỚI (`backend/hbt/cinema/`)

```text
backend/hbt/cinema/
├── __init__.py
├── schema.py            # Hợp đồng JSON duy nhất: TimelineSpec IR v1 (Pydantic v2)
├── hardware.py          # Tự dò CPU (i5-10400 clamp) vs GPU (RTX 2060S NVENC probe)
├── cache.py             # Beat-Level Content-Addressed Cache (SHA-256 + concat -c copy)
├── layer_cache.py       # Pre-baked RGBA Texture Cache (LRU cap RAM + explicit close)
├── preflight.py         # Cổng kiểm định: AABB Collision + Auto-Reflow + Anti-Parrot + Pacing
├── contact_sheet.py     # Xuất ảnh lưới 1 trang duyệt toàn bộ video (< 2.0 giây)
├── motion.py            # Easing curves (ease_out_cubic, ease_out_back, spring) & Keyframes
├── shots.py             # 6 Ngữ pháp Khung hình độc bản "HBT Tactile Desk" (9:16 & 16:9)
├── transitions.py       # Whip-Pan (motion blur 1D), Paper Slide, Editorial Cut
├── compositor.py        # Bộ dựng khung hình Dirty-Rect + Pipe thẳng FFmpeg (CPU/NVENC)
├── audio_director.py    # Siết thở <=120ms, Silence Drop 320ms, J/L-Cut 160ms, Foley, -14 LUFS
├── director_ai.py       # Bộ đạo diễn biên tập (Dual-Pass Prompt + Rule-based Shot Assigner)
└── adapters/
    ├── __init__.py
    ├── stickv_adapter.py # Biên dịch StickvProject -> TimelineSpec v1 (nối puppet.py v3)
    └── core_adapter.py   # Biên dịch HBT Core (10–12 cảnh) -> TimelineSpec v1 (không chạm pipeline/)

backend/hbt/shared/tts/
├── resident_worker.py   # Tiến trình con thường trú giữ VieNeu-TTS ấm trong RAM
└── worker_pool.py       # Warm Resident VieNeu-TTS Subprocess (idle_ttl=600s, tự giải phóng RAM)

backend/hbt/api/
└── cinema.py            # REST endpoints: /hardware, /preflight, /contact-sheet, /render-beat
```

---

## 3. HỢP ĐỒNG DỮ LIỆU & BỘ ĐỆM 2 TẦNG (`schema.py`, `layer_cache.py`, `cache.py`)

- **`TimelineSpec` IR v1:** Thống nhất đầu vào cho cả `StickV` (`9:16` / `16:9`) và `HBT Core` (`10–12` cảnh), chứa `AudioPlan`, `preflight_passed`, và danh sách `BeatSpec` có khóa băm SHA-256 (`content_hash`).
- **`LayerCache` & `FontCache`:** Giữ các lớp nền bàn làm việc + thẻ bảng + dải Karaoke theo word chunk trong RAM với trần cứng `256 MB` (CPU) / `512 MB` (GPU), tự động đóng `PIL.Image.close()` khi evict LRU.
- **`BeatCache`:** Chuẩn hóa mọi clip beat theo cùng `fps`, `-video_track_timescale 90000`, `yuv420p`, `48000 Hz stereo` trước khi ghép bằng `concat -c copy` nhằm triệt tiêu 100% sai lệch tiếng/hình.
- **`WarmTTSPool`:** Giữ tiến trình VieNeu-TTS thường trú qua nhiều beat, tự động thu hồi RAM sau `idle_ttl_sec=600s` và rơi về WAV dự phòng khi chạy trên CI.

---

## 4. KIỂM ĐỊNH TIỀN KỲ & 6 NGỮ PHÁP "HBT TACTILE DESK" (`preflight.py`, `shots.py`)

- **`PreflightQualityGate`:**
  1. Kiểm tra tọa độ âm (`y < 0`, `x < 0`) và vượt Safe-Zone `9:16` / `16:9`.
  2. Kiểm tra va chạm AABB giữa `board`, `puppet` và `karaoke_bbox`.
  3. **Anti-Parrot (`> 65%` trùng từ):** Tự động chuyển bảng sao chép lời thoại sang dạng phân tích từ khóa/số liệu; ép beat CTA cuối thành `recap_card` (`recap_grid`).
  4. **Pacing:** Chặn lặp 2 `shot_type` liên tiếp và Auto-Reflow sạch 100% trước khi render.
- **6 Ngữ pháp HBT Tactile Desk:** `desk_wide`, `card_hero`, `split_compare`, `data_spotlight`, `puppet_closeup`, `recap_grid`.

---

## 5. AUDIO DIRECTOR & EDITORIAL DIRECTOR AI (`audio_director.py`, `director_ai.py`)

- **Siết thở (`<= 120ms`)** bằng NumPy 16-bit PCM + crossfade 8ms chống tiếng tách.
- **J/L-Cut (`160ms`)**, **Silence Drop (`320ms`)** trước câu nhấn `punch`, **Foley thủ tục** (khi thiếu file local trên CI) và **Loudness `-14 LUFS`** qua `-filter_complex_script` (UTF-8).
- **Dual-Pass Prompt & Rule-based Shot Assigner:** Tách pass nội dung/dữ kiện khỏi pass phân bổ góc máy, chuyển cảnh (`whip_pan`, `paper_slide`, `editorial_cut`) và diễn hoạt 18x10 Puppet.

---

## 6. LỘ TRÌNH 6 COMMIT GIAO HÀNG (C1–C6)

| Commit | Phạm vi                       | Nội dung chính                                                                               |
| :----- | :---------------------------- | :------------------------------------------------------------------------------------------- |
| **C1** | `feat(cinema-core)`           | `TimelineSpec` IR v1, `hardware.py` NVENC probe, `LayerCache`, `BeatCache`, `WarmTTSPool`.   |
| **C2** | `feat(cinema-preflight)`      | `PreflightQualityGate` (AABB Auto-Reflow, Anti-Parrot, Pacing) & `ContactSheet` (< 2s).      |
| **C3** | `feat(cinema-visual)`         | `motion.py`, 6 shot `HBT Tactile Desk`, `transitions.py`, `DirtyRectCompositor`.             |
| **C4** | `feat(cinema-audio-director)` | `AudioDirector` (`-filter_complex_script`, -14 LUFS, J/L-cut) & `director_ai.py`.            |
| **C5** | `feat(cinema-adapters-api)`   | `stickv_adapter.py`, `core_adapter.py`, REST endpoints `/api/cinema/*`.                      |
| **C6** | `feat(cinema-ui)`             | `CinemaInspectorPanel` trên `StickvPage` & `HbtCoreWorkspace`, i18n `vi.ts`, lưu trữ đặc tả. |
