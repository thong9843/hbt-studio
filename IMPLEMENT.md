# HBT Studio — Đặc tả triển khai (cho Claude Code)

> Đọc theo thứ tự: `CLAUDE.md` → `PLAN.md` → file này → `reference/pipeline/*.py` → `DESIGN.md`.
> Phiên bản: v1.4 · 21/10/2026 (v1.1 thương hiệu HBT; v1.2 50fps, outro, lời đọc 750 ký tự; v1.3 outro có lời; v1.4 ảnh bìa).
> **Mục 4b–4d bên dưới GHI ĐÈ các tham số cũ ở mục 4** khi có mâu thuẫn.
> Phạm vi file này: **Giai đoạn 1** (mốc M0–M4). Giai đoạn 2 chỉ định nghĩa interface ở mục 12.
> Mọi tham số dựng video trong `reference/` **đã chạy thật trên 6 video**: giữ nguyên, trừ khi file này ghi khác.

---

## 0. Môi trường (Windows 10/11)

### Hồ sơ máy

Chủ dự án dùng hai máy và sẽ cho biết đang dùng máy nào ở đầu mỗi lần mở chat.

| Máy | CPU | GPU | RAM |
|---|---|---|---|
| **Máy cũ** | Intel i5-10400 | không có GPU rời | 16 GB |
| **Máy mới** | Intel i5-14400F | NVIDIA RTX 2060 Super, 8 GB VRAM | 32 GB |

**Quy tắc:** không giả định có GPU. Mọi tính năng cần GPU phải có đường dự phòng chạy bằng CPU (Whisper: mục 5.2).

### Phần mềm

