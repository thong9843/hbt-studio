# HBT Studio — Đặc tả triển khai Giai đoạn 2 (GĐ2)

> Duyệt 02/11/2026. Đọc sau `CLAUDE.md`, `IMPLEMENT.md` (§12, §13.B4), `docs/gd2/PRD.md`.
> Mã kiểm K1–K12 là chuẩn của `IMPLEMENT.md` §13.B4.3; file này **nối tiếp** K13–K18, không đổi K1–K12.
> Ràng buộc cứng: không sửa `backend/hbt/models.py`, `backend/hbt/pipeline/`, `reference/`, `backend/hbt/api/projects.py`; `PIPELINE_VERSION` giữ nguyên.

## 1. Quyết định kỹ thuật

| #   | Chốt                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| E1  | Dữ liệu nháp lưu **`draft.json`** cạnh `project.json`                                                                                                                                                                                                                                                                                            |
| E2  | JSON nháp **`hbt_draft: 1`, dạng PHẲNG** (mục 2). Bộ đọc tách trường nháp → `draft.json`; phần còn lại → bộ kiểm M5 (`ScriptIn`, K1–K12) **không đổi**. Nút **Tạo dự án từ JSON nháp** ở Trang chủ                                                                                                                                               |
| E2b | Tâm trạng nhạc là khoá gốc **`music_mood`** (không dùng `music.mood`, vì `music` là trường cấm K4)                                                                                                                                                                                                                                               |
| E3  | Kiểm khi nhận nháp: K1–K12 như M5 · K13–K18 (mục 3)                                                                                                                                                                                                                                                                                              |
| E4  | VieNeu cho HBT: trước khi sinh, `{cách đọc}` → đọc chữ trong ngoặc; `\|` → nghỉ 0,25 s; mỗi cảnh một đoạn rồi nối → `voice.wav`, đặt `voice.file`. Pipeline nhận file giọng như cũ                                                                                                                                                               |
| E4b | Giọng HBT **không có mặc định cố định**: lần đầu chọn ở bước Giọng, app nhớ lựa chọn lần trước (như PVA `auto.voices`), lưu ở `workspace/settings/` (mục 7). Chưa chọn thì nút Tạo giọng tắt + nhắc chọn                                                                                                                                         |
| E5  | Nhạc: dùng trường **`moods`** (danh sách) **đã có** của bài trong `library/music/index.json`, không thêm trường mới; nháp có `music_mood` thì tự chọn bài đầu tiên có `moods` khớp, không khớp thì để trống. So khớp: chữ thường + bỏ dấu, bằng nhau; danh sách giá trị là **mở** (không ép enum). Chỉ ĐỌC index, không bao giờ ghi (chốt 02/11) |
| E6  | ComfyUI do chủ dự án tự cài và tự tải checkpoint. App chỉ gọi `http://127.0.0.1:8188`, workflow JSON trong repo, ảnh 768×1344. Không có ComfyUI → tự rẽ đường tay                                                                                                                                                                                |
| E7  | Mã ở `backend/hbt/gd2/` + `backend/hbt/api/gd2.py`; **không sửa** `api/projects.py` (đăng ký router ở `main.py`)                                                                                                                                                                                                                                 |

## 2. JSON nháp `hbt_draft: 1`

### 2.1 Trường

| Khoá                                                     | Kiểu                       | Bắt buộc                  | Đi về đâu                               |
| -------------------------------------------------------- | -------------------------- | ------------------------- | --------------------------------------- |
| `hbt_draft`                                              | số, phải bằng `1`          | có                        | bỏ sau khi đọc                          |
| `topic`                                                  | chuỗi không rỗng           | có                        | `draft.json`                            |
| `series_hint`                                            | chuỗi                      | không                     | `draft.json`                            |
| `music_mood`                                             | chuỗi                      | không                     | `draft.json`                            |
| `sources`                                                | mảng `{id, claim, url}`    | không                     | `draft.json`                            |
| `scenes[].image_prompt`                                  | chuỗi                      | khuyến nghị (thiếu → K18) | `draft.json` (`scenes[i].image_prompt`) |
| `scenes[].voice`, `card`, `labels`, `punch`, `caption_y` | như `IMPLEMENT.md` 13.B4.1 | như M5                    | khối `hbt_script`                       |
| `publish`, `thumbnail`                                   | như `IMPLEMENT.md` 13.B4.1 | như M5                    | khối `hbt_script`                       |

