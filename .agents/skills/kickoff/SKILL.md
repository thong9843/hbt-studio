---
name: kickoff
description: Dùng khi tôi gõ "kickoff" hoặc "/kickoff" kèm máy và việc để bắt đầu một đợt HBT Studio. Đọc bối cảnh, báo kế hoạch, KHÔNG code. Không dùng giữa đợt.
---

# Kickoff đợt HBT Studio

Máy và việc: lấy từ câu tôi gõ kèm "kickoff".
Chưa viết code, chưa sửa file. Làm lần lượt:

1. Đọc CLAUDE.md, GEMINI.md; PLAN.md mục 6, 10, 11; IMPLEMENT.md mục 0, mục 11 và các mục mốc đó trỏ tới; docs/postv/IMPLEMENT-POSTV.md nếu việc thuộc PostV.
2. Không đọc DESIGN.md của getdesign. Giao diện theo DESIGN-HBT.md.
3. Chạy git status, git branch --show-current, git log --oneline -5, git stash list.
4. Báo ngắn dạng bảng: máy (có/không GPU); mốc đang mở, nhánh, việc xong/chưa; việc phiên này + mục đặc tả; luật sẽ áp; điểm chưa rõ; kế hoạch (commit | file | test | dòng).
5. Chờ tôi duyệt rồi mới làm.
