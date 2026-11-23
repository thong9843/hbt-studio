# HBT STUDIO — ĐẶC TẢ SMART ASSET DIRECTOR & LỘ TRÌNH NÂNG CẤP TỐI ƯU CPU

> **Mốc nền tảng:** `main` @ `a7ed925` (4 động cơ chuẩn 60fps: HBT Core, PostV, Chatting, StickV · Ponytail `full` · 6 nhánh Git cố định).
> **Phần cứng ưu tiên:** Máy local Windows chạy CPU (`i5-10400`, 16 GB RAM, không GPU rời). Giữ nguyên `FFMPEG_RESOURCE_CLAMP` (`-threads 2 -filter_threads 2`).

---

## 0. BẤT BIẾN HỆ THỐNG & QUY TẮC GIT

1. **Lộ trình 3 đợt đã chốt (ưu tiên tối đa máy CPU):**
   - **Đợt 1 (Ưu tiên #1 — Làm ngay):** `Smart Asset Director` — Tự tìm và tự tải tài nguyên online theo keyword, chống trùng lặp xuyên video, khóa nhịp chống spam meme/SFX.
     - **Đợt 1A (`GD3-Chatting`):** Xây lõi `backend/hbt/shared/asset_director/` và nối dứt điểm vào **Chatting**.
     - **Đợt 1B (`GD2-PostV`, `GD1-HBT`, `GD4-StickV`):** Nối tiếp cùng lõi `asset_director` vào 3 động cơ còn lại.
   - **Đợt 2 (Làm sau Đợt 1):** `Editorial Cinema` bản tối ưu CPU (`Preflight Quality Gate` + `Beat-Level Hash Cache` + `Audio Director`).
   - **Đợt 3 (Làm cuối cùng):** `Publish Kit` (`publish.txt` SEO A/B + câu bình luận ghim mồi) + 3 mẫu ảnh bìa High-CTR (Clickbait sạch: Khoanh đỏ/Che mờ, Chia đôi đối lập, Tin nhắn che từ chốt).
   - **Hoãn / Bỏ:** Tạm hoãn đồng bộ máy GPU mới; bỏ hoàn toàn Động cơ 5, Batch Factory và Lên lịch đăng tự động.

2. **Quy tắc vùng cấm & Ngoại lệ cho Đợt 1A:**
   - **Ngoại lệ có duyệt trên nhánh `GD3-Chatting`:** ĐƯỢC PHÉP chỉnh sửa `backend/hbt/chatting/` để xử lý triệt để lỗi spam meme và nối `Smart Asset Director`.
   - **5 vùng cấm khóa tuyệt đối:** `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`.
   - **Bảo toàn dữ liệu & lịch sử:** Không xóa hay ghi đè dữ liệu cũ trong `library/` (chỉ thêm file mới khi auto-fetch), giữ nguyên `workspace/`, `assets/`, `brand/`, `.env`, 2 stash cũ và **không dời 4 tag lịch sử `v1`, `v2`, `v3`, `v4`**.

3. **Kiểm thử cuối đợt (chạy duy nhất 1 lần qua Git Bash):**
   `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`
   _(Không chạy slow tests / Playwright e2e; chủ dự án nghiệm thu trực tiếp trên giao diện)._

---

## 1. KIẾN TRÚC LÕI DÙNG CHUNG — `backend/hbt/shared/asset_director/`

Tái sử dụng trực tiếp các cổng API miễn phí đã có trong `backend/hbt/shared/online_sources/` (kiểm tra đúng tên hàm thực tế trên đĩa trước khi gọi):

- `stickers_online.py` — **Giphy Stickers** (ưu tiên #1 cho reaction/sticker vì phản hồi nhanh)
- `greenmeme.py` — **GreenScreenMemes** (dùng cho meme phông xanh `.mp4` tại cao trào mạnh)
- `tuna_sfx.py` — **Voicemod Tuna** (ưu tiên #1 cho SFX meme, chuẩn hóa `-16 LUFS`)
- `pixabay_audio.py` & nguồn **Freesound** (`FREESOUND_API_KEY`, đã thay Jamendo) — dùng cho nhạc nền BGM và dự phòng SFX
- `meme_tagging.py` — chuẩn hóa `tags`, `topic`, `duration_sec` khi ghi vào `index.json`

### 1.1. Cấu trúc module

```text
backend/hbt/shared/asset_director/
|-- __init__.py       # Export AssetDirector, PacingPolicy, DirectorConfig, direct_chat_assets
|-- models.py         # Pydantic/dataclass: BeatCue, PacingPolicy, AssetCandidate, ResolvedAsset, DirectorReport
|-- pacing.py         # Lớp 2: Pacing Governor (khóa cứng mật độ, khoảng nghỉ, ưu tiên cao trào)
|-- freshness.py      # Bộ nhớ độ mới & chống trùng lặp (workspace/asset_usage.json)
|-- resolver.py       # Luồng Local -> Auto-Fetch Online -> Tải vào library/ -> Hậu xử lý & ghi index.json
`-- director.py       # Facade điều phối tổng (direct_assets + reroll_asset cho nút "Đổi cái khác")
```

### 1.2. Lớp 1 — Chấm điểm ngữ cảnh từ AI (Prompt Contract)

Thay vì để Gemini rải `sticker_tag` / `meme` tự do sau mỗi câu thoại, mọi động cơ dùng `AssetDirector` áp cùng chuẩn tín hiệu cho từng câu/beat:

- `beat_role`: `"setup" | "build" | "twist" | "punchline" | "reaction"`
- `intensity`: số nguyên từ `1` đến `5`:
  - `1 - 2`: dẫn chuyện / hỏi đáp bình thường
  - `3`: có nhấn nhẹ nhưng chưa đủ để chèn meme
  - `4`: cao trào / bẻ lái rõ ràng
  - `5`: đỉnh điểm hài hước / sốc / cú chốt punchline
- `meme_query`: chuỗi từ khóa tiếng Anh ngắn `2 - 4` từ (vd: `"cat shocked"`, `"side eye"`, `"facepalm"`, `"mind blown"`) — **chỉ được điền khi `intensity >= 4` và `beat_role` thuộc `{"twist", "punchline", "reaction"}`**, còn lại bắt buộc `null`.
- `sfx_query`: chuỗi từ khóa tiếng Anh ngắn `1 - 3` từ (vd: `"vine boom"`, `"bruh"`, `"bonk"`, `"dramatic sting"`) — chỉ điền tại điểm nhấn thật sự (`intensity >= 4`), còn lại `null`.
- `music_mood`: tâm trạng nhạc nền tổng thể của video (`"vui_nhon" | "kich_tinh" | "bi_an" | "thu_gian" | "hanh_dong"`).

### 1.3. Lớp 2 — Bộ Điều Tiết Nhịp Cứng (`pacing.py` — Pacing Governor)

Ngay cả khi LLM trả về thừa `meme_query` / `sticker_tag` / `sfx_query`, `PacingGovernor` hậu kiểm bằng luật cứng Python không thể vượt rào:

| Tham số khóa (`PacingPolicy`)   | Cấu hình chuẩn cho `chatting`                                                                   | Chuẩn bị sẵn cho `postv` / `stickv` / `core` (Đợt 1B) |
| :------------------------------ | :---------------------------------------------------------------------------------------------- | :---------------------------------------------------- |
| `max_visual_memes`              | **Tối đa `2 - 3` / video** (trần cứng `min(3, max(1, floor(total_msgs * 0.18)))`)               | PostV: tối đa 3 · Core/StickV: tối đa 2               |
| `min_gap_beats`                 | **Tối thiểu `4` tin nhắn** giữa 2 meme/sticker                                                  | Tối thiểu `3` cảnh/đoạn                               |
| `min_gap_seconds`               | **Tối thiểu `8.0s`** giữa 2 meme/sticker                                                        | Tối thiểu `8.0s`                                      |
| `forbid_consecutive`            | **`True`** (cấm tuyệt đối 2 câu liền kề cùng có meme)                                           | `True`                                                |
| `skip_opening_setup`            | **`True`** (bỏ qua tin nhắn index `0` nếu `beat_role == "setup"`)                               | `True`                                                |
| `max_punch_sfx`                 | **Tối đa `2 - 4` điểm nhấn / video**, giãn cách `>= 6.5s` _(không tính tiếng UI `pop`/gõ phím)_ | Tối đa `4` / video, giãn cách `>= 6.0s`               |
| `video_meme_duration_range`     | **`1.2s - 3.8s`** (đọc duration thực tế, cắt gọn nếu file gốc dài hơn)                          | `1.2s - 3.8s`                                         |
| `static_sticker_duration_range` | **`0.9s - 1.6s`** (theo `intensity`: mức 4 là `1.1s`, mức 5 là `1.5s`)                          | `0.9s - 1.6s`                                         |

**Thuật toán chọn điểm rơi đắt giá nhất (`select_beats`):**

1. Lọc ứng viên hợp lệ: có tín hiệu (`meme_query` hoặc `sticker_tag` legacy) AND `intensity >= 4`. Nếu toàn video không có câu nào đạt mức `4`, cho phép hạ 1 bậc xuống đúng 1 câu có `intensity == 3` cao nhất thuộc nhóm `punchline` / `twist` để tránh video bị khô.
2. Xếp hạng ứng viên theo khóa giảm dần: `(intensity, role_weight, position_spread_bonus)`, trong đó `role_weight`: `punchline=5, twist=4, reaction=4, build=2, setup=1`.
3. Duyệt tham lam (greedy) từ ứng viên điểm cao nhất: chỉ giữ nếu thỏa `abs(idx - kept_idx) >= min_gap_beats` và `abs(est_t - kept_t) >= min_gap_seconds` cho tới khi đủ `max_visual_memes`.
4. Toàn bộ các beat không được chọn bị xóa sạch `meme_id` / `sticker_tag` / `meme_query`. Thực hiện quy trình lọc độc lập cho `sfx_query` theo bộ luật `punch_sfx`.

### 1.4. Lớp 3 — Bộ Nhớ Chống Lặp (`freshness.py`) & Tự Tải Thông Minh (`resolver.py`)

#### A. Bộ nhớ độ mới (`workspace/asset_usage.json`)

Lưu lịch sử gọn nhẹ theo định dạng JSON (ghi nguyên tử qua file `.tmp` + `os.replace`, có lock an toàn):

```json
{
  "version": 1,
  "video_seq": 42,
  "assets": {
    "memes:shocked-cat-a1b2": {
      "category": "memes",
      "source": "giphy",
      "source_id": "abc123",
      "last_video_seq": 40,
      "last_used_at": "2026-11-23T02:30:00Z",
      "use_count": 2
    }
  }
}
```

- **Quy tắc chấm điểm & chống lặp:**
  - **Cùng 1 video:** Cấm lặp tuyệt đối (`used_in_current_video` -> loại ngay).
  - **Cooldown `6` video gần nhất (`cooldown_videos = 6`):** Nếu `age = current_seq - last_video_seq < 6`, trừ điểm nặng `penalty = 0.65 * (1 - age / 6)`.
  - **Xoay vòng kho đều:** Trừ thêm điểm nhẹ `min(0.20, use_count * 0.03)` để ưu tiên các file mới tải hoặc ít được dùng.

#### B. Luồng `Local-First -> Smart Auto-Fetch` (`resolver.py`)

Với mỗi từ khóa đã vượt qua `PacingGovernor`:

1. **Quét kho local (`library/{memes,stickers,sfx,music}/index.json`):**
   - Chuẩn hóa từ khóa + ánh xạ đồng nghĩa Việt-Anh cơ bản (vd: `sốc/bất ngờ` <-> `shock/surprised`, `cà khịa/khinh` <-> `side eye/smug`, `bó tay` <-> `facepalm`, `cười` <-> `laugh`).
   - Tính `final_score = keyword_match_score(0..1) - cooldown_penalty - use_decay`.
2. **Quyết định có tải Online hay không:**
   - Dùng ngay file local tốt nhất nếu `final_score >= 0.55` và **không** nằm trong vòng cooldown 6 video gần nhất.
   - Nếu không có file local đạt chuẩn (hoặc toàn bộ file khớp đều vừa dùng gần đây) VÀ `auto_fetch_online=True` VÀ chưa chạm trần tải trong phiên:
     - **Meme / Sticker hình ảnh:** Ưu tiên `Giphy Stickers` (`stickers_online.py`) cho reaction nhanh; gọi `GreenScreenMemes` (`greenmeme.py`) khi `beat_role == "punchline"` hoặc `intensity == 5` cần clip meme phông xanh nổi bật.
     - **SFX:** Ưu tiên `Voicemod Tuna` (`tuna_sfx.py`), fallback `Pixabay SFX` / `Freesound`.
     - **BGM:** Gọi `Freesound` hoặc `Pixabay Music` (lọc thời lượng `>= 50s`, ưu tiên không lời).
   - **Khử trùng lặp khi tải về:** Kiểm tra `source_id` / URL đã tồn tại trong `index.json` chưa; nếu trùng thì lấy ứng viên kế tiếp trong top 6 kết quả trả về.
   - **Lưu vĩnh viễn vào `library/`:** Tải thẳng file vào `library/{stickers|memes|sfx|music}/`, chạy hậu xử lý chuẩn (tạo `.jpg` thumbnail cho meme, chuẩn hóa `-16 LUFS` bằng FFmpeg kèm `FFMPEG_RESOURCE_CLAMP` cho SFX, đo `duration_sec` bằng `ffprobe`), tự ghi `tags`, `topic`, `source`, `source_id` vào `index.json` và ghi nhận vào `workspace/asset_usage.json`.
3. **Bảo vệ CPU & Mạng (Fail-Safe tuyệt đối):**
   - Timeout cứng **`4.5s`** cho mỗi lượt gọi tìm kiếm, **`10.0s`** cho lượt tải file; tái dùng In-Memory TTL Cache 10 phút.
   - **Trần tải mỗi lần tạo kịch bản:** Tối đa **`3` meme/sticker**, **`3` SFX**, **`1` BGM mới** — tổng thời gian phát sinh chỉ vài giây, không làm treo máy CPU.
   - Nếu rớt mạng, API timeout hoặc chưa cấu hình API key: ghi log warning gọn và **rơi êm về file local ít dùng nhất**, tuyệt đối không bao giờ làm fail job tạo kịch bản hay render.

#### C. Hàm đổi nhanh 1 chạm (`reroll_asset`)

- Nhận `(category, query, exclude_ids, auto_fetch_online)` -> trả về 1 phương án khác khớp từ khóa nhưng loại trừ toàn bộ `exclude_ids` (file hiện tại + các file đã dùng trong cùng video), tự động tìm/tải thêm online nếu kho local đã cạn ứng viên mới.

---

## 2. TÍCH HỢP ĐỢT 1A — CHATTING (`GD3-Chatting`)

### 2.1. Backend (`backend/hbt/chatting/` & `backend/hbt/api/chatting.py`)

1. **`prompt.py`:**
   - Viết lại quy tắc chọn meme/SFX: nhấn mạnh **ít mà chất**, yêu cầu Gemini chấm `beat_role` và `intensity` (1..5) cho từng tin nhắn; chỉ gợi ý `meme_query` / `sfx_query` tiếng Anh ngắn gọn tại 2-3 đỉnh cao trào cảm xúc thật sự; **cấm rải sticker ở mọi câu**.
2. **`models.py`:**
   - Bổ sung các trường tùy chọn có giá trị mặc định an toàn (tương thích ngược 100% với toàn bộ `chat.json` cũ):
     - Trên `ChatMessage`: `beat_role: str | None = None`, `intensity: int = 2`, `meme_query: str | None = None`, `sfx_query: str | None = None`, `sfx_id: str | None = None`, `asset_origin: Literal["local", "online_fetched"] | None = None`.
     - Trên `ChatSettings` / request payload: `auto_fetch_online: bool = True`.
3. **`llm.py`:**
   - Thay thế logic rải sticker hoặc chọn meme dày đặc cũ bằng `AssetDirector.direct_chat_doc(doc, auto_fetch_online=...)`.
   - Trả kèm `director_summary` gọn (`memes_kept`, `memes_stripped`, `sfx_kept`, `fetched_online_count`) để hiển thị minh bạch.
4. **`timeline.py` & `render.py`:**
   - Giữ thời lượng linh hoạt: video/GIF meme cắt gọn trong `1.2s - 3.8s` theo thời lượng thực tế; sticker tĩnh `0.9s - 1.6s`.
   - Nếu tin nhắn có `sfx_id`, trộn thêm lớp âm thanh SFX tại đúng thời điểm tin nhắn bật lên (`-16 LUFS`, không át giọng VieNeu-TTS, giữ tổng âm lượng chuẩn `-14 LUFS`).
5. **`api/chatting.py`:**
   - Truyền `auto_fetch_online` qua cả endpoint tạo kịch bản lẻ lẫn luồng `POST /api/chatting/auto`.
   - Thêm endpoint **`POST /api/chatting/{slug}/messages/{msg_id}/reroll-asset`**: nhận `{kind: "meme" | "sticker" | "sfx", auto_fetch_online?: bool}`, đổi sang 1 tài nguyên mới không trùng, lưu `chat.json` và trả về tin nhắn đã cập nhật.

### 2.2. Frontend (`frontend/src/pages/chatting/`, `i18n/vi.ts`)

- Giữ giao diện tối giản chuẩn Studio Craft, **không thêm rác UI**:
  - Trên thanh tùy chọn tạo kịch bản Chatting: thêm 1 công tắc gọn **"Tự tải tài nguyên online"** (mặc định Bật).
  - Trong `ChattingEditor.tsx`: chỉ tại các tin nhắn có gắn meme/sticker hoặc SFX, hiện gọn 1 thẻ tên/ảnh nhỏ + badge `Mới tải` (nếu vừa tải online) + nút 1 chạm **"Đổi cái khác"** gọi endpoint `reroll-asset` và nút **"Bỏ"** (`x`) để gỡ nhanh.
  - Toàn bộ nhãn tiếng Việt khai báo trong `frontend/src/i18n/vi.ts`.

---

## 3. PHẠM VI DỰ KIẾN CÁC ĐỢT TIẾP THEO (CHƯA CODE TRONG ĐỢT 1A)

- **Đợt 1B:** Nối `AssetDirector` vào `PostV` (`GD2-PostV`), `StickV` (`GD4-StickV`) và `HBT Core` (`GD1-HBT`) để đồng bộ hóa tự tải BGM/SFX/Meme cho toàn bộ 4 động cơ.
- **Đợt 2 — Editorial Cinema (Tối ưu CPU):**
  1. _Preflight Quality Gate:_ Tự rà lỗi tràn khung chữ / vi phạm Safe-Zone / lặp thoại trước khi tốn CPU render.
  2. _Beat-Level Hash Cache:_ Băm từng phân cảnh/tin nhắn; sửa 1 đoạn chỉ dựng lại đúng đoạn đó rồi `concat -c copy`.
  3. _Audio Director:_ Siết khoảng lặng thừa, ngắt nhạc nền `0.32s` trước cú twist, J/L-cut `0.18s`.
- **Đợt 3 — Publish Kit & 3 Mẫu Bìa High-CTR (Clickbait sạch):**
  - Tự sinh gói xuất bản dùng chung cho 4 động cơ (`3` tiêu đề A/B, mô tả ngắn, hashtag theo nền tảng, `1` câu bình luận ghim mồi).
  - Tự vẽ bìa bằng Pillow theo 3 mẫu sạch (có thật trong video): _Khoanh đỏ & Che mờ_ (Core/StickV), _Chia đôi đối lập_ (Core/StickV), _Tin nhắn/Bình luận che từ chốt_ (Chatting/PostV).

---

## 4. TIÊU CHÍ KIỂM THỬ & NGHIỆM THU ĐỢT 1A

### 4.1. Kiểm thử tự động

- **`backend/tests/test_asset_director.py`:**
  - Test `PacingGovernor`: kịch bản 15 tin nhắn mà LLM nhồi meme vào cả 15 tin -> bị siết còn tối đa `2 - 3` tin, khoảng cách `>= 4` tin, không có 2 tin liền kề, bỏ qua tin `setup` đầu tiên, giữ đúng các tin `intensity=5` (`punchline`/`twist`).
  - Test `FreshnessMemory`: cấm trùng trong cùng 1 video; tài nguyên dùng ở video `N` bị trừ điểm cooldown trong 6 video tiếp theo và hồi điểm từ video `N+6`.
  - Test `Resolver`: ưu tiên local khi khớp tốt & không cooldown; tự động gọi mock Giphy/GreenScreenMemes/Tuna/Pixabay/Freesound khi kho thiếu hoặc bị cooldown; tôn trọng trần tải `3 meme / 3 SFX / 1 BGM`; rơi êm về local khi API timeout `4.5s` hoặc lỗi mạng.
  - Test `reroll_asset`: luôn trả tài nguyên khác với danh sách `exclude_ids`.
- **`backend/tests/test_chatting_llm.py`, `test_chatting_timeline.py`, `test_chatting_api.py`:**
  - Xác nhận tương thích ngược khi đọc `chat.json` cũ không có các trường mới.
  - Xác nhận thời lượng meme động nằm trong `1.2s - 3.8s`, sticker tĩnh `0.9s - 1.6s`.
  - Xác nhận endpoint `POST /api/chatting/{slug}/messages/{msg_id}/reroll-asset` hoạt động đúng.
- **Frontend Vitest (`Chatting*.test.tsx`):**
  - Test công tắc `auto_fetch_online` và nút **"Đổi cái khác"** cập nhật đúng tin nhắn.

### 4.2. Nghiệm thu thực tế nhanh trên máy cũ (`i5-10400`)

- Tạo mới 1 video **Chatting** dài ~14-18 tin nhắn: xác nhận chỉ có **2-3 meme/sticker rơi đúng cao trào**, kho `library/` tự xuất hiện file mới tải về kèm `index.json`, và tạo tiếp tập thứ 2 cùng chủ đề không bị lặp lại đúng meme của tập 1.
