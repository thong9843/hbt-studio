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

### 2. Cài thư viện của dự án

Tại thư mục gốc repo:

```powershell
npm install
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\pip install -e "backend[dev]"
copy .env.example .env
```

Muốn phụ đề chính xác bằng Whisper (dùng từ M4), cài thêm:

```powershell
backend\.venv\Scripts\pip install -e "backend[whisper]"
backend\.venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

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

## Thư mục

| Thư mục       | Nội dung                                                    |
| ------------- | ----------------------------------------------------------- |
| `backend/`    | FastAPI + pipeline dựng video (Python 3.11)                 |
| `frontend/`   | React + TypeScript + Vite + Tailwind                        |
| `brand/`      | Logo, avatar, favicon HBT                                   |
| `library/`    | Thư viện nhạc (`index.json` lên Git, file mp3 thì không)    |
| `reference/`  | Code dựng video đã chạy thật — chỉ để đối chiếu khi port    |
| `workspace/`  | Project và video của bạn — **không** lên Git                |