| Thành phần | Phiên bản | Cài |
|---|---|---|
| Git | mới nhất | `winget install Git.Git` |
| Python | **3.11.x (ghim)** | `winget install Python.Python.3.11` |
| Node.js | 20 LTS trở lên | `winget install OpenJS.NodeJS.LTS` |
| FFmpeg | ≥ 6.0, có `libx264`, `zoompan`, `xfade`, `sidechaincompress`, `loudnorm` | `winget install Gyan.FFmpeg` (thêm vào PATH) |
| Driver NVIDIA | hỗ trợ CUDA 12 (chỉ máy có GPU) | GeForce Experience / trang NVIDIA |
| faster-whisper | bản ổn định mới nhất (đã cài và chạy thử trên máy cũ 24/10/2026: `faster-whisper 1.2.1`, `ctranslate2 4.8.3`, `onnxruntime 1.31.0`, `av 18.1.0`) | `pip install faster-whisper`; máy có GPU cần thêm thư viện CUDA 12 (xem README của faster-whisper: `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) |

**Python:** dự án ghim **Python 3.11.x**. Máy nào đã có Python mới hơn thì cài thêm 3.11 **song song** (không gỡ bản cũ), gọi bằng `py -3.11`, và tạo `backend\.venv` đúng bằng bản 3.11 (`py -3.11 -m venv backend\.venv`). Kiểm tra bằng `py -3.11 --version` (README có bước này). Claude Code phải **hỏi chủ dự án trước khi cài** Python hay bất kỳ phần mềm cấp hệ thống nào.

**Thư viện CUDA trên Windows (ghi 26/10/2026, máy mới):** `nvidia-cublas-cu12 12.9.2.10`, `nvidia-cudnn-cu12 9.27.0.42` trong `backend\.venv`. Các DLL (`cublas64_12.dll`, cuDNN…) nằm ở `site-packages
vidia\*in`, không có trong PATH, nên lúc đầu CUDA báo `Library cublas64_12.dll is not found or cannot be loaded` và app rơi xuống `small` CPU. Cách nạp (b6, chủ dự án duyệt): ở đầu `whisper_worker.run()`, **trước khi import `faster_whisper`**, chỉ trên Windows, với mỗi thư mục `nvidia\*in` có thật thì gọi `os.add_dll_directory()` và thêm vào đầu `PATH` của **riêng tiến trình con** (có ghi log). Không có thư mục nvidia (máy cũ, CI Linux) thì không làm gì. Không sửa PATH hệ thống. `/health.gpu` giữ nguyên (chỉ đếm thiết bị CUDA).

Model Whisper tải lần chạy đầu về `models/` (đã ignore); chọn model và thiết bị theo phần cứng: mục 5.2. Lỗi CUDA, không có GPU hoặc Whisper không dùng được → rơi về CPU, rồi về căn theo khoảng lặng.

---

## 1. Cấu trúc repo

```
hbt-studio/
├─ CLAUDE.md                 # quy tắc cho Claude Code
├─ PLAN.md  IMPLEMENT.md  DESIGN.md
├─ package.json              # script gốc: dev, build, lint, test
├─ .env.example  .gitignore  README.md
├─ backend/
│  ├─ pyproject.toml         # fastapi, uvicorn, pydantic>=2, pillow, numpy, python-multipart, sse-starlette; extra [whisper]
│  ├─ hbt/
│  │  ├─ main.py             # FastAPI app, mount /files, CORS chỉ cho localhost:5173
│  │  ├─ config.py           # đọc .env: WORKSPACE_DIR, WHISPER_MODEL, DEFAULT_FPS…
│  │  ├─ models.py           # Pydantic: Project, Scene, Card, Label, Settings, Job
│  │  ├─ storage.py          # đọc/ghi project.json, quản lý file media
│  │  ├─ jobs.py             # hàng đợi job (ThreadPoolExecutor max_workers=1), tiến độ, huỷ
│  │  ├─ api/                # projects.py, assets.py, render.py, music.py, lint.py, publish.py
│  │  ├─ pipeline/
│  │  │  ├─ text.py          # = reference/pipeline/text.py
│  │  │  ├─ align.py         # reference/pipeline/align.py + `match_script` (khớp âm tiết Whisper với kịch bản)
│  │  │  ├─ whisper.py       # chạy Whisper ở tiến trình con, bậc rơi, timeout, huỷ (5.2)
│  │  │  ├─ whisper_worker.py # tiến trình con: nạp faster-whisper, nhận dạng, ghi JSON
│  │  │  ├─ bench.py         # `cli bench-align`
│  │  │  ├─ visual.py        # = reference/pipeline/visual.py
│  │  │  ├─ audio.py         # chuẩn hoá giọng, chọn đoạn nhạc, ducking, whoosh
│  │  │  ├─ captions.py      # chia cụm, vẽ trạng thái karaoke, file concat, xuất .srt
│  │  │  ├─ render.py        # điều phối toàn bộ; dựa trên reference/pipeline/render_reference.py
│  │  │  └─ lint.py          # kiểm tra từ nhạy cảm
│  │  ├─ fonts/              # Be Vietnam Pro (OFL) — đã kèm
│  │  └─ data/sensitive_words.json
│  ├─ cli.py                 # `python -m cli render <project_dir> [--preview] [--fps 60]`
│  └─ tests/
├─ frontend/
│  ├─ package.json  vite.config.ts  tailwind.config.ts
│  └─ src/  (app/, pages/, components/, api/, i18n/vi.ts, styles/tokens.css)
├─ library/music/            # nhạc tải từ Pixabay + index.json (ignore file mp3, giữ index.json)
├─ brand/                    # logo HBT, avatar, favicon (frontend copy sang public/)
├─ reference/pipeline/       # code tham khảo — KHÔNG import trực tiếp, chỉ để đối chiếu
└─ workspace/                # ignore toàn bộ: projects/<slug>/…
```

`.gitignore` bắt buộc có: `workspace/`, `models/`, `library/music/**` (kèm `!library/music/index.json`), `*.mp3`, `*.m4a`, `*.ogg`, `*.flac`, `*.aac`, `*.mp4`, `*.wav`, `.env`, `node_modules/`, `.venv/`, `__pycache__/`. Ngoại lệ: `brand/outro/*.mp4`, `library/outro/voice.wav`.

---

## 2. Chạy dự án

```
npm install                         # cài frontend + concurrently
python -m venv backend/.venv && backend\.venv\Scripts\pip install -e backend[whisper]
npm run dev                         # chạy song song: uvicorn 127.0.0.1:8000 + vite 127.0.0.1:5173
```

`.env.example`:
```
WORKSPACE_DIR=./workspace
LIBRARY_DIR=./library
WHISPER_MODEL=auto         # auto | small | medium | large-v3 (mục 5.2)
WHISPER_DEVICE=auto        # auto | cuda | cpu
DEFAULT_FPS=50
```
(`WHISPER_MODEL=auto` là trạng thái đích; M4 cập nhật `.env.example` và `config.py` cho khớp. Hiện `.env.example` còn `large-v3`.)

Backend chỉ bind `127.0.0.1`. Không có đăng nhập.

---

## 3. Mô hình dữ liệu

Mỗi project là 1 thư mục `workspace/projects/<slug>/`:

```
project.json
images/scene-01.png …        # ảnh gốc người dùng tải lên
voice.<ext>  music.<ext>
build/                       # file trung gian (xoá được), có cache theo hash
renders/<job_id>/video.mp4  captions.srt  publish.txt  log.txt
```

### 3.1 `project.json` (ví dụ đầy đủ — tập "muỗi")

```json
{
  "version": 1,
  "slug": "muoi-dot-nguoi-nay",
  "title": "Vì sao muỗi đốt người này mà tha người kia?",
  "series": "Vì sao vậy ta?",
  "theme": { "primary": "#146268", "accent": "#DE5C48" },
  "voice": "voice.mp3",
  "music": { "file": "music.mp3", "start": null, "credit": "The Wacky Sprint – nkbloom (Pixabay)" },
  "settings": { "fps": 50, "captions": true, "aligner": "auto", "sfx_on_punch": true, "outro": true },
  "scenes": [
    {
      "image": "images/scene-01.png",
      "card": { "y": "top", "lines": [
        { "text": "Bạn là người", "size": "s" },
        { "text": "“được muỗi yêu”?", "size": "l", "color": "accent" } ] },
      "labels": [],
      "voice": "Ngồi cùng một phòng, | mà chỉ mình bạn | bị muỗi cắn liên tục? | Bạn là người | “được muỗi yêu” đấy!",
      "punch": false,
      "caption_y": null
    },
    {
      "image": "images/scene-05.png",
      "card": { "y": "top", "lines": [
        { "text": "Mùi da thu hút muỗi", "size": "s" },
        { "text": "gấp 100 lần", "size": "xl", "color": "accent" } ] },
      "voice": "Nhưng thứ quyết định | là mùi da. | Người có nhiều | một chất tự nhiên trên da | có thể thu hút muỗi | gấp 100{một trăm} lần người khác.",
      "punch": false
    }
  ],
  "publish": {
    "hook": "Bạn có phải người \"được muỗi yêu\"? 🦟",
    "hashtags": ["visaovayta", "muoi", "khoahoc", "haybiettuot", "learnontiktok"]
  },
  "thumbnail": {
    "scene": 1,
    "lines": ["BẠN CÓ PHẢI", "NGƯỜI ĐƯỢC", "MUỖI YÊU?"],
    "series": "VÌ SAO VẬY TA?",
    "accent": "#FFD43B"
  }
}
```

### 3.2 Quy ước trường

| Trường | Giá trị |
|---|---|
| `card.y` | `top`=110, `upper`=560, `middle`=760, `lower`=1300, hoặc số pixel (khung 1080×1920) |
| `card.lines[].size` | `s`=50, `m`=62, `l`=84, `xl`=100 (≥70 dùng ExtraBold) |
| `card.lines[].color` | `ink` (mặc định), `primary`, `accent`, hoặc mã hex |
| `labels[]` | `{text, x, y, size, color, rot}` — chữ **gắn cố định vào ảnh** (di chuyển theo hiệu ứng phóng), dùng cho chữ trên băng rôn, số trên bục… |
| `voice` (gốc project) | `"voice.mp3"` hoặc `{"file", "trim_end"}`: file giọng; `trim_end` = giây của file gốc để cắt đuôi (mục 4d.3) |
| `scenes[].voice` | Lời đọc của cảnh. `|` = ngắt cụm phụ đề. `100{một trăm}` = hiển thị "100", đọc "một trăm" |
| `punch` | `true` = cảnh "cú lật": phóng giật + hiện thẻ nhanh + whoosh |
| `caption_y` | `null` = tự động (1400; nếu đáy thẻ > 1100 thì 230), hoặc số pixel |
| `music.start` | `null` = tự chọn đoạn hay; hoặc số giây |

Validate bằng Pydantic. Đúng **1 đoạn lời cho mỗi cảnh**; số cảnh 3–12.

---

## 4. Pipeline dựng video (`pipeline/render.py`)

Mỗi bước báo tiến độ (0–100) và ghi log. Bước nào có output trùng hash đầu vào thì bỏ qua (cache trong `build/`).

| # | Bước | Chi tiết | Tiến độ |
|---|---|---|---|
| 1 | Kiểm tra | Validate project, đủ ảnh/giọng, chạy `lint` với danh sách từ hiện hành (mục 7). Có mức `block` → dừng, báo `Chặn xuất: Cảnh N: …` (CLI lấy danh sách như app: bản riêng ở `workspace/settings/` nếu có, không thì bản mặc định) | 0–3 |
| 2 | Chuẩn hoá giọng | `prep_voice` (reference): highpass 70 Hz, trễ 0,2 s, đệm 1,6 s, loudnorm −14 LUFS, mono 44,1 kHz → `build/voice.wav` | 3–6 |
| 3 | Căn chữ | Ghép token mọi cảnh (giữ chỉ số cảnh) → `render.run_alignment()` (Whisper qua `whisper.run_whisper` + `align.match_script`, rơi về `scene_align.align_scenes`; mục 5). Lưu `build/timing.json` | 6–20 |
| 4 | Mốc chuyển cảnh | cut_k = (kết thúc chữ cuối cảnh k−1 + bắt đầu chữ đầu cảnh k)/2; offset xfade = cut − 0,2; thời lượng theo `durations()` (reference) | 20 |
| 5 | Lớp hình | `visual.build_scene_layers`: ảnh fit 1080×1920 + nhãn cố định; lớp thẻ chữ PNG trong suốt | 20–25 |
| 6 | Clip từng cảnh | `render_scene` (reference): zoompan trên ảnh phóng 2160×3840, cảnh lẻ 1.00→1.08, chẵn 1.08→1.00; `punch`: 1.18→1.00 trong 0,4 s rồi 1.00→1.05; thẻ hiện dần sau 0,3 s (punch: 0,15 s). Encode trung gian `crf 16 veryfast` | 25–70 |
| 7 | Âm thanh | Chọn đoạn nhạc (mục 6), `mix_audio` (reference): nhạc −27 LUFS, ducking theo giọng, fade vào 0,8 s / ra 2,5 s, whoosh tại các cảnh `punch`, tổng −14 LUFS | 70–75 |
| 8 | Phụ đề | `captions.py` (mục 5.3) → PNG trạng thái + `captions.ffconcat` + `captions.srt` | 75–80 |
| 9 | Ghép cuối | `assemble` (reference): xfade `slideleft` 0,4 s + phủ phụ đề + tiếng; H.264 `crf 18 medium`, `-r {fps}`, yuv420p, AAC 192k, `+faststart` | 80–98 |
| 10 | Kiểm tra đầu ra | ffprobe đúng fps, 1080×1920, độ dài; đo `ebur128` trong khoảng −15…−13 LUFS; sinh `publish.txt` | 98–100 |

**Chế độ Xem nhanh (`preview=true`):** 540×960, 30 fps, **phóng ×2 (2160×3840, `lanczos`) trước zoompan** như reference 30 fps (chốt 26/10/2026 theo số đo rung: không phóng thì zoompan làm tròn vị trí cắt về pixel nguyên của ảnh 1080 và hình rung; rung x/y giảm từ 0,19–0,39 px xuống 0,05–0,09 px, dựng cả video muỗi 59 s → 66 s; áp cho cả Xem nhanh 10 s), clip cảnh `ultrafast crf 23`, ghép cuối `veryfast crf 30`, AAC 96 kbps. Dùng để duyệt trước khi xuất bản đẹp. Mục tiêu dưới ~10 MB cho video 50 giây; đo thực tế trên tập "muỗi": 3,7 MB, 36 s dựng (trước đó `ultrafast crf 23` + AAC 192k: 39,8 MB). Tham số bản đẹp không đổi.

**Xem nhanh 10 s đầu** (chủ dự án chốt 23/10/2026): nút **Xem nhanh** mặc định chỉ dựng 10 giây đầu (`preview_seconds = 10`, vẫn 540×960, 30 fps); nút phụ **Xem nhanh cả video** giữ cách dựng cũ.
- **Phần dùng chung với cả video:** giọng, căn chữ (cache `timing.json`), mốc chuyển cảnh, điểm nhạc (`music_start`) vẫn tính trên **cả video**; nên lần đầu vẫn tốn thời gian căn chữ (chấp nhận), thời gian dựng tuỳ máy.
- **Cảnh nào được dựng:** những cảnh bắt đầu trước giây T. Cảnh cuối của đoạn chỉ giữ các khung trước giây T nhưng `zoompan` vẫn tính theo độ dài đầy đủ của cảnh, nên 10 s đầu giống hệt khung hình của bản xem nhanh cả video. Cảnh sau T không dựng.
- **Tiếng:** trộn nhạc/giọng/whoosh trên cả video như thường rồi giữ T giây đầu, **fade ra 0,3 s** ở cuối (không cắt đột ngột).
- **Không có:** outro, `captions.srt`, đo độ lớn (LUFS; `lufs = null`). Vẫn kiểm fps, kích thước và độ dài ≈ T (±0,25 s). Phụ đề karaoke vẫn hiện trên hình trong 0–T.
- **Video ngắn hơn hoặc bằng T:** dựng như xem nhanh cả video (có outro nếu bật), `preview_seconds` trong `meta.json` là `null`.
- **`meta.json`:** `preview_seconds` (10 hoặc `null`); `music_start`, `music_start_source`, `music_sha256` vẫn là của cả video; `duration` là độ dài thật của file.
- **CLI:** `python -m cli render <dir> --preview --seconds 10`.

**FPS:** mặc định **50** (cho phép 30, 50, 60). Không cho chọn số lạ như 45 (nền tảng dễ chuyển đổi lại gây giật). Xem mục 4b.

### 4b. Chất lượng chuyển động 50fps (ghi đè bước 6 và 9)

Đã chạy thật trên 6 video, chủ dự án xác nhận mượt hơn bản 30/60fps cũ. Mã tham khảo: `reference/pipeline/render50_reference.py` (đối chiếu từng tham số).

| Hạng mục | Quy cách |
|---|---|
| FPS | 50 |
| Phóng ảnh | Ảnh nội bộ **3240×5760** (`scale ... flags=lanczos`, gấp 3 lần) rồi `zoompan` ra 1080×1920. Hết rung lăn tăn khi phóng chậm |
| Easing phóng | `smoothstep(p) = p·p·(3−2p)`: cảnh lẻ 1.00→1.08, cảnh chẵn 1.08→1.00. Cảnh `punch`: 1.18→1.00 trong 0,45 s theo `easeOutCubic`, rồi 1.00→1.05 theo smoothstep |
| Chuyển cảnh | **Không dùng `xfade`.** Ghép bằng Python (numpy): trượt ngang theo `easeInOutCubic` trong 0,4 s (20 khung), mỗi khung lấy **6 mẫu con** trong nửa chu kỳ khung (màn trập 180°) rồi lấy trung bình để tạo nhoè chuyển động |
| Mã hoá | Clip cảnh `crf 12 veryfast`; bản cuối `crf 16 veryfast`, `-profile:v high`, `-g 100`, yuv420p, AAC 192k |
| Lý do chất lượng cao | TikTok/YouTube nén lại video khi đăng, nên cần dư chi tiết đầu vào. Dung lượng ~45–55 MB cho video 45–55 giây là bình thường |
| Hiệu năng | Máy 1 nhân dựng ~3,6 giây cho mỗi giây video. Giữ chế độ **Xem nhanh** (540×960, 30fps) để duyệt trước |

Nút xuất cuối: **50fps (mặc định)**, **60fps**, **30fps**.

### 4c. Outro (tự động thêm cuối mỗi video)

- Clip dựng sẵn: `brand/outro/outro_4s_50fps.mp4` (4,0 giây, 1080×1920, 50fps). Mã tạo: `reference/pipeline/outro_reference.py` (Pillow, nền đỏ chấm bi, logo bật nảy, dòng "Theo dõi để biết tuốt mọi chuyện!", nút THEO DÕI, 2 nút chữ TikTok và YouTube, tên kênh). **Không dùng logo TikTok/YouTube.**
- **Clip theo fps xuất (chủ dự án chốt 26/10/2026):** xuất 60 fps dùng `brand/outro/outro_4s_60fps.mp4`; xuất 50 và 30 fps dùng clip 50 như cũ (`render.outro_clip_for`; thiếu clip 60 thì dùng clip 50). Lý do: đổi 50→60 bằng filter `fps=` lặp khung (cứ 6 khung có 1 khung trùng hệt, khoảng 10 khung/giây ở outro). Clip 60 dựng bằng đúng mã `outro_reference.py` chỉ đổi `FPS=60` (chạy bản sao tạm có đổi đường dẫn font và logo; `reference/` không sửa): 4,0 s (240 khung), 1080×1920, `libx264 crf 14`, `yuv420p`, mốc hình 1,15 / 2,15 / 2,55 / 2,85 s như clip 50. Kiểm: không còn mẫu khung lặp đều; so cùng thời điểm với clip 50 dựng lại từ cùng mã thì PSNR 46 dB (cùng nội dung). Chữ ở mép nét của clip 60 khác clip 50 gốc một chút (PSNR khoảng 26–30 dB so với clip 50 đã đăng) vì bản dựng lại dùng font và Pillow của repo.
- Cài đặt: `settings.outro` (mặc định `true`) chỉ là bật/tắt; clip outro cố định **4,0 giây** (không có cài đặt thời lượng).
- **Thời điểm hình** trong clip: nút THEO DÕI 1,15 s, nút TikTok 2,15 s, nút YouTube 2,55 s, tên kênh 2,85 s (đã căn theo lời đọc).
- Ghép vào video: nối sau cảnh cuối bằng hoà trộn hình (`fade`) **0,5 s** kèm `acrossfade` **0,5 s** cho tiếng; không áp phụ đề karaoke lên outro. Nhạc nền tiếp tục nhỏ dần trong 2,5 giây cuối của **phần có lời**.
- **Lời outro:** file `library/outro/voice.wav` đã có sẵn (44,1 kHz mono, dài 2,65 s, **−16,2 LUFS**, đỉnh **−1,5 dBFS**; độ lớn riêng của file này không được dùng để suy ra độ lớn outro), đọc câu `Theo dõi Hay Biết Tuốt trên TikTok và YouTube nhé!`. Dùng chung mọi video, không cần tạo lại. Thiếu file thì vẫn dựng được, outro chỉ còn tiếng "ting".
- **Âm thanh outro** (đã chạy thật):
  - Giọng đặt trễ **0,5 s** (lời bắt đầu khoảng 0,6 s, kết thúc khoảng 3,0 s).
  - Hai tiếng "ting" tổng hợp bằng FFmpeg (như `synth_whoosh`): `vol 0,22` tại **0,15 s** và `vol 0,18` tại **1,15 s**.
  - Outro đạt **−14,0 LUFS**, đỉnh khoảng **−2 dBFS**. Quy trình khi dựng:
    1. Nhân đôi giọng sang stereo (`pan=stereo|c0=c0|c1=c0`) rồi trộn với hai tiếng "ting". Chưa chỉnh độ lớn: mức này đo được **−13,4 LUFS**.
    2. **Đo** tổng bằng `ebur128`, tính `gain = −14,0 − số đo` (ở mẫu hiện tại khoảng −0,6 dB), áp gain.
    3. Giới hạn đỉnh bằng `alimiter=limit=0.89:level=0`. **Không để `level` mặc định** vì filter sẽ tự nâng mức lên −13 LUFS.
  - Không dựa vào độ lớn riêng của `voice.wav`; luôn đo lại sau khi trộn.
  - Mờ ra **0,3 s** cuối clip.
- UI: công tắc **Thêm outro** trong tab Xuất video.

### 4d. Lời đọc Vbee

- **Giới hạn ký tự:** lời đọc mỗi video **≤ 750 ký tự** (tính cả dấu cách; bỏ ký hiệu `|` và `{}`), vì gói Vbee giới hạn 3.000 ký tự mỗi ngày. Hiển thị bộ đếm cạnh ô lời đọc, cảnh báo vàng khi > 750 (mức `warn`, vẫn cho xuất).
- **Cắt quảng cáo cuối file Vbee:** file giọng từ Vbee có thể kèm câu giới thiệu hoặc quảng cáo ở cuối. Sau khi căn chữ (bước 3), mọi âm thanh nằm **sau chữ cuối của kịch bản** đều bị cắt:
  1. Với Whisper (M4): `voice_end = end(token cuối) + 0,35 s`, cắt đuôi, fade ra 80 ms.
     - **Chốt M4 Đợt 1a (24/10/2026):** cắt sau bước 3, trên `build/voice.wav`. Sau `voice_end` đệm sao cho tổng **1,6 s sau chữ cuối** (nghĩa là đệm `1,6 − 0,35 = 1,25 s`), rồi chuẩn hoá lại −14 LUFS. Chỉ cắt khi token cuối của kịch bản **khớp thật** với âm tiết Whisper nghe được; token cuối chỉ được nội suy thì **không cắt**, chỉ cảnh báo `Có thể có đoạn thừa ở cuối file giọng…`. Cắt > 8 s: job `failed` + `needs_confirmation`, gửi lại với `allow_long_trim` (cơ chế M2, mục 9), không thêm API.
  2. Với chế độ khoảng lặng (chưa có Whisper), căn 2 cấp: cấp 1 ghép cảnh ↔ nhóm đoạn tiếng, cấp 2 ghép cụm câu ↔ đoạn tiếng trong từng cảnh (mục 5.2). Chỉ **tự động** bỏ đoạn cuối khi đủ **cả ba** điều kiện:
     - điều kiện bảo vệ: tối đa `số đoạn tiếng − số cụm câu` đoạn cuối (và không quá 3);
     - bỏ đoạn đó làm chi phí ghép **giảm từ 1,0 trở lên**;
     - đoạn cuối dài **từ 1,5 giây**.

     Ngược lại giữ nguyên và ghi cảnh báo `Có thể có đoạn thừa ở cuối file giọng (x,xx giây), chưa cắt` (nếu bỏ đoạn đó vẫn làm chi phí giảm). Kịch bản ngắn (khoảng 3 cảnh) thường không đạt ngưỡng 1,0 nên chỉ cảnh báo.
  3. **Tự cắt tay bằng `voice.trim_end`:** trong `project.json`, `voice` có thể là `"voice.mp3"` hoặc `{"file": "voice.mp3", "trim_end": 41.5}`. `trim_end` là giây trên **file giọng gốc** (nghe file gốc để chọn điểm cắt). Có `trim_end` thì cắt **trước khi căn chữ** (để đoạn thừa không làm lệch căn), không chạy cắt tự động và không cần xác nhận, fade ra 80 ms, đệm lại 1,6 s. `trim_end` nằm sau hết file giọng thì báo lỗi.
  4. Ghi log `Đã cắt N đoạn thừa ở cuối file giọng (x,xx giây)` và hiện trong UI kèm nút **nghe phần đã cắt** để chủ dự án xác nhận. Cắt quá 8 giây thì dừng và hỏi.
     - **Chốt M4 Đợt 1a (24/10/2026):** phần bị cắt lưu ở `renders/<job_id>/trimmed_tail.wav` (không ở `build/`, vì nút Dọn file tạm xoá `build/`), cho cả đường Whisper, khoảng lặng và `voice.trim_end`. `meta.json` có `trimmed_tail` (tên file hoặc `null`) và `trimmed_tail_seconds`; `GET /renders` và `output` của job trả `trimmed_tail` (URL hoặc `null`). Job `needs_confirmation` cũng lưu file này và trả URL ở trường `cut_audio` để nghe trong hộp xác nhận. Phát qua `GET /files` sẵn có, không thêm endpoint.
  5. Âm lượng và hạ nhạc (ducking) chỉ tính trên phần giọng đã cắt.

### 4e. Ảnh bìa (thumbnail)

Mỗi video có ảnh bìa, tạo cùng lúc với video (module `pipeline/thumbnail.py`). Mã tham khảo: `reference/pipeline/thumbnail_reference.py` (đối chiếu từng tham số; file đó ghi cứng đường dẫn font và logo nên không chạy trực tiếp).

- **Đầu ra** (trong `renders/<job>/`):
  - `cover_9x16.jpg`: 1080×1920, JPG chất lượng 93, sRGB, dưới 5 MB, dùng cho TikTok/Reels.
  - `youtube_3x2.jpg`: 1080×720, là dải cắt giữa y=600..1320 của cùng ảnh, dùng cho YouTube Shorts.
- **Dữ liệu** (`project.json` → `thumbnail`, mục 3.1): `scene` (cảnh làm nền, mặc định 1), `lines` (2–3 dòng tiêu đề), `series` (chữ trên nhãn series), `accent` (màu dòng cuối, mặc định `#FFD43B`).
- **Nền:** ảnh của cảnh được chọn (`thumbnail.scene`), độ sáng ×0,82, bão hoà ×1,1, thêm dải tối mềm quanh y=960 (alpha tối đa 0,5).
- **Tiêu đề:** 2–3 dòng IN HOA, căn giữa, font **Bricolage Grotesque** 800 (width 78).
  - Font này (OFL) phải được thêm vào `backend/hbt/fonts/` kèm giấy phép. Khi chưa có thì dự phòng Be Vietnam Pro ExtraBold.
  - Dòng lớn nhất cỡ tối đa 185 px và vừa trong 950 px. Dòng cuối (từ khoá) màu `accent` (mặc định vàng `#FFD43B`), lớn hơn ×1,12 (tối đa 205 px) nếu vẫn vừa 950 px.
  - Tổng chiều cao khối chữ tối đa 610 px.
  - Viền tối bằng 11% cỡ chữ, cộng bóng đổ lệch (10, 12).
- **Vùng an toàn:** khối tiêu đề nằm trong y=600..1320 (vừa khung cắt 3:2 của YouTube Shorts). Nhãn series (cao 84 px, y=330) và logo HBT (rộng 300 px, y=1385) nằm trong y=240..1680 (vừa khung cắt 3:4 của lưới hồ sơ TikTok).
- **Quy tắc chung:** chữ luôn vẽ bằng Pillow. Áp dụng lint từ nhạy cảm (mục 7) cho các dòng bìa.
- **Quyết định M4 Đợt 3** (chủ dự án chốt 23/10/2026):
  - **Font:** `backend/hbt/fonts/BricolageGrotesque-Variable.ttf` (bản variable từ kho `google/fonts`, trục `opsz` 12–96, `wght` 200–800, `wdth` 75–100), giấy phép `OFL-BricolageGrotesque.txt`; giấy phép Be Vietnam Pro đổi tên `OFL-BeVietnamPro.txt`. Pillow đặt `set_variation_by_axes([96, 800, 78])` (thứ tự trục của file là opsz, wght, wdth). Thiếu file thì dự phòng Be Vietnam Pro ExtraBold. Cố định, không chỉnh trong Cài đặt.
  - **Chữ:** mỗi dòng chuẩn hoá NFC rồi `.upper()` khi vẽ ("đ"→"Đ", "ư"→"Ư", "ỷ"→"Ỷ"); `project.json` giữ nguyên chữ người dùng nhập. Nhãn series lấy `thumbnail.series`, trống thì `project.series`, trống cả hai thì bỏ nhãn.
  - **Khi nào vẽ:** cùng lúc với video ở bản đẹp và Xem nhanh cả video; **bỏ qua** ở Xem nhanh 10 s đầu. Project không có khối `thumbnail` thì không vẽ (và `publish.txt` không có khối `[Thumbnail]`).
  - **Lỗi vẽ bìa** (thiếu logo, ảnh nền hỏng…) chỉ là cảnh báo: log `Không vẽ được ảnh bìa: …`, `result.warnings`, video vẫn xuất; `meta.json` để `cover_9x16` và `youtube_3x2` là `null`; tab Xuất video hiện cảnh báo ở khối "Cảnh báo khi dựng".
  - **`meta.json`** thêm `cover_9x16` và `youtube_3x2` (tên file hoặc `null`); `GET /renders` và `output` của job trả `cover` và `youtube_cover` (URL hoặc `null`).
  - JPG chất lượng 93 (`subsampling=0`); nếu quá 5 MB thì hạ dần chất lượng (tối thiểu 70).
- **UI tab Xuất video:** ô nhập 2–3 dòng, chọn cảnh nền, xem trước hai khung cắt 3:4 và 3:2, nút tải hai file. `publish.txt` có khối `[Thumbnail]` gồm 3 dòng (mục 8, đã làm từ M1; M4 chỉ thêm file ảnh thật): `Dòng chữ bìa: <các dòng cách nhau bằng dấu />`, `TikTok: cover_9x16.jpg`, `YouTube Shorts: youtube_3x2.jpg`.

**Vùng an toàn TikTok:** nội dung quan trọng (thẻ, phụ đề) trong khoảng y = 100…1500, tránh mép phải 120 px.

---

## 5. Căn chữ & phụ đề

### 5.1 Token (`text.parse_voice`)
- Tách theo khoảng trắng; `|` đánh dấu cụm mới; token kết thúc bằng `, . ! ? : ; …` cũng kết thúc cụm.
- Mỗi token có `disp` (hiển thị) và `syl` (danh sách âm tiết đã bỏ dấu, dùng để so khớp).

### 5.2 Căn thời gian (`render.run_alignment`)
1. **Whisper** (mặc định): faster-whisper, `language="vi"`, `word_timestamps=True`, **không dùng `initial_prompt`** (điểm lệch tham số reference đã duyệt 24/10/2026, số đo bên dưới; reference dùng lời đọc 220 ký tự đầu). Chuẩn hoá âm tiết nghe được (`text.norm`), so khớp với âm tiết kịch bản bằng `difflib.SequenceMatcher(autojunk=False)`; âm tiết không khớp thì nội suy giữa 2 điểm neo. Thời gian token = âm tiết đầu → âm tiết cuối.
   - **Chọn cấu hình theo phần cứng** (chủ dự án chốt 22/10/2026). `.env`: `WHISPER_DEVICE=auto`, `WHISPER_MODEL=auto`.

     | Phần cứng | Thiết bị | Kiểu tính | Model |
     |---|---|---|---|
     | Có CUDA (máy mới, RTX 2060 Super 8 GB) | `cuda` | `int8_float16` | `large-v3` (cần thư viện CUDA 12 theo README của faster-whisper) |
     | Không có GPU (máy cũ) | `cpu` | `int8` | `small` |

     Trong **Cài đặt** cho đổi sang `medium` hoặc `large-v3` trên CPU, kèm cảnh báo "sẽ chậm". Không giả định có GPU: `auto` kiểm tra CUDA lúc chạy (`/health.gpu`).
   - **Cache:** kết quả căn chữ lưu ở `build/timing.json`, khoá theo **hash file giọng** và **hash kịch bản** (kèm phương pháp, model, mã nguồn); chỉ căn lại khi một trong hai đổi.
   - **Điểm lệch đã duyệt (24/10/2026):** khoá còn gồm thêm `whisper_timeout_seconds`, "đã cài faster-whisper chưa" và "có CUDA không" (`WhisperConfig.key_parts`). Nhờ vậy tăng giới hạn thời gian, cài Whisper hoặc đổi máy thì căn lại, không dùng nhầm kết quả khoảng lặng cũ.
   - **Dự phòng khi lỗi hoặc chậm:** Whisper lỗi (không cài, lỗi CUDA, thiếu RAM) hoặc quá chậm (vượt **giới hạn thời gian** đặt trong Cài đặt) thì tự rơi về căn theo khoảng lặng (mục dưới) và ghi log lý do; kết quả ghi rõ phương pháp đã dùng.
   - **Chốt M4 Đợt 1a (chủ dự án duyệt 24/10/2026):**
     - **Bậc rơi theo mục 0:** CUDA lỗi (lúc nạp hoặc lúc chạy) hoặc không có GPU → CPU `small` `int8` → khoảng lặng. Mỗi bậc ghi log lý do.
     - **Tiến trình con:** Whisper chạy trong tiến trình con (`python -m hbt.pipeline.whisper_worker`), không chạy trong tiến trình app. Hết giờ hoặc huỷ job thì kill tiến trình con; model được giải phóng khi tiến trình thoát (bước 3 bên dưới).
     - **Giới hạn thời gian:** một giá trị cố định `whisper_timeout_seconds` (Cài đặt, mặc định **900 s**), tính cho cả bước Whisper (mọi bậc cộng lại). Hết giờ thì rơi thẳng về khoảng lặng.
     - **Ưu tiên cấu hình:** `whisper_model` trong `workspace/settings/app.json` (Cài đặt) ghi đè `.env`; giá trị `auto` thì xét `WHISPER_MODEL` trong `.env`, vẫn `auto` thì chọn theo phần cứng (bảng trên).
     - **Model:** đã có trong `models/` thì nạp thẳng từ đó (`local_files_only`), không tải lại; chưa có thì tải về `models/` (`download_root`). `faster_whisper` chỉ được import khi dùng.
     - **Dữ liệu vào:** Whisper chạy trên `build/voice.wav` (kết quả bước 2).
     - **Tỉ lệ khớp** (âm tiết kịch bản khớp âm tiết nghe được) chỉ ghi vào log và `meta.json`, không có ngưỡng chặn.
     - **Phương pháp đã dùng** (kèm model, thiết bị, lý do nếu rơi bậc) ghi ở `meta.json`, log và khối kết quả tab Xuất video.
     - **`bench-align`** chỉ có 3 chỉ số: thời gian, tỉ lệ khớp, độ lệch mốc cắt cảnh so với căn khoảng lặng. Không so với bản đã đăng; golden test là xem video (mục 10b).
     - **`bench-align --prompt off|on|both`** (mặc định `off`, khớp đường dựng): `on` và `both` chỉ để so sánh (ở 1b); báo thêm từng mốc cắt cảnh và ghi rõ model vượt giới hạn thời gian.
     - **Tiến độ:** trong lúc Whisper chạy, thanh tiến độ đi từ 6% đến 20% theo phần giọng đã nghe (khung bước 3 ở mục 4); tiến trình con ghi tỉ lệ sau mỗi đoạn nhận dạng, tiến trình cha đọc.
     - Chưa qua golden (xem Xem nhanh, mục 10b) thì chỉ báo số đo, **không** tự đổi mặc định.
   - **Điểm lệch tham số reference: bỏ `initial_prompt` cho mọi model (chủ dự án duyệt 24/10/2026).** Đo bằng `bench-align --models small,medium,large-v3 --prompt both` trên "muỗi" (máy cũ, CPU `int8`, máy rảnh, 24/10/2026). Có prompt, cả ba model bỏ sót nửa đầu kịch bản (tỉ lệ khớp 61–63%); bỏ prompt thì khớp 89–91%. Lệch mốc cắt cảnh so với căn khoảng lặng (khoảng lặng từng khớp bản đã đăng trong 4 ms ở 7 mốc):

     | Model | Prompt | Thời gian | Khớp | Lệch TB | Lệch max | Từng mốc (ms) |
     |---|---|---|---|---|---|---|
     | small | có | 22,0 s | 62,9% | 3684 | 12374 | 5329 · 7759 · 12374 · 125 · 74 · 62 · 65 |
     | small | không | 18,5 s | 89,4% | 129 | 354 | 49 · 1 · 354 · 85 · 324 · 42 · 45 |
     | medium | có | 107,3 s | 62,9% | 1752 | 7051 | 7051 · 4621 · 6 · 105 · 206 · 168 · 105 |
     | medium | không | 57,8 s | 90,1% | 137 | 258 | 11 · 241 · 126 · 105 · 156 · 258 · 65 |
     | large-v3 | có | 130,3 s | 60,9% | 12109 | 24651 | 24651 · 22221 · 17606 · 13725 · 4796 · 1618 · 145 |
     | large-v3 | không | 111,4 s | 91,4% | 330 | 435 | 389 · 89 · 354 · 435 · 384 · 322 · 335 |

     Không model nào vượt 900 s. Ngưỡng số 0,05 s đã bỏ (26/10/2026); đạt hay không do chủ dự án xem video, mục 10b (chỉ báo số, mục dưới). **Mặc định `auto` giữ như bảng trên** (CPU → `small` `int8`; CUDA → `large-v3` `int8_float16`); mặc định cuối của mỗi máy chốt sau golden test. `large-v3` trên CPU lệch đều khoảng 0,3–0,4 s ở gần như mọi mốc, chưa rõ nguyên nhân: kiểm ở 1b.
   - **Đo thật để chốt mặc định:** lệnh `python -m cli bench-align <dự án> [--models small,medium,large-v3]` (làm ở M4) báo thời gian chạy, tỉ lệ âm tiết khớp với kịch bản và độ lệch mốc cắt cảnh so với căn khoảng lặng. Mặc định cuối cùng chốt theo số đo thật trên từng máy.
2. **Dự phòng — khoảng lặng** (`pipeline/scene_align.py`; dùng khi không cài Whisper hoặc `aligner="silence"`), căn **2 cấp**:
   - Cấp 1: ghép các cảnh (mỗi cảnh là một đoạn lời) với các nhóm đoạn tiếng liên tiếp; chi phí theo tổng thời lượng so với trọng số của cảnh.
   - **Điểm lệch khỏi mô tả ban đầu** (chủ dự án duyệt 21/10/2026): thêm vào chi phí cấp 1 một **số hạng phạt khoảng nghỉ**. Nếu cảnh kết thúc bằng dấu cuối câu (`.` `?` `!`) thì ranh giới sau cảnh đó phải rơi vào khoảng nghỉ dài: phạt `4,0 × max(0, ngưỡng − độ dài khoảng nghỉ)`, với ngưỡng = 0,85 × phân vị 75 của các khoảng nghỉ trong chính file (nên không phụ thuộc giọng cụ thể). Cảnh không kết thúc bằng dấu cuối câu thì không bị phạt. Không có số hạng này, trên tập "muỗi" ranh giới cảnh 6→7 và 7→8 trôi sang đoạn kế bên (lệch hàng giây); có nó thì 7 mốc cắt khớp bản đã đăng trong 4 ms. Test: `test_scene_boundary_follows_the_long_pause_when_the_scene_ends_a_sentence` (đã kiểm tra bằng cách tắt số hạng này thì test fail).
   - Cấp 2: trong từng cảnh, ghép các cụm câu với các đoạn tiếng của cảnh đó bằng quy hoạch động của reference (`align_silence`).
   - Nếu một cảnh có ít đoạn tiếng hơn số cụm câu, hạ dần ngưỡng khoảng lặng **chỉ trong phạm vi cảnh đó**: (0,25 s, −38 dB) → (0,18 s, −36 dB) → (0,12 s, −35 dB) → (0,08 s, −34 dB), dừng khi đủ đoạn. Nếu số đoạn toàn file ít hơn số cảnh thì hạ ngưỡng toàn cục.
   - Nếu cả khi đó vẫn ít đoạn hơn cụm (hai cụm nói liền không có khoảng nghỉ), các cụm chia nhau đoạn theo trọng số, nên có thể lệch nửa giây trong cảnh đó; Whisper khắc phục.
   - Quyết định bỏ đoạn thừa ở cuối file: mục 4d.2.
3. Sau khi căn xong: giải phóng model Whisper khỏi VRAM.

### 5.3 Phụ đề karaoke (`captions.py`)
- **Cụm:** theo `|` và dấu câu; cụm > 7 token thì tự tách đôi. Tối đa 2 dòng, rộng 900 px.
- **Kiểu:** Be Vietnam Pro ExtraBold 70 px, chữ trắng viền tối 7 px + bóng; **chữ đang đọc** đổi màu vàng `#FFD43B` (cùng viền tối 7 px và bóng), đọc xong trở lại trắng; **không có nền viên thuốc** (chủ dự án chốt 26/10/2026, thay kiểu cũ: nền vàng bo 18 px, chữ tối). Dòng cao 96 px, căn giữa tại `caption_y` (tâm khối chữ; mặc định **1400** từ 26/10/2026 để đáy khối 2 dòng, kể cả dấu và chân chữ, ≤ 1500 trong vùng an toàn TikTok y=100…1500; trước đó 1420 cho đáy tới 1519).
- **Thời gian hiện cụm:** từ (đầu chữ đầu − 0,05 s) đến đầu cụm sau nếu khoảng cách < 0,6 s, ngược lại đến (cuối chữ cuối + 0,25 s). Chữ k sáng từ đầu chữ k đến đầu chữ k+1.
- **Hiển thị:** bỏ `, . : ;` cuối token; giữ `? ! …`.
- **Kỹ thuật:** mỗi trạng thái 1 PNG 1080×1920 trong suốt; file `ffconcat` có `duration`; phủ bằng `overlay` (xem `assemble`).
- Xuất kèm `captions.srt` (theo cụm) để tải lên YouTube nếu muốn.

---

## 6. Âm thanh & thư viện nhạc

### 6.1 Tự chọn đoạn nhạc (`music.start = null`)
Tính độ lớn theo cửa sổ 1 s; bỏ 2 s đầu; chọn thời điểm đầu tiên có độ lớn ≥ (trung vị − 3 dB) để bỏ phần dạo đầu quá nhỏ; nếu đoạn còn lại ngắn hơn video thì lùi điểm bắt đầu. Ghi điểm đã chọn vào log để người dùng chỉnh tay.

**Quyết định P3 (chủ dự án chốt 23/10/2026):** mỗi lần dựng (xem nhanh và bản đẹp) ghi vào `renders/<job>/meta.json` hai khoá `music_start` (giây thật đã dùng, `null` nếu không có nhạc) và `music_start_source` (`"manual"` khi `music.start` đặt tay, `"auto"` khi app tự chọn). `GET /projects/{slug}/renders` trả cả hai khoá; không thêm route, không thêm trường vào `project.json`. Khi `music.start + độ dài phần có lời` vượt độ dài nhạc, log ghi CẢNH BÁO (không chặn). `meta.json` còn có `music_sha256` (SHA-256 file nhạc đã dùng, `null` khi không nhạc); `GET /renders` thêm `music_matches_current` (hash file nhạc hiện tại == `music_sha256`). Tab Âm thanh chỉ hiện "app chọn giây X" và nút **Dùng giá trị này** khi cờ này là `true`; `false` thì hiện ghi chú nhạc đã đổi. Thư viện nhạc không có điểm bắt đầu riêng.

### 6.2 Thư viện `library/music/index.json`
```json
[{ "id": "the-wacky-sprint", "file": "funny/the-wacky-sprint.mp3", "title": "The Wacky Sprint", "artist": "nkbloom",
   "source": "Pixabay", "url": "https://pixabay.com/…", "license": "Pixabay Content License",
   "moods": ["vui", "tinh nghịch"], "bpm": null }]
```
UI cho chọn nhạc từ thư viện hoặc tải file mới (tải mới thì hỏi tên, tác giả, nguồn, giấy phép, tâm trạng → thêm vào index). `credit` của project tự điền từ thư viện.

### 6.3 Whoosh
Tổng hợp bằng FFmpeg (`synth_whoosh` trong reference), không dùng file ngoài → không vướng bản quyền.

Thông số (chủ dự án chốt 20/10/2026, giống 6 video cũ), áp khi `settings.sfx_on_punch = true`:
- Thời điểm `at` = lúc bắt đầu trượt chuyển cảnh vào cảnh `punch` đó (v1.2 không còn `xfade`, mốc vẫn là `cut − 0,2 s`, mục 4b). Cảnh 1 là `punch` thì `at = 0`.
- Âm lượng `vol = 0.30`, áp trước bước loudnorm tổng (−14 LUFS) trong `mix_audio`.

### 6.4 Video không có nhạc
Cho phép dựng khi `music` trống (chủ dự án chốt 20/10/2026). Bỏ bước cắt nhạc và ducking; giọng đã chuẩn hoá −14 LUFS (bước 2) được chuyển sang **stereo** để xuất. Whoosh (nếu có) vẫn trộn vào rồi loudnorm tổng −14 LUFS như khi có nhạc.


### 6.5 Âm thanh tổng hợp (thông số đã chạy thật, chủ dự án cung cấp 21/10/2026)
Tất cả tổng hợp bằng FFmpeg, không dùng file ngoài. Xuất stereo 44,1 kHz.

| Tiếng | Lệnh `aevalsrc` / chuỗi lọc | Dùng ở |
|---|---|---|
| **Vút** (cảnh "cú lật") | như `synth_whoosh` trong `render_reference.py`: `anoisesrc=d=0.7:c=pink:a=0.6`, `highpass=f=300,lowpass=f=6000,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.35`; âm lượng 0,30 | mục 6.3 |
| **Ting** (outro) | `aevalsrc='0.35*(sin(2*PI*1318*t)+0.6*sin(2*PI*1976*t)+0.4*sin(2*PI*2637*t))*exp(-5*t)':d=0.9:s=44100`; hai tiếng: âm lượng 0,22 tại 0,15 s và 0,18 tại 1,15 s | mục 4c |
| **Rít** ngắt nhịp (tuỳ chọn, chưa làm ở M1) | `aevalsrc='0.6*sin(2*PI*(900*t-1300*t*t))*exp(-4*t)':d=0.38:s=44100`, rồi `afade=t=out:st=0.25:d=0.13` | dự phòng |

---

## 7. Kiểm tra nội dung nhạy cảm (`pipeline/lint.py`)

`data/sensitive_words.json`:
```json
{ "categories": [
  { "id": "alcohol",  "level": "warn",  "words": ["bia", "rượu", "say xỉn", "nhậu"] },
  { "id": "blood",    "level": "warn",  "words": ["máu me", "đổ máu", "túi máu"] },
  { "id": "chemical", "level": "warn",  "words": ["axit", "chất độc", "hoá chất"] },
  { "id": "violence", "level": "warn",  "words": ["giết", "đâm chém", "súng"] },
  { "id": "drugs",    "level": "block", "words": ["ma tuý", "cần sa"] },
  { "id": "politics", "level": "warn",  "words": ["đảng", "chính phủ", "biểu tình"] },
  { "id": "map",      "level": "warn",  "words": ["bản đồ", "hoàng sa", "trường sa"], "hint": "Kiểm tra ảnh bản đồ có đủ Hoàng Sa, Trường Sa" }
]}
```
- So khớp không phân biệt hoa thường, theo ranh giới từ, trên `card.lines[].text`, `labels[].text`, `voice`, `publish.hook`.
- Trả về danh sách `{scene, field, word, category, level, hint}`. `warn` → hiện cảnh báo vàng, vẫn cho xuất; `block` → chặn xuất.
- Người dùng chỉnh danh sách ngay trong trang Cài đặt.
- Thêm cảnh báo khi lời đọc có chữ số mà không ghi cách đọc (`100` thay vì `100{một trăm}`): mức `info`.

**Quyết định M4 Đợt 2 (chủ dự án chốt 23/10/2026):**
- **Nguồn danh sách:** `hbt/data/sensitive_words.json` (mặc định, nằm trên Git) và bản riêng `workspace/settings/sensitive_words.json` (ưu tiên khi có). Không có file `.txt` riêng trong `library/`.
- **Mức xử lý:** `block` chặn xuất (nút Xem nhanh và Xuất bị khoá); `warn` và `info` chỉ nhắc, không chặn và không có nút "Vẫn dựng".
- **So khớp** (`pipeline/textmatch.py`): chuẩn hoá NFC, không phân biệt hoa thường, theo ranh giới từ (ký tự chữ, số, `_` ở hai bên thì không khớp), cụm nhiều từ khớp với một hay nhiều khoảng trắng. **Không bỏ dấu**: "bia" không khớp "bìa". Riêng dấu thanh ở cụm `oa`, `oe`, `uy` có hai cách đặt, nên cả văn bản lẫn từ khoá được đưa về cách đặt ở nguyên âm thứ hai trước khi so: "hoá"="hóa", "tuý"="túy", "thuỷ"="thủy", "khoẻ"="khỏe".
- **Vùng quét** (`field` trong kết quả): `card.lines` (nối các dòng thẻ), `labels`, `voice`, `publish.hook`, `thumbnail.lines` (4e). Mỗi từ báo một lần cho mỗi vùng và cảnh. `publish.hook` và `thumbnail.lines` có `scene` là `null`. Không quét `title` và `hashtags`.
- **Lời đọc:** quét **cả chữ hiển thị lẫn chữ đọc trong `{…}`**; `|`, `{`, `}` được đổi thành dấu cách trước khi so (để "nhậu|rượu" không dính thành một từ).
- **Số chưa ghi cách đọc** (`category = "number_reading"`, mức `info`, `field = "voice"`): báo **mọi** số trần không có `{cách đọc}` đi kèm, kể cả số một chữ số và năm; số có phân cách (`1.000`, `3,5`) tính là một số; **mỗi cảnh một dòng** liệt kê các số theo thứ tự xuất hiện, không lặp (ví dụ cảnh 3: `Số chưa ghi cách đọc: 1, 100.`; `word` là chuỗi `1, 100`).
- `POST /projects/{slug}/lint` dùng danh sách hiện hành (bản riêng nếu có). Test: `test_textmatch.py`, `test_lint.py`, `test_api.py`.

---

Thêm vào lint: tổng ký tự lời đọc > 750 → `warn` (mục 4d); lời đọc có chữ số chưa ghi cách đọc → `info`.

## 8. Sinh nội dung đăng (`publish.txt`)

```
[TikTok]
{hook}
#{hashtags cách nhau bằng dấu cách}

[YouTube Shorts]
Title: {title} #shorts
Description: {hook} Series "{series}". Nhạc: {music.credit}

[Thumbnail]
Dòng chữ bìa: {thumbnail.lines cách nhau bằng dấu /}
TikTok: cover_9x16.jpg
YouTube Shorts: youtube_3x2.jpg
```
Hiện trong UI với nút **Sao chép** từng khối. Khối `[Thumbnail]` chỉ có khi project có `thumbnail`; hai tên file trỏ tới `cover_9x16.jpg` và `youtube_3x2.jpg` trong cùng thư mục `renders/<job>/` (có thể vắng nếu vẽ bìa lỗi, xem 4e).

---

## 9. API (`/api`, JSON, lỗi theo dạng `{detail}`)

| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | `{ok, ffmpeg, whisper, gpu, missing}` — kiểm tra môi trường (xem định nghĩa dưới bảng) |
| GET | `/projects` | danh sách `{slug, title, updated_at, thumb, last_render}` |
| POST | `/projects` | `{title, series?, scene_count=8}` → tạo project rỗng |
| GET / PUT / DELETE | `/projects/{slug}` | đọc / lưu toàn bộ `project.json` / xoá |
| POST | `/projects/{slug}/duplicate` | nhân bản làm template |
| POST | `/projects/{slug}/assets` | multipart: `kind=image|voice|music`, `scene_index` (từ 0, với ảnh) |
| GET | `/projects/{slug}/scenes/{scene_index}/preview.png` | khung hình tĩnh: ảnh + nhãn + thẻ + phụ đề mẫu (cụm đầu) |
| POST | `/projects/{slug}/lint` | kết quả mục 7 |
| POST | `/projects/{slug}/thumbnail/preview.jpg` | `{thumbnail?}` → ảnh bìa 9:16 theo **bản nháp** (không lưu); bỏ `thumbnail` thì dùng khối đã lưu; `?w=16..1080` thu nhỏ |
| POST | `/projects/{slug}/build/clean` | dọn `build/` → `{before_bytes, after_bytes, freed_bytes, kept, failed}` |
| POST | `/projects/{slug}/render` | `{preview: bool, fps?: 30|60}` → `{job_id}` |
| GET | `/jobs` | chỉ đọc: job đang chạy và đang chờ, cũ nhất trước: `[{id, slug, kind: preview|final, status: queued|running, progress, step}]` (giao diện gọi một lần khi mở app để nối lại thẻ tiến độ) |
| GET | `/jobs/{id}` | `{status: queued|running|done|failed|cancelled, progress, step, log_tail, output}` |
| GET | `/jobs/{id}/events` | SSE: `event: progress` `data: {progress, step, message}` |
| POST | `/jobs/{id}/cancel` | huỷ (kill tiến trình ffmpeg con) |
| GET | `/music` · POST `/music` | thư viện nhạc (mỗi bài có `id`) |
| GET | `/music/{id}/audio` | nghe thử bài trong thư viện (Range) |
| POST | `/projects/{slug}/music/from-library` | `{id}` → chép bài vào project, đặt ghi công |
| GET | `/settings/sensitive-words` · PUT | danh sách từ nhạy cảm |
| GET | `/files/{path}` | phục vụ file trong workspace (chặn `..`) |

**Định nghĩa `/health`** (chủ dự án duyệt 20/10/2026):
- `ffmpeg`: `ffmpeg -version` chạy được.
- `missing`: các mục bắt buộc còn thiếu. Encoder: `libx264` (theo `ffmpeg -encoders`). Filter: `zoompan`, `xfade`, `sidechaincompress`, `loudnorm`, `silencedetect` (theo `ffmpeg -filters`). Nếu FFmpeg không chạy được thì `missing = ["ffmpeg"]`.
- `ok`: `true` khi và chỉ khi `missing` rỗng. Whisper và GPU **không** ảnh hưởng `ok` vì đã có đường dự phòng (mục 5.2).
- `whisper`: import được `faster_whisper`. `gpu`: CTranslate2 thấy ít nhất 1 thiết bị CUDA.
- Cách đọc: mỗi dòng của `ffmpeg -encoders` / `-filters` được nhận diện theo dạng "2–6 ký tự cờ rồi tên", bỏ dòng chú thích; **không** dựa vào dòng `------` (FFmpeg 6.1 không in dòng này cho `-filters`, bản 9.0 có; số cờ cũng khác nhau). Đã thử trên 6.1.1 (Ubuntu, CI) và 9.0.2 (Windows).

**Chi tiết triển khai M2** (chủ dự án duyệt 21/10/2026):
- **Lỗi** luôn là `{"detail": "<chuỗi>"}`: 404 không có project/job/file (slug đúng dạng mà chưa có), 409 xung đột (đang dựng, job đã kết thúc), 400 dữ liệu sai (file hỏng, `scene_index` sai), 413 file quá lớn, 422 body sai, project chưa đủ để dựng, hoặc slug/đường dẫn file không hợp lệ, 503 thiếu FFmpeg/ffprobe.
- **Đánh số cảnh** (chủ dự án chốt 21/10/2026): ba nơi, hai cách đếm, một quy tắc đổi.
  - **API dùng chỉ số từ 0**, tham số tên `scene_index`: trong đường dẫn `/projects/{slug}/scenes/{scene_index}/preview.png`, trường form `scene_index` khi tải ảnh, và trường `scene_index` trong kết quả lint (`null` nếu áp dụng cho cả video). Chỉ số ngoài khoảng → 404 (preview) hoặc 400 (tải ảnh).
  - **Người dùng thấy số thứ tự từ 1** ("Cảnh 1"), và trường `thumbnail.scene` trong project.json cũng tính từ 1 (mục 4e).
  - **Tên file ảnh** do backend đặt, đánh số từ 1: `scene_index` 0 → `images/scene-01.<ext>` (`storage.scene_image_stem` / `scene_index_from_stem`, có test hai chiều).
  - **Giao diện** hiển thị số từ 1 qua **một chỗ duy nhất**: `frontend/src/utils/scene.ts` (`sceneNumber`: từ 0 → từ 1; `sceneIndex`: từ 1 → từ 0). Không được tự cộng/trừ 1 ở nơi khác. Có test ép hai chiều đổi luôn ngược nhau (Vitest).
- **Project nháp:** `POST /projects` tạo project chưa có ảnh/lời/giọng (mô hình cho phép rỗng). `POST /render` trả 422 kèm danh sách còn thiếu (`Project chưa đủ để dựng: Cảnh 1: chưa có ảnh; …`).
- **`PUT /projects/{slug}`** thay toàn bộ `project.json`, không đổi slug (khác slug → 400), không tạo mới (chưa có → 404). **`DELETE`** → 204; 409 nếu project đang có job xếp hàng/đang chạy. **`duplicate`** chép `project.json`, ảnh, giọng, nhạc nhưng không chép `build/` và `renders/`; tiêu đề mặc định "… (bản sao)".
- **`POST /projects/{slug}/assets`** (multipart `kind`, `file`, `scene_index` với ảnh) trả `{kind, path, project}`. Ảnh PNG/JPG/WEBP (≤ 30 MB, kiểm tra bằng Pillow) lưu thành `images/scene-NN.<ext>`; giọng/nhạc (≤ 200 MB, kiểm tra bằng ffprobe) lưu thành `voice.<ext>`/`music.<ext>`. Tải giọng mới thì bỏ `trim_end` cũ; tải nhạc mới thì đặt lại `start`/`credit`. 409 khi project đang dựng.
- **`preview.png`:** 1080×1920, tuỳ chọn `?w=16..1080` để thu nhỏ; cache trong `build/previews/`; cảnh chưa có ảnh dùng `brand/hay-biet-tuot_avatar.png`.
- **`POST /projects/{slug}/lint`:** `{issues, counts, blocked, problems}`. Từ M4: độ dài lời đọc, từ nhạy cảm (mục 7) và số chưa ghi cách đọc. **`/settings/sensitive-words`**: bản mặc định ở `hbt/data/sensitive_words.json`; khi sửa thì lưu bản riêng ở `workspace/settings/sensitive_words.json` và ưu tiên bản này.
- **`POST /projects/{slug}/render`** nhận `{preview, preview_seconds, fps: 30|50|60, outro, allow_long_trim}`, trả 202 `{job_id}`. `preview_seconds` (số giây, 0 < giá trị ≤ 60, mặc định `null` = cả video; giao diện gửi 10) chỉ hợp lệ khi `preview = true`, sai thì 422 và không tạo job; job và `GET /renders` trả `preview_seconds`, `output.lufs` và `output.srt` có thể là `null` ở bản 10 s (mục 4). Trước khi tạo job, lint chạy với danh sách từ hiện hành: có từ mức `block` → **422** `Có từ bị chặn, sửa rồi dựng lại: Cảnh N: …` (liệt kê các từ), không tạo job (cùng kiểu với `Project chưa đủ để dựng`, kiểm sau lỗi thiếu dữ liệu và trước kiểm FFmpeg). Kết quả ở `renders/<job_id>/` (`video.mp4`, `captions.srt`, `publish.txt`, `log.txt`, `meta.json`).
- **Job:** một luồng dựng, job nằm trong bộ nhớ (giữ 200 job; mất khi khởi động lại server, file đã xuất vẫn còn). `GET /jobs/{id}` → `{id, project, status, progress, step, log_tail, output, error, needs_confirmation, …}`; `output` có URL `/api/files/...`. **SSE** `GET /jobs/{id}/events`: `event: progress` (`{progress, step, message}`) rồi `event: end` (`{status, error, output}`); người nối sau nhận lại từ đầu. **Huỷ**: job xếp hàng huỷ ngay và không bao giờ chạy; job đang chạy bị kill ffmpeg, đợi tối đa 5 s cho luồng dừng, không để lại video dở. Đuôi giọng cần cắt > 8 s: job `failed` với `needs_confirmation = true` (gửi lại với `allow_long_trim`).
- **`POST /music`** (multipart `file`, `title`, `artist`, `source`, `license` bắt buộc; `url`, `moods` cách nhau dấu phẩy, `bpm` 30–300) lưu phẳng `library/music/<slug-tiêu-đề>.<ext>`, tạo `id` (slug từ tiêu đề, bỏ dấu tiếng Việt kể cả `đ`, trùng thì `-2`, tạo một lần, không đổi) và thêm vào `index.json`. `file` trong index là đường dẫn tương đối trong `library/music/` (cho thư mục con, dùng `/`; từ chối tuyệt đối, ổ đĩa, `..`, `\`, đuôi ngoài các đuôi âm thanh của mục 9). Bài thiếu `id` trong `index.json` được gán id từ tiêu đề theo thứ tự trong file rồi ghi lại một lần. Thư mục con chỉ dành cho file đặt tay rồi khai vào `index.json`.
- **`GET /files/{path}`** chỉ phục vụ trong workspace, hỗ trợ Range (206) cho video; chặn `..`, đường dẫn tuyệt đối, ổ đĩa và mọi thư mục ẩn (bắt đầu bằng dấu chấm).
- **Slug project** (chủ dự án chốt 21/10/2026): chỉ `[a-z0-9-]` (không bắt đầu/kết thúc/đôi dấu gạch), tối đa 60 ký tự, và không trùng tên thiết bị dành riêng của Windows (`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`). Mọi nơi dùng slug đều kiểm tra và trả **422** `Slug không hợp lệ: …` (đọc, sửa, xoá, nhân bản, tải file, xem trước, lint, dựng, và `/files/projects/<slug>/…`; slug trong thân `PUT` cũng vậy). Đường dẫn `/files` có `..`, đường dẫn tuyệt đối, ổ đĩa hoặc thư mục ẩn cũng 422; đường dẫn đúng dạng mà không có file thì 404. Tiêu đề trùng tên thiết bị Windows ("Con", "NUL"…) được thêm hậu tố `-video`; hậu tố chống trùng (`-2`, `-3`…) không làm slug vượt 60 ký tự.
- **Thiếu FFmpeg** (chủ dự án chốt 21/10/2026): server không sập. `/health` báo `ffmpeg: false`, `missing: ["ffmpeg"]`. `POST /render` trả **503** kèm lời nhắn cài (`winget install Gyan.FFmpeg`, mở lại terminal, xem README.md) và **không tạo job**; cũng trả 503 nếu FFmpeg thiếu encoder/filter bắt buộc hoặc thiếu ffprobe. Tải giọng/nhạc và `POST /music` trả 503 (cần ffprobe để kiểm tra file). Project chưa đủ vẫn nhận 422 trước 503. Những việc không cần FFmpeg (CRUD, ảnh, xem trước, lint, `/files`, từ nhạy cảm) vẫn chạy.
- Chưa làm (ngoài đặc tả M2): endpoint riêng cho `publish.txt` (đã có qua `/files`).

**Bổ sung cho giao diện M3** (quyết định khi làm M3, chờ chủ dự án xác nhận khi duyệt):
- `GET /music/{id}/audio` phát bài trong thư viện (nghe thử, hỗ trợ Range; `id` là `id` trong `GET /music`; sai định dạng → 422, không có → 404; M4 đổi từ tên file sang id, route cũ đã bỏ); `POST /projects/{slug}/music/from-library` `{id}` chép bài vào project và đặt ghi công `"tên bài – nghệ sĩ (nguồn)"`.
- **`POST /projects/{slug}/thumbnail/preview.jpg`** (chủ dự án chốt 23/10/2026): dùng đúng bộ vẽ của video (`pipeline/thumbnail.py`), JPEG 1080×1920; giao diện tự cắt khung 3:4 (y=240..1680) và 3:2 (y=600..1320). 404 nếu không có project; 422 nếu chưa có khối `thumbnail` (cả bản nháp lẫn đã lưu), cảnh nền vượt số cảnh hoặc chưa có ảnh, hoặc không vẽ được (thiếu logo…); `lines` phải 2–3 dòng (sai thì 422).
- **`POST /projects/{slug}/build/clean`** (chủ dự án chốt 23/10/2026): xoá mọi thứ trong `build/` **trừ `timing.json` và `timing.json.key`** (căn chữ là bước đắt nhất); không động `renders/`, ảnh, giọng, nhạc, `project.json`. Trả dung lượng trước/sau/giải phóng, danh sách file giữ lại và số mục không xoá được (`failed`). 404 nếu không có project; **409** khi project đang được dựng (không xoá gì). Không có lệnh CLI tương ứng.
- `GET /projects/{slug}/renders` lịch sử các lần xuất (mới nhất trước, đọc từ `renders/<job_id>/meta.json`).
- `POST /projects/{slug}/scenes/reorder` `{order}` (hoán vị của `0..n-1`; cảnh mới thứ i là cảnh cũ `order[i]`). Ảnh tên chuẩn `images/scene-NN.<ext>` được đổi tên theo chỉ số mới để tải ảnh về sau không ghi đè ảnh của cảnh khác. 409 khi project đang dựng.
- `POST /projects/{slug}/scenes/{scene_index}/preview.png` `{scene, theme?}`: xem trước bản nháp chưa lưu (ảnh phải nằm trong thư mục project, nếu không 422), để thấy kết quả ngay khi đang gõ.
- `GET|PUT /settings/app`: `{default_fps, theme{primary,accent}, whisper_model, whisper_timeout_seconds}` lưu ở `workspace/settings/app.json`. `default_fps` và `theme` áp dụng cho project tạo mới; hai trường Whisper chỉ được lưu, M4 mới dùng.

---

## 10. Giao diện

### 10.1 Thương hiệu & phong cách

> Từ M5: giao diện theo §13 + DESIGN-HBT.md v2.

**Thương hiệu là HBT, phong cách học theo Nike.**

| Tài sản (thư mục `brand/`) | Dùng ở |
|---|---|
| `hbt-logo-mark.png` (nền trong suốt, 832×677) | Góc trái thanh trên cùng (cao 36–44 px), màn hình chờ, trang trống |
| `hay-biet-tuot_avatar.png` (1080×1080, nền đỏ) | Ảnh đại diện kênh, ảnh mặc định của project chưa có ảnh |
| `hbt-avatar-192.png`, `hbt-avatar-512.png` | Icon app / manifest |
| `favicon.ico`, `hbt-avatar-32.png` | Favicon |

- Tên app hiển thị: **HBT Studio**. Không sửa, kéo méo hay đổi màu logo; giữ khoảng trống quanh logo ≥ 1/4 chiều cao logo.
- Màu thương hiệu HBT dùng làm màu nhấn của giao diện: đỏ `#B22228`, kem `#F7EEDA`, vàng mù tạt `#F4B630`, mực `#1E1816`. Nền và chữ chính theo phong cách đen trắng của `DESIGN.md`.
- Phong cách lấy từ `DESIGN.md` (Nike): tương phản đen trắng mạnh, tiêu đề chữ hoa rất đậm, khoảng trắng rộng, ảnh lớn tràn khung, nút bo tròn dạng viên thuốc, ít đường viền.

**Cài DESIGN.md một lần, ghim phiên bản:**
- Chạy `npx getdesign@0.6.20 add nike` (ghim phiên bản thay vì `@latest`), chủ dự án đọc duyệt `DESIGN.md`, commit lại. Không chạy lại tự động.
- Chuyển token trong `DESIGN.md` thành biến CSS ở `frontend/src/styles/tokens.css`, map vào Tailwind.
- **Không** dùng logo, wordmark, tên, khẩu hiệu hay hình ảnh của Nike. Nếu `DESIGN.md` nhắc tới font độc quyền của Nike thì **không** dùng, thay bằng Be Vietnam Pro.
- Font giao diện: **Be Vietnam Pro** (thay cho font trong DESIGN.md) để hiển thị tiếng Việt chuẩn.
- Mọi chữ giao diện tiếng Việt, đặt trong `src/i18n/vi.ts`.
- Có chế độ sáng/tối theo hệ thống.

### 10.2 Màn hình

| Màn | Nội dung |
|---|---|
| **Dự án** (`/`) | Lưới thẻ project (ảnh cảnh 1, tiêu đề, ngày, trạng thái xuất). Nút **Tạo video mới**, **Nhân bản**. Thanh trạng thái môi trường từ `/health` (FFmpeg ✓, Whisper ✓, GPU ✓) |
| **Soạn video** (`/p/:slug`) | Cột trái: danh sách cảnh, kéo để đổi thứ tự. Giữa: trình sửa cảnh đang chọn — ô thả ảnh, các dòng thẻ chữ (chữ, cỡ, màu), vị trí thẻ, nhãn cố định, lời đọc (có đếm số chữ và gợi ý cú pháp `|`, `{}`), công tắc **Cú lật**. Phải: **ảnh xem trước** cảnh (gọi `preview.png`, cập nhật sau 600 ms ngừng gõ) |
| **Âm thanh** (tab) | Tải giọng đọc (có trình phát), chọn nhạc từ thư viện hoặc tải mới, ô `music.start`, nút nghe thử 10 s đoạn nhạc được chọn (P3, mục 6.1: nếu `music.start` trống và lần dựng gần nhất có `music_start_source = "auto"` thì hiện "Lần dựng gần nhất app chọn giây X", nghe thử phát từ X và có nút **Dùng giá trị này** điền X vào `music.start`; chưa có lần dựng nào thì phát từ giây 0 kèm ghi chú bấm Xem nhanh) |
| **Xuất video** (tab) | Kết quả lint; nút **Xem nhanh** (dựng 10 giây đầu), nút phụ **Xem nhanh cả video** và **Xuất bản đẹp 50fps**, công tắc **Thêm outro**; thanh tiến độ theo bước (SSE); trình phát video; nút tải `video.mp4`, `captions.srt`; khối `publish.txt` có nút sao chép; lịch sử các lần xuất (bản 10 s ghi "Xem nhanh 10 giây đầu"); khối kết quả hiện độ lớn "—" khi không đo; **Ảnh bìa** (nhập 2–3 dòng, chọn cảnh nền, chữ series, màu dòng cuối, xem trước hai khung 3:4 và 3:2 sau 600 ms ngừng gõ, nút tải `cover_9x16.jpg` và `youtube_3x2.jpg` từ lần xuất gần nhất có bìa, nút Bỏ ảnh bìa); nút **Dọn file tạm** (hỏi xác nhận, báo dung lượng đã giải phóng, khoá khi đang dựng; mục 9) |
| **Cài đặt** | Danh sách từ nhạy cảm, model Whisper, fps mặc định, màu chủ đề mặc định |

Lưu tự động (debounce 1 s) khi sửa project; có chỉ báo "Đã lưu".

---

## 10b. Kiểm thử

- **pytest**
  - `text.parse_voice`: `|`, `{}`, dấu câu, số.
  - `align_silence`: tạo âm thanh giả (các đoạn sóng sine cách nhau bởi khoảng lặng) → kiểm tra mỗi cụm rơi đúng đoạn.
  - `align_whisper`: test so khớp + nội suy bằng dữ liệu `heard` giả (không cần model).
  - `render` end-to-end ở chế độ preview với 3 ảnh màu + giọng giả: file ra đúng 540×960, 30 fps, có audio.
  - `lint`: bắt được "bia", không bắt nhầm "bìa".
  - Mục 4b (chuyển động):
    - Số khung hình của clip = `round(thời lượng × 50)`.
    - `smoothstep(0) = 0`, `smoothstep(1) = 1` và đơn điệu tăng.
    - Chuyển cảnh dài đúng 20 khung.
    - ffprobe bản dựng ra 50 fps, 1080×1920.
  - Mục 4c (outro):
    - Tổng thời lượng = phần có lời + 4,0 − 0,5.
    - `settings.outro = false` thì không có outro.
    - Đoạn outro có tiếng, dài đúng 4,0 s, độ lớn −14 ±1 LUFS.
    - Thiếu `library/outro/voice.wav` thì vẫn dựng được (chỉ có tiếng "ting").
  - Mục 4d (lời đọc):
    - File giọng giả (8 cảnh) có đoạn thừa 3 s sau câu cuối thì bị cắt và có ghi log.
    - Kịch bản ngắn (3 cảnh) có đoạn thừa 3 s: không cắt, chỉ cảnh báo.
    - Không có đoạn thừa thì không bao giờ bị cắt.
    - `voice.trim_end` cắt trước khi căn chữ; nằm sau hết file thì báo lỗi.
    - Căn 2 cấp: cảnh có 5 cụm nhưng chỉ 3 đoạn tiếng rõ thì cụm cuối vẫn rơi đúng đoạn cuối.
    - Đoạn thừa trên 8 s thì dừng và hỏi.
    - Lint cảnh báo khi lời đọc có 751 ký tự, không cảnh báo khi 750.
  - `thumbnail` (mục 4e): khối chữ tiêu đề nằm trọn trong y=600..1320; logo và nhãn series nằm trong y=240..1680; đầu ra đúng kích thước 1080×1920 (`cover_9x16.jpg`) và 1080×720 (`youtube_3x2.jpg`).
- **Golden test (chủ dự án chốt 26/10/2026): kiểm bằng mắt/tai, không có ngưỡng số.** Chủ dự án xem **Xem nhanh cả video** tập "muỗi" (`workspace/samples/muoi/`, aligner `auto`) trên **mỗi máy** và đánh dấu cụm nào thấy chữ karaoke nổi lệch so với lời đọc. **Đạt** khi không cụm nào bị đánh dấu. Dựng bằng CLI: `python -m cli render workspace/samples/muoi --preview` (hoặc project sao chép của nó). Không còn mốc đánh tay, `golden_marks.json` hay lệnh `golden-import`. Claude Code chỉ chuẩn bị video và bảng cụm (số cụm từ 1, cảnh từ 1, chữ) làm phiếu xem; không tự chấm đạt hay rớt.
  - **Mặc định Whisper mỗi máy** = model nhẹ nhất đạt (máy cũ thử `small` trước). Đợt này không đổi mặc định trong code: chỉ báo, chờ chủ dự án chốt.
- **Vitest:** hàm tiện ích frontend (định dạng thời gian, gọi API).

---

## 11. Danh sách việc (Claude Code làm lần lượt, đánh dấu khi xong)

### M0 · Khởi tạo
- [x] Tạo cấu trúc mục 1, `.gitignore`, `.env.example`, `README.md` hướng dẫn cài trên Windows
- [x] `package.json` gốc với `dev`, `lint`, `test` (dùng `concurrently`)
- [x] FastAPI `/api/health` kiểm tra `ffmpeg -version`, import faster-whisper, CUDA
- [x] Vite + React + TS + Tailwind, trang trống gọi `/api/health`
- [x] ruff, ESLint, Prettier; GitHub Actions chạy lint + pytest (không cần GPU)
- **Xong khi:** `npm run dev` mở trang hiện trạng thái môi trường.
- **Tag:** `v0.1.0` trỏ vào commit tài liệu `ad64301` (đã push, giữ nguyên). Bản M0 là `v0.1.1` (commit merge `f329c8e`). Không force-push tag (chủ dự án chốt 20/10/2026).

### M1 · Bộ dựng (không giao diện)
> Ranh giới (chủ dự án chốt 20/10/2026): `models.py` (Pydantic, dùng ở bước 1), tự chọn đoạn nhạc (mục 6.1) và sinh `publish.txt` (mục 8) làm luôn trong M1 vì `render.py` cần. Lint từ nhạy cảm (mục 7) để M4; trong M1 bước 1 chỉ để sẵn chỗ gọi.

- [x] Copy `reference/pipeline/{text,align,visual}.py` vào `backend/hbt/pipeline/`
- [x] Viết `audio.py`, `captions.py`, `render.py` theo mục 4–6 dựa trên `render_reference.py`
- [x] Cache theo hash trong `build/`; ghi `log.txt`; trả tiến độ qua callback
- [x] `cli.py render <dir> [--preview] [--fps 30|50|60]`; chất lượng chuyển động theo mục 4b
- [x] Outro (mục 4c) và cắt đuôi file giọng (mục 4d)
- [x] Test mục 10b (phần của M1; test lint từ nhạy cảm và thumbnail thuộc M4)
- **Xong khi:** dựng được tập "muỗi" 50 fps, 1080×1920, −14 ±1 LUFS, phụ đề đúng chữ, có outro 4 giây, và đuôi giọng thừa (nếu có) bị cắt.

**Quyết định kỹ thuật khi làm M1** (Claude Code ghi 21/10/2026; các mục đánh dấu ⚠ chờ chủ dự án duyệt):
- **Mục 4d.2 có điều kiện bảo vệ** (chủ dự án duyệt 21/10/2026): tối đa `số đoạn tiếng − số cụm câu` đoạn cuối. Quy tắc phạt 0,5 đơn thuần trên tập "muỗi" (22 cụm, 20 đoạn) đã bỏ nhầm câu kết thật "Comment cho mình biết!" rồi cắt mất khỏi âm thanh. Đã siết thêm: xem 4d.2.
- **`text.parse_voice` sửa so với reference:** nhóm `{...}` được giữ nguyên dù có khoảng trắng bên trong (`100{một trăm}`, `Comment{com men}`); reference dùng `split()` nên chẻ đôi nhóm này và phụ đề hiện ký tự `{`.
- **Clip cảnh:** luồng ảnh thẻ chữ được ép chạy cùng fps của clip (`-framerate`). Mặc định 25 fps làm clip 1,0 s ở 50 fps chỉ có 49 khung. Hình ảnh không đổi.
- **Sau khi cắt đuôi giọng (4d):** đệm lại `TAIL` = 1,6 s sau chữ cuối và chuẩn hoá lại −14 LUFS trên phần giọng giữ lại. Đặc tả chưa nói rõ đoạn đệm sau khi cắt.
- **Phụ đề:** cụm không chồng lên cụm sau; cụm kết thúc đúng lúc cụm sau hiện (cách chữ đầu 0,05 s), thay vì kéo đến đầu chữ đầu cụm sau.
- **Tiếng "ting" của outro:** dùng thông số bản đã chạy thật (mục 6.5), thay bản tạm của Claude Code.
- **`settings.outro`** chỉ là bật/tắt; clip outro cố định 4,0 s (chủ dự án chốt 21/10/2026: bỏ ý "3–5 giây" ở mục 4c).
- **Đếm 750 ký tự (4d):** bỏ các ký tự `|`, `{`, `}` (giữ nội dung trong `{}`), gộp khoảng trắng, các cảnh nối bằng một dấu cách.
- **Aligner khoảng lặng** (khi chưa có Whisper) chỉ ghép được theo từng đoạn nghỉ; nếu giọng ít đoạn hơn số cụm câu thì một số cụm phụ đề lệch cả giây trong cảnh đó. Whisper (M4) khắc phục.
- **Cache `build/`:** khoá gồm hash mã nguồn các module pipeline (`render.PIPELINE_VERSION`), nên sửa thuật toán thì cache cũ tự mất hiệu lực.
- **Outro không có lời:** mix bắt đầu từ nền im lặng dài đúng 4,0 s (`amix duration=first`); cách `apad=whole_dur` đôi khi chỉ ra 2,05 s.

### M2 · API
- [x] Models Pydantic + storage + toàn bộ endpoint mục 9
- [x] Job runner 1 luồng, SSE, huỷ job
- [x] `preview.png` từng cảnh (dùng chung code `visual.py` + `captions.render_caption`)
- **Xong khi:** tạo project, tải file, dựng video hoàn toàn bằng `curl`.

### M3 · Giao diện
- [x] Áp `DESIGN-HBT.md` → tokens.css + màu HBT; gắn logo, favicon, icon từ `brand/` (không dùng `DESIGN.md` của getdesign)
- [x] 4 màn hình mục 10.2, kéo thả ảnh/cảnh, lưu tự động
- [x] Theo dõi tiến độ bằng SSE, trình phát video, tải file
- **Xong khi:** làm trọn 1 video chỉ bằng giao diện, không mở terminal.

**Quyết định kỹ thuật khi làm M3** (23/10/2026, chờ chủ dự án duyệt):
- **Biểu tượng:** `DESIGN-HBT.md` mục 6 ghi `lucide-react`, nhưng danh sách thư viện được phép không có. Đã vẽ bộ biểu tượng SVG riêng (`components/icons.tsx`, nét 1,8). Nếu muốn dùng `lucide-react`, chủ dự án duyệt rồi đổi.
- **Font:** chỉ có ba bản (500/700/800) trong `backend/hbt/fonts/`; đổi sang `.woff2` bằng fontTools (cài trong `backend/.venv`). Độ đậm 400 dùng bản 500, 600 dùng bản 700.
- **Lưu tự động:** giữ bản nháp trên máy, `PUT` sau 1 s; trước khi tải file, đổi thứ tự cảnh hoặc dựng thì lưu ngay. Ctrl+S lưu ngay, Alt+↑/↓ chuyển cảnh.
- **Xoá cảnh:** API không có thao tác xoá cảnh. Giao diện đưa cảnh cần xoá xuống cuối bằng `POST /scenes/reorder` (máy chủ đổi tên ảnh) rồi `PUT` bỏ cảnh cuối; ảnh mồ côi của cảnh bị xoá vẫn nằm trong `images/` và bị ghi đè khi thêm cảnh mới.
- **Nghe thử nhạc thư viện:** `GET /music/{id}/audio` (M3 dùng tên file; M4 đổi sang `id`, bảng `GET /music` có trường `id`).
- **Bản đẹp:** chọn 30/50/60 fps, mặc định theo fps của project; nút "Xem nhanh" là nút đen duy nhất, "Xuất bản đẹp" là nút vàng duy nhất.
- **Thiếu so với bản nháp lời chủ dự án:** chưa có chuyển trang trượt 200 ms (mục 7); biến thể `lucide-react` như trên.
- **Kiểm thử trình duyệt thật:** kịch bản Playwright chạy trên Edge có sẵn (không lưu trong repo), dựng đủ 8 cảnh, xem nhanh và bản đẹp 1080×1920 50 fps (261 s), tải lại trang, tối/sáng.

- **Thời gian dựng bản đẹp (đo 22/10/2026, i5-10400, không GPU, máy rảnh, tập "muỗi" 8 cảnh 50 s, 1080×1920 50 fps):** 143 s, tương đương M1 (145 s). Lần 261 s ở M3 đo khi trình duyệt và máy chủ dev đang chạy; không có lỗi hiệu năng trong bộ dựng. Khi đo thời gian, tắt `npm run dev` và trình duyệt.

**Backlog sau M3 (chưa làm, không thuộc mốc nào):**
- Chuyển sang `lucide-react` (cần chủ dự án duyệt thêm thư viện, xem quyết định Biểu tượng ở trên).
- Thêm font độ đậm 400 và 600 thật (hiện dùng 500 và 700 thay thế).
- Ảnh chụp màn hình giao diện cho README/tài liệu.
- Hiệu ứng chuyển trang trượt 200 ms (mục 7 của bản nháp lời chủ dự án).

**Mục theo dõi:** một test pytest từng rớt đúng một lần khi máy đang bận, chưa tái hiện được. CI đã in tên test rớt (`scripts/ci_annotate.py`); nếu rớt lại thì ghi tên test và điều kiện vào đây rồi điều tra.

### M4 · Hoàn thiện
- [ ] Whisper làm mặc định, fallback khoảng lặng; hiển thị phương pháp đã dùng
- [ ] Whisper chọn model/thiết bị theo phần cứng (`WHISPER_MODEL=auto`, mục 5.2), giới hạn thời gian trong Cài đặt, rơi về khoảng lặng kèm log; cập nhật `.env.example` và `config.py`
- [ ] `python -m cli bench-align <dự án> [--models small,medium,large-v3]`: thời gian, tỉ lệ âm tiết khớp kịch bản, độ lệch mốc cắt cảnh so với căn khoảng lặng
- [x] Lint nội dung + trang chỉnh danh sách từ
- [x] Thư viện nhạc + tự chọn đoạn nhạc + ghi công tự động (Đợt 2a/2b)
- [x] `publish.txt` + nút sao chép (khối `[Thumbnail]` đủ 3 dòng)
- [x] `thumbnail.py` (mục 4e): ảnh bìa, API xem trước, UI tab Xuất video; dọn `build/` bằng nút trong UI
- **Xong khi:** chủ dự án xem Xem nhanh cả video "muỗi" trên mỗi máy, không cụm nào thấy lệch (golden test, mục 10b); kịch bản có chữ "bia" hiện cảnh báo.

**Kế hoạch M4 (chủ dự án chốt 23/10/2026):**
- **Đợt 2 (máy cũ):**
  - (a) Thư viện nhạc có id: slug từ tiêu đề, bỏ dấu tiếng Việt, trùng thì `-2`, tạo một lần. `file` là đường dẫn tương đối trong `library/music/`, cho thư mục con; từ chối tuyệt đối, ổ đĩa, `..`, `\`. Bỏ route `/music/{file}/audio` (dùng `/music/{id}/audio`). `.gitignore`: `library/music/**` + `!library/music/index.json` + chặn `*.mp3 *.m4a *.ogg *.flac *.aac`.
  - (b) Tự chọn đoạn nhạc theo 6.1 (đã có) + `music.start`; ghi công từ thư viện; không thêm trường mới.
  - (c) Lint từ nhạy cảm theo mục 7 (`sensitive_words.json`, warn/block theo danh mục), trang Cài đặt, áp cả dòng chữ bìa.
  - [x] (d) Xem nhanh 10 s đầu (chủ dự án chốt 23/10/2026): nút Xem nhanh mặc định chỉ dựng 10 s đầu (540×960, 30 fps như cũ), giữ tuỳ chọn xem nhanh cả video; căn chữ và điểm nhạc (`music_start`) vẫn tính trên cả video; thời gian dựng tuỳ máy. Chi tiết kỹ thuật ghi vào mục 4 và 9 khi làm.
- **Đợt 1 (Whisper theo mục 5.2, cache `timing.json`, `bench-align`, cắt đuôi giọng bằng Whisper)** — chia đôi (chủ dự án chốt 24/10/2026, vì máy mới đang hỏng):
  - **1a (máy cũ, không GPU):** toàn bộ code Đợt 1; đường CPU chạy thật (`small`, `int8`); đường CUDA viết theo đặc tả nhưng chỉ kiểm bằng test giả lập.
  - **1b (máy mới, khi sửa xong):** kiểm đường CUDA thật (`large-v3`, `int8_float16`), chạy `bench-align --prompt both` để đo `large-v3` CUDA **không prompt và có prompt**, kiểm độ lệch đều 0,3–0,4 s của `large-v3` (so bằng cách xem video nếu cần), chốt mặc định theo số đo và golden test.
- **Đợt 3:** thumbnail (4e), `publish.txt` có khối [Thumbnail], lệnh dọn `build/`, golden test trên cả hai máy.

### M5 · Giao diện mới + khối JSON kịch bản

Nhánh `feat/m5-ui-json` (từ `b240e97`, đã gộp `main` v0.5.1), tag `v0.6.0`. Đặc tả đầy đủ ở mục 13. Mỗi commit: `npm run lint && npm run test` xanh. Không sửa `backend/hbt/pipeline/` (giữ `PIPELINE_VERSION` của `v0.5.1`).

- [ ] **Đợt 0 · Tài liệu:** PLAN/IMPLEMENT mục M5 và mục 13, DESIGN-HBT.md v2, CLAUDE.md (`docs(M5)`); sửa dòng nhật ký 26/10 bị vỡ (`docs(plan)`).
- [x] **Đợt 1 · Backend khối JSON:** `backend/hbt/script.py` (parse, gộp, K1–K12 và K6b, đo 888 px) · `backend/hbt/api/script.py` (`script/check`, `script/apply`) · `backend/hbt/backups.py` (`backups`, `restore`) · (B′) `render_seconds` + `align_cached` trong `jobs.py` và `/renders` · (B6) `cover`, `last_final` trong `GET /projects`.
- [x] **Đợt 2 · Nền giao diện:** `tokens.css` v2 sáng/tối · thành phần dùng chung (Button, IconButton, Chip, Switch, Card, Badge, Input, Toast, Dialog, Progress, Skeleton) đủ trạng thái mục 13.B3 · AppShell + thanh trái · reduced-motion · logo. Xong 27/10/2026 (nhánh `feat/m5-ui-json`): token v2, 10 thành phần + Menu/Drawer, AppShell, trang mẫu `/dev/ui` (quyết định ở 13.B7).
- [x] **Đợt 3a:** Trang chủ, Dự án, màn trống, hộp Video mới. Xong 28/10/2026 (quyết định ở 13.B8).
- [x] **Đợt 3b:** Soạn video (dải cảnh, thả nhiều ảnh, thẻ chữ, bộ đếm, lời đọc, tuỳ chọn, xem trước, vùng an toàn). Xong 28/10/2026 (quyết định ở 13.B9).
- [x] **Đợt 3c:** Âm thanh (+ nút Sáng/Tối, sửa thẻ trống Trang chủ). Xong 28/10/2026 (quyết định ở 13.B10).
- [x] **Đợt 3d:** Xuất video (lịch sử lưới, ước tính) + Cài đặt. Xong 28/10/2026 (quyết định ở 13.B11).
- [x] **Đợt 4:** Hộp Dán JSON + menu Bản sao lưu. Xong 28/10/2026 (quyết định ở 13.B12).
- [x] **Đợt 5:** xoá bí danh, Tab/focus, `GET /jobs` + nối lại job, cảnh báo rời Cài đặt, Button/`/dev/ui`, e2e. Xong 28/10/2026 (quyết định ở 13.B13); còn 6 bước đóng mốc.
- **Xong khi:** tiêu chí X1–X8 ở PLAN.md mục "Kiểm chứng M5" đều đạt và chủ dự án duyệt từng màn.

**Test cần có (M5):**

> Chạy `pytest` toàn bộ chỉ một lần tại một thời điểm và không dựng video khi đang chạy test: `test_cancel.py` đếm tiến trình ffmpeg trên toàn máy nên đỏ nếu có ffmpeg khác chạy cùng lúc (đã gặp ở Đợt 1 khi chạy hai pytest song song).

| Loại                                | Ca                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pytest `test_script.py`             | Dạng đầy đủ và mảng ngắn cho cùng kết quả · trường vắng giữ nguyên · `card` ghi đè cả khối · `labels: []` xoá · `caption_y: null` · `hbt_script: 2` lỗi · trường lạ (`pucnh`) lỗi · trường cấm (`image`, `music`) lỗi · K3 từng giá trị sai · K5 "“được muỗi yêu”?" cỡ l = 16 → cảnh báo, "gấp 100 lần" cỡ xl = 11 → cảnh báo, 15/10 không cảnh báo · K6 một từ đơn > 888 px → lỗi · K6b dòng tự xuống hàng → cảnh báo, không lỗi · K7 · K8 · K9 751 ký tự cảnh báo, 750 không · K10 "ma tuý" → cảnh báo chặn xuất · K11 · K12 · NFC (chữ tổ hợp) · hashtag `#muoi` → `muoi` · ít phần tử → áp n cảnh + cảnh báo · nhiều phần tử → lỗi; `add` → thêm cảnh; `trim` → bỏ thừa · sau gộp ngoài 3–12 → lỗi · `realign_scenes` đúng cảnh đổi lời |
| pytest `test_api_script.py`         | `check` không đổi mtime `project.json` · `apply` tạo sao lưu + trả `backup_id` · 409 khi đang dựng · 409 khi `base_hash` cũ · 422 khi có lỗi (không ghi) · slug sai 422 · `restore` trả đúng dữ liệu trước `apply` và tự sao lưu bản hiện tại · tạo 11 bản → còn 10 · `id` có `..` → 422 · `duplicate` không chép `backups/` · `build/clean` không xoá `backups/`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| pytest đối chiếu                    | JSON thẻ chữ "muỗi" và **kết quả mong đợi sinh một lần từ `import_cards.py`** (chỉ JSON, không media) trong `backend/tests/data/`: `card/punch` sau gộp phải giống (X3). `import_cards.py` nằm trong `workspace/` (bị ignore) nên test không import nó                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| pytest (B′, B6)                     | Job xong có `render_seconds` > 0 và `align_cached` trong `meta.json`; `/renders` trả hai trường; ghi `meta.json` lỗi không làm hỏng job · `PIPELINE_VERSION` bằng giá trị của `v0.5.1` và `git diff v0.5.1 -- backend/hbt/pipeline/ reference/` rỗng (X6) · `GET /projects` trả `cover` (lần dựng gần nhất có bìa) và `last_final`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Vitest                              | Đếm ký tự dùng chung bộ ca với pytest (`shared/char_cases.json`) · sắp tên file tự nhiên · gán ảnh khi thả nhiều (có ảnh sẵn, dư ảnh, > 12) · định dạng dòng khác biệt · tính ước tính (trung vị, không lịch sử, bản cũ thiếu trường) · trạng thái nút chính (thiếu nguyên liệu → tắt + lý do) · nhãn dự án (Đã xuất · fps / Đã xem nhanh / Chưa dựng)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| e2e Playwright (Edge, máy cá nhân)  | Luồng X1 trên bản sao "muỗi"; dán JSON → kiểm → áp → hoàn tác; sáng/tối; Tab qua thanh trái và hộp thoại                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Thủ công                            | DevTools Performance khi rảnh (13.B3.2 luật 9); chủ dự án xem từng màn                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

---

## 12. Giai đoạn 2 — interface để sẵn (chưa làm)

```python
class ScriptProvider(Protocol):   # Claude API / Gemini API
    def draft(self, topic: str, series: str, n_scenes: int) -> ProjectDraft: ...
    # Bản nháp bắt buộc có: lời đọc từng cảnh (số viết dạng 100{một trăm}), thẻ chữ,
    # prompt ảnh (không chữ, không bản đồ VN), thể loại nhạc + từ khoá Pixabay,
    # nguồn kiểm chứng cho từng số liệu, và phải qua lint từ nhạy cảm (mục 7).

class ImageProvider(Protocol):    # Forge API (--api) / ComfyUI API / thủ công
    def generate(self, prompt: str, style: str, w: int = 768, h: int = 1344) -> bytes: ...

class VoiceProvider(Protocol):    # VieNeu-TTS local / Vbee API / thủ công
    def synthesize(self, text: str, voice_id: str) -> bytes: ...
```
Khoá API đặt trong `.env`, không commit. Mọi bản nháp sinh tự động đều phải qua 3 điểm duyệt (kịch bản → ảnh → video).

---

## 13. M5: giao diện mới + khối JSON kịch bản

> Đặc tả duyệt 27/10/2026 (gồm O1–O3), nhánh `feat/m5-ui-json`, tag `v0.6.0`. Mã K1–K12, tên trường, tên API và mã lỗi dưới đây là chuẩn; đổi thì hỏi chủ dự án. Hệ thiết kế đầy đủ ở `DESIGN-HBT.md` v2.
> Mốc cơ sở của "không đổi pipeline" là tag **`v0.5.1`** (đã sửa `render.py`), không phải `b240e97`.
> Mục tiêu: giao diện trẻ trung, nút nổi bật, ít chữ; dán JSON kịch bản vào app thay cho `workspace/import_cards.py`. Không database, không đăng nhập; **không sửa `backend/hbt/pipeline/`**.

### 13.B1 Hệ thiết kế v2 (thay DESIGN-HBT v1.1)

**Màu** (biến CSS trong `frontend/src/styles/tokens.css`)

| Token | Sáng | Tối | Dùng cho |
|---|---|---|---|
| `--bg` | `#F5F5F7` | `#0F0F12` | Nền trang |
| `--card` | `#FFFFFF` | `#18181C` | Thẻ, thanh trái (tối: `#16161A`) |
| `--soft` | `#F0F0F3` | `#26262C` | Chip, nút phụ, ô nhỏ |
| `--soft-2` | `#F5F5F7` | `#1F1F25` | Khối lồng trong thẻ, ô nhập nền |
| `--line` | `#ECECF0` | `#26262C` | Viền thanh trái, viền thẻ (tối) |
| `--text` / `--text-2` / `--muted` | `#16120F` / `#3A3540` / `#6E6A72` | `#F4F4F6` / `#C9C9D1` / `#A0A0AA` | Chữ chính / phụ / nhãn |
| `--primary` / `--on-primary` | `#16120F` / `#FFFFFF` | `#F4F4F6` / `#0F0F12` | Nút chính (Xem nhanh), chip đang chọn, mục thanh trái đang chọn |
| `--accent` | `#F4B630` (chữ `#16120F`) | như sáng | Xuất bản đẹp, thanh tiến độ, cảnh đang chọn, vòng focus |
| `--brand` | `#B22228` (chữ trắng) | như sáng | Nút Tạo video, logo, mũi tên khác biệt |
| `--tint-red` | nền `#FDECEC`, chữ `#9C1D22` | — | Nhãn "Đã xuất" |
| `--tint-yel` | nền `#FFF3D1`, chữ `#6B4A00` | — | Nhãn "Đã xem nhanh", cảnh báo |
| `--ok` | chấm `#22A55B`; ô `#E6F5EC` / `#187A42` | chấm `#3CCB7F` | Môi trường sẵn sàng, "Sẵn sàng" |
| `--danger` | `#B3261E` | `#FF6B6B` | Lỗi, xoá, mức Chặn (luôn kèm chữ / biểu tượng) |

**Hình dạng, chữ, bố cục**

| Hạng mục | Quy cách |
|---|---|
| Bo góc | Thẻ 24 · hộp thoại 28 · khung xem trước 28 · khối lồng 16–18 · ô nhập 14 · nút, chip, nhãn 999 |
| Bóng | Thẻ: `0 1px 2px rgba(22,18,15,.04), 0 8px 24px rgba(22,18,15,.05)`; menu/hộp thoại: `0 24px 64px rgba(22,18,15,.25)`. Tối: không bóng, viền 1 px `--line` |
| Font | Be Vietnam Pro (file 500/700/800 sẵn có; 400→500, 600→700 như M3) |
| Cỡ chữ | Hero 56/62 800 (màn trống) · tiêu đề Trang chủ 40/48 800 · H1 32/40 800 CHỮ HOA (Dự án, Cài đặt) · tiêu đề trang soạn 22 800 · H2 16/22 700 · nội dung 14–15 · nhãn 12/600 `--muted` · số liệu `tabular-nums` |
| Nút | Cao 48 (nút chính ở cột xem trước 54); chip 36 (nhỏ 32); nút icon 36–44 tròn; vùng chạm ≥ 36, ưu tiên 44 |
| Thanh trái | Rộng 232, nền `--card`, viền phải 1 px. Thứ tự: logo `brand/hbt-logo-mark.png` (36 px) + "HBT Studio" · nút **Tạo video** (đỏ) · Trang chủ · Dự án · [khối dự án đang mở: tên + Soạn video / Âm thanh / Xuất video] · Cài đặt · [thẻ tiến độ dựng khi có job] · Môi trường (FFmpeg / Whisper / GPU, chấm + chữ) |
| Soạn video / Âm thanh | Thanh đầu 48 · dải cảnh (thẻ cao ~120: ảnh 54×96, số cảnh, nút +, vùng thả) · 3 cột `1fr 1fr 300px`, khoảng cách 18 · cột phải: 2 nút chính + dòng ước tính + khung 288×512 + ‹ n/8 › |
| Dưới 1280 px | Thanh trái thu còn biểu tượng (72 px); dưới 1024 cột xem trước thành ngăn kéo |

### 13.B2 Màn hình (theo mockup v2)

| Màn | Thành phần | API |
|---|---|---|
| **Trang chủ** (mới) | Tiêu đề "HÔM NAY LÀM VIDEO GÌ?"; thẻ **Tiếp tục làm** (dự án sửa gần nhất: bìa/ảnh cảnh 1, tên, nhãn trạng thái, series, chấm Ảnh n/8 · Giọng · Nhạc · Ảnh bìa, nút Mở dự án / Xem video); thẻ tối **Lần xuất gần nhất** (tên, fps, độ dài, LUFS, thời gian dựng, Xem video); **Gần đây** 4 dự án + "Xem tất cả" | `GET /projects`, `GET /projects/{slug}/renders` (dự án đầu), `/health` |
| **Dự án** | Lưới 4 thẻ/hàng: ảnh 9:16 (`cover` của lần dựng gần nhất có bìa; không có thì ảnh cảnh 1; không có ảnh thì ô HBT + "0/8 ảnh"), tên 2 dòng, nhãn trạng thái, ngày, menu ⋯ (Nhân bản, Xoá… có xác nhận, khoá khi đang dựng). **Nhãn:** "Đã xuất · fps" nếu `last_final` có; không có thì "Đã xem nhanh" nếu `last_render` có; còn lại "Chưa dựng" | `GET /projects` (thêm `cover`, `last_final`, xem 13.B6), `duplicate`, `DELETE` |
| **Dự án trống** | Hero "TẠO VIDEO / ĐẦU TIÊN", 1 câu, nút Tạo video, 3 bước (Kịch bản · Ảnh 9:16 · Giọng + nhạc) | — |
| **Hộp Video mới** | Tên, chip series (3 series + Khác), chip số cảnh 3–12 (mặc định 8), Huỷ / Tạo | `POST /projects` |
| **Soạn video** | Dải cảnh kéo đổi thứ tự; **thả nhiều ảnh** (13.B2.1); cột 1 "Cảnh n · Thẻ chữ": ảnh + Đổi ảnh, chip vị trí Trên / Trên giữa / Giữa / Dưới / px, mỗi dòng: ô chữ có bộ đếm `n/giới hạn` (vàng khi vượt), chip S M L XL, 3 chấm màu Mực / Chính / Nhấn (`aria-label`), + Dòng; cột 2 "Lời đọc": ô lời, số ký tự cảnh, chip `\|` Ngắt cụm, `{ }` Cách đọc số, thanh "Cả video n/750"; thẻ Tuỳ chọn: công tắc Cú lật, Phụ đề Tự động / px, Nhãn cố định (n) ›; cột 3: nút chính, ước tính, xem trước (POST preview.png sau 600 ms), nút Vùng an toàn (lớp y 100–1500, mép phải 120 px); thanh đầu: "Đã lưu", nút Dán JSON | `GET/PUT /projects/{slug}`, `assets`, `scenes/reorder`, `POST preview.png`, `/lint` |
| **Âm thanh** | Thẻ Giọng đọc (trình phát, "Đã cắt đuôi x s" + Nghe, vùng thả giọng mới); thẻ Điểm bắt đầu nhạc (chip Tự chọn / Đặt tay, "Lần trước: giây X" + Nghe + Dùng — chỉ khi `music_matches_current`); thẻ Nhạc nền (chip lọc tâm trạng, mỗi bài: ▶, tên, tác giả · nguồn, tâm trạng, Chọn / Đang dùng; ghi công; Tải nhạc, Không nhạc) | `assets`, `/music`, `/music/{id}/audio`, `from-library`, `/renders` |
| **Xuất video** | Thẻ Kiểm tra (Sẵn sàng / có cảnh báo / bị chặn + 3 số; mỗi lỗi có "Đến cảnh N"); thẻ Kết quả (độ dài, LUFS, căn chữ + tỉ lệ khớp, cắt đuôi + Nghe); Nội dung đăng (3 khối + Sao chép); Ảnh bìa (3 dòng, chip cảnh nền, xem trước 3:4 và 3:2, Bỏ); Lịch sử dạng lưới (bìa / ảnh cảnh 1, nhãn Bản đẹp / Xem nhanh / 10 s đầu, ngày giờ, thẻ đang xem viền vàng); Dọn file tạm; cột phải: chip FPS 30/50/60 (mặc định theo Cài đặt), công tắc Outro, nút chính, "Xem nhanh cả video", ước tính, trình phát, tải video.mp4 / captions.srt / ảnh bìa | `/lint`, `/render`, SSE, `cancel`, `/renders`, `thumbnail/preview.jpg`, `build/clean`, `/files` |
| **Cài đặt** | Thẻ FPS mặc định; Căn chữ (chip Tự động / small / medium / large-v3 + ghi chú, ô giới hạn giây); Màu chủ đề (2 ô màu); Từ nhạy cảm (mỗi nhóm: nút gạt Cảnh báo / Chặn, từ dạng chip có ×, nhóm ít dùng gộp thu gọn, ô Thêm từ); nút Lưu | `/settings/app`, `/settings/sensitive-words` |
| **Hộp Dán JSON** | 13.B4.6 | 13.B4.7 |

**13.B2.1 Thả nhiều ảnh:** xếp theo tên file kiểu tự nhiên (2 < 10); gán từ cảnh 1; nếu có cảnh đã có ảnh → hỏi xác nhận ghi đè một lần; ảnh dư → hỏi thêm cảnh (tối đa 12), phần vượt 12 bỏ và báo; tải **lần lượt từng file** (nhẹ máy), thanh tiến độ n/N.

**Chữ UI:** ngắn, đúng nghĩa; toàn bộ trong `i18n/vi.ts`. Không viết câu giải thích dài trên màn; giải thích đưa vào `title` / chú thích khi cần.

### 13.B3 Hiệu ứng tương tác và hiệu năng

**13.B3.1 Trạng thái từng thành phần**

| Thành phần | Hover | Nhấn | Focus (bàn phím) | Tắt / khác |
|---|---|---|---|---|
| Nút chính (đen / vàng / đỏ) | Nền đậm hoặc sáng 8%, nhấc `translateY(-1px)` | `scale(.97)` 90 ms | Vòng 2 px `--accent`, cách 2 px (trên nền vàng: vòng `--text`) | Mờ .4, `not-allowed`, chú thích lý do (vd "Thiếu ảnh cảnh 3"); đang chạy: vòng xoay nhỏ |
| Nút phụ, chip | Nền `--soft` → đậm hơn 1 bậc | `scale(.97)` | Như trên | Chip đang chọn đổi nền 150 ms |
| Nút icon tròn | Hiện nền `--soft` | `scale(.94)` | Như trên | |
| Mục thanh trái | Nền `--soft` | `scale(.98)` | Như trên | Mục đang chọn đổi nền 150 ms |
| Thẻ bấm được (dự án, lịch sử, bài nhạc, dòng khác biệt, Gần đây) | Nhấc `translateY(-2px)`, bóng đậm hơn (lớp `::after` đổi `opacity`) | `scale(.99)` | Như trên | Thẻ tĩnh: không hiệu ứng |
| Dòng danh sách / menu | Nền `--soft-2` | Nền `--soft` | Như trên | |
| Ô nhập, ô lời đọc | Viền `#D9D9DE` | — | Viền `--text` + quầng `--accent` 3 px mờ .35 | Lỗi: viền `--danger` + chữ lỗi dưới ô; vượt giới hạn: viền `--accent` |
| Ảnh cảnh ở dải | `scale(1.04)` | — | Vòng focus | Đang chọn: vòng vàng 3 px; đang kéo: nhấc + mờ .9, chỗ thả có vạch vàng |
| Vùng thả | — | — | — | Khi kéo file vào: nền `--tint-yel` + viền vàng nét đứt (tĩnh) |
| Công tắc | Nền đậm hơn | — | Vòng focus | Núm trượt `translateX` 150 ms |
| Hộp thoại | — | — | Focus vào ô đầu, Esc đóng | Hiện: nền mờ `opacity` 150 ms + `scale(.98→1)` 180 ms; đóng 120 ms |
| Thông báo | — | — | — | Trượt lên 8 px + hiện 200 ms; tự ẩn 3 s, thông báo Hoàn tác 8 s |
| Thanh tiến độ | — | — | — | `transform: scaleX()` 300 ms tuyến tính, không sọc chạy |
| Đang tải | — | — | — | Khung xương tĩnh màu `--soft`, không hiệu ứng lấp lánh |

**13.B3.2 Luật hiệu năng (bắt buộc)**

1. Chỉ dùng CSS `transition`; chỉ đổi `transform`, `opacity`, `background-color`, `color`, `border-color`. Không đổi trực tiếp `width/height/top/left/box-shadow/filter`.
2. Thời lượng 90–200 ms, `cubic-bezier(.2,0,0,1)`.
3. Không `backdrop-filter`, `blur`, gradient động, hoạt ảnh lặp vô hạn (chỉ vòng xoay khi đang chạy việc).
4. Không thêm thư viện hoạt ảnh hay dependency mới cho hiệu ứng.
5. `prefers-reduced-motion: reduce` → bỏ mọi `transform`/chuyển động, giữ đổi màu.
6. Không `will-change` toàn cục; không poll API định kỳ khi rảnh (tiến độ dùng SSE).
7. Ảnh trong lưới / dải cảnh / lịch sử dùng bản thu nhỏ (`preview.png?w=`, `cover` thu nhỏ nếu có), `loading="lazy"`, `decoding="async"`.
8. Xem trước cảnh: giữ debounce 600 ms, huỷ yêu cầu cũ (`AbortController`).
9. Kiểm: DevTools Performance 10 s khi rảnh: không khung hình nào ngoài di chuột; CPU tab ≈ 0%.

### 13.B4 Khối JSON kịch bản

**13.B4.1 Dạng đầy đủ**

```json
{
  "hbt_script": 1,
  "scenes": [
    {
      "voice": "…",
      "card": { "y": "top", "lines": [{ "text": "…", "size": "s", "color": "ink" }] },
      "labels": [],
      "punch": false,
      "caption_y": null
    }
  ],
  "publish": { "hook": "…", "hashtags": ["…"] },
  "thumbnail": { "scene": 1, "lines": ["…", "…"], "series": "", "accent": "#FFD43B" }
}
```

- `hbt_script` không bắt buộc; có thì phải bằng 1.
- **Dạng ngắn:** gốc là mảng → coi là `scenes` (đúng mẫu chat kịch bản `[{punch, card}]`).

**13.B4.2 Quy tắc gộp**

| Quy tắc | Nội dung |
|---|---|
| Trường vắng | Giữ nguyên giá trị cũ |
| Trường có mặt | Ghi đè **cả trường** (`card` thay toàn bộ; `labels: []` xoá hết nhãn; `publish`, `thumbnail` thay cả khối) |
| `null` | Chỉ hợp lệ ở `caption_y` (= tự động); ở mọi nơi khác (`voice`, `card`, `labels`, `punch`, `publish`, `thumbnail`, `hbt_script`) là lỗi K3 |
| Không đổi qua JSON | `image`, `voice` gốc (file giọng), `music`, `settings`, `title`, `slug`, `series`, `theme` → nếu xuất hiện là **lỗi** (K4) |
| Chuẩn hoá | NFC mọi chuỗi; hashtag bỏ `#` đầu và khoảng trắng hai đầu |
| Đếm ký tự | Số ký tự Unicode sau NFC (Python `len`, JS `[...s.normalize('NFC')].length`); dùng chung bộ ca test cho hai phía |
| Mô hình đầu vào | **`ScriptIn` riêng trong `backend/hbt/script.py`, `extra="forbid"`** (cho K4), chặt cả các khối con (`card`, `lines`, `labels`, `publish`, `thumbnail` là lớp con `extra="forbid"` của lớp trong `models.py`, nên `colour` hay `pucnh` ở bất kỳ cấp nào đều là K4). **Không đổi `models.py`** (`Project` giữ `extra="ignore"`); K12 vẫn kiểm bản sau gộp bằng `Project.model_validate` |

**13.B4.3 Quy tắc kiểm** (Lỗi = không cho áp · Cảnh báo = vẫn áp)

| Mã | Kiểm | Mức |
|---|---|---|
| K1 | JSON không đọc được → báo dòng:cột | Lỗi |
| K2 | Số phần tử ≠ số cảnh | 13.B4.5 |
| K3 | `y` ∈ top/upper/middle/lower hoặc số px; `size` ∈ s/m/l/xl; `color` ∈ ink/primary/accent/#RRGGBB; `labels`, `caption_y`, `punch` đúng kiểu — theo Pydantic hiện có | Lỗi |
| K4 | Trường lạ / sai tên / trường cấm (13.B4.2) — `ScriptIn` với `extra="forbid"` | Lỗi |
| K5 | Dòng thẻ: xl ≤ 10, l ≤ 15, m ≤ 22, s ≤ 26 ký tự | Cảnh báo |
| K6 | **Một từ đơn rộng > 888 px** (`TEXT_W = 960 − 2×36`) khi đo bằng đúng font và cỡ của bộ vẽ thẻ — tràn thật, như "TRÀN" trong `import_cards.py` (hàm đo dùng chung với `visual.py`, chỉ đọc) | Lỗi |
| K6b | `_wrap` tách một dòng thành k dòng: "Dòng n tự xuống hàng thành k dòng" | Cảnh báo |
| K7 | Thẻ 0 dòng; > 3 dòng; > 1 dòng màu `accent` | Cảnh báo |
| K8 | Chữ thẻ chứa `\|`, `{`, `}` | Cảnh báo |
| K9 | Tổng lời đọc > 750 ký tự; cảnh có lời trống | Cảnh báo |
| K10 | Lint từ nhạy cảm trên bản sau gộp: `block` → cảnh báo đỏ "sẽ chặn xuất"; `warn` → vàng | Cảnh báo |
| K11 | `thumbnail.lines` 2–3 dòng; `thumbnail.scene` ≤ số cảnh sau gộp | Lỗi |
| K12 | Toàn bộ project sau gộp qua `Project.model_validate` | Lỗi (giữ bản cũ) |

**Phạm vi áp (chốt ở Đợt 1):**

- K5–K8 chỉ kiểm cảnh có `card` trong JSON (thẻ không đổi thì không kiểm lại).
- K9 "cảnh có lời trống" chỉ áp cho cảnh có `voice` trong JSON hoặc cảnh mới thêm (`extra: "add"`), để JSON chỉ có thẻ chữ không báo lời trống hàng loạt. K9 "tổng > 750" và K10 chạy trên toàn bản sau gộp.
- Mỗi cảnh báo K10 có thêm `level`: `block` (đỏ, "sẽ chặn xuất") hoặc `warn` (vàng).
- K5 và K6 có thể cùng hiện trên một dòng; K6b hiện khi một dòng tự xuống hàng, kể cả khi dòng đó cũng bị K6.
- K11 (`thumbnail.lines` 2–3, `thumbnail.scene` ≤ số cảnh) và K2 (ngoài 3–12) không báo trùng thêm một lỗi K12.

**13.B4.4 Ghi chú hệ quả** (hiện ở bước Kiểm tra): cảnh đổi `voice` → "n cảnh sẽ căn chữ lại ở lần dựng tới".

**13.B4.5 Lệch số cảnh**

| Trường hợp | Xử lý |
|---|---|
| JSON ít phần tử hơn | Cảnh báo; áp cho cảnh 1…n, còn lại giữ nguyên |
| JSON nhiều phần tử hơn | Lỗi, trừ khi gửi `extra: "add"` (thêm cảnh trống, chưa có ảnh) hoặc `extra: "trim"` (bỏ phần thừa) — giao diện hiện 2 nút **Thêm cảnh** / **Bỏ phần thừa** |
| Số cảnh sau gộp ngoài 3–12 | Lỗi |

**13.B4.6 Giao diện (hộp 3 bước)**

1. **Dán:** ô dán (nền tối, chữ đơn cách) + thả file `.json`; trước khi kiểm, app lưu ngay bản đang soạn.
2. **Kiểm tra:** 3 ô số (Số cảnh n = n, Lỗi, Cảnh báo); danh sách khác biệt theo cảnh, chỉ trường đổi (cũ → mới, nhãn cỡ / màu, cảnh báo ngay dưới dòng); "+k cảnh" thu gọn; dòng "Giữ nguyên:" liệt kê các trường không đụng; ghi chú 13.B4.4. Có lỗi → nút Áp dụng tắt.
3. **Áp dụng:** nút "Áp dụng n cảnh" → thông báo "Đã áp dụng n cảnh · Hoàn tác" (8 s). Khoá khi đang dựng.

Hoàn tác về sau: menu "Bản sao lưu" (danh sách 10 bản, ngày giờ, Khôi phục có xác nhận) — đặt trong menu ⋯ của thanh đầu Soạn video.

**13.B4.7 API mới**

| Method | Path | Thân / kết quả | Lỗi |
|---|---|---|---|
| POST | `/projects/{slug}/script/check` | `{script, extra?: "add"\|"trim"}` → `{ok, base_hash, counts{json, project, after}, errors[], warnings[], diff[], realign_scenes[]}`; mỗi lỗi/cảnh báo `{code, scene_index?, field, message}`; mỗi diff `{scene_index?, field, before, after}`. **Không ghi gì** | 404, 422 slug/body |
| POST | `/projects/{slug}/script/apply` | `{script, extra?, base_hash}` → kiểm lại; sao lưu `project.json` hiện tại; ghi bản gộp → `{project, backup_id, base_hash}` (hash mới sau khi ghi) | 422 có lỗi (`{detail, errors[]}`, không ghi, không sao lưu); **409** đang dựng hoặc `base_hash` khác (project đã đổi sau khi kiểm); 409 được kiểm trước khi sao lưu |
| GET | `/projects/{slug}/backups` | `[{id, created_at, reason}]` mới nhất trước, ≤ 10 | 404 |
| POST | `/projects/{slug}/backups/{id}/restore` | Sao lưu bản hiện tại (`reason: "restore"`) rồi khôi phục → `{project, backup_id, base_hash}` (`backup_id` là bản vừa sao lưu; ghi lại đúng byte bản được chọn nên `base_hash` trở về giá trị cũ) | 404; 409 đang dựng; 422 id sai dạng hoặc bản sao lưu hỏng / thuộc project khác |

- Lưu ở `workspace/projects/<slug>/backups/project-YYYYMMDD-HHMMSS[-n].json`; giữ 10 bản mới nhất (xoá bản cũ hơn); `duplicate` không chép `backups/`; "Dọn file tạm" không đụng `backups/`; `id` chỉ nhận `[0-9-]` (chặn đường dẫn).
- **`id`** = phần giữa `project-` và `.json`, khớp `^\d{8}-\d{6}(-\d+)?$` (sai dạng → 422). Trùng giây thì thêm `-n` (n = 1, 2, …), sắp theo số (`-10` mới hơn `-9`). Giờ trong tên và `created_at` là UTC.
- **File phụ** `project-….meta.json` cạnh mỗi bản: `{reason: "apply"|"restore", created_at}`. Thiếu hoặc hỏng thì `reason` = null và `created_at` lấy từ giờ sửa file. Dọn còn 10 bản thì xoá cả cặp.
- `apply` và `restore` trả 409 khi đang dựng; `apply` còn 409 khi `base_hash` lệch. Cả hai kiểm trước khi sao lưu hay ghi gì. `restore` đọc bản được chọn trước khi sao lưu bản hiện tại, nên khôi phục bản cũ nhất trong 10 bản vẫn đúng.
- `check` không ghi gì (kể cả sao lưu, kể cả dời ảnh cũ): đọc `project.json` thẳng từ đĩa. `base_hash` tính trên byte nguyên của file, không chuẩn hoá JSON.
- `script` trong thân yêu cầu nhận chuỗi JSON (K1 báo dòng:cột) hoặc giá trị đã đọc.
- Mã nguồn: `backend/hbt/script.py` (parse, gộp, kiểm), `backend/hbt/api/script.py`, `backend/hbt/backups.py`. `base_hash` = SHA-256 nội dung `project.json`.

### 13.B5 Ước tính thời gian dựng (chốt B′ 27/10)

| Cách | Mô tả |
|---|---|
| A | Giao diện tính từ `/renders`: `created_at` − giờ trong `job_id`; trung vị 3 lần gần nhất cùng loại |
| B | Thêm `render_seconds` vào `meta.json` trong `render.py` (đổi `PIPELINE_VERSION` → cache cũ hết hiệu lực một lần) |
| **B′ (chốt)** | Job runner (`jobs.py`, ngoài pipeline) ghi thêm `render_seconds` và `align_cached` vào `meta.json` sau khi job xong; `/renders` trả 2 trường. Không đổi `PIPELINE_VERSION`. Giao diện: trung vị 3 lần gần nhất cùng loại (10 s / cả video / bản đẹp theo fps), quy theo giây video; chưa có lịch sử → hệ số mặc định từ số đo (máy cũ: bản đẹp 50 fps ≈ 3 s/giây video, 60 fps ≈ 4,2 s/giây); bản cũ không có trường thì bỏ qua |

### 13.B6 Điểm đã kiểm khi lập kế hoạch (đã kiểm 27/10/2026, chỉ đọc)

**6a. `GET /projects` → `last_render`:** chưa có `cover`. `storage.last_render` (`backend/hbt/storage.py`) chỉ trả `job_id, preview, fps, duration, created_at, video`; `backend/hbt/api/projects.py` (`list_projects`) chỉ đổi `video` sang URL. `GET /projects/{slug}/renders` đã có `cover`. **Quyết định (chủ dự án 27/10), code ở Đợt 1:** `ProjectSummary` thêm

- `cover` = URL `/api/files/projects/<slug>/renders/<job>/cover_9x16.jpg` của lần dựng **gần nhất có file `cover_9x16.jpg`** (duyệt từ mới đến cũ, gặp là dừng; không có thì `null`). Lần dựng mới nhất vẽ bìa lỗi (chỉ cảnh báo) thì lấy bìa của lần cũ hơn;
- `last_final` = bản đẹp (không phải xem nhanh) mới nhất, **đủ các khoá như `last_render`** (`job_id, preview, fps, duration, render_seconds, align_cached, created_at, video`; `video` là URL) hoặc `null`.

`last_render` và `GET /projects/{slug}/renders` cũng trả `render_seconds`, `align_cached` (bản dựng cũ thiếu thì `null`). Hai khoá mới nằm cuối `ProjectSummary`, thứ tự khoá cũ giữ nguyên.

Nhãn lưới dự án suy từ hai trường này và `last_render` (13.B2, dòng **Dự án**).

**6b. 888 px và hàm đo chữ:** `workspace/import_cards.py` khai `TEXT_W = 960 - 2*36`, khớp mặc định `maxw=960, pad=36` của `visual.draw_card`, và đo bằng `v.SIZES`, `v.font`, `v._wrap` + `ImageDraw.textlength`. Dùng chung được mà không sửa `visual.py`: **port logic đo chữ sang `backend/hbt/script.py`** (import `SIZES`, `font`, `_wrap` từ `hbt.pipeline.visual`, tự khai báo `TEXT_W`). `import_cards.py` nằm trong `workspace/` (bị ignore) nên `script.py` và CI không import được nó. **X3** kiểm bằng fixture kết quả mong đợi **sinh một lần** từ `import_cards.py` trên JSON thẻ chữ "muỗi", đặt ở `backend/tests/data/` (chỉ JSON, không media).

**6c. Cờ cache căn chữ:** `aligner_info` chưa có (đọc lại từ `timing.json` y hệt lần đầu, `RenderResult` cũng không có cờ). `jobs.py` đủ thông tin mà không đụng pipeline: **`align_cached` = mtime của `build/timing.json` không đổi trước/sau `_render`** (thiếu file trước đó → `False`).

**6d. Ghi `render_seconds`:** `meta.json` do pipeline ghi ở cuối `render.py`. Trong `jobs.py` (`_run`, nhánh `else:` sau khi có `result`, **trước `job._finish(DONE, …)`**) ghi thêm `render_seconds` (= `result.seconds`, làm tròn 1 chữ số) và `align_cached` vào `result.job_dir / "meta.json"`. Ghi an toàn (ghi file tạm rồi `os.replace`); lỗi chỉ ghi log, **không làm hỏng job**. Chỉ ghi khi job thành công (Xem nhanh hay bản đẹp) và `meta.json` đã có; job huỷ hoặc lỗi thì không ghi, không tạo `meta.json`, không đổi trường pipeline đã ghi. `render_seconds` lấy từ `result.seconds` (thời gian dựng thật, **không** tính xếp hàng). `align_cached` chỉ `True` khi `build/timing.json` có trước job và mtime không đổi sau job. `storage` (`/renders`) trả thêm hai trường. Không đụng `backend/hbt/pipeline/`.

### 13.B7 Quyết định Đợt 2 (chủ dự án duyệt 27/10/2026)

1. **Tên token và màu Tailwind cũ là bí danh tạm.** `tokens.css` có khối bí danh cuối file (`--surface` → `--card`, `--surface-2` → `--soft`, `--text-muted` → `--muted`, `--border` → `--line`, `--brand-red` → `--brand`, `--brand-cream`, `--brand-ink`); `tailwind.config.ts` giữ `surface`, `surface-2`, `text-muted`, `border`, `brand-red`, `brand-cream`, `brand-ink`, `rounded-frame`. Màn cũ vì thế còn chạy. **Xoá hết ở Đợt 5**, kèm test `grep` không còn tên cũ trong `frontend/src` và `tokens.css`.
2. **Thay `Shell.tsx` bằng `AppShell` ngay Đợt 2.** "Trang chủ" tạm trỏ `/` (chưa đánh dấu đang chọn). Nút **Tạo video** tạm mở hộp tạo cũ qua `/?new=1` (`ProjectsPage` đọc rồi xoá tham số). Nối đúng ở Đợt 3a.
3. **Thẻ tiến độ dựng ở thanh trái chỉ là khung nhận props** (`render: { percent, step } | null` truyền qua `AppShell` → `SideNav`; test ẩn/hiện theo props). Context job toàn cục và giữ SSE khi đổi màn làm ở Đợt 3d.
4. **Bỏ `refetchInterval` của `/health`.** Chấm Môi trường chỉ lấy khi mở app và khi tab lấy lại focus (`refetchOnWindowFocus: true` riêng cho truy vấn này; mặc định toàn app vẫn `false`). Có test: 5 phút giả lập không có request thứ hai.
5. **Trang mẫu thành phần `/dev/ui`** (`pages/Gallery.tsx`), route chỉ đăng ký khi `import.meta.env.DEV` và nạp bằng `lazy`. Kiểm: sau `npm run build`, `grep -ri gallery frontend/dist` rỗng. Chuỗi chữ của trang nằm ở `vi.ui.kit` trong `i18n/vi.ts` nên vẫn vào bundle (vài trăm byte, không có mã trang).
6. **Không thêm gói npm.** Dialog, Drawer, Menu, Toast tự viết (`components/ui/overlay.ts`: focus vào ô đầu, bẫy Tab, Esc đóng, trả focus, giữ 120 ms để chạy hoạt ảnh đóng). `ConfirmDialog` và `Toast` giữ API cũ (thêm tuỳ chọn `undo`, 8 s).
7. **Đo lại tương phản theo token** (`tokens.test.ts`, ≥ 4,5:1 sáng và tối, 25 cặp). Cặp "Sẵn sàng" `#1A7F45` trên `#E6F5EC` chỉ đạt 4,47:1 nên đổi chữ sang `#187A42` (DESIGN-HBT.md mục 2 và bảng 13.B1 đã sửa). Các giá trị khác giữ nguyên.
8. **Test chạy nhanh:** `@pytest.mark.slow` cho test dựng/căn chữ thật từ 3 s (đo `--durations=0` trên máy cũ), `npm run test:fast` bỏ chúng; `npm run test` và CI vẫn chạy đủ. Vitest đọc `tokens.css` và `ui.css` bằng `?raw` nên `vite.config.ts` bật `css.include` cho hai file này.

**X6 (đổi mốc so sánh):** `PIPELINE_VERSION` không đổi so với tag `v0.5.1`, và `git diff v0.5.1 -- backend/hbt/pipeline/ reference/` rỗng (v0.5.1 đã sửa `render.py`; `b240e97` không còn là mốc).

### 13.B8 Quyết định Đợt 3a (chủ dự án duyệt 28/10/2026)

1. **Route:** Trang chủ ở `/`, Dự án ở `/projects`, đường dẫn lạ (`*`) về `/`. Nút **Tạo video** ở thanh trái mở hộp Video mới (`NewProjectProvider` trong `AppShell`); bỏ luồng `/?new=1` và hộp tạo cũ. Tạo xong chuyển sang `/p/:slug`.
2. **Tên series lưu khác PLAN §9** (không sửa PLAN): chip hiển thị đúng chữ lưu vào `series` (chữ này in lên nhãn bìa): "Vì Sao" · "Vì sao Trái Đất" · "Vì sao vậy ta?" · "Khác" (tự nhập, lưu nguyên văn). Lý do: khớp bìa các video đã đăng (project cũ lưu `Vì Sao` và `Vì sao vậy ta?`); bỏ dấu "…".
3. **Thẻ dự án:** ảnh = `cover` → ảnh cảnh 1 (file gốc qua `/api/files/...`) → ô HBT; ảnh lỗi rơi về ô HBT đúng một lần. Không có ảnh thì hiện **"Chưa có ảnh"**, thay cho "0/8 ảnh" ở 13.B2 (`GET /projects` không trả số ảnh/cảnh, không sửa backend). Ngày trên thẻ = `updated_at`.
4. **Thẻ "Lần xuất gần nhất" ở Trang chủ lấy bản mới nhất trong mọi dự án** (mỗi dự án: bản đẹp mới nhất, không có thì lần dựng gần nhất; chọn theo `created_at`), lệch 13.B2 ("dự án đầu") để tránh thẻ trống khi dự án vừa tạo chưa dựng. Số liệu chỉ từ `last_final` / `last_render`, không gọi `/renders`, nên **không có LUFS** trên thẻ (hiện fps, độ dài, thời gian dựng; thiếu thì "—").
5. **"Tiếp tục làm":** dự án đầu danh sách (`updated_at` mới nhất); chấm Ảnh n/N · Giọng · Nhạc · Ảnh bìa lấy bằng một lần `GET /projects/{slug}`, không poll. "Gần đây" = 4 dự án kế sau dự án đó; chỉ có một dự án thì bỏ mục.
6. **Nợ UI → Đợt 3d:** menu ⋯ của thẻ chưa khoá khi đang dựng (cần context job toàn cục); tạm bắt lỗi 409 và hiện Toast.
7. **Backlog:** bản thu nhỏ `?w=` cho `cover` (luật 13.B3.2 mục 7); hiện dùng bản gốc với `loading="lazy"` `decoding="async"`.
8. **Quy trình từ 28/10/2026:** trong đợt đã duyệt không dừng để hỏi hay cho xem từng màn; điểm chưa rõ tự chọn phương án an toàn nhất và ghi vào mục "Cần chốt" của báo cáo cuối đợt. Chỉ dừng giữa chừng khi test đỏ không tự sửa được hoặc phải sửa `pipeline/` / `models.py`.

### 13.B9 Quyết định Đợt 3b (chủ dự án duyệt 28/10/2026)

1. **Thẻ "Lần xuất gần nhất" (Trang chủ)** dùng token mới `--hero` / `--on-hero` (nền tối cố định, không phủ ở khối tối) thay cho `--primary`, vì `--primary` đảo sang sáng ở chế độ tối. Viền `--card-border` (trong suốt ở sáng, `--line` ở tối). `tokens.test.ts` kiểm tương phản ≥ 4,5:1 và token không bị phủ.
2. **Bộ đếm ký tự dòng thẻ** (xl 10, l 15, m 22, s 26; chỉ cảnh báo) dùng chung bộ ca `shared/char_cases.json` với pytest (`test_script.py`, K5) và Vitest (`charCount.test.ts`). Đếm số ký tự Unicode sau NFC; `Input` có `limit` cũng đếm theo NFC.
3. **Bố cục Soạn video:** dải cảnh ngang (`components/compose/SceneStrip.tsx`, kéo bằng tay nắm hoặc bàn phím) · 3 cột `1fr 1fr 300px` (thẻ chữ · lời đọc + Tuỳ chọn · xem trước 9:16 cố định) · dưới 1024 px xem trước thành ngăn kéo (không vẽ khi chưa mở). Màn dùng `components/ui/*`, không còn `.btn` / `.input` / `.chip` / `.spinner` (có test quét mã nguồn). **Bỏ hàng tab trong `ComposePage`** vì thanh trái đã có Soạn video / Âm thanh / Xuất video. Thanh đầu: nút quay lại, tên dự án, "Đã lưu", nút **Bìa & đăng**; **Dán JSON và menu ⋯ chưa hiện** (Đợt 4).
4. **Xem nhanh / Xuất bản đẹp** ở cột 3 chỉ chuyển sang tab Xuất video; tắt kèm lý do khi thiếu nguyên liệu ("Thiếu ảnh cảnh 3 · Thiếu giọng đọc", `utils/blockers.ts`). **Dòng ước tính để Đợt 3d**: Đợt 3b không gọi `/renders`, chỉ chừa `data-slot="estimate"` trong `PreviewPane`.
5. **Ngăn kéo "Bìa & đăng"** chứa `ThumbnailEditor` (không có nút tải file vì không đọc lịch sử dựng; tab Xuất vẫn có) và ô **Câu mở đầu** + **Hashtag** (`publish.hook`, `publish.hashtags`; app cũ chưa có chỗ sửa hai trường này). Hashtag gõ có hoặc không có `#`, lưu không `#`.
6. **Thả nhiều ảnh (13.B2.1):** `utils/dropImages.ts` xếp tên tự nhiên; gán từ cảnh 1; hộp ghi đè (một lần) rồi hộp thêm cảnh cho ảnh dư (hai hộp nối tiếp, "Bỏ ảnh dư" thì chỉ gán vào cảnh đang có); phần vượt 12 bỏ và báo; tải lần lượt từng file, tiến độ `n/N`; thêm cảnh được lưu ngay trước khi tải ảnh.
7. **Vùng an toàn** là lớp phủ CSS tĩnh trên khung xem trước (y 100–1500, mép phải 120 px, phần trăm của 1080×1920), không gọi API.
8. **Đổi thứ tự khi đang dựng:** API trả 409 thì hiện Toast kèm gợi ý và nút Thử lại.
9. **Thanh trái 72 px dưới 1280 px** đã làm ở Đợt 2 (`AppShell`), Đợt 3b không thêm commit riêng.
10. **Backlog:** bản thu nhỏ `?w=` cho ảnh cảnh ở dải (luật 13.B3.2 mục 7), hiện dùng ảnh gốc với `loading="lazy"` `decoding="async"`; màn cũ không có "nhân bản cảnh" nên Đợt 3b không thêm; dọn khoá i18n cũ (`compose.tabs`, `compose.editor`…).

### 13.B10 Quyết định Đợt 3c (chủ dự án duyệt 28/10/2026)

1. **Nút Sáng/Tối** ở đáy thanh trái (trên chấm Môi trường). Chữ và biểu tượng là **chế độ hiện tại** (Sáng + mặt trời / Tối + trăng); `aria-pressed` = đang tối; `aria-label` "Đổi sang chế độ tối/sáng"; thu 72 px chỉ còn biểu tượng (có `title`). Lần đầu theo `prefers-color-scheme` và **không ghi gì**; bấm rồi thì ghi `localStorage['hbt-theme']` (`light` | `dark`, bọc `try/catch`) và đặt `data-theme` trên `<html>` (dùng lại khối `[data-theme]` của `tokens.css`). Script chặn nhỏ trong `<head>` của `index.html` đặt `data-theme` trước lần vẽ đầu, chịu được `localStorage` ném lỗi. Test: `themeBoot.test.ts` (thứ tự script, khoá, lỗi lưu trữ), `ThemeToggle.test.tsx`.
2. **Khối trống cạnh "Tiếp tục làm"** (hiện khi chưa có lần xuất nào, chữ "Chưa có lần xuất nào") dùng `bg-hero text-on-hero` như thẻ "Lần xuất gần nhất"; test lớp và test tương phản `--on-hero`/`--hero` ≥ 4,5:1 cả hai chế độ.
3. **Màn Âm thanh** (`pages/AudioTab.tsx` + `components/audio/*`), bố cục 3 cột `1fr 1fr 300px`: [Giọng đọc + Điểm bắt đầu nhạc] · [Nhạc nền] · `PreviewPane` dùng lại của Soạn video (‹ n/N ›); dưới 1024 px thành ngăn kéo. Xem nhanh / Xuất bản đẹp chỉ chuyển sang tab Xuất video. Không dùng `.btn`/`.input`/`.card` (test quét `AudioTab.legacy.test.ts`).
4. **Giọng đọc:** trình phát; khi lần dựng gần nhất có `trimmed_tail` thì hiện nhãn "Đã cắt đuôi" + nút Nghe (phát file qua `/api/files`); chưa dựng lần nào hoặc không cắt thì ẩn. Ô "Cắt đuôi tại giây" (`voice.trim_end`) và vùng thả giọng mới giữ như cũ.
5. **Điểm bắt đầu nhạc:** chip Tự chọn / Đặt tay (Tự chọn = `music.start = null`). "Lần trước: giây X" + Nghe + **Dùng** chỉ khi lần dựng gần nhất có `music_start_source = "auto"` và `music_matches_current`; **Dùng** chuyển sang Đặt tay và điền X. Thiếu dữ liệu thì ẩn dòng (bỏ các câu giải thích dài của bản cũ).
6. **Nhạc nền:** danh sách bài từ `GET /music` (▶, tên, tác giả · nguồn, nhãn tâm trạng, Chọn / Đang dùng); chip lọc tâm trạng lấy từ `moods` **đã có** trong `index.json` và **ẩn khi không bài nào có `moods`**; "Đang dùng" suy từ `music.credit` = `Tên – Tác giả (Nguồn)` (dạng backend tự điền); chip **Không nhạc**; ô Ghi công; **Tải nhạc** = hộp tải file từ máy (không tải từ mạng) rồi dùng luôn.
7. **Nghe thử:** một đoạn phát tại một thời điểm (bắt đầu đoạn mới thì dừng đoạn cũ); `<audio preload="none">`, không tải trước. Lịch sử dựng (`/renders`) lấy đúng một lần khi mở màn, không poll.
8. **Không làm (thuộc 3d):** "Còn ≈ … · Huỷ", nối thẻ tiến độ, ước tính. Chip "Ý MỚI" của mockup là ghi chú, không vẽ.
9. **Cần chốt (chưa quyết, đã chọn phương án an toàn):** (a) không thấy `workspace/mockup/audio.png`, màn làm theo 13.B2 + bổ sung của chủ dự án; (b) `/renders` không trả `trimmed_tail_seconds` (chỉ job trả) nên nhãn "Đã cắt đuôi" chưa có số giây, thêm cần sửa backend; (c) "Đang dùng" suy từ chuỗi ghi công nên mất khi người dùng sửa ô Ghi công; (d) chưa có trường "bài đang dùng" trong `project.json`; (e) khối cần sửa màu ở Trang chủ không có chữ "Có thể bạn muốn", đã áp cho khối trống cạnh "Tiếp tục làm" (nền `bg-primary` cũ); (f) trang `/dev/ui` gỡ `data-theme` khi đóng nên có thể làm mất chế độ đã chọn trong phiên dev.

### 13.B11 Quyết định Đợt 3d (chủ dự án duyệt 28/10/2026)

1. **Job toàn cục:** `RenderJobProvider` (trong `AppShell`) giữ job và luồng SSE qua `useJob`; `EventSource` chỉ mở khi có `jobId` và đóng khi job kết thúc, lúc rảnh không có kết nối hay request. Thẻ tiến độ ở thanh trái đọc từ context (`AppShell` vẫn nhận `render` để ghi đè khi test). `ProgressBar.tsx` cũ bỏ, dùng `ui/Progress` (`scaleX`). Mở lại trang khi job đang chạy thì app không biết job đó (chưa có API liệt kê job); backend vẫn trả 409.
2. **Ước tính** (`utils/estimate.ts`): trung vị hệ số `render_seconds ÷ duration` của 3 lần gần nhất cùng loại (10 s đầu / cả video / bản đẹp theo fps), nhân độ dài video sắp dựng; chưa có lịch sử thì dùng hệ số mặc định (bản đẹp 50 fps 3, 60 fps 4,2; 30 fps 1,8 theo tỉ lệ; Xem nhanh 10 s đầu 4; Xem nhanh cả video 1,5). Độ dài video chưa biết = số cảnh × 6 s. "Còn ≈ …" = ước tính × (1 − tiến độ); tiến độ 0% hiện "Đang ước tính…". Lịch sử `/renders` lấy một lần khi mở Soạn video, Âm thanh, Xuất video, làm mới khi job kết thúc.
3. **Xem nhanh tự dựng:** nút Xem nhanh ở Soạn video / Âm thanh chuyển sang tab Xuất kèm `location.state = { auto: 'preview' }`; tab Xuất chờ kiểm tra và môi trường xong, rồi dựng 10 s đầu đúng một lần (xoá `state` để tải lại không dựng lại). Thiếu nguyên liệu hoặc bị chặn thì không dựng, thẻ Kiểm tra hiện lý do. Xuất bản đẹp chỉ chuyển tab.
4. **Màn Xuất video:** thẻ Kiểm tra (Sẵn sàng / Có cảnh báo / Bị chặn, 3 số, "Đến cảnh N" mở thẳng cảnh đó), Kết quả, Nội dung đăng, Ảnh bìa, Lịch sử dạng lưới (viền vàng tĩnh cho thẻ đang xem, bìa hoặc ảnh cảnh 1), Dọn file tạm; cột phải có chip fps 30/50/60 (mặc định `settings.fps` của dự án), công tắc Outro, Xem nhanh / Xuất bản đẹp / Xem nhanh cả video, ước tính, tiến độ + Huỷ, trình phát và nút tải video.mp4 / captions.srt / bìa. Nguyên liệu thiếu (ảnh, giọng) tính ngay ở giao diện (`renderBlockers`).
5. **Khoá menu ⋯** theo slug của job đang chạy (Nhân bản, Xoá tắt, `title` "Đang dựng"); catch 409 → Toast giữ lại làm lưới an toàn.
6. **Nút tải bìa** trong ngăn kéo "Bìa & đăng": lấy `/renders` chỉ khi ngăn kéo mở; tải `cover_9x16.jpg` và `youtube_3x2.jpg` từ lần dựng gần nhất có đủ hai file.
7. **`trimmed_tail_seconds`** thêm vào tóm tắt lần dựng (`last_render`, `last_final`) và `/renders` (đọc từ `meta.json`, bản cũ `null`); chỉ sửa `storage.py`, không đụng `pipeline/` hay `models.py`. Nhãn "Đã cắt đuôi X s" ở Âm thanh. Đóng mục (b) của 13.B10.9.
8. **Màn Cài đặt** viết lại bằng `components/ui/*`: thẻ FPS mặc định (chip), Căn chữ (chip Tự động / small / medium / large-v3, ghi chú theo máy, giới hạn giây), Màu chủ đề, Từ nhạy cảm (chip có ×, ô Thêm từ, chip mức Lưu ý / Cảnh báo / Chặn, nhóm mức Lưu ý gộp thu gọn). **Một nút Lưu** ghi cả cài đặt chung và danh sách từ (bỏ lưu tự động của bản cũ). Test quét mã nguồn: `ExportTab.legacy.test.ts`, `SettingsPage.legacy.test.ts`. CSS cũ và bí danh token giữ nguyên đến Đợt 5.
9. **Không làm:** tải ảnh riêng làm bìa (sau `v1.0.0`), hộp JSON (Đợt 4), xoá bí danh token (Đợt 5).
10. **Cần chốt (chưa quyết, đã chọn phương án an toàn):** (a) không có `workspace/mockup/export.png`, `settings.png`; hai màn làm theo 13.B2 + DESIGN-HBT v2; (b) hệ số mặc định của Xem nhanh (4 và 1,5), bản đẹp 30 fps (1,8) và "số cảnh × 6 s" là số tạm, chưa đo trên máy cũ; (c) "nhóm ít dùng" ở Cài đặt hiểu là nhóm mức Lưu ý; mức chọn bằng 3 chip (Lưu ý / Cảnh báo / Chặn) thay cho nút gạt hai trạng thái vì dữ liệu có ba mức; (d) CI của `4e0ded9` chưa kiểm được (`gh` chưa đăng nhập), nếu đỏ sửa ở đầu Đợt 4; (e) mở lại trang giữa lúc đang dựng: thẻ tiến độ không tự nối lại job (cần API liệt kê job); (f) `library/music/index.json` đang sửa dở trong cây làm việc (dữ liệu do app ghi), không commit.

### 13.B12 Quyết định Đợt 4 (chủ dự án duyệt 28/10/2026)

1. **Chỉ làm frontend** (không sửa backend, `pipeline/`, `models.py`; không thêm gói npm). Dùng đúng 4 API của 13.B4.7. `ApiError` giữ thêm `body` (thân JSON của lỗi) để đọc `errors[]` của 422 từ `script/apply`.
2. **Vị trí:** thanh đầu Soạn video có nút **Dán JSON** (cạnh Bìa & đăng) và menu **⋯** (`Menu`, mục duy nhất **Bản sao lưu**). Hộp Dán JSON: `components/script/PasteJsonDialog.tsx` (bước 1 Dán, bước 2 Kiểm tra, nút Áp dụng ở chân hộp); `ScriptCheckView` + `DiffValue` + `utils/scriptDiff.ts` vẽ 3 ô số, khác biệt theo cảnh (cũ → mới, cảnh báo ngay dưới), "+k cảnh mới" thu gọn, dòng "Giữ nguyên:", ghi chú căn chữ lại. `BackupsDialog.tsx` liệt kê ≤ 10 bản (ngày giờ, Áp JSON / Khôi phục / Không rõ) và Khôi phục có xác nhận.
3. **Lưu trước khi kiểm:** `flush()` của `useAutosave` (đã có) chạy trước mỗi lần `script/check`, nên không cần hàm mới. `script` gửi lên là chuỗi người dùng dán nguyên văn (K1 báo dòng:cột từ backend); thả hoặc chọn file `.json` thì đọc vào ô dán.
4. **Lệch số cảnh:** JSON nhiều hơn dự án thì hiện hai chip **Thêm cảnh** / **Bỏ phần thừa**; bấm là kiểm lại với `extra` tương ứng (chip đang chọn đổi được). Nhãn nút "Áp dụng n cảnh" với n = min(JSON, số cảnh sau gộp).
5. **Áp dụng:** gửi `base_hash` của lần kiểm. Thành công → thay project trong editor bằng `project` trả về, đóng hộp, Toast "Đã áp dụng n cảnh" kèm **Hoàn tác** (8 s, không hỏi xác nhận, gọi restore bằng `backup_id` vừa nhận). 422 → hiện `errors[]` ngay trong hộp, nút Áp dụng tắt. 409 hash lệch → Toast rồi tự kiểm lại để lấy hash mới. 409 đang dựng → Toast, giữ hộp.
6. **Khoá khi đang dựng:** theo `RenderJobProvider` (job của chính dự án đang `running`/`starting`): Áp dụng và Khôi phục tắt kèm lý do; Toast áp dụng **không** có Hoàn tác nếu đang dựng lúc áp. Nếu máy chủ vẫn trả 409 (vd mở lại trang giữa lúc dựng) thì hiện Toast như thường.
7. **Test:** Vitest cho endpoints, `scriptDiff`, hộp Dán + Kiểm tra, Áp dụng (409/422/khoá/Hoàn tác), Bản sao lưu, test quét `script.legacy.test.ts` (không lớp cũ, không chữ tiếng Việt cứng trong JSX). E2E `e2e/script-json.spec.ts` (dự án `e2e-dan-json-…`, xoá cuối bài bằng `DELETE`): dán fixture `dao-phuc-sinh.cards.json` → Áp dụng → tải lại còn dữ liệu → Khôi phục bản trước. Sau đợt này e2e có 6 kịch bản.
8. **Việc của chủ dự án:** xoá tay `workspace/import_cards.py` (nằm ngoài git).
9. **Cần chốt (chưa quyết, đã chọn phương án an toàn):** (a) không có mockup `workspace/mockup/` cho hộp này, làm theo 13.B2 + 13.B4.6; (b) dòng "Giữ nguyên:" do giao diện suy ra (ảnh, file giọng, nhạc, cài đặt, tên & series luôn; nội dung đăng / ảnh bìa nếu JSON không đổi chúng), không phải backend trả; (c) Hoàn tác và Khôi phục đều tạo thêm một bản sao lưu `restore`, nên chiếm chỗ trong 10 bản; (d) mở lại trang giữa lúc đang dựng thì giao diện không biết job (chưa có API liệt kê job), chỉ dựa vào 409; (e) menu ⋯ mới có một mục; (f) `script/check` chạy mỗi lần bấm Kiểm tra hoặc chọn Thêm cảnh / Bỏ phần thừa, không chạy khi gõ (không poll); (g) CI của `4a88794` và các commit Đợt 4 chưa kiểm được (`gh` chưa đăng nhập).


### 13.B13 Quyết định Đợt 5 (chủ dự án duyệt 28/10/2026)

1. **Xoá bí danh** (13.B7.1): khối bí danh cuối `tokens.css`, các khoá `surface`, `surface-2`, `text-muted`, `border`, `brand-red`, `brand-cream`, `brand-ink`, `frame` trong `tailwind.config.ts`, và mọi lớp `.btn*` / `.input` / `.label` / `.card` / `.chip*` / `.spinner` cũ trong `index.css` (chỉ giữ `.num`). Không màu nào đổi giá trị: các lớp cũ không còn nơi dùng. Test `legacyAliases.test.ts` quét `frontend/src` + `tailwind.config.ts`, chỉ bắt đúng tên cũ (`bg-surface`, `text-text-muted`, `border-border`, `rounded-frame`, `var(--surface)`…), không bắt `border`, `border-line`, `text-muted`, `rounded-card`. `manifest.webmanifest` giữ `#f7eeda` (không phải token).
2. **Tab/focus:** `Menu` giữ Tab/Shift+Tab trong menu khi đang mở (như mũi tên, thêm Home/End); Esc trả focus về nút ⋯. `Dialog`/`Drawer` đã giữ focus (`useModal`). Vòng focus toàn cục là `:focus-visible` trong `index.css`. E2E `e2e/focus.spec.ts` (kịch bản thứ 7): thứ tự Tab ở thanh trái, Dialog "Video mới", Menu ⋯ và hộp Bản sao lưu giữ focus bên trong, Esc trả focus về nút đã mở.
3. **`GET /jobs`** (chỉ đọc, `JobManager.active()`): job đang chạy và đang chờ, cũ nhất trước: `{id, slug, kind: preview|final, status, progress, step}`. `RenderJobProvider` gọi **đúng một lần** khi mở app, nối lại SSE của job đang chạy (không có thì job đầu hàng), đặt `slug` để khoá ⋯ / Hoàn tác / Khôi phục / Dán JSON. Không đè job người dùng tự bắt đầu trước khi API trả lời; lỗi mạng thì bỏ qua (409 của máy chủ vẫn là lưới an toàn). Không đụng `pipeline/` hay `models.py`.
4. **Cảnh báo rời Cài đặt** (`components/settings/LeaveGuard.tsx`): có thay đổi chưa Lưu thì đổi màn trong app → `ConfirmDialog` ("Ở lại" / "Rời đi"); đóng hoặc tải lại tab → `beforeunload`. Chỉ gắn khi có thay đổi, gỡ khi Lưu xong hoặc rời màn. Cần data router nên `main.tsx` dùng `createBrowserRouter` (một route `*` bọc `ToastProvider` + `App`; `App` giữ `<Routes>`). Chữ ở `vi.settings.leave`.
5. **CLAUDE.md** nêu hai máy theo mục 0.
6. **Button** luôn render `<button>`; liên kết dùng `<a class="ui-btn">` / `<Link className="ui-btn">` (test quét không truyền `href`/`to`/`as` vào `<Button>`). **`/dev/ui`** nhớ `data-theme` của app lúc mở và trả lại khi đóng (và ở chip "Theo hệ thống"), không xoá lựa chọn Sáng/Tối. Đóng mục (f) của 13.B10.9.
7. **Số test cuối đợt** (máy cũ, 28/10/2026): pytest 743 passed (686 không `slow`); Vitest 57 file, 743 test; e2e 7/7. `git diff v0.5.1 -- backend/hbt/pipeline/ reference/` rỗng; `PIPELINE_VERSION = 0112661f2845`.
8. **Cần chốt (chưa quyết, đã chọn phương án an toàn):** (a) nếu có nhiều job (đang chờ), chỉ job đầu hàng được nối lại; khi nó xong thì khoá của job xếp sau chỉ còn dựa vào 409; (b) cảnh báo rời Cài đặt chỉ khi đổi đường dẫn (đổi tham số tìm kiếm không hỏi), "dirty" đặt khi có sửa và không tự bỏ nếu sửa về giá trị cũ; (c) chưa kiểm Esc khi hai hộp chồng nhau (vd Dán JSON + xác nhận); (d) `npm run e2e` chạy dựng Xem nhanh thật (FFmpeg) ở kịch bản export-settings; (e) CI của các commit Đợt 4–5 chưa kiểm được (`gh` chưa đăng nhập); (f) `library/music/index.json` vẫn sửa dở, không commit, không stash.
