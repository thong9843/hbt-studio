# IMPLEMENT-POSTV — Đặc tả triển khai PostV

Ngày 29/10/2026 · Dựa trên `main` `b086d06` (`v1.1.0`) · Chỉ là tài liệu thiết kế; chưa có mã.
Đi kèm: `02-PRD.md` (mục tiêu, Brief ↔ mã), `06-cau-hoi-mo.md` (mã câu `C-nn`).
Ký hiệu: **[KC]** đã kiểm chứng · **[SL]** suy luận · **[?]** chưa biết.
Luật gốc vẫn áp: `CLAUDE.md`, `IMPLEMENT.md` mục 0 (không giả định GPU), `DESIGN-HBT.md` v2.

## 0. Nguyên tắc

| #   | Nguyên tắc                                                                                                                               |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| N1  | **Không sửa** `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`. `PIPELINE_VERSION` giữ nguyên; video HBT cũ dựng giống hệt |
| N2  | Mã PostV nằm trong `backend/hbt/postv/` (import từ `pipeline/` được, không ngược lại)                                                    |
| N3  | Project PostV là `kind: "postv"`; project cũ **không có** trường `kind` và không bị ghi lại khác đi                                      |
| N4  | Không request ra ngoài (nguồn chỉ do người dán). Trừ tải trọng số VieNeu lần đầu về `models/` (cần chủ dự án duyệt ở PV0)                |
| N5  | Một luồng job nặng tại một thời điểm (dùng lại `JobManager`)                                                                             |
| N6  | Chữ trên video (thẻ, phụ đề) vẽ bằng Pillow, font trong `backend/hbt/fonts/` (Be Vietnam Pro, có OFL)                                    |
| N7  | Mọi thông số tạo hình (vị trí, cỡ, màu, thời gian hiệu ứng) nằm trong **cấu hình mẫu** `postv/templates/*.json`, không cứng trong mã     |

## 1. Bảng tái sử dụng

| Cần                   | Dùng lại (file / hàm thật)                                                                                                                   | Cách dùng                                                           |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Chuẩn hoá giọng       | `pipeline/audio.prep_voice` (trễ 0,2 s, đệm 1,6 s, −14 LUFS, mono)                                                                           | Gọi trực tiếp                                                       |
| Token lời đọc         | `pipeline/text.parse_voice` (`\|`, `{}`)                                                                                                     | Gọi theo từng đoạn (segment)                                        |
| Căn chữ               | `render.run_alignment`, `render.whisper_alignment`, `pipeline/whisper.py`, `scene_align.py`, `align.py`                                      | Import `run_alignment`; **chép** phần điều phối bước 2–4 (D15)      |
| Mốc đoạn              | `render.scene_offsets`, `compute_offsets`, `offsets_valid`, `clip_durations`                                                                 | Coi mỗi segment là một "cảnh" khi gọi                               |
| Cache                 | `pipeline/cache.py` (`digest`, `is_fresh`, `mark`, `publish_atomic`)                                                                         | Khoá có `PIPELINE_VERSION` + `POSTV_VERSION`                        |
| Nhạc                  | `audio.pick_music_start`, `mix_audio`, `trim_with_fade`; `library.MusicLibrary`, `POST /music`                                               | Dùng nguyên (ducking, −14 LUFS)                                     |
| Outro                 | `render.outro_clip_for`, `audio.build_outro_audio`, `audio.join_audio`, `brand/outro/`, `library/outro/voice.wav`                            | Dùng nguyên                                                         |
| Phụ đề                | `captions.Phrase`, `write_ffconcat`, `write_srt`, `caption_y_for` (không dùng)                                                               | Tự viết bộ tách cụm 1–3 từ và bộ vẽ trạng thái (B5)                 |
| Bìa                   | `thumbnail.render_cover`, `save_covers`, `LOGO_FILE`; `Thumbnail` (`models.py`), `POST /assets kind=cover`                                   | Gọi `render_cover` trực tiếp, không qua `make_covers` (B7)          |
| Lint                  | `sensitive.py` (`compile_words`, `find_hits`, `SensitiveStore`), `/settings/sensitive-words`                                                 | PostV tự quét nguồn + kịch bản; không gọi `lint_project(Project)`   |
| Job                   | `jobs.JobManager` (`render_fn` có thể thay, SSE, huỷ), `api/render.py`, `RenderOptions`, `RenderResult`                                      | Rẽ theo `kind` trong `jobs.py` (B2)                                 |
| Lần xuất, lịch sử     | `Storage.list_renders`, `meta.json`, `delete_render`                                                                                         | PostV ghi `meta.json` cùng khoá để lưới Lịch sử dùng được           |
| Ffmpeg                | `pipeline/ffutil.py` (`run_ffmpeg`, `probe`, `media_duration`, `measure_lufs`), `cancel.py`                                                  | Dùng nguyên                                                         |
| Thư viện có giấy phép | Mẫu `library.MusicLibrary` / `MusicEntry` (`title`, `artist`, `source`, `license` bắt buộc)                                                  | Sao mẫu cho `BackgroundLibrary` (không thêm vào `library.py`)       |
| Giao diện             | `components/ui/*`, `RenderJobProvider`, `components/export/*`, `ThumbnailEditor`, `CoverDrop`, `components/audio/*`, `SideNav`, `i18n/vi.ts` | Dùng lại; chữ mới ở `vi.postv`                                      |
| Cổng nhà cung cấp     | `IMPLEMENT.md` §12: `VoiceProvider.synthesize(text, voice_id) -> bytes`                                                                      | VieNeu là một `VoiceProvider`; `ScriptProvider` mở rộng sau (Could) |

## 2. Phần mới

