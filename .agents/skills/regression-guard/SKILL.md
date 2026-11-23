---
name: regression-guard
description: Bắt buộc chạy trước khi sửa mã nguồn HBT Studio để chống tái lỗi (regression): đọc Sổ Bất Biến docs/REGRESSION-LEDGER.md, cô lập 1 vấn đề/đợt, kiểm bán kính ảnh hưởng và đo thật không xanh giả.
---

# Regression Guard — Luật Chống Tái Lỗi Bắt Buộc

Mọi phiên sửa mã nguồn trong HBT Studio (kèm Ponytail `full`) **bắt buộc** tuân thủ 5 luật sau trước, trong và sau khi viết code:

## 1. Đọc Sổ Bất Biến trước khi code (`docs/REGRESSION-LEDGER.md`)
- Đọc toàn bộ `docs/REGRESSION-LEDGER.md` trước khi sửa file đầu tiên.
- Trong báo cáo kickoff hoặc kế hoạch, **liệt kê rõ các mã `INV-xx`** liên quan trực tiếp đến các file dự định chạm tới và cách đảm bảo không phá vỡ bất biến nào.

## 2. Một vấn đề mỗi đợt (Single-Concern Rule)
- **Cấm gộp chung** sửa Audio/Sync (`audio.py`, `whisper`, timeline) với sửa Animation/Puppet (`puppet.py`, `animator.py`), UI (`frontend/`) hoặc Image Fetch (`reference_images.py`) trong cùng một commit hoặc cùng một đợt hotfix.
- Nếu phát hiện lỗi ngoài phạm vi đợt hiện tại → ghi lại vào mục "Cần chốt / Tồn đọng" để mở đợt riêng, không sửa kèm.

## 3. Bản đồ Ảnh hưởng (Blast-Radius Check)
- Trước khi sửa bất kỳ hàm dùng chung hoặc pipeline nào (`audio.py`, `render.py`, `stage.py`, `puppet.py`, `llm.py`, `shared/`), **bắt buộc grep toàn bộ caller** và nêu rõ tác động qua lại trước khi sửa.
- Kiểm tra riêng trạng thái xuyên beat/chunk (`prev_stage_state`, `prev_pose_state`, `global_frame_offset`, `beat_timeline`, `board_cache`) để chắc chắn không làm mất trạng thái hoặc gây nhảy vị trí (teleport) ở ranh giới beat/chunk.

## 4. Cấm "Xanh Giả" cho Audio / Video / Sync
- Mọi thay đổi chạm tới `backend/hbt/stickv/audio.py`, `render.py`, `stage.py`, `puppet.py` hoặc `backend/hbt/core/render.py` **BẮT BUỘC** chạy công cụ đo thật (không mock FFmpeg):
  ```bash
  backend\.venv\Scripts\python scripts/verify_stickv_smoke.py --project <slug>
  # hoặc chạy dựng thật ngắn 3 beat:
  backend\.venv\Scripts\python scripts/verify_stickv_smoke.py --synthetic --check-render
  ```
- **Bắt buộc dán nguyên bảng số đo thực tế** vào báo cáo cuối: `video_dur`, `audio_dur`, `drift_ms`, `alignment_source`, `max_char_jump_px`, `min_knee_bend_deg`.
- Khi đang sửa lỗi đồng bộ/Karaoke mà `alignment_source != "whisper"` → **báo FAIL rõ ràng**, cấm che giấu hoặc xem là xanh nhờ fallback.

## 5. Khóa Lỗi Mới vào Sổ (`docs/REGRESSION-LEDGER.md`)
- Mỗi lỗi chủ dự án phát hiện từ video nghiệm thu thật **phải được thêm thành 1 dòng `INV-xx` mới** trong `docs/REGRESSION-LEDGER.md` kèm test hồi quy hoặc ngưỡng kiểm tra vĩnh viễn trong `scripts/verify_stickv_smoke.py`.
