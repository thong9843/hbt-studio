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
| faster-whisper | bản ổn định mới nhất | `pip install faster-whisper`; máy có GPU cần thêm thư viện CUDA 12 (xem README của faster-whisper: `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) |

**Python:** dự án ghim **Python 3.11.x**. Máy nào đã có Python mới hơn thì cài thêm 3.11 **song song** (không gỡ bản cũ), gọi bằng `py -3.11`, và tạo `backend\.venv` đúng bằng bản 3.11 (`py -3.11 -m venv backend\.venv`). Kiểm tra bằng `py -3.11 --version` (README có bước này). Claude Code phải **hỏi chủ dự án trước khi cài** Python hay bất kỳ phần mềm cấp hệ thống nào.

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
| `caption_y` | `null` = tự động (1420; nếu đáy thẻ > 1100 thì 230), hoặc số pixel |
| `music.start` | `null` = tự chọn đoạn hay; hoặc số giây |

Validate bằng Pydantic. Đúng **1 đoạn lời cho mỗi cảnh**; số cảnh 3–12.

---

## 4. Pipeline dựng video (`pipeline/render.py`)

Mỗi bước báo tiến độ (0–100) và ghi log. Bước nào có output trùng hash đầu vào thì bỏ qua (cache trong `build/`).

| # | Bước | Chi tiết | Tiến độ |
|---|---|---|---|
| 1 | Kiểm tra | Validate project, đủ ảnh/giọng, chạy `lint` với danh sách từ hiện hành (mục 7). Có mức `block` → dừng, báo `Chặn xuất: Cảnh N: …` (CLI lấy danh sách như app: bản riêng ở `workspace/settings/` nếu có, không thì bản mặc định) | 0–3 |
| 2 | Chuẩn hoá giọng | `prep_voice` (reference): highpass 70 Hz, trễ 0,2 s, đệm 1,6 s, loudnorm −14 LUFS, mono 44,1 kHz → `build/voice.wav` | 3–6 |
| 3 | Căn chữ | Ghép token mọi cảnh (giữ chỉ số cảnh) → `align.align()` (mục 5). Lưu `build/timing.json` | 6–20 |
| 4 | Mốc chuyển cảnh | cut_k = (kết thúc chữ cuối cảnh k−1 + bắt đầu chữ đầu cảnh k)/2; offset xfade = cut − 0,2; thời lượng theo `durations()` (reference) | 20 |
| 5 | Lớp hình | `visual.build_scene_layers`: ảnh fit 1080×1920 + nhãn cố định; lớp thẻ chữ PNG trong suốt | 20–25 |
| 6 | Clip từng cảnh | `render_scene` (reference): zoompan trên ảnh phóng 2160×3840, cảnh lẻ 1.00→1.08, chẵn 1.08→1.00; `punch`: 1.18→1.00 trong 0,4 s rồi 1.00→1.05; thẻ hiện dần sau 0,3 s (punch: 0,15 s). Encode trung gian `crf 16 veryfast` | 25–70 |
| 7 | Âm thanh | Chọn đoạn nhạc (mục 6), `mix_audio` (reference): nhạc −27 LUFS, ducking theo giọng, fade vào 0,8 s / ra 2,5 s, whoosh tại các cảnh `punch`, tổng −14 LUFS | 70–75 |
| 8 | Phụ đề | `captions.py` (mục 5.3) → PNG trạng thái + `captions.ffconcat` + `captions.srt` | 75–80 |
| 9 | Ghép cuối | `assemble` (reference): xfade `slideleft` 0,4 s + phủ phụ đề + tiếng; H.264 `crf 18 medium`, `-r {fps}`, yuv420p, AAC 192k, `+faststart` | 80–98 |
| 10 | Kiểm tra đầu ra | ffprobe đúng fps, 1080×1920, độ dài; đo `ebur128` trong khoảng −15…−13 LUFS; sinh `publish.txt` | 98–100 |

**Chế độ Xem nhanh (`preview=true`):** 540×960, 30 fps, zoompan trên ảnh 1080×1920, clip cảnh `ultrafast crf 23`, ghép cuối `veryfast crf 30`, AAC 96 kbps. Dùng để duyệt trước khi xuất bản đẹp. Mục tiêu dưới ~10 MB cho video 50 giây; đo thực tế trên tập "muỗi": 3,7 MB, 36 s dựng (trước đó `ultrafast crf 23` + AAC 192k: 39,8 MB). Tham số bản đẹp không đổi.

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
  2. Với chế độ khoảng lặng (chưa có Whisper), căn 2 cấp: cấp 1 ghép cảnh ↔ nhóm đoạn tiếng, cấp 2 ghép cụm câu ↔ đoạn tiếng trong từng cảnh (mục 5.2). Chỉ **tự động** bỏ đoạn cuối khi đủ **cả ba** điều kiện:
     - điều kiện bảo vệ: tối đa `số đoạn tiếng − số cụm câu` đoạn cuối (và không quá 3);
     - bỏ đoạn đó làm chi phí ghép **giảm từ 1,0 trở lên**;
     - đoạn cuối dài **từ 1,5 giây**.

     Ngược lại giữ nguyên và ghi cảnh báo `Có thể có đoạn thừa ở cuối file giọng (x,xx giây), chưa cắt` (nếu bỏ đoạn đó vẫn làm chi phí giảm). Kịch bản ngắn (khoảng 3 cảnh) thường không đạt ngưỡng 1,0 nên chỉ cảnh báo.
  3. **Tự cắt tay bằng `voice.trim_end`:** trong `project.json`, `voice` có thể là `"voice.mp3"` hoặc `{"file": "voice.mp3", "trim_end": 41.5}`. `trim_end` là giây trên **file giọng gốc** (nghe file gốc để chọn điểm cắt). Có `trim_end` thì cắt **trước khi căn chữ** (để đoạn thừa không làm lệch căn), không chạy cắt tự động và không cần xác nhận, fade ra 80 ms, đệm lại 1,6 s. `trim_end` nằm sau hết file giọng thì báo lỗi.
  4. Ghi log `Đã cắt N đoạn thừa ở cuối file giọng (x,xx giây)` và hiện trong UI kèm nút **nghe phần đã cắt** để chủ dự án xác nhận. Cắt quá 8 giây thì dừng và hỏi.
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
- **UI tab Xuất video:** ô nhập 2–3 dòng, chọn cảnh nền, xem trước hai khung cắt 3:4 và 3:2, nút tải hai file. `publish.txt` thêm khối `[Thumbnail]` gồm 3 dòng (mục 8): `Dòng chữ bìa: <các dòng cách nhau bằng dấu />`, `TikTok: cover_9x16.jpg`, `YouTube Shorts: youtube_3x2.jpg`.

**Vùng an toàn TikTok:** nội dung quan trọng (thẻ, phụ đề) trong khoảng y = 100…1500, tránh mép phải 120 px.

---

## 5. Căn chữ & phụ đề

### 5.1 Token (`text.parse_voice`)
- Tách theo khoảng trắng; `|` đánh dấu cụm mới; token kết thúc bằng `, . ! ? : ; …` cũng kết thúc cụm.
- Mỗi token có `disp` (hiển thị) và `syl` (danh sách âm tiết đã bỏ dấu, dùng để so khớp).

### 5.2 Căn thời gian (`align.align`)
1. **Whisper** (mặc định): faster-whisper, `language="vi"`, `word_timestamps=True`, `initial_prompt` = lời đọc (220 ký tự đầu). Chuẩn hoá âm tiết nghe được (`text.norm`), so khớp với âm tiết kịch bản bằng `difflib.SequenceMatcher(autojunk=False)`; âm tiết không khớp thì nội suy giữa 2 điểm neo. Thời gian token = âm tiết đầu → âm tiết cuối.
   - **Chọn cấu hình theo phần cứng** (chủ dự án chốt 22/10/2026). `.env`: `WHISPER_DEVICE=auto`, `WHISPER_MODEL=auto`.

     | Phần cứng | Thiết bị | Kiểu tính | Model |
     |---|---|---|---|
     | Có CUDA (máy mới, RTX 2060 Super 8 GB) | `cuda` | `int8_float16` | `large-v3` (cần thư viện CUDA 12 theo README của faster-whisper) |
     | Không có GPU (máy cũ) | `cpu` | `int8` | `small` |

     Trong **Cài đặt** cho đổi sang `medium` hoặc `large-v3` trên CPU, kèm cảnh báo "sẽ chậm". Không giả định có GPU: `auto` kiểm tra CUDA lúc chạy (`/health.gpu`).
   - **Cache:** kết quả căn chữ lưu ở `build/timing.json`, khoá theo **hash file giọng** và **hash kịch bản** (kèm phương pháp, model, mã nguồn); chỉ căn lại khi một trong hai đổi.
   - **Dự phòng khi lỗi hoặc chậm:** Whisper lỗi (không cài, lỗi CUDA, thiếu RAM) hoặc quá chậm (vượt **giới hạn thời gian** đặt trong Cài đặt) thì tự rơi về căn theo khoảng lặng (mục dưới) và ghi log lý do; kết quả ghi rõ phương pháp đã dùng.
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
- **Kiểu:** Be Vietnam Pro ExtraBold 70 px, chữ trắng viền tối 7 px + bóng; **chữ đang đọc**: nền vàng `#FFD43B` bo góc 18 px, chữ tối. Dòng cao 96 px, căn giữa tại `caption_y`.
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
| POST | `/projects/{slug}/assets` | multipart: `kind=image|voice|music`, `scene_index` (từ 0, với ảnh) |
| GET | `/projects/{slug}/scenes/{scene_index}/preview.png` | khung hình tĩnh: ảnh + nhãn + thẻ + phụ đề mẫu (cụm đầu) |
| POST | `/projects/{slug}/lint` | kết quả mục 7 |
| POST | `/projects/{slug}/render` | `{preview: bool, fps?: 30|60}` → `{job_id}` |
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
- **`POST /projects/{slug}/render`** nhận `{preview, fps: 30|50|60, outro, allow_long_trim}`, trả 202 `{job_id}`. Trước khi tạo job, lint chạy với danh sách từ hiện hành: có từ mức `block` → **422** `Có từ bị chặn, sửa rồi dựng lại: Cảnh N: …` (liệt kê các từ), không tạo job (cùng kiểu với `Project chưa đủ để dựng`, kiểm sau lỗi thiếu dữ liệu và trước kiểm FFmpeg). Kết quả ở `renders/<job_id>/` (`video.mp4`, `captions.srt`, `publish.txt`, `log.txt`, `meta.json`).
- **Job:** một luồng dựng, job nằm trong bộ nhớ (giữ 200 job; mất khi khởi động lại server, file đã xuất vẫn còn). `GET /jobs/{id}` → `{id, project, status, progress, step, log_tail, output, error, needs_confirmation, …}`; `output` có URL `/api/files/...`. **SSE** `GET /jobs/{id}/events`: `event: progress` (`{progress, step, message}`) rồi `event: end` (`{status, error, output}`); người nối sau nhận lại từ đầu. **Huỷ**: job xếp hàng huỷ ngay và không bao giờ chạy; job đang chạy bị kill ffmpeg, đợi tối đa 5 s cho luồng dừng, không để lại video dở. Đuôi giọng cần cắt > 8 s: job `failed` với `needs_confirmation = true` (gửi lại với `allow_long_trim`).
- **`POST /music`** (multipart `file`, `title`, `artist`, `source`, `license` bắt buộc; `url`, `moods` cách nhau dấu phẩy, `bpm` 30–300) lưu phẳng `library/music/<slug-tiêu-đề>.<ext>`, tạo `id` (slug từ tiêu đề, bỏ dấu tiếng Việt kể cả `đ`, trùng thì `-2`, tạo một lần, không đổi) và thêm vào `index.json`. `file` trong index là đường dẫn tương đối trong `library/music/` (cho thư mục con, dùng `/`; từ chối tuyệt đối, ổ đĩa, `..`, `\`, đuôi ngoài các đuôi âm thanh của mục 9). Bài thiếu `id` trong `index.json` được gán id từ tiêu đề theo thứ tự trong file rồi ghi lại một lần. Thư mục con chỉ dành cho file đặt tay rồi khai vào `index.json`.
- **`GET /files/{path}`** chỉ phục vụ trong workspace, hỗ trợ Range (206) cho video; chặn `..`, đường dẫn tuyệt đối, ổ đĩa và mọi thư mục ẩn (bắt đầu bằng dấu chấm).
- **Slug project** (chủ dự án chốt 21/10/2026): chỉ `[a-z0-9-]` (không bắt đầu/kết thúc/đôi dấu gạch), tối đa 60 ký tự, và không trùng tên thiết bị dành riêng của Windows (`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`). Mọi nơi dùng slug đều kiểm tra và trả **422** `Slug không hợp lệ: …` (đọc, sửa, xoá, nhân bản, tải file, xem trước, lint, dựng, và `/files/projects/<slug>/…`; slug trong thân `PUT` cũng vậy). Đường dẫn `/files` có `..`, đường dẫn tuyệt đối, ổ đĩa hoặc thư mục ẩn cũng 422; đường dẫn đúng dạng mà không có file thì 404. Tiêu đề trùng tên thiết bị Windows ("Con", "NUL"…) được thêm hậu tố `-video`; hậu tố chống trùng (`-2`, `-3`…) không làm slug vượt 60 ký tự.
- **Thiếu FFmpeg** (chủ dự án chốt 21/10/2026): server không sập. `/health` báo `ffmpeg: false`, `missing: ["ffmpeg"]`. `POST /render` trả **503** kèm lời nhắn cài (`winget install Gyan.FFmpeg`, mở lại terminal, xem README.md) và **không tạo job**; cũng trả 503 nếu FFmpeg thiếu encoder/filter bắt buộc hoặc thiếu ffprobe. Tải giọng/nhạc và `POST /music` trả 503 (cần ffprobe để kiểm tra file). Project chưa đủ vẫn nhận 422 trước 503. Những việc không cần FFmpeg (CRUD, ảnh, xem trước, lint, `/files`, từ nhạy cảm) vẫn chạy.
- Chưa làm (ngoài đặc tả M2): endpoint riêng cho `publish.txt` (đã có qua `/files`).

**Bổ sung cho giao diện M3** (quyết định khi làm M3, chờ chủ dự án xác nhận khi duyệt):
- `GET /music/{id}/audio` phát bài trong thư viện (nghe thử, hỗ trợ Range; `id` là `id` trong `GET /music`; sai định dạng → 422, không có → 404; M4 đổi từ tên file sang id, route cũ đã bỏ); `POST /projects/{slug}/music/from-library` `{id}` chép bài vào project và đặt ghi công `"tên bài – nghệ sĩ (nguồn)"`.
- `GET /projects/{slug}/renders` lịch sử các lần xuất (mới nhất trước, đọc từ `renders/<job_id>/meta.json`).
- `POST /projects/{slug}/scenes/reorder` `{order}` (hoán vị của `0..n-1`; cảnh mới thứ i là cảnh cũ `order[i]`). Ảnh tên chuẩn `images/scene-NN.<ext>` được đổi tên theo chỉ số mới để tải ảnh về sau không ghi đè ảnh của cảnh khác. 409 khi project đang dựng.
- `POST /projects/{slug}/scenes/{scene_index}/preview.png` `{scene, theme?}`: xem trước bản nháp chưa lưu (ảnh phải nằm trong thư mục project, nếu không 422), để thấy kết quả ngay khi đang gõ.
- `GET|PUT /settings/app`: `{default_fps, theme{primary,accent}, whisper_model, whisper_timeout_seconds}` lưu ở `workspace/settings/app.json`. `default_fps` và `theme` áp dụng cho project tạo mới; hai trường Whisper chỉ được lưu, M4 mới dùng.

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
| **Âm thanh** (tab) | Tải giọng đọc (có trình phát), chọn nhạc từ thư viện hoặc tải mới, ô `music.start`, nút nghe thử 10 s đoạn nhạc được chọn (P3, mục 6.1: nếu `music.start` trống và lần dựng gần nhất có `music_start_source = "auto"` thì hiện "Lần dựng gần nhất app chọn giây X", nghe thử phát từ X và có nút **Dùng giá trị này** điền X vào `music.start`; chưa có lần dựng nào thì phát từ giây 0 kèm ghi chú bấm Xem nhanh) |
| **Xuất video** (tab) | Kết quả lint; nút **Xem nhanh** và **Xuất bản đẹp 50fps**, công tắc **Thêm outro**; thanh tiến độ theo bước (SSE); trình phát video; nút tải `video.mp4`, `captions.srt`; khối `publish.txt` có nút sao chép; lịch sử các lần xuất |
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
- [ ] Thư viện nhạc + tự chọn đoạn nhạc + ghi công tự động
- [ ] `publish.txt` + nút sao chép
- [ ] `thumbnail.py` (mục 4e)
- **Xong khi:** phụ đề lệch < 0,05 s trên tập "muỗi"; kịch bản có chữ "bia" hiện cảnh báo.

**Kế hoạch M4 (chủ dự án chốt 23/10/2026):**
- **Đợt 2 (máy cũ):**
  - (a) Thư viện nhạc có id: slug từ tiêu đề, bỏ dấu tiếng Việt, trùng thì `-2`, tạo một lần. `file` là đường dẫn tương đối trong `library/music/`, cho thư mục con; từ chối tuyệt đối, ổ đĩa, `..`, `\`. Bỏ route `/music/{file}/audio` (dùng `/music/{id}/audio`). `.gitignore`: `library/music/**` + `!library/music/index.json` + chặn `*.mp3 *.m4a *.ogg *.flac *.aac`.
  - (b) Tự chọn đoạn nhạc theo 6.1 (đã có) + `music.start`; ghi công từ thư viện; không thêm trường mới.
  - (c) Lint từ nhạy cảm theo mục 7 (`sensitive_words.json`, warn/block theo danh mục), trang Cài đặt, áp cả dòng chữ bìa.
  - (d) Xem nhanh 10 s đầu (chủ dự án chốt 23/10/2026): nút Xem nhanh mặc định chỉ dựng 10 s đầu (540×960, 30 fps như cũ), giữ tuỳ chọn xem nhanh cả video; căn chữ và điểm nhạc (`music_start`) vẫn tính trên cả video; thời gian dựng tuỳ máy. Chi tiết kỹ thuật ghi vào mục 4 và 9 khi làm.
- **Đợt 1 (máy mới):** Whisper theo mục 5.2, cache `timing.json`, `bench-align`, cắt đuôi giọng bằng Whisper.
- **Đợt 3:** thumbnail (4e), `publish.txt` có khối [Thumbnail], lệnh dọn `build/`, golden test trên cả hai máy.

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