- Khoá lạ ở gốc hoặc trong cảnh (ngoài bảng trên và các khoá M5) → K4 như M5. Trường cấm của M5 (`image`, `music`, `settings`, `title`, `slug`, `series`, `theme`, `thumbnail.image`) vẫn cấm.
- `image_prompt` và các trường nháp **không** vào `ScriptIn`; bộ đọc nháp bóc chúng ra trước, phần còn lại (bỏ `hbt_draft`, thêm `hbt_script: 1`) là khối `hbt_script` hợp lệ.
- `sources[].id` duy nhất. `sources[].url` là chuỗi, **chỉ lưu và hiện**, app không tải.
- Số cảnh theo K2 của M5 (3–12).

### 2.2 Mẫu hợp lệ (3 cảnh)

```json
{
  "hbt_draft": 1,
  "topic": "Vì sao muỗi thích đốt một số người hơn?",
  "series_hint": "Vì sao…",
  "music_mood": "tò mò",
  "sources": [
    {
      "id": "s1",
      "claim": "Muỗi phát hiện CO2 từ xa khoảng 10 m",
      "url": "https://www.cdc.gov/mosquitoes/"
    }
  ],
  "scenes": [
    {
      "voice": "Có người ngồi cả buổi không sao, | có người bị đốt sưng cả chân.",
      "card": {
        "y": "top",
        "lines": [
          { "text": "VÌ SAO MUỖI", "size": "l", "color": "ink" },
          { "text": "CHỌN BẠN?", "size": "xl", "color": "accent" }
        ]
      },
      "labels": [],
      "punch": true,
      "caption_y": null,
      "image_prompt": "close-up of a mosquito on human skin, macro photo, vertical 9:16"
    },
    {
      "voice": "Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét.",
      "card": {
        "y": "top",
        "lines": [{ "text": "CO2 TỪ 10 MÉT", "size": "l", "color": "ink" }]
      },
      "labels": [],
      "punch": false,
      "caption_y": null,
      "image_prompt": "person breathing out in warm evening air, vertical 9:16"
    },
    {
      "voice": "Thở nhiều, đổ mồ hôi nhiều | thì muỗi tìm bạn dễ hơn.",
      "card": {
        "y": "top",
        "lines": [{ "text": "THỞ NHIỀU = DỄ BỊ ĐỐT", "size": "m", "color": "ink" }]
      },
      "labels": [],
      "punch": false,
      "caption_y": null,
      "image_prompt": "person jogging at dusk near a pond, vertical 9:16"
    }
  ],
  "publish": {
    "hook": "Bạn có phải \"nam châm hút muỗi\"?",
    "hashtags": ["haybiettuot", "muoi", "visao"]
  },
  "thumbnail": {
    "scene": 1,
    "lines": ["VÌ SAO MUỖI", "CHỌN BẠN?"],
    "series": "",
    "accent": "#FFD43B"
  }
}
```

### 2.3 Tách

| Từ JSON nháp                                                             | Đến                                                         |
| ------------------------------------------------------------------------ | ----------------------------------------------------------- |
| `topic`, `series_hint`, `music_mood`, `sources`, `scenes[].image_prompt` | `draft.json`                                                |
| phần còn lại, bỏ `hbt_draft`, thêm `hbt_script: 1`                       | khối `hbt_script` → `script/check` và `script/apply` của M5 |

### 2.4 `draft.json`

```json
{
  "draft": 1,
  "topic": "…",
  "series_hint": "",
  "music_mood": "tò mò",
  "sources": [{ "id": "s1", "claim": "…", "url": "…" }],
  "scenes": [{ "image_prompt": "…", "image_prompt_ok": true }],
  "images_approved": false
}
```

- `scenes` cùng thứ tự và số lượng với `project.json`. `image_prompt_ok = false` khi K18 (thiếu hoặc rỗng): cảnh đó đi đường tay.
- `images_approved`: cờ "đã duyệt ảnh" (G2). Đổi ảnh của một cảnh đặt lại `false`.
- Ghi nguyên tử (file tạm rồi đổi tên), `ensure_ascii=False`.
- Dự án cũ không có `draft.json` chạy bình thường.

## 3. Mã kiểm K13–K18

Nối tiếp K1–K12 (`IMPLEMENT.md` 13.B4.3). K1–K12 chạy như M5 trên phần `hbt_script` sau khi tách.