```
backend/hbt/postv/
  __init__.py
  models.py        PostvProject + union AnyProject (mục 3)
  parse.py         tách bài/bình luận từ chữ dán (mục 5, PV2)
  script.py        ước thời lượng, tỉ lệ biến đổi, lint nguồn + kịch bản
  backgrounds.py   BackgroundLibrary / BackgroundEntry (library/backgrounds/index.json)
  card.py          vẽ thẻ bài (Pillow) theo cấu hình mẫu
  captions.py      tách cụm 1–3 từ, vẽ trạng thái kiểu Hooked
  voice.py         VieNeuProvider, FileVoice (VoiceProvider)
  render.py        render_postv(...) → RenderResult
  publish.py       publish.txt có dòng nguồn
  templates/story_cards.json  (thẻ theo đoạn, làm trước)  ·  fixed_card.json (thẻ cố định, biến thể)
backend/hbt/api/postv.py, api/backgrounds.py
frontend/src/pages/postv/  (5 bước)   ·   frontend/src/i18n/vi.ts  (khối `postv`)
```

### 2.1 Chỗ phải sửa ngoài `postv/`

| File                                  | Sửa                                                                                                                                                                                         | Mốc     |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `backend/hbt/storage.py`              | `load_any`/`save_any` (đọc `kind` trước khi validate); `create(kind=…)`; `list_projects` thêm `kind` và bỏ qua `scenes[0]` với PostV; `save_asset` nhận PostV cho `voice`, `music`, `cover` | PV1     |
| `backend/hbt/jobs.py`                 | `submit`: gọi `render_problems()`/lint đúng loại; `_run`: chọn `render_postv` khi `kind == "postv"`                                                                                         | PV1/PV5 |
| `backend/hbt/api/projects.py`         | `POST/GET/PUT /projects` theo `kind`; `ProjectSummary.kind`                                                                                                                                 | PV1     |
| `backend/hbt/main.py`                 | Gắn router `postv`, `backgrounds`                                                                                                                                                           | PV2/PV3 |
| `.gitignore`                          | Thêm `library/backgrounds/*` (giữ `index.json` nếu muốn) — **kiểm lại cách `library/music` đang xử lý** [?]                                                                                 | PV3     |
| `frontend/src/app/App.tsx`, `SideNav` | Route `postv/:slug/*`, khối thanh trái theo loại dự án                                                                                                                                      | PV1/PV6 |
| `README.md`, `IMPLEMENT.md`           | Ghi mục PostV khi mốc đóng                                                                                                                                                                  | PV8     |

Không sửa `models.py` là có chủ ý (N1): `PostvProject` ở `postv/models.py`, dispatch ở `storage.py`. Router khác (`script`, `music`, `lint`…) gọi `Storage.load` với slug PostV sẽ nhận **400** rõ ràng ("dự án PostV, dùng màn PostV"), không 500; có test quét mọi router.

## 3. Schema `kind: "postv"`

`project.json` PostV (ví dụ rút gọn):

```json
{
  "version": 1,
  "kind": "postv",
  "slug": "bai-dem-khuya",
  "title": "…",
  "series": "",
  "source": { "url": "", "note": "", "pasted_at": "2026-10-29T08:00:00Z" },
  "post": {
    "handle": "wangxuan334",
    "age": "17h",
    "text": "…",
    "card_text": null,
    "likes": 12000,
    "replies": 340,
    "shares": 560
  },
  "comments": [
    {
      "id": "c1",
      "handle": "cozy_bear41",
      "age": "14h",
      "text": "…",
      "likes": null,
      "parent": null,
      "picked": true
    }
  ],
  "segments": [
    { "role": "hook", "card": "hook", "voice": "…", "ref": null },
    { "role": "post", "card": "post", "voice": "…", "ref": null },
    { "role": "comment", "card": "comment", "voice": "…", "ref": "c1" },
    { "role": "commentary", "card": "none", "voice": "…", "ref": null }
  ],
  "template": "story_cards",
  "style": {},
  "background": { "mode": "auto", "clip_ids": [], "seed": 1, "start_offset": null },
  "voice": { "engine": "vieneu", "voice_id": "…", "file": "voice.wav", "trim_end": null },
  "music": { "file": "…", "start": null, "credit": "" },
  "settings": {
    "fps": 60,
    "captions": true,
    "aligner": "auto",
    "outro": true,
    "card_animation": "smooth",
    "censor": { "enabled": true, "sfx": "bleep", "blur_card": true }
  },
  "publish": { "hook": "", "hashtags": [] },
  "thumbnail": { "scene": 1, "lines": ["…", "…"], "series": "", "accent": "#FFD43B", "image": null }
}
```

