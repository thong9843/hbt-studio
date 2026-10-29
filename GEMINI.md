# GEMINI.md

Đọc toàn bộ CLAUDE.md trước khi làm bất cứ việc gì. Đó là luật chính của dự án.

## Bổ sung cho Antigravity
- Trong tài liệu repo, chữ "Claude Code" nghĩa là bạn (agent Antigravity). Mọi luật áp cho Claude Code đều áp cho bạn.
- Bắt đầu mỗi đợt bằng skill `kickoff` (.agents/skills/kickoff/SKILL.md).
- Windows: chạy test bằng Git Bash để `set -o pipefail` và `&&` chạy đúng:
  "C:\Program Files\Git\bin\bash.exe" -lc "set -o pipefail && npm run lint && npm run test"
- Không tự cài phần mềm hệ thống, không sửa PATH. Gói trong backend\.venv, backend\.venv-tts, npm chỉ cài khi kế hoạch đã duyệt có ghi.
- Không dừng giữa đợt để hỏi; chỗ chưa rõ chọn phương án an toàn nhất, ghi "Cần chốt" trong báo cáo cuối.
- `gh` đã đăng nhập: tự kiểm CI bằng `gh run list` / `gh run watch`, ghi link run vào báo cáo.
- Không `git push --force`, không rebase, không dời tag, không xoá `workspace/projects/*`.