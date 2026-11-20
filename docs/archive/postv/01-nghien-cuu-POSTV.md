01 – Nghiên cứu: HBT Thread Studio

Ngày tra: 21/10/2026. Chỉ dùng thông tin công khai. Ký hiệu: [KC] đã kiểm chứng (có nguồn) · [SL] suy luận · [?] chưa biết.

1. ThreadViral (tham chiếu chính)
   Mục Nội dung
   Luồng Dán link bài Threads công khai (hoặc tự gõ văn bản) → hệ thống chọn bài + bình luận → duyệt ~1 phút → chọn giọng → chọn nhạc/hiệu ứng → tải MP4 (hoặc nhận qua Telegram) [KC]
   Tính năng Chọn bình luận tự động (ưu tiên được nhiều tương tác, lọc quảng cáo/spam) hoặc chọn tay; giọng Việt/Anh/Trung, nhiều giọng, gán giọng riêng từng câu; phụ đề từng từ; Brand Kit (tên, avatar, logo, kiểu phụ đề); sửa kịch bản trước khi dựng; xem lại rồi "Sửa nhanh / Chỉnh & render lại"; ảnh bìa; nhập từ link Shopee, văn bản, ảnh chụp tin nhắn [KC]
   Giá Trang chủ không nêu giá; tặng credit khi đăng ký, không cần thẻ [KC]. Gói/giá cụ thể [?]
   Giới hạn Chỉ bài công khai; video lưu 24 giờ; render vài phút; file Library xoá sau 30 ngày không dùng [KC]
   Pháp lý (điều khoản của chính họ) Người dùng tự chịu trách nhiệm quyền sử dụng nội dung; "đăng công khai không có nghĩa ai cũng được dùng lại"; nên ghi nguồn, dẫn link, xin phép, gỡ khi chủ nội dung yêu cầu; cấm lộ thông tin cá nhân, bóp méo ý tác giả [KC]
   Điểm yếu (của hướng đi) Phụ thuộc đám mây, video chỉ giữ 24h, phải trả credit; cách họ đọc bài từ link chưa rõ có nằm trong khuôn khổ Meta không [?]; dễ ra video "đọc lại nguyên văn" nếu người dùng không thêm góc nhìn [SL]

Nguồn: threadviral.com · Điều khoản ThreadViral · Hướng dẫn Sforum/CellphoneS

2. Công cụ tương tự
   Công cụ Nguồn vào Quy trình Giá công khai Điểm yếu / bài học
   Hooked – Reddit Post to Video Chủ đề (AI viết bài + bình luận giả) hoặc URL Reddit Chọn thời lượng 15–180s → kiểu thẻ mở đầu, hiện/ẩn tên tác giả → nền, giọng, nhạc, phụ đề → tạo; có API Pro $29/tháng ($290/năm, 1.000 credit); Lifetime $89 (dùng khoá API riêng); gói credit từ $19 [KC] AI tự bịa bài/bình luận → rủi ro "nội dung giả"; số ngôn ngữ ghi không nhất quán (25 hay 30+). Học: thẻ mở đầu tuỳ chọn hiện tên, đặt thời lượng đích, bình luận xen vào lời đọc
   StoryTok Link Reddit hoặc văn bản tự nhập Dán → chỉnh → tạo → tải Trả theo lượt: $8/10 video (≤5.000 ký tự/truyện), $35/50 video; không gói miễn phí [KC] Chủ yếu Reddit; nền tuỳ chỉnh chỉ cho gói trả phí; đóng nguồn. Học: nền gameplay 60fps là chuẩn thể loại
   Kapwing (quy trình Reddit story) Kịch bản tự dán (500–1.000 ký tự) Chọn bài → rút gọn, bỏ chửi thề → "Use My Own Script" → 9:16, kiểu phụ đề, B-roll, giọng → xuất 720p/1080p → chia sẻ TikTok Giá/watermark không nêu trong trang hướng dẫn; dán link làm B-roll chỉ cho Pro [KC] Bản chất là trình dựng đa dụng, không có bước chọn đoạn. Học: hướng dẫn chính họ khuyên xin phép + ghi nguồn truyện NoSleep, cắt ~750 từ
   Imagine.art Shorts Nhiều chế độ (Create/Captions/Auto Clipper…) Chọn chế độ → nhập Trang không nêu giá [?] Thông tin công khai quá ít để so sánh; chỉ ghi nhận

Nguồn: Hooked · StoryTok · Kapwing · Imagine.art

Nhận xét chung [SL]: cả nhóm đều là dịch vụ đám mây trả tiền theo lượt; không ai có bước "góc nhìn riêng của kênh" bắt buộc → đây là điểm khác biệt có thể bán và cũng là lớp bảo vệ trước rủi ro nội dung tái sử dụng. Công cụ chạy local, một người dùng, giọng Vbee + bộ dựng HBT Studio hiện có thì không bị giới hạn credit/24h.

3. Tra cứu quy định Threads/Meta
   3.1 Điều đã kiểm chứng [KC]

# Phát hiện Nguồn

