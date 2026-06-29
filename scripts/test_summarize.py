"""
Phase 3 - Bước 1: Test thật summarize() — KHÔNG cần UI, dùng TRỰC TIẾP dữ
liệu transcript thật đã có trong meetings.db (từ các phiên họp bạn đã ghi ở
Phase 1/2), để tự đánh giá chất lượng tóm tắt TRƯỚC khi tôi xây UI báo cáo
(Phase 3 Bước 2) bao quanh nó.

Yêu cầu trước khi chạy:
    1. Đã có file .env với GROQ_API_KEY thật.
    2. Đã có ít nhất 1 phiên họp trong meetings.db (chạy app ít nhất 1 lần).

Cách chạy:
    python scripts/test_summarize.py                  # tự lấy phiên họp MỚI NHẤT
    python scripts/test_summarize.py 3                 # chỉ định meeting_id = 3
    python scripts/test_summarize.py --db duong/khac.db 3
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from app.ai.base_provider import ProviderError  # noqa: E402
from app.ai.groq_provider import GroqProvider  # noqa: E402
from app.report import build_transcript_text  # noqa: E402
from app.storage.db import MeetingStore, StorageError  # noqa: E402

load_dotenv()


def _format_bullet_list(items: list[str]) -> str:
    """In list[str] ra dạng bullet người đọc được, hoặc '(Không có)' nếu
    rỗng — [] nghĩa là model đã xác nhận thật không có gì (xem
    SummaryResult docstring), KHÔNG phải lỗi/thiếu dữ liệu."""
    if not items:
        return "(Không có)"
    return "\n".join(f"- {item}" for item in items)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_id", type=int, nargs="?", default=None,
                        help="ID phiên họp cần tóm tắt (mặc định: mới nhất)")
    parser.add_argument("--db", default="meetings.db", help="Đường dẫn file DB")
    args = parser.parse_args()

    try:
        provider = GroqProvider()
    except ProviderError as exc:
        print(f"LỖI khởi tạo provider: {exc}")
        return 1

    try:
        store = MeetingStore(args.db)
    except StorageError as exc:
        print(f"LỖI mở database {args.db}: {exc}")
        return 1

    try:
        meetings = store.list_meetings()
        if not meetings:
            print(f"Không có phiên họp nào trong {args.db}. Hãy chạy app ghi ít nhất 1 lần trước.")
            return 1

        if args.meeting_id is not None:
            meeting = next((m for m in meetings if m[0] == args.meeting_id), None)
            if meeting is None:
                print(f"Không tìm thấy phiên họp #{args.meeting_id}. Các phiên có sẵn:")
                for m in meetings:
                    print(f"  #{m[0]}  bắt đầu {m[1]}  ngôn ngữ mẹ đẻ={m[3]}")
                return 1
        else:
            meeting = meetings[0]  # list_meetings() trả mới nhất trước

        meeting_id, started_at, ended_at, user_native_lang = meeting
        print(f"=== Phiên họp #{meeting_id} (bắt đầu {started_at}, ngôn ngữ mẹ đẻ={user_native_lang}) ===")

        transcript_text = build_transcript_text(store, meeting_id)
        if not transcript_text:
            print(f"Phiên họp #{meeting_id} không có segment nào (transcript rỗng).")
            return 1
        print(f"Transcript: {len(transcript_text.splitlines())} dòng, {len(transcript_text)} ký tự.\n")

    except StorageError as exc:
        print(f"LỖI đọc database: {exc}")
        return 1
    finally:
        store.close()

    print("Đang gọi Groq để tổng hợp biên bản...")
    try:
        summary = provider.summarize(transcript_text, user_native_lang)
    except ProviderError as exc:
        print(f"LỖI khi gọi Groq API: {exc}")
        print("Nếu là lỗi 429: đã hết quota free tier, đợi reset hoặc xem README phần xử lý 429.")
        return 1

    print("\n--- TÓM TẮT ---")
    print(summary.overview)
    print("\n--- QUYẾT ĐỊNH ---")
    print(_format_bullet_list(summary.decisions))
    print("\n--- VIỆC CẦN LÀM ---")
    print(_format_bullet_list(summary.action_items))
    print("---------------------\n")

    print("Tự đánh giá:")
    print("  1. Tóm tắt có đúng nội dung chính cuộc họp/đoạn audio không, hay lệch ý?")
    print("  2. Phần 'Quyết định' — nếu cuộc họp KHÔNG có quyết định rõ ràng (vd chỉ là")
    print("     podcast/video test), model có THÀNH THẬT nói không có, hay tự bịa ra")
    print("     1 quyết định nào đó cho có? (đây là điểm rủi ro nhất, kiểm tra kỹ).")
    print("  3. Có đoạn nào tóm tắt sai do lỗi transcribe gốc (STT nghe nhầm) không —")
    print("     đây là lỗi DI TRUYỀN từ Phase 1, không phải lỗi của summarize() riêng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