| Trường                            | Quy tắc                                                                                                                                                                                                                                                           |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kind`                            | Chỉ PostV mới có. Union: `AnyProject = Annotated[Union[Annotated[Project,Tag("video")], Annotated[PostvProject,Tag("postv")]], Discriminator(fn)]`, `fn` trả `"postv"` nếu `data.get("kind") == "postv"`, ngược lại `"video"` → **project cũ không cần sửa file** |
| `extra`                           | `ignore` như `_Model` hiện có (tái dùng `Theme`, `Music`, `Publish`, `Thumbnail` từ `models.py` bằng import)                                                                                                                                                      |
| `source`                          | Chỉ lưu chuỗi. `url` không được truy cập. `Xoá nguồn` đặt `post.text`, `comments[].text` rỗng, giữ `segments`                                                                                                                                                     |
| `post.card_text`                  | Chữ hiện trên thẻ (mặc định: câu đầu của `post.text`, ≤ 160 ký tự [SL]); vì thẻ chỉ có chỗ cho vài dòng (video mẫu)                                                                                                                                               |
| `post.likes`, `replies`, `shares` | Số nguyên ≥ 0, **nhập tay** (chữ dán không có số, mục 5b). Cần đủ ba số để thẻ vẽ hàng số; thiếu thì chỉ nhắc (K-26). `comments[].likes` tuỳ chọn                                                                                                                 |
| `segments`                        | 2–40 đoạn; `role` ∈ `hook`, `post`, `comment`, `commentary`. Nên có ≥ 1 `commentary`; thiếu thì chỉ nhắc (C-09, D5)                                                                                                                                               |
| `segments[].card`                 | `hook` (thẻ tiêu đề, chữ lớn, ô nhấn), `post`, `comment`, `none`; mặc định theo `role` (`commentary` → `none`). Thẻ giữ tới đoạn có thẻ khác hoặc `none`                                                                                                          |
| `segments[].voice`                | Cú pháp lời đọc như `Scene.voice` (`\|`, `{}`)                                                                                                                                                                                                                    |
| `background.clip_ids`             | Rỗng = dùng cả thư viện; có giá trị = chỉ các clip này. `seed` làm việc chọn/nối clip lặp lại được                                                                                                                                                                |
| `voice.engine`                    | `vieneu` (sinh local) hoặc `file` (đã nạp). `file` là đường dẫn trong project như `Voice.file`                                                                                                                                                                    |
| `settings.fps`                    | ∈ {30, 50, 60}; mặc định **60** (D12)                                                                                                                                                                                                                             |
| `settings.card_animation`         | `smooth` (mặc định) hoặc `bounce` (mục 6, D21)                                                                                                                                                                                                                    |
| `settings.censor`                 | `enabled` (mặc định bật), `sfx` (`bleep`), `blur_card` (làm mờ cả chữ trên thẻ, mặc định bật). Xem mục 6b                                                                                                                                                         |
| `thumbnail`                       | Dùng `Thumbnail`; `scene` bị bỏ qua (PostV không có cảnh ảnh); không có `image` thì lấy khung gameplay (D14)                                                                                                                                                      |

`PostvProject.render_problems()`: thiếu bài gốc · không đoạn nào có lời · chưa có file giọng · không có nền hoặc có clip thiếu `source`/`license`/file · `settings.fps` sai.

Thư mục: giống project cũ (`workspace/projects/<slug>/`: `project.json`, `voice.*`, `music.*`, `images/cover.*`, `build/`, `renders/`, `backups/`); **không có** ảnh cảnh.

## 4. Thư viện nền

`library/backgrounds/index.json` + file video; `BackgroundEntry`:

| Trường                               | Quy tắc                                                                                  |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| `id`, `file`                         | Như `MusicEntry` (slug, đường dẫn tương đối an toàn); đuôi `.mp4 .mov .mkv .webm`        |
| `title`, `source`, `license`         | Clip nền: bắt buộc, thiếu thì chặn xuất. Sticker: tuỳ chọn, thiếu chỉ nhắc (K-25)        |
| `url`                                | Tuỳ chọn                                                                                 |
| `width`, `height`, `fps`, `duration` | Đo bằng `ffprobe` lúc thêm; chỉ nhận video **dọc** (cao > rộng), ≥ 1080×1920 [SL] (K-10) |
| `tags`                               | Tuỳ chọn (vd `minecraft`, `parkour`)                                                     |

Thêm clip qua `POST /backgrounds` (multipart: file + metadata, ≤ 2 GB [SL]); ảnh xem nhanh khung giữa cho lưới; **không** xoá/sửa ở mốc đầu (như `/music`).

## 5. API mới

| Method + đường dẫn                                               | Nội dung                                                                             | Mã lỗi                       | Mốc |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ---------------------------- | --- |
| `POST /projects` (`kind:"postv"`)                                | Tạo dự án PostV rỗng                                                                 | 422                          | PV1 |
| `GET /projects`, `GET/PUT /projects/{slug}`                      | Thêm `kind`; PostV trả/nhận `PostvProject`                                           | 404, 422                     | PV1 |
| `POST /postv/parse` `{text}`                                     | Thuần hàm, không ghi: `{post, comments[], warnings[], guess}`                        | 422 (rỗng/quá 200 KB)        | PV2 |
| `POST /projects/{slug}/postv/script/check`                       | `{seconds, chars, commentary_ratio, issues[]}`; ước giây theo tốc độ đọc đo ở PV0    | 404, 409 (đang dựng)         | PV2 |
| `DELETE /projects/{slug}/postv/source`                           | Xoá chữ nguồn (US11)                                                                 | 409                          | PV8 |
| `GET/POST /backgrounds`, `GET /backgrounds/{id}/video`, `/thumb` | Như `/music`                                                                         | 400/413/422                  | PV3 |
| `GET /projects/{slug}/postv/card.png?segment=&w=`                | Thẻ xem trước                                                                        | 404                          | PV3 |
| `GET /projects/{slug}/postv/preview.png?t=`                      | Khung ghép thẻ + phụ đề trên khung nền tại giây `t` (xem trước tĩnh)                 | 422                          | PV6 |
| `GET /voices`                                                    | Danh sách giọng/mẫu VieNeu                                                           | 503 (chưa cài)               | PV4 |
| `POST /projects/{slug}/voice/synthesize`                         | Sinh giọng; chạy như job nếu > ~10 s [?]; trả `job_id`                               | 409, 503                     | PV4 |
| `POST /projects/{slug}/assets` (`voice`, `music`, `cover`)       | Như hiện có, cho phép PostV                                                          | theo `IMPLEMENT.md` §9       | PV1 |
| `POST /projects/{slug}/render`                                   | Giữ nguyên; rẽ theo `kind`. `preview`, `preview_seconds`, `fps`, `outro` dùng như cũ | 422 (`render_problems`), 503 | PV5 |

Quy ước lỗi, slug, SSE: như `IMPLEMENT.md` §9. Không endpoint nào nhận URL để tải.

## 5b. Định dạng chữ dán đã thấy (mẫu 1, 29/10/2026)

Mẫu thật do chủ dự án đưa: chữ copy từ trang một bài Threads (1 bài + 15 bình luận). Mẫu lưu ở `workspace/samples/threads-01.txt` (không commit). Có 2 mẫu (K-28); PV0 nên thêm mẫu có số liệu trong chữ copy nếu có.

| Đặc điểm                                                                          | Quy tắc parser (PV2)                                                                                                                                                                                                            |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Khối                                                                              | `handle` / `tuổi` / thân (1+ dòng) / (dòng trống hoặc 2 dấu cách cuối). **Khối đầu = bài gốc**; các khối sau = bình luận, **phẳng** (không dấu hiệu trả lời lồng)                                                               |
| Mốc thời gian                                                                     | Mẫu 1: tuổi (`17h`). Mẫu 2: **ngày tuyệt đối** `MM/DD/YY` (vd `08/25/26`, `25` không thể là tháng nên đọc là tháng/ngày/năm) → thẻ hiện `25/08/2026`. Parser nhận cả hai kiểu                                                   |
| Dòng nhiễu                                                                        | Mẫu 2 có dòng `1`, `/`, `2` ngay sau thân khối đầu (bộ đếm ảnh 1/2 của bài nhiều ảnh) → bỏ bộ ba dòng này. Dòng chỉ có số có thể là số liệu thật ở mẫu khác: gắn cờ cho người dùng xác nhận                                     |
| Không có bài gốc                                                                  | Mẫu 2 **bắt đầu bằng bình luận** (bài gốc là ảnh, không có chữ). Parser không tự đoán: bước 1 có công tắc "Khối này là bài gốc / bình luận" và ô nhập chữ bài gốc tay                                                           |
| Liên kết chia sẻ                                                                  | `https://www.threads.com/share/<id>/` chỉ lưu vào `source.url`; app **không truy cập** (D2/D3)                                                                                                                                  |
| Nhận khối mới                                                                     | Dòng `^[A-Za-z0-9._]{1,30}$` mà dòng kế là tuổi `^\d+\s?(s\|m\|h\|d\|w\|giây\|phút\|giờ\|ngày\|tuần)$`; thân chạy tới cặp (handle, tuổi) kế. Thân nhiều dòng giữ nguyên                                                         |
| Không có                                                                          | Số like/bình luận/chia sẻ và nhãn "Đã ghim" trong chữ dán (cả mẫu 1 và 2): **nhập tay ở bước 1**. Bài gốc phải có đủ ba số (K-26). **[?]** chưa thấy mẫu nào có số trong chữ copy                                               |
| Giữ nguyên                                                                        | Emoji, `=))`, viết tắt, dấu 2 dấu cách cuối dòng (gọt khoảng trắng thừa)                                                                                                                                                        |
| Tuổi trên thẻ                                                                     | `17h` → "17 giờ", `5d` → "5 ngày", `m` → phút, `w` → tuần (giống video mẫu "5 ngày")                                                                                                                                            |
| Mã nhúng (HTML `<blockquote class="text-post-media" data-text-post-permalink=…>`) | Mẫu 1 gồm cả đoạn này: **chỉ chứa link**, không có chữ. Parser nhận ra, lấy permalink bằng regex lưu vào `source.url` (không tải, không render HTML, không chạy `<script>`), báo "Mã nhúng không chứa chữ, hãy dán chữ của bài" |
| Không nhận ra                                                                     | Trả `guess: "unknown"` + toàn bộ chữ là một khối để sửa tay                                                                                                                                                                     |
| Bài dài                                                                           | Bình luận dài nhất trong mẫu ~450 ký tự: thẻ cắt `…`, lời đọc vẫn đủ (mục 6, hàng Thẻ)                                                                                                                                          |

