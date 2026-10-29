# HBT Studio

Web app chạy **local** để dựng video ngắn tiếng Việt cho kênh **Hay Biết Tuốt**.
Kế hoạch: [`PLAN.md`](PLAN.md) · Đặc tả: [`IMPLEMENT.md`](IMPLEMENT.md) · Quy tắc cho Claude Code: [`CLAUDE.md`](CLAUDE.md)

## Cài đặt trên Windows

### 1. Cài công cụ (một lần)

Mở PowerShell:

```powershell
winget install Git.Git
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
```

Đóng và mở lại terminal để PATH nhận FFmpeg. Kiểm tra:

```powershell
py -3.11 --version    # Python 3.11.x
node --version        # v20 trở lên
ffmpeg -version       # 6.0 trở lên
```

Dự án ghim **Python 3.11.x**. Nếu máy đã có Python mới hơn, cài thêm 3.11 song song (không gỡ bản cũ) và luôn gọi bằng `py -3.11`; `py -3.11 --version` phải in `Python 3.11.x`. Nếu đang dùng Claude Code, hãy để nó hỏi bạn trước khi cài bất kỳ phần mềm nào.

### 2. Cài thư viện của dự án

Tại thư mục gốc repo:

```powershell
npm install
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\pip install -e "backend[dev]"
copy .env.example .env
```

Muốn phụ đề chính xác bằng Whisper (mặc định `WHISPER_MODEL=auto`, `WHISPER_DEVICE=auto`), cài thêm:

```powershell
backend\.venv\Scripts\pip install -e "backend[whisper]"
```

Máy có GPU NVIDIA cài thêm thư viện CUDA 12 (máy không có GPU **không** cần):

