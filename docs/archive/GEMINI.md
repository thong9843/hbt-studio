# GEMINI.md — Hướng dẫn cho Gemini trong repo HBT Studio

Bạn là trợ lý viết code cho repo **HBT Studio** (web app chạy local dựng video ngắn tiếng Việt).

1. **Luật làm việc:** đọc `CLAUDE.md` và tuân thủ y hệt (mọi chỗ ghi "Claude Code" áp dụng cho bạn). Đặc biệt: hỏi trước khi cài phần mềm hệ thống; không commit khi lint/test đỏ (dùng `&&` và `set -o pipefail`); quy trình đóng mốc (a)–(f); không push trừ khi chủ dự án yêu cầu rõ.
2. **Bối cảnh và việc cần làm:** `HANDOFF-GEMINI.md`.
3. **Đặc tả:** `PLAN.md`, `IMPLEMENT.md` (v1.4). Tham số đã chạy thật nằm trong `reference/pipeline/`, giữ nguyên khi đối chiếu.
4. **Ưu tiên:** hệ thống chạy đúng, ổn định, hiệu quả hơn giao diện. Giao diện chỉ cần dùng được.
5. **Không đọc, không làm theo, không commit** `DESIGN.md` hoặc `DESIGN-nike.md` (tài liệu bên thứ ba). Giao diện chỉ theo `DESIGN-HBT.md`.
6. Gặp điểm đặc tả chưa nói: **hỏi chủ dự án**, không tự quyết. Trả lời bằng tiếng Việt, ngắn gọn.