## 6. Renderer `postv/render.py`

Đầu vào/ra giống `render_project` (`RenderOptions`, `RenderResult`, `progress`, `cancel_token`). Không dùng `compose` (không trượt cả khung qua Python): nền chạy liền nên dựng bằng ffmpeg [SL nhanh hơn, đo ở PV5].

| Bước | %      | Việc                                                                                                                                                                                                | Dùng lại                                         |
| ---- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| 1    | 0–3    | Kiểm tra `render_problems()`, file, giấy phép nền, quét từ nhạy cảm (từ nhạy cảm **không** chặn; chuyển sang bước che, mục 6b)                                                                      | `sensitive.py`                                   |
| 2    | 3–10   | Giọng: `voice.engine == "vieneu"` mà chưa có file → sinh (cache theo hash lời + giọng); `prep_voice` → `build/voice.wav`; `voice.trim_end` tay nếu có                                               | `audio.prep_voice`                               |
| 3    | 10–25  | Token từng segment → `run_alignment` (Whisper → khoảng lặng) → `build/timing.json`. **Không cắt đuôi quảng cáo** (VieNeu không có)                                                                  | `run_alignment`, `cache`                         |
| 3b   | 25     | **Che từ nhạy cảm:** token trùng danh sách → khoảng thời gian (mục 6b)                                                                                                                              | `sensitive.py`                                   |
| 4    | 25     | Mốc từng segment (`scene_offsets`); quyết định lúc đổi thẻ (`segments[].card`) và vị trí phụ đề                                                                                                     | `scene_offsets`, `offsets_valid`                 |
| 5    | 25–45  | **Nền:** video dọc 1080×1920 nên **không crop**; chọn clip theo `seed`, mỗi clip dùng 7,5 s hoặc 15 s (đo từ mẫu), cắt thẳng, nối đủ `total` (+ đệm); `fps=q.fps` → `build/bg.mp4` (một lần ffmpeg) | `ffutil.run_ffmpeg`                              |
| 6    | 45–50  | Thẻ: `card.py` vẽ `build/card.png` (RGBA); hiệu ứng ở bước 9                                                                                                                                        | Pillow, `fonts/`                                 |
| 7    | 50–55  | Âm thanh: `pick_music_start`, `mix_audio` (ducking; bíp đè qua tham số `sfx`), outro (`build_outro_audio`, `join_audio`)                                                                            | `audio.*`                                        |
| 8    | 55–60  | Phụ đề: tách cụm 1–3 từ, vẽ trạng thái (từ bị che thì làm mờ), `write_ffconcat`, `write_srt`                                                                                                        | `captions.Phrase`, `write_ffconcat`, `write_srt` |
| 9    | 60–98  | **Một lệnh ffmpeg:** `bg` + `card.png` (`fade in/out` alpha, cùng idiom `CARD_FADE`) + phụ đề (`ffconcat`) → thân; `xfade` 0,5 s với outro (`outro_clip_for(fps)`, ép `fps` khớp); gắn tiếng        | `ffutil`, `outro_clip_for`                       |
| 10   | 98–100 | `probe` (kích thước, fps, độ dài ±0,25 s, có tiếng), `measure_lufs` (−15…−13), bìa, `publish.txt`, `meta.json` (cùng khoá với HBT + `kind`, `background_ids`)                                       | `measure_lufs`, `render_cover`                   |

