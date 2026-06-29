"""
Phase 2 - Bước 1: Test thật suggest_answer() — KHÔNG cần UI, chỉ gọi trực
tiếp qua terminal để bạn tự đánh giá CHẤT LƯỢNG câu trả lời gợi ý trước khi
tôi xây UI (nút "Nhờ AI trả lời" + Suggestion Drawer) bao quanh nó.

Yêu cầu trước khi chạy: đã có file .env với GROQ_API_KEY thật (giống Phase 0/1).

Cách chạy:
    python scripts/test_suggest_answer.py

Mặc định dùng 1 ví dụ câu hỏi tiếng Anh + ngôn ngữ mẹ đẻ "vi". Có thể tự
sửa 3 biến QUESTION / CONTEXT / USER_NATIVE_LANG dưới đây để thử tình huống
giống thật hơn (vd câu hỏi tiếng Trung, hoặc câu hỏi về số liệu để xem model
có tự bịa số hay trả placeholder đúng như đã thiết kế).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from app.ai.base_provider import ProviderError  # noqa: E402
from app.ai.groq_provider import GroqProvider  # noqa: E402

load_dotenv()

# ---- Tự sửa 3 biến này để thử tình huống khác ----
CONTEXT = (
    "Boss: Let's do a quick check-in on the project before we move on.\n"
    "Boss: I want to understand where things stand right now."
)
QUESTION = "So, what's our current customer churn rate this quarter?"
USER_NATIVE_LANG = "vi"
# ---------------------------------------------------


def main() -> int:
    try:
        provider = GroqProvider()
    except ProviderError as exc:
        print(f"LỖI khởi tạo provider: {exc}")
        return 1

    print("=== ĐẦU VÀO ===")
    print(f"Ngữ cảnh:\n{CONTEXT}\n")
    print(f"Câu hỏi: {QUESTION}")
    print(f"Ngôn ngữ mẹ đẻ: {USER_NATIVE_LANG}\n")

    print("Đang gọi Groq để soạn gợi ý trả lời...")
    try:
        suggestion = provider.suggest_answer(
            question_text=QUESTION, context_text=CONTEXT, user_native_lang=USER_NATIVE_LANG,
        )
    except ProviderError as exc:
        print(f"LỖI khi gọi Groq API: {exc}")
        print("Nếu là lỗi 429: đã hết quota free tier, đợi reset hoặc xem README phần xử lý 429.")
        return 1

    print("\n--- GỢI Ý TRẢ LỜI ---")
    print(suggestion)
    print("---------------------\n")

    print("Tự đánh giá (không có câu trả lời 'đúng/sai' tuyệt đối, chỉ cần xem có ổn không):")
    print("  1. Câu trả lời có TỰ NHIÊN, đọc lên nghe được không (không cứng/dịch máy)?")
    print("  2. Nếu câu hỏi cần số liệu cụ thể (như ví dụ mặc định) — model có TỰ BỊA số")
    print("     hay trả về placeholder kiểu [số liệu cụ thể] đúng như thiết kế?")
    print("  3. Độ dài 2-4 câu có hợp lý để đọc nhanh trong lúc họp không, hay dài/ngắn quá?")
    print("\nThử đổi QUESTION/CONTEXT trong file này sang vài tình huống khác (câu hỏi tiếng")
    print("Trung, câu hỏi không cần số liệu, câu hỏi khó/nhạy cảm...) rồi báo lại kết quả.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
