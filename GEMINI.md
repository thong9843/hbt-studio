# GEMINI.md

Đọc toàn bộ CLAUDE.md và AGENTS.md (Ponytail harness) trước khi làm bất cứ việc gì. CLAUDE.md là luật chính của dự án; AGENTS.md là quy tắc bắt buộc trước khi code (chế độ mặc định `full`, các skill mở rộng ở `.agents/skills/ponytail*/SKILL.md`). Luật push, merge và tag nằm ở CLAUDE.md (mục Bắt buộc và Quy trình mốc); không chép lại ở đây.

## Bổ sung cho Antigravity
- Trong tài liệu repo, chữ "Claude Code" nghĩa là bạn (agent Antigravity). Mọi luật áp cho Claude Code đều áp cho bạn.
- Bắt đầu mỗi đợt bằng skill `kickoff` (.agents/skills/kickoff/SKILL.md).
- Windows: chạy test bằng Git Bash để `set -o pipefail` và `&&` chạy đúng. Chỉ chạy khi xong cả giai đoạn (theo CLAUDE.md, thêm `npm run e2e`), không chạy sau từng commit:
  "C:\Program Files\Git\bin\bash.exe" -lc "set -o pipefail && npm run lint && npm run test"
- Không tự cài phần mềm hệ thống, không sửa PATH. Gói trong backend\.venv, backend\.venv-tts, npm chỉ cài khi kế hoạch đã duyệt có ghi.
- Không dừng giữa đợt để hỏi; chỗ chưa rõ chọn phương án an toàn nhất, ghi "Cần chốt" trong báo cáo cuối.
- `gh` đã đăng nhập: tự kiểm CI bằng `gh run list` / `gh run watch`, ghi link run vào báo cáo.
- Không `git push --force`, không rebase, không dời tag, không xoá `workspace/projects/*`.
- **Quy ước 5 Nhánh & 4 Tag Cố Định (chống nhầm nhánh):** Repo chỉ duy trì đúng 5 nhánh chính thức (`main`, `GD1-HBT`, `GD2-PostV`, `GD3-Chatting`, `GD4-StickV`) và tag chuẩn `v1`–`v4` (tiếp tục `v5`, `v6`... hoặc `v4.1`). Cấm để tồn đọng nhánh `feat/*` rác sau khi merge. **Pre-flight Branch Check:** Trước khi sửa bất kỳ file nào, bắt buộc in `git branch --show-current` và `git log -1 --oneline` để xác nhận đang đứng đúng nhánh chủ dự án yêu cầu.
