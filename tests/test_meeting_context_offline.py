"""
Unit test cho `meeting_context` (🔒 MỚI Vòng 9 — xem CONTRACTS.md Mục 18):
tham số optional mới của `AIProvider.suggest_answer()`, implement CHUNG ở
`app/ai/openai_compat_base.py` (dùng qua `GroqProvider` ở đây, vì logic dùng
CHUNG cho Groq/OpenAI/Gemini — xem docstring `OpenAICompatProvider`).

KHÔNG gọi API thật (cùng quy ước offline/mock với test_groq_provider_offline.py).
Không import fake helpers từ file test khác — mỗi file test tự chứa fake
riêng, độc lập chạy được qua `python3 tests/test_meeting_context_offline.py`
(đúng convention đã có của dự án).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.groq_provider import GroqProvider  # noqa: E402


class _FakeChatChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeChatResponse:
    def __init__(self, content):
        self.choices = [_FakeChatChoice(content)]


class _FakeChatCompletions:
    def __init__(self, response=None):
        self._response = response

    def create(self, **kwargs):
        return self._response


class _CapturingChatCompletions:
    """Không trả response cố định -- ghi lại `messages` gửi đi mỗi lần gọi,
    để assert NỘI DUNG prompt (không chỉ kết quả cuối)."""

    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeChatResponse(content="ok")


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, chat=None):
        self.chat = chat


def _make_provider_with_fake_client(fake_client):
    provider = GroqProvider(api_key="fake-key-for-test")
    provider._client = fake_client  # ghi đè client thật bằng fake, không gọi network
    return provider


def test_suggest_answer_khong_truyen_meeting_context_van_hoat_dong_nhu_cu():
    """Backward-compat: mọi lời gọi CŨ (3 tham số vị trí, không biết khái
    niệm meeting_context) phải tiếp tục chạy đúng y hệt trước Vòng 9 --
    đây là lý do meeting_context PHẢI có default "" (xem base_provider.py)."""
    fake_response = _FakeChatResponse(content="Câu trả lời không có bối cảnh.")
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.suggest_answer("Q?", "ctx", "vi")
    assert result == "Câu trả lời không có bối cảnh."
    print("OK: test_suggest_answer_khong_truyen_meeting_context_van_hoat_dong_nhu_cu")


def test_suggest_answer_meeting_context_duoc_nhet_vao_system_prompt():
    capturing = _CapturingChatCompletions()
    fake_client = _FakeClient(chat=_FakeChat(capturing))
    provider = _make_provider_with_fake_client(fake_client)

    provider.suggest_answer(
        "What's the timeline?", "ctx", "vi",
        meeting_context="Đây là buổi phỏng vấn xin việc vị trí Backend Developer. "
        "Tôi là ứng viên, người phỏng vấn là trưởng nhóm kỹ thuật.",
    )

    assert len(capturing.calls) == 1, "meeting_context hợp lệ không nên kích hoạt retry"
    system_msg = capturing.calls[0]["messages"][0]["content"]
    assert "phỏng vấn xin việc" in system_msg
    assert "BACKGROUND CONTEXT" in system_msg
    print("OK: test_suggest_answer_meeting_context_duoc_nhet_vao_system_prompt")


def test_suggest_answer_khong_co_meeting_context_thi_prompt_khong_co_block_thua():
    capturing = _CapturingChatCompletions()
    fake_client = _FakeClient(chat=_FakeChat(capturing))
    provider = _make_provider_with_fake_client(fake_client)

    provider.suggest_answer("Q?", "ctx", "vi")  # không truyền meeting_context

    system_msg = capturing.calls[0]["messages"][0]["content"]
    assert "BACKGROUND CONTEXT" not in system_msg
    print("OK: test_suggest_answer_khong_co_meeting_context_thi_prompt_khong_co_block_thua")


def test_suggest_answer_meeting_context_rong_khong_co_block_thua():
    """meeting_context="" (mặc định) phải hành xử giống hệt như KHÔNG
    truyền gì -- tránh trường hợp MeetingContextDialog trả về chuỗi rỗng
    (người dùng bỏ qua) mà vẫn vô tình chèn block prompt trống."""
    capturing = _CapturingChatCompletions()
    fake_client = _FakeClient(chat=_FakeChat(capturing))
    provider = _make_provider_with_fake_client(fake_client)

    provider.suggest_answer("Q?", "ctx", "vi", meeting_context="")

    system_msg = capturing.calls[0]["messages"][0]["content"]
    assert "BACKGROUND CONTEXT" not in system_msg
    print("OK: test_suggest_answer_meeting_context_rong_khong_co_block_thua")


def test_suggest_answer_meeting_context_khong_lam_mat_context_text_cu():
    """meeting_context (system prompt) và context_text (user content, cửa
    sổ trượt vài câu gần nhất) là 2 khái niệm TÁCH BIỆT -- thêm cái mới
    không được làm mất/đổi cái cũ."""
    capturing = _CapturingChatCompletions()
    fake_client = _FakeClient(chat=_FakeChat(capturing))
    provider = _make_provider_with_fake_client(fake_client)

    provider.suggest_answer(
        "What's the timeline?",
        "Boss: Let's review the quarterly numbers.",
        "vi",
        meeting_context="Buổi họp nội bộ phòng kinh doanh.",
    )

    user_msg = capturing.calls[0]["messages"][1]["content"]
    assert "Let's review the quarterly numbers" in user_msg
    assert "What's the timeline?" in user_msg
    print("OK: test_suggest_answer_meeting_context_khong_lam_mat_context_text_cu")


if __name__ == "__main__":
    test_suggest_answer_khong_truyen_meeting_context_van_hoat_dong_nhu_cu()
    test_suggest_answer_meeting_context_duoc_nhet_vao_system_prompt()
    test_suggest_answer_khong_co_meeting_context_thi_prompt_khong_co_block_thua()
    test_suggest_answer_meeting_context_rong_khong_co_block_thua()
    test_suggest_answer_meeting_context_khong_lam_mat_context_text_cu()
    print("\n=== TẤT CẢ TEST MEETING_CONTEXT (suggest_answer, Vòng 9) PASS ===")
