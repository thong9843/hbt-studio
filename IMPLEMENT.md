# HBT Studio — Đặc tả triển khai (cho Claude Code)

> Đọc theo thứ tự: `CLAUDE.md` → `PLAN.md` → file này → `reference/pipeline/*.py` → `DESIGN.md`.
> Phiên bản: v1.1 · 20/10/2026 (bổ sung thương hiệu HBT, ghim getdesign).
> Phạm vi file này: **Giai đoạn 1** (mốc M0–M4). Giai đoạn 2 chỉ định nghĩa interface ở mục 12.
> Mọi tham số dựng video trong `reference/` **đã chạy thật trên 6 video**: giữ nguyên, trừ khi file này ghi khác.

---

## 0. Môi trường (Windows 10/11, RTX 2060 Super 8 GB)

| Thành phần | Phiên bản | Cài |
|---|---|---|
| Git | mới nhất | `winget install Git.Git` |
| Python | 3.11.x | `winget install Python.Python.3.11` |
| Node.js | 20 LTS trở lên | `winget install OpenJS.NodeJS.LTS` |
| FFmpeg | ≥ 6.0, có `libx264`, `zoompan`, `xfade`, `sidechaincompress`, `loudnorm` | `winget install Gyan.FFmpeg` (thêm vào PATH) |
| Driver NVIDIA | hỗ trợ CUDA 12 | GeForce Experience / trang NVIDIA |
| faster-whisper | bản ổn định mới nhất | `pip install faster-whisper` + thư viện CUDA (xem README của faster-whisper: `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) |

Lần chạy Whisper đầu tiên sẽ tải model `large-v3` (~3 GB) về `models/` (đã ignore). Nếu không có GPU hoặc lỗi CUDA → tự rơi về CPU, rồi về chế độ căn theo khoảng lặng.

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
│  │  │  ├─ align.py         # = reference/pipeline/align.py
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

`.gitignore` bắt buộc có: `workspace/`, `models/`, `library/music/**/*.mp3`, `*.mp4`, `*.wav`, `.env`, `node_modules/`, `.venv/`, `__pycache__/`.

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
WHISPER_MODEL=large-v3
WHISPER_DEVICE=auto        # auto | cuda | cpu
DEFAULT_FPS=60
```

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
  "settings": { "fps": 60, "captions": true, "aligner": "auto", "sfx_on_punch": true },
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
| `voice` | Lời đọc của cảnh. `|` = ngắt cụm phụ đề. `100{một trăm}` = hiển thị "100", đọc "một trăm" |
| `punch` | `true` = cảnh "cú lật": phóng giật + hiện thẻ nhanh + whoosh |
| `caption_y` | `null` = tự động (1420; nếu đáy thẻ > 1100 thì 230), hoặc số pixel |
| `music.start` | `null` = tự chọn đoạn hay; hoặc số giây |

Validate bằng Pydantic. Đúng **1 đoạn lời cho mỗi cảnh**; số cảnh 3–12.

---

## 4. Pipeline dựng video (`pipeline/render.py`)

Mỗi bước báo tiến độ (0–100) và ghi log. Bước nào có output trùng hash đầu vào thì bỏ qua (cache trong `build/`).

| # | Bước | Chi tiết | Tiến độ |
|---|---|---|---|
| 1 | Kiểm tra | Validate project, đủ ảnh/giọng, chạy `lint` (mục 7). Lỗi mức `block` → dừng | 0–3 |
| 2 | Chuẩn hoá giọng | `prep_voice` (reference): highpass 70 Hz, trễ 0,2 s, đệm 1,6 s, loudnorm −14 LUFS, mono 44,1 kHz → `build/voice.wav` | 3–6 |
| 3 | Căn chữ | Ghép token mọi cảnh (giữ chỉ số cảnh) → `align.align()` (mục 5). Lưu `build/timing.json` | 6–20 |
| 4 | Mốc chuyển cảnh | cut_k = (kết thúc chữ cuối cảnh k−1 + bắt đầu chữ đầu cảnh k)/2; offset xfade = cut − 0,2; thời lượng theo `durations()` (reference) | 20 |
| 5 | Lớp hình | `visual.build_scene_layers`: ảnh fit 1080×1920 + nhãn cố định; lớp thẻ chữ PNG trong suốt | 20–25 |
| 6 | Clip từng cảnh | `render_scene` (reference): zoompan trên ảnh phóng 2160×3840, cảnh lẻ 1.00→1.08, chẵn 1.08→1.00; `punch`: 1.18→1.00 trong 0,4 s rồi 1.00→1.05; thẻ hiện dần sau 0,3 s (punch: 0,15 s). Encode trung gian `crf 16 veryfast` | 25–70 |
| 7 | Âm thanh | Chọn đoạn nhạc (mục 6), `mix_audio` (reference): nhạc −27 LUFS, ducking theo giọng, fade vào 0,8 s / ra 2,5 s, whoosh tại các cảnh `punch`, tổng −14 LUFS | 70–75 |
| 8 | Phụ đề | `captions.py` (mục 5.3) → PNG trạng thái + `captions.ffconcat` + `captions.srt` | 75–80 |
| 9 | Ghép cuối | `assemble` (reference): xfade `slideleft` 0,4 s + phủ phụ đề + tiếng; H.264 `crf 18 medium`, `-r {fps}`, yuv420p, AAC 192k, `+faststart` | 80–98 |
| 10 | Kiểm tra đầu ra | ffprobe đúng fps, 1080×1920, độ dài; đo `ebur128` trong khoảng −15…−13 LUFS; sinh `publish.txt` | 98–100 |

**Chế độ Xem nhanh (`preview=true`):** 540×960, 30 fps, zoompan trên ảnh 1080×1920, `ultrafast`. Dùng để duyệt trước khi xuất bản đẹp.

**FPS:** mặc định **60** (cho phép 30). Không cho chọn số lạ như 45.

**Vùng an toàn TikTok:** nội dung quan trọng (thẻ, phụ đề) trong khoảng y = 100…1500, tránh mép phải 120 px.

---

## 5. Căn chữ & phụ đề

### 5.1 Token (`text.parse_voice`)
- Tách theo khoảng trắng; `|` đánh dấu cụm mới; token kết thúc bằng `, . ! ? : ; …` cũng kết thúc cụm.
- Mỗi token có `disp` (hiển thị) và `syl` (danh sách âm tiết đã bỏ dấu, dùng để so khớp).

### 5.2 Căn thời gian (`align.align`)
1. **Whisper** (mặc định): faster-whisper, `language="vi"`, `word_timestamps=True`, `initial_prompt` = lời đọc (220 ký tự đầu). Chuẩn hoá âm tiết nghe được (`text.norm`), so khớp với âm tiết kịch bản bằng `difflib.SequenceMatcher(autojunk=False)`; âm tiết không khớp thì nội suy giữa 2 điểm neo. Thời gian token = âm tiết đầu → âm tiết cuối.
2. **Dự phòng — khoảng lặng:** `align_silence` (quy hoạch động ghép cụm câu ↔ đoạn có tiếng). Dùng khi không cài Whisper hoặc `aligner="silence"`.
3. Sau khi căn xong: giải phóng model Whisper khỏi VRAM.

### 5.3 Phụ đề karaoke (`captions.py`)
- **Cụm:** theo `|` và dấu câu; cụm > 7 token thì tự tách đôi. Tối đa 2 dòng, rộng 900 px.
- **Kiểu:** Be Vietnam Pro ExtraBold 70 px, chữ trắng viền tối 7 px + bóng; **chữ đang đọc**: nền vàng `#FFD43B` bo góc 18 px, chữ tối. Dòng cao 96 px, căn giữa tại `caption_y`.
- **Thời gian hiện cụm:** từ (đầu chữ đầu − 0,05 s) đến đầu cụm sau nếu khoảng cách < 0,6 s, ngược lại đến (cuối chữ cuối + 0,25 s). Chữ k sáng từ đầu chữ k đến đầu chữ k+1.
- **Hiển thị:** bỏ `, . : ;` cuối token; giữ `? ! …`.
- **Kỹ thuật:** mỗi trạng thái 1 PNG 1080×1920 trong suốt; file `ffconcat` có `duration`; phủ bằng `overlay` (xem `assemble`).
- Xuất kèm `captions.srt` (theo cụm) để tải lên YouTube nếu muốn.

---

## 6. Âm thanh & thư viện nhạc

### 6.1 Tự chọn đoạn nhạc (`music.start = null`)
Tính độ lớn theo cửa sổ 1 s; bỏ 2 s đầu; chọn thời điểm đầu tiên có độ lớn ≥ (trung vị − 3 dB) để bỏ phần dạo đầu quá nhỏ; nếu đoạn còn lại ngắn hơn video thì lùi điểm bắt đầu. Ghi điểm đã chọn vào log để người dùng chỉnh tay.

### 6.2 Thư viện `library/music/index.json`
```json
[{ "file": "funny/the-wacky-sprint.mp3", "title": "The Wacky Sprint", "artist": "nkbloom",
   "source": "Pixabay", "url": "https://pixabay.com/…", "license": "Pixabay Content License",
   "moods": ["vui", "tinh nghịch"], "bpm": null }]
```
UI cho chọn nhạc từ thư viện hoặc tải file mới (tải mới thì hỏi tên, tác giả, nguồn, giấy phép, tâm trạng → thêm vào index). `credit` của project tự điền từ thư viện.

### 6.3 Whoosh
Tổng hợp bằng FFmpeg (`synth_whoosh` trong reference), không dùng file ngoài → không vướng bản quyền.

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

---

## 8. Sinh nội dung đăng (`publish.txt`)

```
[TikTok]
{hook}
#{hashtags cách nhau bằng dấu cách}

[YouTube Shorts]
Title: {title} #shorts
Description: {hook} Series "{series}". Nhạc: {music.credit}
```
Hiện trong UI với nút **Sao chép** từng khối.

---

## 9. API (`/api`, JSON, lỗi theo dạng `{detail}`)

| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | `{ok, ffmpeg, whisper, gpu, missing}` — kiểm tra môi trường (xem định nghĩa dưới bảng) |
| GET | `/projects` | danh sách `{slug, title, updated_at, thumb, last_render}` |
| POST | `/projects` | `{title, series?, scene_count=8}` → tạo project rỗng |
| GET / PUT / DELETE | `/projects/{slug}` | đọc / lưu toàn bộ `project.json` / xoá |
| POST | `/projects/{slug}/duplicate` | nhân bản làm template |
| POST | `/projects/{slug}/assets` | multipart: `kind=image|voice|music`, `scene` (với ảnh) |
| GET | `/projects/{slug}/scenes/{i}/preview.png` | khung hình tĩnh: ảnh + nhãn + thẻ + phụ đề mẫu (cụm đầu) |
| POST | `/projects/{slug}/lint` | kết quả mục 7 |
| POST | `/projects/{slug}/render` | `{preview: bool, fps?: 30|60}` → `{job_id}` |
| GET | `/jobs/{id}` | `{status: queued|running|done|failed|cancelled, progress, step, log_tail, output}` |
| GET | `/jobs/{id}/events` | SSE: `event: progress` `data: {progress, step, message}` |
| POST | `/jobs/{id}/cancel` | huỷ (kill tiến trình ffmpeg con) |
| GET | `/music` · POST `/music` | thư viện nhạc |
| GET | `/settings/sensitive-words` · PUT | danh sách từ nhạy cảm |
| GET | `/files/{path}` | phục vụ file trong workspace (chặn `..`) |

**Định nghĩa `/health`** (chủ dự án duyệt 20/10/2026):
- `ffmpeg`: `ffmpeg -version` chạy được.
- `missing`: các mục bắt buộc còn thiếu. Encoder: `libx264` (theo `ffmpeg -encoders`). Filter: `zoompan`, `xfade`, `sidechaincompress`, `loudnorm`, `silencedetect` (theo `ffmpeg -filters`). Nếu FFmpeg không chạy được thì `missing = ["ffmpeg"]`.
- `ok`: `true` khi và chỉ khi `missing` rỗng. Whisper và GPU **không** ảnh hưởng `ok` vì đã có đường dự phòng (mục 5.2).
- `whisper`: import được `faster_whisper`. `gpu`: CTranslate2 thấy ít nhất 1 thiết bị CUDA.

---

## 10. Giao diện

### 10.1 Thương hiệu & phong cách

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
| **Âm thanh** (tab) | Tải giọng đọc (có trình phát), chọn nhạc từ thư viện hoặc tải mới, ô `music.start`, nút nghe thử 10 s đoạn nhạc được chọn |
| **Xuất video** (tab) | Kết quả lint; nút **Xem nhanh** và **Xuất bản đẹp 60fps**; thanh tiến độ theo bước (SSE); trình phát video; nút tải `video.mp4`, `captions.srt`; khối `publish.txt` có nút sao chép; lịch sử các lần xuất |
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
- **Golden test thủ công (M1):** chủ dự án đặt bộ file tập "muỗi" vào `workspace/samples/muoi/`, chạy CLI, so với bản đã đăng.
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

### M1 · Bộ dựng (không giao diện)
- [ ] Copy `reference/pipeline/{text,align,visual}.py` vào `backend/hbt/pipeline/`
- [ ] Viết `audio.py`, `captions.py`, `render.py` theo mục 4–6 dựa trên `render_reference.py`
- [ ] Cache theo hash trong `build/`; ghi `log.txt`; trả tiến độ qua callback
- [ ] `cli.py render <dir> [--preview] [--fps]`
- [ ] Test mục 10b
- **Xong khi:** dựng được tập "muỗi" 60 fps, 1080×1920, −14 ±1 LUFS, phụ đề đúng chữ.

### M2 · API
- [ ] Models Pydantic + storage + toàn bộ endpoint mục 9
- [ ] Job runner 1 luồng, SSE, huỷ job
- [ ] `preview.png` từng cảnh (dùng chung code `visual.py` + `captions.render_caption`)
- **Xong khi:** tạo project, tải file, dựng video hoàn toàn bằng `curl`.

### M3 · Giao diện
- [ ] Áp `DESIGN.md` → tokens.css + màu HBT; gắn logo, favicon, icon từ `brand/` (theo mục 10.1)
- [ ] 4 màn hình mục 10.2, kéo thả ảnh/cảnh, lưu tự động
- [ ] Theo dõi tiến độ bằng SSE, trình phát video, tải file
- **Xong khi:** làm trọn 1 video chỉ bằng giao diện, không mở terminal.

### M4 · Hoàn thiện
- [ ] Whisper làm mặc định, fallback khoảng lặng; hiển thị phương pháp đã dùng
- [ ] Lint nội dung + trang chỉnh danh sách từ
- [ ] Thư viện nhạc + tự chọn đoạn nhạc + ghi công tự động
- [ ] `publish.txt` + nút sao chép
- **Xong khi:** phụ đề lệch < 0,05 s trên tập "muỗi"; kịch bản có chữ "bia" hiện cảnh báo.

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