1 Quy định "Automated Data Collection" của Meta: "Platform APIs are the only allowable means to access data programmatically, unless you have our prior written permission." Cấm dùng script/thư viện HTTP/mã tự động để lấy dữ liệu ngoài API, cấm gọi tới domain ngoài graph.facebook.com, cấm lấy dữ liệu chưa được API cung cấp hoặc thiếu quyền (có thể cần App Review). Áp dụng dù không cố ý hoặc không thành công. Meta – Automated Data Collection
2 Tổng quan Threads API ghi mục đích cho phép: tạo/đăng bài thay người dùng và chỉ hiển thị các bài đó cho chính người tạo. Không nói gì về đọc bài người khác. Threads API Overview
3 Keyword Search có tồn tại: cần threads_basic + threads_keyword_search. Chưa được duyệt → chỉ tìm được bài của chính tài khoản đăng nhập; được duyệt → tìm được bài công khai. Giới hạn 2.200 truy vấn/24h; không trả trường owner; từ khoá nhạy cảm trả mảng rỗng. Keyword Search
4 API lấy phản hồi (replies): tài liệu nói về "phản hồi do một người dùng tạo"; username, permalink chỉ có cho người dùng công khai và chính mình. Chưa thấy nói rõ có lấy được phản hồi của bài người khác hay không. Retrieve Replies
5 oEmbed: dùng cho bài công khai (không cần token trong ví dụ, 1.000 yêu cầu/giờ) nhưng chỉ để nhúng hiển thị; cấm dùng metadata/nội dung để phân tích, trích xuất, biến đổi hay lưu lại. oEmbed
6 Điều khoản Nền tảng Meta: cấm bán/cấp phép/mua Platform Data; phải xoá khi hết nhu cầu hoặc khi người dùng yêu cầu; cấm làm lộ danh tính (re-identify). Meta Platform Terms
7 Chính ThreadViral nêu trong điều khoản: bài đăng công khai không đồng nghĩa ai cũng được dùng lại. ThreadViral Terms
3.2 Chưa kiểm chứng được [?]
Điều khoản sử dụng Threads (Supplemental Terms) và Điều khoản dịch vụ Meta bản gốc: trang help.instagram.com không tải được nội dung, trang facebook.com chặn robot. Mình không đọc được nguyên văn, nên không trích dẫn điều khoản về giấy phép nội dung người dùng. Bạn nên tự mở: help.instagram.com/769983657850414.
Quy trình và tiêu chí App Review để được duyệt threads_keyword_search cho một công cụ cá nhân; có được duyệt cho mục đích "đọc bài người khác để làm video" hay không.
Cách ThreadViral lấy nội dung từ link (API, xin phép Meta, hay cách khác).
Luật bản quyền/tác giả Việt Nam áp dụng cho trích dẫn bình luận người khác. Mình không phải luật sư; đây là điểm nên hỏi chuyên gia nếu kênh kiếm tiền.
3.3 Kết luận suy luận [SL]
Câu hỏi Trả lời
Tự lấy bài Threads của người khác (kể cả công khai) bằng script có được phép không? Không, trừ khi qua API chính thức hoặc có văn bản cho phép của Meta (mục 1). Cào HTML/gọi link bằng mã tự động rơi vào nhóm bị cấm.
Qua API chính thức thì sao? Mơ hồ. Có endpoint tìm kiếm từ khoá công khai, nhưng cần App Review và Overview chỉ nêu mục đích "đăng bài/hiển thị cho chính người tạo". Dùng để dựng video từ bài người khác chưa có căn cứ rõ là được.
oEmbed? Không dùng được để lấy chữ làm video (cấm trích xuất/lưu).
Mặc định thiết kế Chỉ hỗ trợ dán thủ công. Có rủi ro khoá/hạn chế nếu làm khác. 4. Khuyến nghị cách lấy nội dung
Đường Quyết định Lý do
A. Dán văn bản bài + bình luận thủ công Đường chính, bắt buộc Người dùng tự đọc trên Threads và tự chép; công cụ không gửi yêu cầu nào tới Meta.
B. Dán link Chỉ lưu URL làm dòng dẫn nguồn + nút "Mở bài trong trình duyệt" để người dùng tự xem rồi dán chữ. Không tự tải trang. Tránh "yêu cầu tự động ngoài API".
C. Nhập file (.txt/.md/.docx/.json) Có Không liên quan Meta.
D. Threads API chính thức Không làm ở giai đoạn này. Ghi vào "ngoài phạm vi / xem lại sau" Chờ có văn bản rõ về quyền; có thể hỏi Meta Developer Support. Nếu làm sau: chỉ cho bài của chính kênh, tuỳ chọn, có cờ tắt.
E. Cào/headless/dịch vụ cào bên thứ ba Cấm trong thiết kế Nằm ngoài quy định Meta; thêm rủi ro với tài khoản.

Bù lại cho trải nghiệm kém hơn ThreadViral [SL]: làm bước dán nhanh (ô dán dán cả bài lẫn bình luận, tự tách theo dòng/dấu phân cách), nhập hàng loạt bình luận, gợi ý chọn đoạn bằng AI sau khi dán. Mất ~1–2 phút dán tay, đổi lại an toàn và dữ liệu ở lại máy.

Điều kiện bắt buộc đi kèm (đưa vào PRD): che danh tính mặc định, bước duyệt nguồn của con người, bắt buộc có phần góc nhìn của kênh, dẫn nguồn, kiểm tra từ nhạy cảm, và gỡ video khi chủ bài yêu cầu.

5. Câu hỏi cần bạn trả lời trước khi sang bước viết (2)–(6)
   Repo HBT Studio: phiên này chưa liên kết với máy của bạn nên mình chưa đọc được PLAN.md/IMPLEMENT.md. Bạn đính kèm 2 file đó (và nếu được project.json mẫu + cấu trúc thư mục) hay liên kết thư mục từ ứng dụng desktop?
   Đồng ý chốt "chỉ dán thủ công" làm mặc định (mục 4, đường D để sau)?
   Nơi lưu file: mình không ghi trực tiếp vào C:\Video_AI\hbt-thread-design\ được từ phiên này; mình giao file qua khung chat và bạn chép vào thư mục, hoặc liên kết thư mục để mình ghi thẳng. Bạn chọn cách nào?