| Chủ đề                | Quy định                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Xem nhanh             | 540×960, 30 fps, tối đa 10 s đầu, không outro, dùng lại cache — như `quality_for(preview=True)`                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Bản đẹp               | 1080×1920 ở 30/50/60 fps; mã hoá như `quality_for` (`veryfast`, CRF 16, AAC 192k)                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Thẻ                   | Thẻ trắng bo góc rộng ~87–92 %, đỉnh y ≈ 12–35 % (đo từ video mẫu, PRD mục 7c). `hook`: chữ đen đậm to + ô nhấn xanh lá bo góc quanh từ nhấn. `post`/`comment`: avatar tròn trơn, tên tài khoản và thời gian đúng như bài dán (K-22), thân (tối đa ~6 dòng; dài hơn thì cắt `…`, lời đọc vẫn đủ), hàng 3 số (like, bình luận, chia sẻ; icon tự vẽ). Icon tự vẽ; không logo/giao diện nền tảng khác. Vị trí, cỡ, màu ở `story_cards.json`                                                                                   |
| Hiệu ứng thẻ          | **"Mượt" (mặc định):** vào = hiện dần 0,35 s + trượt xuống 24 px (`easeOutCubic`); đổi thẻ = hoà 0,3 s; ra = mờ 0,25 s. **"Nảy" (tuỳ chọn):** vào = phóng 0,92→1,04→1 trong 0,3 s + hiện dần; thẻ hook luôn "nảy" nhẹ. Nền không hiệu ứng (D6). Mọi thời gian ở cấu hình mẫu                                                                                                                                                                                                                                               |
| Phụ đề                | 1–3 từ mỗi lần; cơ chế karaoke của HBT (từ đang đọc đổi màu). Preset **"HBT"** (mặc định theo lời chủ dự án): vàng `#FFD43B`, Be Vietnam Pro ExtraBold. Preset **"Mẫu postv-thu-01"**: CHỮ HOA, trắng viền đen, từ đang đọc xanh lá, y ≈ 76 %. **Màu từ đang đọc** chọn bằng chip preset (vàng `#FFD43B`, xanh lá, xanh dương, đỏ) + ô màu tuỳ chỉnh (hex), lưu ở `style.caption.highlight_color`; ô nhấn của thẻ hook dùng cùng màu (K-23). Vùng an toàn TikTok y ≤ 1500. Từ đang đọc "nảy" 1→1,12→1 trong 0,12 s: Should |
| Số chạy tăng          | Số like, bình luận, chia sẻ trên thẻ đếm từ 0 tới giá trị nhập trong ~1 s đầu sau khi thẻ hiện (D20); vẽ bằng vài chục trạng thái PNG trong `ffconcat`, không tính từng khung. Tắt được ở thẻ                                                                                                                                                                                                                                                                                                                              |
| Bìa                   | `thumbnail.image` (cắt giữa) nếu có; không thì ffmpeg trích 1 khung nền tại `min(3 s, total/2)` → `render_cover(..., fit_background=True)`                                                                                                                                                                                                                                                                                                                                                                                 |
| Cache                 | Khoá có `render.PIPELINE_VERSION` + `POSTV_VERSION` (băm module `postv/`); đổi hiệu ứng thẻ không dựng lại nền                                                                                                                                                                                                                                                                                                                                                                                                             |
| Hủy                   | `cancel.use_token`; không để video dở (cùng mẫu `RenderCancelled`)                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Chỉ nhắc (không chặn) | Thời lượng ≥ 120 s (không có giới hạn dưới) · thiếu/ít commentary · trích nguyên văn quá ngưỡng · nền ngắn phải nối · Whisper rơi về khoảng lặng                                                                                                                                                                                                                                                                                                                                                                           |

## 6b. Che từ nhạy cảm (D24, K-27)

