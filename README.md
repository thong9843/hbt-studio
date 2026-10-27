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

### 3. Chạy

```powershell
npm run dev
```

Mở <http://127.0.0.1:5173>. Trang chủ hiện trạng thái môi trường (FFmpeg, Whisper, GPU).
API chạy ở <http://127.0.0.1:8000> (chỉ máy này truy cập được), tài liệu API ở `/docs`.

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

Chỉ chạy trên máy cá nhân, không nằm trong CI. Dùng trình duyệt **Microsoft Edge** có sẵn của Windows (không phải tải trình duyệt). Kịch bản: mở trang chủ, tạo project, thêm 3 cảnh, lưu, tải lại trang và kiểm tra dữ liệu còn đủ; project thử được xoá sau khi chạy.

```powershell
npm run e2e
```

Lệnh tự bật `npm run dev` nếu chưa chạy (nếu đang chạy sẵn thì dùng luôn). Kịch bản nằm ở `e2e/`, cấu hình ở `playwright.config.ts`.
