# HBT Studio

Studio dựng video tự động tiếng Việt chạy **local** (`9:16` & `16:9`, mặc định **`60fps`**) cho kênh **Hay Biết Tuốt**.  
Tối ưu chạy mượt trên **CPU local** (kẹp luồng FFmpeg, không bắt buộc GPU rời).

## 4 Động cơ chính

| Động cơ | Đường dẫn | Chức năng cốt lõi |
| --- | --- | --- |
| **HBT Core** | `/core` | Truyện tranh kiến thức 2D `9:16` · Luồng 2 nút (Gemini JSON + VieNeu-TTS + Cloudflare Flux 2D) · Ken Burns `60fps` mượt + Whisper Karaoke 2 dòng. |
| **PostV** | `/postv` | Video bài đăng Threads / Reddit `60fps` trên nền gameplay + meme phản ứng. |
| **Chatting** | `/chatting` | Video hội thoại Messenger / Instagram iOS `60fps`, hỗ trợ đính kèm ảnh/video & meme theo ngữ cảnh. |
| **StickV** | `/stickv` | MC Người que 2D diễn hoạt khớp tay/biểu cảm `60fps` + 5 phông nền động + ảnh tư liệu Polaroid (Wikimedia / Pixabay / Iconify). |

- **Thư viện (`/library`):** Quản lý tập trung nhạc nền, SFX, nền gameplay, meme, sticker, linh kiện Puppet 2D, watermark và kho video đã xuất.

## Cài đặt & Chạy nhanh (Windows)

**Yêu cầu:** Python `3.11.x` (`backend\.venv`), Node.js `v20+`, FFmpeg `6.0+`, và môi trường giọng đọc VieNeu-TTS (`backend\.venv-tts`, trọng số trong `models\hf_vieneu`).

```powershell
# 1. Cài gói frontend & chuẩn bị môi trường
npm install
py -3.11 -m venv backend\.venv && backend\.venv\Scripts\pip install -e "backend[dev]"

# 2. Chạy ứng dụng (Backend 127.0.0.1:8000 + Frontend 127.0.0.1:5173)
npm run dev

# 3. Kiểm tra lint, test nhanh & build production
npm run lint && npm run test:fast && npm run build
```

## Cấu hình API Key

Có thể nhập trực tiếp trên giao diện **`/settings`** (lưu local trong `workspace/app_settings.json`) hoặc đặt trong tệp `.env` ở gốc repo:

| Biến môi trường | Công dụng |
| --- | --- |
| `GEMINI_API_KEY` | Sinh kịch bản JSON tự động cho HBT Core, Chatting & StickV. |
| `CLOUDFLARE_ACCOUNT_ID` & `CLOUDFLARE_API_TOKEN` | Vẽ ảnh minh họa 2D cho HBT Core bằng Cloudflare Workers AI Flux (Free Tier). |
| `PIXABAY_API_KEY` / `GIPHY_API_KEY` | Tìm & tải tài nguyên nền, meme, sticker và ảnh tư liệu minh họa. |

## Cấu trúc 6 nhánh Git

- **`main`** — Nhánh ổn định chính, tích hợp đầy đủ các giai đoạn đã kiểm thử.
- **`GD-Config`** — Cấu hình công cụ, skill & harness hỗ trợ (`Ponytail`, Repo Harness).
- **`GD1-HBT`** (`v1`) — Động cơ HBT Core (`/core`).
- **`GD2-PostV`** (`v2`) — Động cơ PostV (`/postv`).
- **`GD3-Chatting`** (`v3`) — Động cơ Chatting (`/chatting`).
- **`GD4-StickV`** (`v4`) — Động cơ StickV (`/stickv`).

Chi tiết quy tắc phát triển, đặc tả và kiến trúc xem tại [`CLAUDE.md`](CLAUDE.md), [`IMPLEMENT.md`](IMPLEMENT.md) và thư mục [`docs/`](docs/).