| Việc                 | Quy định                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Danh sách            | Dùng `sensitive.py` (`SensitiveStore`, `compile_words`, `find_hits`) + **nhóm mới `tuc` (chửi thề)** thêm vào `backend/hbt/data/sensitive_words.json` ở PV2 (danh sách mặc định hiện chỉ có rượu bia, máu, hoá chất, bạo lực, ma tuý, chính trị, bản đồ; mẫu 2 có nhiều từ tục không nằm trong đó). Người dùng sửa ở Cài đặt như cũ                                          |
| Phạm vi              | Mọi nhóm, **cả mức cảnh báo và chặn**; PostV không chặn xuất vì từ nhạy cảm (C-17 xác nhận phạm vi)                                                                                                                                                                                                                                                                          |
| Tìm khoảng thời gian | Khớp chuỗi từ trên chữ đọc đã chuẩn hoá (cả `{…}`), ánh xạ về token rồi lấy `times[i]` từ bước 3; từ nhiều chữ lấy từ đầu token đầu tới cuối token cuối; nới 0,06 s mỗi bên (aligner khoảng lặng kém chính xác hơn Whisper)                                                                                                                                                  |
| Âm thanh             | Tắt tiếng giọng trong khoảng đó (`volume=enable='between(t,a,b)':volume=0`) trên bản sao `build/voice_censored.wav`; **bíp 1 kHz** tổng hợp bằng ffmpeg (cùng cách `synth_whoosh`/`synth_ting`), đúng độ dài khoảng, fade 5 ms, đưa vào `mix_audio(..., sfx)`; mức ~0,35 trước `loudnorm` (chỉnh bằng tai ở PV5). Căn chữ và phụ đề dùng bản **chưa che** nên mốc không lệch |
| Phụ đề               | Vẽ chữ rồi `GaussianBlur` (bán kính ~12 px ở cỡ 70) trên vùng chữ của từ đó; `captions.srt` ghi `***` thay từ                                                                                                                                                                                                                                                                |
| Thẻ                  | `blur_card`: làm mờ đúng từ trên chữ bài/bình luận (vẽ từ ra lớp riêng, làm mờ, dán lại)                                                                                                                                                                                                                                                                                     |
| Không che            | Nút tắt `settings.censor.enabled`; `publish.txt`, tên bài, hook vẫn quét và **nhắc** (không che được chữ đăng)                                                                                                                                                                                                                                                               |
| Test                 | Khớp từ đơn/nhiều chữ/có dấu; ánh xạ token; khoảng thời gian và tắt tiếng đúng (đo RMS trong khoảng = 0); số cụm bíp; phụ đề mờ (vùng chữ khác nền); công tắc tắt thì không đổi                                                                                                                                                                                              |

## 7. Giao diện 5 bước

Theo `DESIGN-HBT.md` v2 và `IMPLEMENT.md` 13.B2/13.B3: thanh trái cố định (khối dự án đang mở có 5 mục), thanh đầu cao 48 ("Đã lưu"), cột xem trước 9:16 288×512 bên phải, nút chính lớn cố định, mọi thành phần đủ thường/hover/nhấn/focus/tắt, sáng/tối, Be Vietnam Pro, chữ ở `vi.postv`, không logo hay tên nền tảng khác; 1024–1279 thu thanh trái, < 1024 xem trước thành ngăn kéo.

| Bước | Route                  | Nội dung                                                                                                                                                                                                                                           | API                                                       | Nút chính           |
| ---- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------- |
| 1    | `/postv/:slug`         | **Nhập nguồn:** ô dán lớn (thả `.txt/.md`), ô link (chỉ lưu, nút "Mở bài" mở tab mới `rel=noopener noreferrer`), kết quả tách (bài + bình luận, sửa/xoá/gộp/tách tay, 3 ô số bài gốc: like, bình luận, chia sẻ), cảnh báo lint nguồn               | `POST /postv/parse`, `PUT /projects/{slug}`               | Tách bài → Tiếp     |
| 2    | `/postv/:slug/pick`    | **Chọn đoạn:** tích bài + bình luận, kéo đổi thứ tự, chip "Gợi ý theo like", thanh ước lượng giây và tỉ lệ biến đổi                                                                                                                                | `PUT`, `POST …/script/check`                              | Tiếp                |
| 3    | `/postv/:slug/script`  | **Kịch bản và giọng:** mỗi đoạn một ô lời đọc (chip `\|`, `{ }`; đoạn `commentary` đánh dấu; thiếu chỉ nhắc), thẻ Giọng (chip VieNeu / Nhập file, chọn giọng, Sinh giọng, trình phát, `trim_end`), thẻ Nhạc (như tab Âm thanh)                     | `/voices`, `…/voice/synthesize`, `/assets`, `/music`      | Sinh giọng / Tiếp   |
| 4    | `/postv/:slug/preview` | **Xem trước và dựng:** lưới nền (chip lọc, chọn nhiều, "Tự chọn"), thẻ (tên tài khoản, hiệu ứng, số like), chọn màu phụ đề, kiểu phụ đề, xem trước tĩnh 9:16, nút **Xem nhanh**                                                                    | `/backgrounds`, `…/card.png`, `…/preview.png`, `…/render` | Xem nhanh           |
| 5    | `/postv/:slug/export`  | **Xuất:** chip fps 30/50/60, công tắc outro, Kiểm tra (lint, giấy phép nền, commentary), **Xuất bản đẹp**, kết quả, Nội dung đăng (có dòng nguồn + Sao chép), Ảnh bìa (chip "Khung gameplay" / ảnh tải lên), Lịch sử, **Tải video.mp4**, Xoá nguồn | `…/render`, `/renders`, `/assets`, `DELETE …/source`      | Xuất bản đẹp (vàng) |

Ba điểm duyệt: nguồn (bước 1–2) → kịch bản (bước 3) → video (bước 5). Nút Xuất bản đẹp sáng khi hết lỗi chặn.

## 8. Mốc PV0…PV8

Nhánh `feat/pvN-…`; mỗi mốc theo 6 bước đóng mốc của `CLAUDE.md`. Gợi ý tag: `v1.2.0` (PV1), `v1.3.0` (PV2)… Mỗi commit: `npm run lint` + test liên quan; cuối đợt `npm run lint && npm run test`.

