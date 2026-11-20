# GEMINI.md

Đọc toàn bộ CLAUDE.md và AGENTS.md (Ponytail mặc định mức `full` + Repo Harness khi có trên `GD-Config`) trước khi làm bất cứ việc gì. CLAUDE.md là luật chính của dự án; AGENTS.md và Repo Harness là quy tắc bắt buộc trước khi code (các skill mở rộng ở `.agents/skills/ponytail*/SKILL.md`), luôn giữ nguyên toàn bộ luật dự án trong CLAUDE.md và GEMINI.md. Luật push, merge và tag nằm ở CLAUDE.md (mục Bắt buộc và Quy trình mốc); không chép lại ở đây.

## Bổ sung cho Antigravity
- Trong tài liệu repo, chữ "Claude Code" nghĩa là bạn (agent Antigravity). Mọi luật áp cho Claude Code đều áp cho bạn.
- Bắt đầu mỗi đợt bằng skill `kickoff` (.agents/skills/kickoff/SKILL.md).
- Windows: chạy test bằng Git Bash để `set -o pipefail` và `&&` chạy đúng. Chỉ chạy khi xong cả giai đoạn (theo CLAUDE.md, thêm `npm run e2e`), không chạy sau từng commit:
  "C:\Program Files\Git\bin\bash.exe" -lc "set -o pipefail && npm run lint && npm run test"
- Không tự cài phần mềm hệ thống, không sửa PATH. Gói trong backend\.venv, backend\.venv-tts, npm chỉ cài khi kế hoạch đã duyệt có ghi.
- Không dừng giữa đợt để hỏi; chỗ chưa rõ chọn phương án an toàn nhất, ghi "Cần chốt" trong báo cáo cuối.
- `gh` đã đăng nhập: tự kiểm CI bằng `gh run list` / `gh run watch`, ghi link run vào báo cáo.
- Không `git push --force`, không rebase, không dời tag, không xoá `workspace/projects/*`.
- **Quy trình Git mới (6 Nhánh & 4 Tag Cố Định):**
  - Nhánh cố định theo giai đoạn: `main`, `GD-Config`, `GD1-HBT` (`v1`), `GD2-PostV` (`v2`), `GD3-Chatting` (`v3`), `GD4-StickV` (`v4`); tính năng lớn kế tiếp tạo `GD5-<TenTinhNang>` (`v5`). Cấm để tồn đọng nhánh `feat/*` rác sau khi merge.
  - Vai trò `GD-Config`: cài đặt, lưu trữ và cấu hình extension, skill, repo hỗ trợ bên ngoài (Ponytail, Repo Harness...); sau khi sạch lint thì merge `--no-ff` vào `main` để toàn dự án áp dụng.
  - Luồng commit trong ngày: code thuộc tính năng/động cơ nào → commit & push lên đúng nhánh `GDx-...`; code ngoài luồng (UI chung, hạ tầng `shared/`, fix toàn cục, tài liệu) → commit & push thẳng lên `main`.
  - **Pre-flight Branch Check:** Bắt buộc in `git branch --show-current` và `git log -1 --oneline` trước khi sửa file đầu tiên trong phiên.
