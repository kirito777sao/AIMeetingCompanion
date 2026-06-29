"""
Phase 0 - Bước 1: Test thu âm loopback 10 giây.

Cách chạy (trên Windows, trong thư mục gốc dự án):
    python scripts/test_capture.py

Trước khi chạy: mở sẵn 1 video/audio nào đó (YouTube, nhạc...) để có tiếng
phát ra loa, vì script này ghi lại CHÍNH ÂM THANH ĐANG PHÁT, không phải mic.

Kết quả: file test_audio/sample.wav
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.audio.capture import record_system_audio, AudioCaptureError  # noqa: E402

if __name__ == "__main__":
    out_path = os.path.join("test_audio", "sample.wav")
    print("Sẽ ghi âm 10 giây audio hệ thống. Hãy đảm bảo đang có âm thanh phát ra loa...")
    print("Bắt đầu ghi trong 2 giây...")
    import time

    time.sleep(2)
    try:
        record_system_audio(out_path, duration=10.0)
    except AudioCaptureError as e:
        print(f"LỖI: {e}")
        sys.exit(1)

    print(f"Đã ghi xong. File lưu tại: {out_path}")
    print("Tiếp theo: chạy `python scripts/test_groq_whisper.py` để kiểm tra STT.")