```powershell
backend\.venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

`auto` chọn theo phần cứng: có CUDA thì `large-v3` trên GPU (`int8_float16`), không thì `small` trên CPU (`int8`). Model tải về `models/` ở lần chạy đầu (`small` khoảng 0,5 GB), những lần sau nạp thẳng từ đó. Whisper lỗi hoặc quá giới hạn thời gian (Cài đặt, mặc định 900 giây) thì app căn theo khoảng lặng; lỗi CUDA thì thử CPU trước. Phương pháp đã dùng hiện ở kết quả dựng. Đã thử với `faster-whisper 1.2.1`, `ctranslate2 4.8.3`. Đo thật từng model: `backend\.venv\Scripts\python -m cli bench-align workspace/projects/<slug> --models small,medium`.

Cần driver NVIDIA hỗ trợ CUDA 12. Không có GPU thì app vẫn chạy, chỉ chậm hơn hoặc dùng chế độ căn theo khoảng lặng.

#### Giọng VieNeu cho PostV (tuỳ chọn)

PostV có thể tự sinh giọng đọc tiếng Việt bằng **VieNeu-TTS**, chạy trên CPU (không cần GPU), trong một môi trường Python riêng để không làm lệch phiên bản gói của app:

```powershell
py -3.11 -m venv backend\.venv-tts
backend\.venv-tts\Scripts\pip install -r backend
equirements-tts.txt
```

`requirements-tts.txt` ghim `vieneu==3.8.3`. Trọng số mô hình (khoảng 580 MB) nằm ở `models\hf_vieneu`. App **không tự tải** trọng số: lần đầu hãy chạy thử một lần có mạng (đặt `HF_HOME` về `models\hf_vieneu`) hoặc chép thư mục `models\hf_vieneu` từ máy đã có. Thiếu gói hoặc thiếu trọng số thì thanh trái ghi "VieNeu: thiếu", bước 3 của PostV nói rõ thiếu gì, và bạn vẫn nhập file giọng như bình thường. Đọc khoảng 1 giây cho mỗi giây giọng trên CPU. Test VieNeu thật (`pytest -m slow`) tự bỏ qua nếu chưa cài.

### 3. Chạy

```powershell
npm run dev
```

Mở <http://127.0.0.1:5173>. Trang chủ hiện trạng thái môi trường (FFmpeg, Whisper, GPU).
API chạy ở <http://127.0.0.1:8000> (chỉ máy này truy cập được), tài liệu API ở `/docs`.

## Hướng dẫn dùng (v1.0)

App dựng video từ nguyên liệu bạn chuẩn bị bên ngoài (kịch bản, ảnh, giọng đọc, nhạc). Ba điểm duyệt do bạn làm: kịch bản, ảnh, video. App không tự viết kịch bản hay vẽ ảnh.

### Làm một video, từng bước

1. **Chuẩn bị nguyên liệu** (làm tay như trước):
   - Kịch bản 3–12 cảnh (thường 8): lời đọc, thẻ chữ từng cảnh. Số và tên nước ngoài viết theo cách đọc.
   - Ảnh từng cảnh, khổ dọc 9:16, **không có chữ** trong ảnh. Tên file nên có số thứ tự (`scene-01`, `scene-02`…).
   - File giọng đọc (mp3 hoặc wav). Tổng lời đọc **không quá 750 ký tự** (gói Vbee 3.000 ký tự/ngày). Đuôi file có quảng cáo thì app tự cắt, nhưng đoạn thừa trên 8 giây thì hỏi bạn nghe lại rồi mới cắt.
   - Nhạc nền: chọn từ thư viện hoặc tải bài từ máy; ghi công tác giả.
2. **Tạo video:** bấm **Tạo video** ở thanh trái, đặt tên, chọn series và số cảnh. App chuyển sang màn **Soạn video**.
3. **Soạn video:**
   - Thả **nhiều ảnh một lần** vào dải cảnh: app xếp theo tên file và gán từ cảnh 1.
   - Dán kịch bản bằng **Dán JSON** (xem dưới) hoặc gõ tay: lời đọc, thẻ chữ (vị trí, cỡ, màu), nhãn, chữ "nhấn" (punch).
   - Bộ đếm trong ô cho biết giới hạn: dòng thẻ chữ theo cỡ (xl 10, l 15, m 22, s 26 ký tự) và lời đọc cả video (750). Vượt thì bộ đếm chuyển vàng; chỉ là cảnh báo, riêng chữ tràn khung thì app báo lỗi.
   - Dùng `|` trong lời đọc để ngắt cụm phụ đề, và `{ }` để ghi cách đọc, ví dụ `100{một trăm}`.
   - **Bìa & đăng:** dòng chữ ảnh bìa, câu mở đầu và hashtag.
   - App tự lưu; **Ctrl+S** lưu ngay.
4. **Âm thanh:** tải file giọng, chọn nhạc nền, điểm bắt đầu nhạc (Tự chọn hoặc Đặt tay), hoặc chọn **Không nhạc**.
5. **Xuất video:**
   - Thẻ **Kiểm tra** báo thiếu nguyên liệu và từ nhạy cảm. Mức **Chặn** thì phải sửa mới dựng được.
   - **Xem nhanh** dựng 10 giây đầu ở độ phân giải thấp để duyệt chữ và nhịp. Bấm **Xuất bản đẹp** khi đã ưng. Chọn 30, 50 hoặc 60 fps (mặc định 50) và bật hoặc tắt outro 4 giây.
   - Dòng ước tính cho biết thời gian dựng dự kiến; bản đẹp trên máy không GPU mất vài phút. Có thể **Huỷ** giữa chừng.
   - Xong thì xem ngay trong trang, bấm **Tải video** để lưu `video.mp4`. Nội dung đăng (`publish.txt`) và ảnh bìa nằm ở thẻ cùng màn; có nút sao chép.
6. **Lịch sử các lần xuất** nằm cuối màn Xuất video. Menu ⋯ của mỗi lần có **Tải video** và **Xoá**. **Dọn file tạm** xoá file trung gian trong `build/` để lấy lại dung lượng, nhưng giữ mốc căn chữ, video đã xuất, ảnh, giọng, nhạc.

File của dự án nằm ở `workspace/projects/<tên-dự-án>/`; video đã xuất ở `renders/<mã-lần-xuất>/`.

### Dán JSON kịch bản

Ở màn Soạn video bấm **Dán JSON** (hoặc thả file `.json` vào hộp). Bước **Kiểm tra** hiện khác biệt từng cảnh và cảnh báo mà **không ghi gì**; bấm **Áp dụng** mới ghi. Mỗi lần áp có một bản sao lưu (giữ 10 bản): bấm **Hoàn tác** trên thông báo, hoặc menu ⋯ → **Bản sao lưu** → **Khôi phục**.

Dạng ngắn là một mảng, mỗi phần tử là một cảnh theo thứ tự:

```json
[
  {
    "voice": "Muỗi đốt người thật ra là để đẻ trứng.",
    "card": {
      "y": "top",
      "lines": [{ "text": "MUỖI", "size": "xl", "color": "ink" }]
    },
    "punch": false
  }
]
```

Dạng đầy đủ là một đối tượng `{ "hbt_script": 1, "scenes": [...], "publish": {...}, "thumbnail": {...} }`. Quy tắc:

- Trường vắng thì giữ nguyên; trường có mặt ghi đè cả trường (`"labels": []` xoá hết nhãn).
- Không đổi được qua JSON: ảnh, file giọng, nhạc, cài đặt, tên, series. Trường lạ hoặc sai tên là lỗi.
- JSON nhiều cảnh hơn dự án: chọn **Thêm cảnh** hoặc **Bỏ phần thừa**.
- Đặc tả đầy đủ các trường và mã kiểm: `IMPLEMENT.md` mục 13.B4.

### Lệnh dòng lệnh

Dựng không cần giao diện (chạy ở thư mục gốc repo):

```powershell
backend\.venv\Scripts\python -m cli render workspace/projects/<tên-dự-án> --preview
backend\.venv\Scripts\python -m cli render workspace/projects/<tên-dự-án> --fps 50 --no-outro
backend\.venv\Scripts\python -m cli bench-align workspace/projects/<tên-dự-án> --models small,medium
```

`--preview` dựng bản Xem nhanh (540×960, 30 fps); thêm `--seconds N` để chỉ dựng N giây đầu. `--allow-long-trim` chỉ dùng sau khi bạn đã nghe đoạn thừa dài ở cuối file giọng.

### Cài đặt và xử lý sự cố

- **Cài đặt** (thanh trái): fps mặc định, model Whisper và giới hạn thời gian, màu chủ đề, danh sách từ nhạy cảm (Lưu ý, Cảnh báo, Chặn). Có một nút **Lưu** cho cả màn; rời màn khi chưa lưu thì app hỏi.
- Nút **Sáng/Tối** ở đáy thanh trái đổi chế độ giao diện.
- Chấm **Môi trường** ở thanh trái báo thiếu FFmpeg, Whisper hoặc GPU. Thiếu FFmpeg thì không dựng được; thiếu Whisper hoặc GPU thì app căn chữ theo khoảng lặng hoặc bằng CPU, chậm hơn.
- Không xoá được dự án hoặc lần xuất vì "file đang mở": đóng trình phát hoặc chương trình đang dùng file rồi thử lại.
- Không bao giờ commit `workspace/`, `models/`, file media và `.env`.

## Lệnh hay dùng

| Lệnh             | Việc                                       |
| ---------------- | ------------------------------------------ |
| `npm run dev`    | Chạy backend (8000) + frontend (5173)      |
| `npm run lint`   | ruff + Prettier + TypeScript + ESLint      |
| `npm run test`   | pytest + Vitest                            |
| `npm run format` | Tự định dạng code Python và TypeScript     |
| `npm run build`  | Đóng gói frontend vào `frontend/dist/`     |
| `npm run e2e`    | Kiểm thử trình duyệt (Playwright), xem dưới |

## Thư mục

| Thư mục       | Nội dung                                                    |
| ------------- | ----------------------------------------------------------- |
| `backend/`    | FastAPI + pipeline dựng video (Python 3.11)                 |
| `frontend/`   | React + TypeScript + Vite + Tailwind                        |
| `brand/`      | Logo, avatar, favicon HBT                                   |
| `library/`    | Thư viện nhạc (`index.json` lên Git, file mp3 thì không)    |
| `reference/`  | Code dựng video đã chạy thật — chỉ để đối chiếu khi port    |
| `workspace/`  | Project và video của bạn — **không** lên Git                |

## Kiểm thử trình duyệt (e2e)

Chỉ chạy trên máy cá nhân, không nằm trong CI. Dùng trình duyệt **Microsoft Edge** có sẵn của Windows (không phải tải trình duyệt). Chín kịch bản: tạo project và lưu, nút Sáng/Tối, màn Âm thanh, Xem nhanh và Huỷ, xoá lần xuất ở Lịch sử, đổi cài đặt, dán JSON kịch bản, Tab/focus, sinh giọng VieNeu ở bước 3 của PostV (tự bỏ qua nếu máy chưa cài VieNeu). Mỗi kịch bản tự xoá project thử bằng `DELETE` khi xong (và báo lỗi nếu không xoá được). Kịch bản Xem nhanh và xoá lần xuất dựng video thật bằng FFmpeg nên mất vài chục giây.

```powershell
npm run e2e
```

Lệnh tự bật `npm run dev` nếu chưa chạy (nếu đang chạy sẵn thì dùng luôn). Kịch bản nằm ở `e2e/`, cấu hình ở `playwright.config.ts`.