| Mã  | Kiểm                                                                                             | Mức      |
| --- | ------------------------------------------------------------------------------------------------ | -------- |
| K13 | `hbt_draft` ≠ 1, hoặc thiếu / rỗng `topic`                                                       | Lỗi      |
| K14 | `sources[]` sai dạng: không phải mảng đối tượng, thiếu `id` / `claim` / `url`, hoặc `id` trùng   | Lỗi      |
| K15 | Sai kiểu: `music_mood` không phải chuỗi, hoặc `scenes[].image_prompt` có mặt mà không phải chuỗi | Lỗi      |
| K16 | Số liệu thiếu nguồn (xem dưới)                                                                   | Cảnh báo |
| K17 | `image_prompt` chứa từ cấm: `text`, `chữ`, `map`, `bản đồ`, `Vietnam map`                        | Cảnh báo |
| K18 | Thiếu `image_prompt` hoặc rỗng: **vẫn tạo dự án**, cảnh đó đi đường tay                          | Cảnh báo |

**K16 (so theo con số):**

1. Lấy lời đọc của cảnh, bỏ mọi phần `{…}` (cách đọc).
2. Lấy các số (chuỗi chữ số, cho phép dấu `.` hoặc `,` giữa các chữ số; chuẩn hoá bỏ dấu phân cách để so).
3. Lấy các số trong `claim` của **mọi** `sources[]`.
4. Số nào của cảnh không xuất hiện trong tập số của claim → cảnh báo "Cảnh n: số X chưa có nguồn".
5. Không so chuỗi con, không thêm `scenes[].source_ids`.

**K17:** so khớp không phân biệt hoa thường, theo từ nguyên (ranh giới từ), nên `context` không báo `text`. Mỗi cảnh báo nêu cảnh và từ.

**Nối phủ định (E3):** app tự thêm phần phủ định khi gửi cho trình tạo ảnh (không chữ, không bản đồ). Phần này không lưu vào `image_prompt` và hiện ở nút Sao chép để Gemini web cũng nhận.

**Phạm vi:** K13–K15 chặn tạo dự án (không ghi gì). K16–K18 chỉ cảnh báo. Lint từ nhạy cảm là K10 như M5 (`block` hiện đỏ "sẽ chặn xuất"). Đặc tả duyệt (E3) ghi `block` là "chặn tạo", khác M5: xem Cần chốt C-1.

## 4. API (`backend/hbt/api/gd2.py`)

Lỗi theo dạng `{detail}` như `IMPLEMENT.md` §9.

| Điểm cuối                                                 | Việc                                                                                                                         | Lỗi                                                     |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `POST /gd2/draft/check` `{draft}`                         | Chỉ kiểm, **không ghi gì**; trả `{ok, errors[], warnings[], scenes, music_match}`                                            | 200 kể cả lỗi nội dung (`ok:false`)                     |
| `POST /gd2/draft/create` `{draft, title?}`                | Kiểm lại; không lỗi thì tạo dự án (dùng hàm tạo của `storage.py`), áp khối `hbt_script`, ghi `draft.json`, tự chọn nhạc (E5) | 422 khi còn lỗi (slug trùng tự thêm `-2`, không có 409) |
| `GET /projects/{slug}/draft`                              | Đọc `draft.json`                                                                                                             | 404 khi dự án không có nháp                             |
| `PUT /projects/{slug}/draft/images-approved` `{approved}` | Đặt cờ duyệt ảnh (G2)                                                                                                        | 404                                                     |
| `POST /projects/{slug}/draft/voice`                       | Job sinh giọng VieNeu cho HBT (G3), cùng hàng đợi job                                                                        | 503 chưa cài VieNeu                                     |
| `GET /gd2/voice/preferences`, `PUT …`                     | Giọng HBT nhớ lần trước (E4b)                                                                                                | —                                                       |
| `POST /projects/{slug}/draft/images/{i}/generate`         | ComfyUI cho cảnh i (G4)                                                                                                      | 503 khi không chạy → rẽ đường tay                       |
| `POST /projects/{slug}/draft/images/generate`             | Cả bộ (G4), huỷ được                                                                                                         | 503                                                     |

Tên chuẩn: đổi thì hỏi chủ dự án. Router đăng ký ở `main.py`; `api/projects.py` không đổi.

## 5. Tách mã (`backend/hbt/gd2/`)