| Mốc     | Việc                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Test                                                                                                                                                                                                                        | Xong khi                                                                                                    | Buổi (~3 giờ) | Máy                                          | Chặn bởi            |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------- | -------------------------------------------- | ------------------- |
| **PV0** | **Kiểm điều chưa biết (không mã sản phẩm).** (a) 3–5 mẫu copy bài + bình luận từ Threads, chủ dự án đưa vào `docs/postv/samples/` (đã che tên) · (b) VieNeu: thử trong `backend/.venv`, đo tốc độ CPU fp32/int8, chất lượng tiếng Việt, đọc `{}`, **giấy phép trọng số** · (c) Whisper `small` CPU trên giọng VieNeu: tỉ lệ khớp · (d) tốc độ đọc ký tự/giây → ngưỡng 120 s · (e) outro 30 fps từ clip 50 · (f) video nền của chủ dự án: hướng, độ phân giải, codec, fps; crop thử · (g) đo ffmpeg một lệnh nền + thẻ + phụ đề 60 s | Không có test mã; mã thử để ở `workspace/` (không commit)                                                                                                                                                                   | Số đo ghi vào `06-cau-hoi-mo.md`; M1–M7 (06 mục 3) có số đo; đã có 2 mẫu (K-28); chủ dự án duyệt            | 1             | Máy cũ (CPU). CUDA sau, máy mới, không chặn  | Mẫu của chủ dự án   |
| **PV1** | `postv/models.py` (`PostvProject`, union); `storage.load_any/save_any/create(kind)`; `list_projects` có `kind`; `api/projects.py`; hộp Video mới chọn loại; route `/postv/:slug` trống; nhãn "PostV" trong lưới Dự án                                                                                                                                                                                                                                                                                                               | Round-trip PostV; project cũ nạp/ghi không đổi; dispatch union; mọi router với slug PostV trả 4xx không 500; slug; `PIPELINE_VERSION` giữ; `git diff v1.1.0 -- backend/hbt/pipeline/ reference/ backend/hbt/models.py` rỗng | Tạo dự án PostV rỗng trên UI, thấy ở lưới, mở được; "muỗi" vẫn mở; lint + test xanh                         | 1,5           | Máy cũ                                       | —                   |
| **PV2** | `postv/parse.py`; `POST /postv/parse`; `postv/script.py` (ước giây, tỉ lệ biến đổi, lint nguồn); UI bước 1–2; `…/script/check`; nhóm `tuc` (chửi thề) thêm vào danh sách từ nhạy cảm; ô nhập like/bình luận/chia sẻ                                                                                                                                                                                                                                                                                                                 | Parser theo từng mẫu thật (golden JSON); lệch/rỗng/quá lớn; **test chặn socket** (không request ra ngoài); lint nguồn; Vitest bước 1–2                                                                                      | Dán mẫu thật → bài + bình luận đúng, sửa tay được, chọn đoạn, thấy ước giây; không có request ra ngoài      | 2,5           | Máy cũ                                       | PV0 (mẫu)           |
| **PV3** | `postv/backgrounds.py` + `api/backgrounds.py`; `postv/card.py` + `templates/story_cards.json` (thẻ hook, bài, bình luận); `card.png`; `.gitignore`; UI chọn nền và thẻ (bước 4 một phần)                                                                                                                                                                                                                                                                                                                                            | Entry thiếu nguồn/giấy phép bị chặn; ffprobe sai → 400; dấu tiếng Việt vẽ đúng (không ô vuông); tràn dòng; thẻ không chứa tên/avatar; API thư viện                                                                          | Thêm clip có giấy phép, xem thẻ ẩn danh đúng dấu trên khung nền; clip thiếu giấy phép bị chặn               | 2             | Máy cũ                                       | K-10                |
| **PV4** | `postv/voice.py` (`VieNeuProvider` qua `VoiceProvider`, `FileVoice`); `GET /voices`; `…/voice/synthesize`; cache giọng; UI bước 3 (giọng, nhạc)                                                                                                                                                                                                                                                                                                                                                                                     | Provider giả cho CI; hash cache; 503 khi chưa cài; test thật VieNeu đánh dấu `slow`, không chạy trong CI; nhập file vẫn dùng được                                                                                           | Sinh giọng cho 1 kịch bản mẫu trên máy cũ bằng CPU, nghe được trong app; không có VieNeu thì nhập file      | 2             | Máy cũ. Nhánh CUDA/VRAM: máy mới (phụ)       | PV0 (C-03, C-04)    |
| **PV5** | `postv/render.py`, `captions.py`, `publish.py`; `jobs.py` rẽ `kind`; nền nối clip; thẻ theo đoạn (hook, bài, bình luận, không thẻ) với hiệu ứng "Mượt"/"Nảy" và số chạy tăng; phụ đề Hooked; outro; bìa; `meta.json`; **che từ nhạy cảm** (bíp đè + làm mờ, mục 6b)                                                                                                                                                                                                                                                                 | Chọn/nối nền theo `seed`; tách cụm 1–3 từ; chuỗi filter; Xem nhanh 10 s; bản đẹp ngắn (`slow`); **framemd5 "muỗi" giống `v1.1.0`**; huỷ job; `render_problems` PostV                                                        | Dựng được video PostV mẫu 50 fps (và 30/60) có nhạc, outro, bìa, `publish.txt` có nguồn; ghi thời gian dựng | 3             | Máy cũ (đo thời gian trên cả hai máy nếu có) | PV2, PV3, PV4, C-08 |
| **PV6** | UI bước 4–5 hoàn chỉnh: Xem nhanh, preview tĩnh, Xuất, Lịch sử, Ảnh bìa (khung gameplay), nội dung đăng; thanh trái theo loại; e2e                                                                                                                                                                                                                                                                                                                                                                                                  | Vitest từng bước; e2e Playwright: dán → chọn → kịch bản (giọng nhập file) → Xem nhanh → Xuất; sáng/tối; Tab/focus                                                                                                           | Làm trọn 1 video PostV bằng giao diện, không terminal; chủ dự án duyệt từng màn                             | 2             | Máy cũ                                       | PV5                 |
| **PV7** | _(Could)_ Bình luận trả lời lồng nhau (đường kẻ dọc), sticker từ nguồn miễn phí không cần ghi công (K-25), biến thể "Thẻ cố định" (`fixed_card.json`)                                                                                                                                                                                                                                                                                                                                                                               | Layout thẻ lồng; sticker thiếu giấy phép bị chặn; mốc đổi thẻ theo `scene_offsets`                                                                                                                                          | Dựng được video mẫu B                                                                                       | 2,5           | Máy cũ                                       | PV6, C-14           |
| **PV8** | Hoàn thiện: tỉ lệ biến đổi + cảnh báo nguyên văn, `Xoá nguồn`, README + `IMPLEMENT.md`/`PLAN.md` ghi PostV, dọn nợ                                                                                                                                                                                                                                                                                                                                                                                                                  | Test `Xoá nguồn` giữ kịch bản; cảnh báo nguyên văn; e2e đầy đủ                                                                                                                                                              | 6 bước đóng mốc; `git diff` không đụng `pipeline/`, `models.py`, `reference/`                               | 1,5           | Máy cũ                                       | PV6                 |

