"""Phân hệ HBT Core Tự động hóa (V1 Bán tự động / V2 1-Click Prompt).

Kế thừa công nghệ tự động hóa từ PostV & Chatting:
- VieNeu-TTS tự động sinh giọng từng phân đoạn (segment), tính mốc micro-giây và bắn SSE.
- Nhạc nền BGM thông minh theo topic (history / fun / science / mystery) nối bằng acrossfade=d=2.0.
- Âm thanh hiệu ứng SFX chuyển thẻ kem / chuyển ảnh từ library/sfx/.
- Kẹp tài nguyên FFmpeg (-threads 2, -filter_threads 2, -preset veryfast, -crf 22,
  -max_muxing_queue_size 512) và giải phóng RAM Pillow (.close() + gc.collect()).
"""