| File            | Việc                                                      |
| --------------- | --------------------------------------------------------- |
| `draft.py`      | `DraftIn`, `split_draft()`, K13–K15                       |
| `checks.py`     | K16–K18                                                   |
| `store.py`      | đọc / ghi `draft.json`                                    |
| `music_pick.py` | chọn nhạc theo `music_mood` (E5)                          |
| `voice.py`      | VieNeu cho HBT: xử lý `{}` và `\|`, ghép `voice.wav` (G3) |
| `comfy.py`      | `ComfyProvider` qua `ImageProvider` (G4)                  |
| `workflows/`    | workflow ComfyUI JSON (G4)                                |

## 6. Mốc

### G1 · Nháp + dự án (máy cũ, ~1,5 buổi, tag `v1.11.0`)

| Việc                                                                                                    | Test                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gd2/draft.py`, `checks.py`, `store.py`, `music_pick.py`; `api/gd2.py` (`check`, `create`, `GET draft`) | pytest: mẫu 3 cảnh hợp lệ; K13 (`hbt_draft: 2`, thiếu `topic`); K14 (thiếu `url`, `id` trùng); K15 (`music_mood: 5`); K16 (số 15 không có trong claim, số trong `{…}` bị bỏ, `10{mười}` khớp claim); K17 (`map`, `bản đồ`, không báo `context`); K18 (thiếu và rỗng, vẫn tạo); khoá lạ → K4; `check` không ghi gì (mtime); `create` tạo `project.json` + `draft.json`; tách đúng |
| Đọc `moods` có sẵn trong `library/music/index.json` (chỉ đọc); tự chọn nhạc                             | pytest: so chữ thường, bỏ dấu; không khớp → để trống; bài không có `moods` bị bỏ qua; bài thiếu `id` thì bỏ chọn và cảnh báo; index không bị ghi (nội dung và mtime)                                                                                                                                                                                                             |
| Giao diện: nút **Tạo dự án từ JSON nháp** ở Trang chủ (theo `DESIGN-HBT.md` v2, chữ trong `vi.ts`)      | Vitest: hộp dán / thả file, danh sách lỗi và cảnh báo, nút tắt khi có lỗi; e2e: dán mẫu → vào trình soạn                                                                                                                                                                                                                                                                         |

### G2 · Bước Ảnh (máy cũ, ~1 buổi, tag `v1.12.0`)

Prompt từng cảnh + nút Sao chép (có phần phủ định), thả ảnh đúng cảnh (dùng `POST /projects/{slug}/assets`), cờ "đã duyệt ảnh" lưu **dấu ảnh từng cảnh**, cảnh K18 tự viết prompt. Màn `/p/:slug/images`, mục "Ảnh" ở thanh trái (giữa Soạn video và Âm thanh, chỉ khi có nháp), tab Xuất chỉ nhắc "Ảnh chưa duyệt" (không chặn xuất).

| Điểm cuối                                                       | Việc                                                                                                        |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `GET /projects/{slug}/draft/exists`                             | `{exists}`, luôn 200 (giao diện ẩn mục Ảnh mà không sinh 404)                                               |
| `GET /projects/{slug}/draft`                                    | Nháp kèm, mỗi cảnh: `image_approved`, `full_prompt`, `forbidden`; `images_approved` tính lúc đọc, không ghi |
| `PUT /projects/{slug}/draft/images-approved` `{approved}`       | Duyệt (lưu `approved_marks` = `scene.image` từng cảnh; thiếu ảnh → 422) hoặc bỏ duyệt (xoá dấu)             |
| `PUT /projects/{slug}/draft/scenes/{i}/prompt` `{image_prompt}` | Đặt prompt (rỗng → `image_prompt_ok=false`); không đổi dấu duyệt                                            |

Test: pytest `test_gd2_images.py`, `test_gd2_docs.py`; Vitest `ImagesTab.test.tsx`, nhắc ở `ExportTab.screen.test.tsx`, mục thanh trái ở `AppShell.test.tsx`; e2e `gd2-images.spec.ts`.

### G3 · Giọng VieNeu cho HBT (máy cũ, ~1,5 buổi, tag `v1.13.0`)

Tái dùng provider VieNeu của PostV (`.venv-tts`). Xử lý `{}` và `|` (E4), mỗi cảnh một đoạn rồi nối `voice.wav`, tiến độ x/N, huỷ được, cache theo hash lời + giọng. Giọng nhớ (E4b). Vbee vẫn thả file. Test: provider giả cho CI; tiền xử lý `{}` / `|`; nút Tạo giọng tắt khi chưa chọn giọng. Test VieNeu thật gắn `slow` và không chạy ở CI.

### G4 · ComfyUI (máy mới, ~2 buổi, tag `v1.14.0`)

`ComfyProvider` (E6), từng cảnh / cả bộ, huỷ được, rẽ đường tay khi không kết nối. Test: server ComfyUI giả; test thật chỉ trên máy mới.

### Quy tắc chung mọi mốc

- Quy trình đợt theo `CLAUDE.md`: test đầy đủ một lần cuối giai đoạn.
- Kiểm chứng cuối mốc: `git diff <tag trước> -- backend/hbt/pipeline/ reference/ backend/hbt/models.py backend/hbt/api/projects.py` rỗng; `PIPELINE_VERSION` không đổi.

## 7. Lưu giọng HBT đã chọn

`workspace/settings/gd2.json`, dạng `{"voice": {"id": "…"}}`, không chứa khoá API. `workspace/` không commit.

## 8. Cần chốt

| #   | Điểm                                                       | Mặc định tạm                                                 |
| --- | ---------------------------------------------------------- | ------------------------------------------------------------ |
| C-1 | K10 `block`: đặc tả GĐ2 ghi "chặn tạo", M5 ghi "chặn xuất" | Làm đúng M5 (cảnh báo đỏ, chặn xuất); chờ chủ dự án xác nhận |
| C-2 | `scenes[].source_ids`                                      | Không thêm (đã chốt: K16 so theo con số)                     |
| C-3 | Danh sách giá trị `moods`                                  | Mở; chủ dự án gắn khi tải nhạc lên (trường `moods` có sẵn)   |
| C-4 | Tên điểm cuối API                                          | Như mục 4                                                    |

## 9. Quyết định đã chốt (G1, 02/11/2026)

| #   | Chốt                                                                                                                                                                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| C-1 | K10 `block` như M5: **vẫn tạo dự án**, cảnh báo đỏ "sẽ chặn xuất", chặn khi xuất                                                                                         |
| C-2 | Không thêm `scenes[].source_ids`; K16 so theo con số                                                                                                                     |
| C-3 | Dùng `moods` có sẵn của thư viện nhạc, không thêm `mood`                                                                                                                 |
| C-4 | Tên điểm cuối API như mục 4                                                                                                                                              |
| G1a | `title` lấy từ `topic`, `series` lấy từ `series_hint`; body `create` có thể ghi đè `title`. Số cảnh = số phần tử `scenes` (3–12, ngoài khoảng là K2); không dùng `extra` |
| G1b | `series_hint` sai kiểu cũng là K15. `image_prompt: null` coi như thiếu (K18). Nút "Từ JSON nháp" đặt ở Trang chủ                                                         |
| G1c | `images_approved` có trong `draft.json` từ G1 (mặc định `false`), chỉ G2 dùng; `PUT …/draft/images-approved` làm ở G2                                                    |
| G1d | Mã cảnh báo thêm `MUSIC` (không phải K): thư viện nhạc không đọc được hoặc có bài thiếu `id`; khi đó để trống nhạc, không ghi gì                                         |

## 10. Quyết định đã chốt (G2, 02/11/2026)

| #   | Chốt                                                                                                                                                                                                                                                                  |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G2a | Duyệt ảnh lưu `approved_marks` (tên file ảnh từng cảnh, đã theo nội dung `images/<hash16>.<ext>`) trong `draft.json`. Đọc nháp: cảnh có ảnh khác dấu, hoặc chưa có ảnh, là chưa duyệt; `images_approved` chỉ đúng khi cả bộ khớp. Đưa ảnh về đúng ảnh cũ thì khớp lại |
| G2b | Ảnh chưa duyệt **không chặn xuất**: tab Xuất chỉ nhắc kèm link sang bước Ảnh, và chỉ với dự án có nháp. Không đụng render, jobs, `api/projects.py`                                                                                                                    |
| G2c | Thêm `GET …/draft/exists` (200 cả khi không có) để giao diện ẩn mục Ảnh mà không phát sinh yêu cầu 404                                                                                                                                                                |
| G2d | Sửa prompt qua `PUT …/draft/scenes/{i}/prompt`. Prompt có từ cấm (K17) vẫn sao chép được, chỉ gắn nhãn                                                                                                                                                                |
| G2e | Mẫu JSON trong `PROMPT-KICH-BAN.md` và `IMPLEMENT-GD2.md` §2.2 phải bằng `backend/tests/data/hbt-draft.sample.json` (có test)                                                                                                                                         |
