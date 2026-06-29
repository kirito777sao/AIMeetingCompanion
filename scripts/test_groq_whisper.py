"""
Phase 0 - Bước 2: Gửi file wav lên Groq Whisper API, in transcript ra console.

Yêu cầu trước khi chạy:
    1. Tạo file .env (copy từ .env.example) và điền GROQ_API_KEY=<key thật của bạn>
    2. Đã chạy scripts/test_capture.py để có file test_audio/sample.wav
       (hoặc chỉ định file khác qua argument)

Cách chạy:
    python scripts/test_groq_whisper.py
    python scripts/test_groq_whisper.py duong/dan/khac.wav
"""

import os
import sys

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def transcribe_file(path: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Thiếu GROQ_API_KEY. Hãy tạo file .env (copy từ .env.example) và điền key thật."
        )

    client = Groq(api_key=api_key)
    with open(path, "rb") as f:
        # response_format="text" để in thẳng ra string, không cần parse JSON
        result = client.audio.transcriptions.create(
            file=(os.path.basename(path), f.read()),
            model="whisper-large-v3-turbo",
            response_format="text",
        )
    return result


if __name__ == "__main__":
    wav_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("test_audio", "sample.wav")

    if not os.path.exists(wav_path):
        print(f"Không tìm thấy file: {wav_path}")
        print("Hãy chạy `python scripts/test_capture.py` trước, hoặc chỉ định đúng đường dẫn.")
        sys.exit(1)

    print(f"Đang gửi {wav_path} lên Groq Whisper API (whisper-large-v3-turbo)...")
    try:
        text = transcribe_file(wav_path)
    except Exception as e:  # noqa: BLE001 - in lỗi rõ ràng cho người mới học
        print(f"LỖI khi gọi Groq API: {e}")
        print("Nếu là lỗi 429: đã hết quota free tier, đợi reset hoặc xem README phần xử lý 429.")
        sys.exit(1)

    print("\n--- TRANSCRIPT ---")
    print(text)
    print("------------------")