Tổng ước lượng (chưa tính đợt fix/cover-drop đã hoãn): **15,5 buổi** cho PV0–PV6 + PV8 (Must/Should), **18 buổi** nếu làm cả PV7. Brief ước 10–12 buổi cho PV0–PV5 với Vbee; phần tăng là VieNeu (PV4), giao diện 5 bước (PV6), mẫu hiệu chỉnh (PV8) [SL].

## 9. Test chung

| Loại          | Ca                                                                                                                                                                   |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pytest        | Union schema · parser theo mẫu · ước giây · thư viện nền · thẻ · tách cụm phụ đề · chọn/nối nền · rẽ `kind` ở `jobs.py` · mọi router với slug PostV (4xx, không 500) |
| pytest `slow` | Dựng thật ngắn; framemd5 "muỗi" so `v1.1.0`; VieNeu thật (chạy tay trên máy)                                                                                         |
| Mạng          | Fixture chặn `socket` trong test PostV: không có kết nối ra ngoài                                                                                                    |
| Vitest        | Từng bước; chữ ở `vi.postv`; trạng thái nút chính                                                                                                                    |
| e2e           | Luồng PostV đầy đủ với giọng nhập file (không cần VieNeu)                                                                                                            |
| Thủ công      | Chủ dự án xem từng màn; xem video: chữ đúng dấu, nhịp thẻ, phụ đề không lệch                                                                                         |

## 10. Rủi ro

| #   | Rủi ro                                                                                                     | Mức  | Cách giảm                                                                                                             |
| --- | ---------------------------------------------------------------------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------- |
| R1  | Giấy phép trọng số VieNeu-TTS **[?]**                                                                      | Thấp | Chủ dự án: miễn phí, bỏ qua; PV0 chép nguyên văn giấy phép vào docs; `FileVoice` vẫn chạy; không đưa trọng số vào Git |
| R2  | VieNeu trên CPU chậm hoặc cần VNNI (máy cũ **[SL]** nên fp32) **[?]**                                      | Vừa  | Đo ở PV0; sinh giọng chạy như job; dự phòng nhập file                                                                 |
| R3  | Whisper lệch trên giọng VieNeu                                                                             | Vừa  | Rơi về khoảng lặng như HBT; đo tỉ lệ khớp ở PV0                                                                       |
| R4  | ~~Nền ngang 16:9 phải cắt/phóng~~ **đã hết**: nền dọc 1080×1920 (K-10)                                     | —    | Chỉ nhận video dọc; từ chối video ngang ở `POST /backgrounds`                                                         |
| R5  | ~~Nguồn 60 fps xuất 50 fps giật~~ **đã hết**: mặc định 60 fps (K-11); 50/30 fps chọn được, có thể giật nhẹ | Thấp | Ghi chú ở chip fps                                                                                                    |
| R6  | Outro 30 fps từ clip 50 (`fps=30` lệch nhịp) như đã gặp với 60 fps                                         | Thấp | PV0 đo; nếu xấu dựng `outro_4s_30fps.mp4` bằng `outro_reference.py` (không sửa `reference/`), cần duyệt asset         |
| R7  | Định dạng chữ khi copy Threads chưa biết **[?]**                                                           | Vừa  | Parser heuristic + sửa tay; PV0 lấy mẫu; PV2 không bắt đầu khi chưa có mẫu                                            |
| R8  | Router cũ gặp slug PostV                                                                                   | Vừa  | `Storage.load` trả 400 rõ; test quét router (PV1)                                                                     |
| R9  | Dung lượng thư viện nền (video 1080p60) làm repo phình                                                     | Vừa  | `.gitignore` ở PV3; chỉ commit `index.json` nếu cần                                                                   |
| R10 | Nội dung tái sử dụng, đời tư người thường                                                                  | Cao  | Nhắc commentary/tỉ lệ biến đổi, che từ nhạy cảm (bíp + mờ), Xoá nguồn                                                 |
| R11 | Đổi `render.py` sau này làm nguội cache PostV (khoá có `PIPELINE_VERSION`)                                 | Thấp | Chấp nhận (chỉ dựng lại một lần)                                                                                      |
| R12 | Synth + render cùng lúc làm quá tải máy                                                                    | Thấp | Một luồng job (N5)                                                                                                    |
| R13 | Nối nhiều clip nền cắt thẳng nhìn giật                                                                     | Thấp | Mẫu của chủ dự án cũng cắt thẳng (7,5/15 s) → chấp nhận (K-17)                                                        |
| R14 | Điều khoản Threads gốc chưa đọc **[?]**                                                                    | Vừa  | Chủ dự án đọc `help.instagram.com/769983657850414`                                                                    |
