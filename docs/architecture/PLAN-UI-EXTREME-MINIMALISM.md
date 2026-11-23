# HBT STUDIO — ĐẶC TẢ TINH GỌN CỰC ĐOAN & NÂNG CHẤT GIAO DIỆN (STUDIO CRAFT)

> **Triết lý:** Đơn giản tới mức cực đoan khi nhìn vào — hiệu quả tức thì khi thao tác. Không dùng Three.js, không `backdrop-blur` diện rộng, không animation chạy rảnh.

---

## 1. BẤT BIẾN & PHẠM VI

- **Nhánh làm việc:** Trực tiếp trên `main` (theo quy ước việc ngoài luồng/UI chung).
- **Vùng cấm tuyệt đối:** Không sửa `backend/hbt/pipeline/`, `backend/hbt/models.py`, `reference/`, `backend/hbt/api/projects.py`, `backend/hbt/postv/`, `backend/hbt/chatting/`.
- **Quy chuẩn:** Toàn bộ chuỗi hiển thị tiếng Việt nằm trong `frontend/src/i18n/vi.ts`, font `Be Vietnam Pro` local, WCAG `>= 4.5:1` cả Light & Dark, giữ nguyên dữ liệu local `library/`, `workspace/`, `assets/`, `brand/` và 2 stash cũ.
- **Kiểm thử cuối đợt (duy nhất 1 lần qua Git Bash):**
  `"C:\Program Files\Git\bin\bash.exe" -lc 'set -o pipefail && npm run lint && npm run test:fast && npm run build'`

---

## 2. BẢNG CẮT GIẢM 60% CHỮ THỪA (NGẮN, ĐÚNG NGHĨA, KHÔNG BỊA)

| Vị trí                        | Chữ dài dòng / lộ mã hiện tại                                                                                                                                                            | Chuẩn tinh gọn mới                                                                                                                                                                                                                                                                                       |
| :---------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trang chủ — Đầu trang**     | Badge `HBT Studio v5.0 · Next-Gen Creator Workstation` + `Chào buổi sáng, hôm nay bạn muốn dựng video gì?` + `Chọn một động cơ bên dưới để bắt đầu dựng video tiếng Việt chuẩn 60fps.`   | Xóa badge & dòng phụ. Chỉ giữ 1 dòng duy nhất: **`Hôm nay dựng gì?`** + ô tìm kiếm gọn + chip thống kê nhỏ bên phải.                                                                                                                                                                                     |
| **Trang chủ — 4 thẻ động cơ** | `Video Kiến thức & Khám phá` + `Video kiến thức 10–12 cảnh từ ý tưởng AI` + nút `Tạo kịch bản AI` (tương tự 3 thẻ kia)                                                                   | Tên ngắn 2 từ + 1 dòng phụ `<= 6 từ` + nút 2 từ:<br>• **HBT Core** · `Kiến thức 10–12 cảnh` · **`Mở Core`**<br>• **PostV** · `Bài đăng Reddit & Threads` · **`Mở PostV`**<br>• **Chatting** · `Hội thoại tin nhắn 60fps` · **`Mở Chatting`**<br>• **StickV** · `Kể chuyện nhân vật 2D` · **`Mở StickV`** |
| **Chatting — Tab & Nút**      | `Từ bài viết / Link (AI viết)` · `Dán kịch bản trực tiếp (Bypass LLM)` · phụ đề ghi `Zalo` nhưng Topbar ghi `Instagram`                                                                  | **`Từ bài viết`** · **`Dán kịch bản`** · Đồng bộ phụ đề khớp nền tảng thực tế (`Messenger / Instagram`).                                                                                                                                                                                                 |
| **HBT Core — Ô nhập**         | `Nhập chủ đề hoặc ý tưởng video sự thật thú vị (vd: ...)` · `Tiêu đề thẻ kem #1` · `Lời thoại phân đoạn 1` · `Prompt ảnh ComfyUI (Tiếng Anh) #1` · `Ảnh phân đoạn 1` · `SFX phân đoạn 1` | **`Nhập chủ đề video...`** · **`Tiêu đề thẻ`** · **`Lời thoại`** · **`Prompt ảnh`** · **`Ảnh nền`** · **`Âm thanh`**                                                                                                                                                                                     |
| **StickV — Timeline & Tab**   | Tab `Kịch... 10` bị xén chữ; Timeline lộ mã tiếng Anh `think_chin`, `present_board`, `emphatic_chop`, `wave_hello`                                                                       | Tab bỏ icon thừa để đủ chỗ: **`Kịch bản`** · **`Hình ảnh`** · **`Âm thanh`** · **`Kiểm tra`**. Timeline hiện **`#1 · 4.8s`** + nhãn tiếng Việt gọn (hoặc bỏ mã pose, giữ 1 dòng tóm tắt lời thoại sắc nét).                                                                                              |

---

## 3. SỬA TRIỆT ĐỂ LỖI XÔ LỆCH, CẮT CHỮ & MẢNG TRỐNG

1. **Trang chủ (`/`) — Bố cục Bento chặt chẽ (Xóa mảng trắng trống 75%):**
   - Gỡ bỏ khung hộp trắng dài thênh thang đang trống 75% bên phải ở mục _Tiếp tục dự án dở_.
   - Gom **Dự án đang làm** và **Video vừa xuất** vào bố cục lưới Bento gọn gàng (2–3 cột cân đối theo chiều ngang, thẻ có tỷ lệ nhất quán, không để khoảng trắng chết).
   - Thay khung hình xám giả lập nhạt nhẽo trong 4 thẻ động cơ bằng **minh họa SVG tối giản, sắc nét** phản ánh đúng định dạng video (thẻ kem Core, bài đăng PostV, bong bóng chat, nhân vật Stickman).
2. **Sân khấu xem trước (`StageCanvas.tsx`) — Nâng chất bằng Dot-Grid Canvas:**
   - Thay khoảng xám trơn tẻ nhạt quanh khung video bằng nền lưới chấm kiến trúc siêu mảnh (`background-image: radial-gradient(...)`, thuần CSS tĩnh, `0%` CPU) + đổ bóng mềm đa tầng dưới khung video để khung xem trước nổi khối sang trọng.
3. **Dải phân cảnh (`SceneTimelineStrip.tsx`) trên cả StickV & HBT Core:**
   - Tăng chiều cao thẻ lên `84px`, padding gọn `10px 12px`, cố định dòng 1 (`#1` + thời lượng `tabular-nums`) và dòng 2 dùng `truncate` (`white-space: nowrap; overflow: hidden; text-overflow: ellipsis`) — chấm dứt 100% lỗi chữ bị cắt đôi theo chiều dọc.
4. **HBT Core (`/core` — `HbtCoreWorkspace.tsx`):**
   - Đưa về đúng bố cục **2 cột Studio đồng nhất với StickV** (Trái: soạn cảnh gọn trong `StudioShell`, Phải: sân khấu xem trước `9:16` trực tiếp trên nền Dot-Grid) thay vì biểu mẫu kéo dài toàn màn hình không thấy khung xem trước.
5. **Chatting (`/chatting` — `ChattingHome.tsx`):**
   - Khóa cụm tùy chọn dưới ô nhập vào lưới cố định **4 cột đều nhau** (`grid-cols-2 md:grid-cols-4 gap-3`), mỗi cột có nhãn nhỏ phía trên (`Nền tảng`, `Nền video`, `Model AI`, `Thời lượng`) và control thẳng hàng bên dưới — chấm dứt hoàn toàn lỗi nhãn `Model Gemini:` bị rớt lẻ loi cuối dòng.
