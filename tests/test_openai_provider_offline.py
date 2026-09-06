"""
Unit test cho app/ai/openai_provider.py — KHÔNG gọi API OpenAI thật.

🔒 Mục tiêu test này KHÁC `test_groq_provider_offline.py`: vì
`translate()`/`suggest_answer()`/`summarize()` đã CHUYỂN sang
`OpenAICompatProvider` (dùng chung, đã test đầy đủ qua GroqProvider), test
ở đây CHỦ Ý chỉ tập trung vào phần RIÊNG của `OpenAIProvider`:
1. `__init__()` đọc đúng key theo thứ tự ưu tiên + đúng tên biến môi
   trường/provider ("openai", KHÁC "groq").
2. `transcribe()` dùng đúng model "whisper-1" + parse response ĐÚNG
   (cùng hình dạng Whisper verbose_json — tái dùng `whisper_utils`).
3. 1-2 test "đại diện" xác nhận translate()/suggest_answer() THỰC SỰ gọi
   được qua provider này (không chỉ tin tưởng kế thừa đúng) — KHÔNG lặp
   lại toàn bộ ~40 test đã có ở test_groq_provider_offline.py cho từng
   nhánh prompt/retry (logic đó dùng chung, đã verify kỹ ở đó rồi).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import httpx  # noqa: E402
import openai  # noqa: E402

from app import config_store  # noqa: E402
from app.ai import openai_compat_base  # noqa: E402
from app.ai.base_provider import ProviderError  # noqa: E402
from app.ai.openai_provider import OpenAIProvider  # noqa: E402


class _FakeSegment:
    def __init__(self, avg_logprob, no_speech_prob):
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class _FakeTranscriptionResponse:
    def __init__(self, text, language, segments):
        self.text = text
        self.language = language
        self.segments = segments


class _FakeChatChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeChatResponse:
    def __init__(self, content):
        self.choices = [_FakeChatChoice(content)]


class _FakeAudioTranscriptions:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.called_models = []

    def create(self, **kwargs):
        self.called_models.append(kwargs.get("model"))
        if self._error:
            raise self._error
        return self._response


class _FakeSequencedAudioTranscriptions:
    """🔒 MỚI (Backlog #2, CONTRACTS.md Mục 29) -- trả lần lượt theo
    `outcomes` (response HOẶC Exception), dùng để test retry (nhiều lần
    gọi liên tiếp CÙNG model) -- khác `_FakeAudioTranscriptions` ở trên chỉ
    trả 1 outcome cố định, không đủ để mô phỏng "lỗi 2 lần rồi thành công
    lần 3"."""

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.called_models: list[str] = []

    def create(self, **kwargs):
        self.called_models.append(kwargs.get("model"))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeAudio:
    def __init__(self, transcriptions):
        self.transcriptions = transcriptions


class _FakeChatCompletions:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, audio=None, chat=None):
        self.audio = audio
        self.chat = chat


def _make_provider_with_fake_client(fake_client, **kwargs):
    provider = OpenAIProvider(api_key="sk-fake-key-for-test", **kwargs)
    provider._client = fake_client
    return provider


def test_init_doc_key_tu_bien_moi_truong_openai_api_key():
    # 🔒 SỬA (Mục 26, cùng đợt audit sau bug config_store ở
    # test_groq_provider_offline.py -- xem CHANGELOG.md): trước đây KHÔNG
    # cách ly config_store.load_api_key -- nếu máy có key OpenAI thật đã
    # lưu qua Settings UI, resolved_key đọc được key thật đó TRƯỚC khi kịp
    # đọc env var (thứ tự ưu tiên: api_key tham số > config_store > env
    # var), assert sẽ fail vì lý do không liên quan gì tới logic "đọc env
    # var" mà test này thật sự muốn xác nhận.
    os.environ.pop("OPENAI_API_KEY", None)
    original_load = config_store.load_api_key
    config_store.load_api_key = lambda provider="groq", base_dir=None: None  # noqa: E731
    try:
        os.environ["OPENAI_API_KEY"] = "sk-fake-from-env"
        provider = OpenAIProvider()
        assert provider._client.api_key == "sk-fake-from-env"
    finally:
        os.environ.pop("OPENAI_API_KEY", None)
        config_store.load_api_key = original_load
    print("OK: test_init_doc_key_tu_bien_moi_truong_openai_api_key")


def test_init_thieu_key_raise_provider_error_voi_huong_dan_openai():
    os.environ.pop("OPENAI_API_KEY", None)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        original_load = config_store.load_api_key
        config_store.load_api_key = lambda provider="groq", base_dir=None: None  # noqa: E731
        try:
            try:
                OpenAIProvider(api_key=None)
                raise AssertionError("Phải raise ProviderError khi thiếu key.")
            except ProviderError as exc:
                assert "OpenAI" in str(exc)
                assert "platform.openai.com" in str(exc)
        finally:
            config_store.load_api_key = original_load
    print("OK: test_init_thieu_key_raise_provider_error_voi_huong_dan_openai")


def test_init_doc_key_tu_config_store_dung_provider_openai():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        config_store.save_api_key("sk-saved-via-settings", provider="openai", base_dir=base)
        # 🔒 Quan trọng: phải đọc đúng provider="openai", KHÔNG lẫn với
        # key "groq" (test khác dùng base_dir riêng, nhưng vẫn xác nhận
        # tường minh ở đây để bắt regression nếu provider bị hardcode nhầm).
        loaded = config_store.load_api_key(provider="openai", base_dir=base)
        assert loaded == "sk-saved-via-settings"
    print("OK: test_init_doc_key_tu_config_store_dung_provider_openai")


_CLIENT_TIMEOUT_ENV_VAR = "OPENAI_CLIENT_TIMEOUT_SECONDS"


def test_client_timeout_mac_dinh_30_giay_khong_phai_600_giay_cua_sdk():
    # 🔒 MỚI (Backlog #1, CONTRACTS.md Mục 28) -- xem lý do đầy đủ ở
    # tests/test_groq_provider_offline.py (cùng cơ chế dùng chung qua
    # `_resolve_client_timeout_seconds()` ở openai_compat_base.py).
    os.environ.pop(_CLIENT_TIMEOUT_ENV_VAR, None)
    provider = OpenAIProvider(api_key="sk-fake-key-for-test")
    assert provider._client.timeout == 30.0
    print("OK: test_client_timeout_mac_dinh_30_giay_khong_phai_600_giay_cua_sdk")


def test_client_timeout_tham_so_va_env_hoat_dong_dung_uu_tien():
    os.environ.pop(_CLIENT_TIMEOUT_ENV_VAR, None)
    try:
        p1 = OpenAIProvider(api_key="sk-fake-key-for-test", client_timeout_seconds=8.0)
        assert p1._client.timeout == 8.0

        os.environ[_CLIENT_TIMEOUT_ENV_VAR] = "15"
        p2 = OpenAIProvider(api_key="sk-fake-key-for-test")
        assert p2._client.timeout == 15.0

        p3 = OpenAIProvider(api_key="sk-fake-key-for-test", client_timeout_seconds=8.0)
        assert p3._client.timeout == 8.0, "Tham số trực tiếp phải thắng env"

        os.environ[_CLIENT_TIMEOUT_ENV_VAR] = "not-a-number"
        p4 = OpenAIProvider(api_key="sk-fake-key-for-test")
        assert p4._client.timeout == 30.0, "Env sai định dạng phải fallback default"
    finally:
        os.environ.pop(_CLIENT_TIMEOUT_ENV_VAR, None)
    print("OK: test_client_timeout_tham_so_va_env_hoat_dong_dung_uu_tien")


def test_transcribe_retry_ket_noi_mang_giu_nguyen_model_khong_fallback():
    # 🔒 MỚI (Backlog #2, CONTRACTS.md Mục 29) -- xác nhận transcribe() của
    # OpenAIProvider CŨNG có lớp retry mới (dùng chung _call_with_retry/
    # _call_with_fallback với Groq, xem test đầy đủ ở
    # test_groq_provider_offline.py) -- không lặp lại toàn bộ kịch bản ở
    # đó, chỉ 1 test "đại diện" xác nhận wiring đúng qua provider này.
    fake_response = _FakeTranscriptionResponse(
        text="hello retry", language="english",
        segments=[_FakeSegment(avg_logprob=-0.1, no_speech_prob=0.02)],
    )
    transcriptions = _FakeSequencedAudioTranscriptions([
        openai.APIConnectionError(
            message="Connection error.",
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        ),
        fake_response,
    ])
    fake_client = _FakeClient(audio=_FakeAudio(transcriptions))
    provider = _make_provider_with_fake_client(fake_client)
    original_sleep = openai_compat_base._sleep_backoff
    openai_compat_base._sleep_backoff = lambda seconds: None
    try:
        result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    finally:
        openai_compat_base._sleep_backoff = original_sleep
    assert result.text == "hello retry"
    assert transcriptions.called_models == ["whisper-1", "whisper-1"], (
        f"Phải retry GIỮ NGUYÊN model whisper-1 (không có fallback model "
        f"mặc định của OpenAI, xem docstring __init__), nhận {transcriptions.called_models}."
    )
    print("OK: test_transcribe_retry_ket_noi_mang_giu_nguyen_model_khong_fallback")


def test_transcribe_dung_model_whisper_1_va_parse_dung():
    fake_response = _FakeTranscriptionResponse(
        text="  Hello from OpenAI  ", language="english",
        segments=[_FakeSegment(avg_logprob=-0.1, no_speech_prob=0.02)],
    )
    fake_transcriptions = _FakeAudioTranscriptions(response=fake_response)
    fake_client = _FakeClient(audio=_FakeAudio(fake_transcriptions))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    assert result.text == "Hello from OpenAI"
    assert result.language == "en", "Phải tái dùng _normalize_language_to_iso (whisper_utils) đúng."
    assert 0.0 <= result.confidence <= 1.0
    assert fake_transcriptions.called_models == ["whisper-1"], (
        f"Phải gọi đúng model whisper-1 mặc định, nhận {fake_transcriptions.called_models}."
    )
    print("OK: test_transcribe_dung_model_whisper_1_va_parse_dung")


def test_transcribe_khong_fallback_model_mac_dinh_429_raise_thang():
    # Mặc định stt_fallback_model="" (TẮT fallback, xem docstring
    # OpenAIProvider.__init__ -- whisper-1 không có model rẻ hơn tương tự
    # whisper-large-v3-turbo của Groq) -- 429 phải raise THẲNG, không thử
    # lại model nào khác.
    #
    # 🔒 SỬA (02/09/2026): SDK `openai` hiện tại BẮT BUỘC `message` làm
    # tham số dương đầu tiên cho RateLimitError -- gọi thiếu message như
    # code CŨ raise TypeError ngay khi TẠO exception giả (lỗi của TEST,
    # không phải app thật) trên SDK mới hơn (xem cùng lý do đã sửa ở
    # test_groq_provider_offline.py, CONTRACTS.md Mục 19).
    fake_message = "Rate limit reached"
    fake_resp = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
    )
    fake_transcriptions = _FakeAudioTranscriptions(
        error=openai.RateLimitError(
            fake_message, response=fake_resp,
            body={"error": {"message": fake_message, "type": "invalid_request_error", "code": "rate_limit_exceeded"}},
        )
    )
    fake_client = _FakeClient(audio=_FakeAudio(fake_transcriptions))
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi 429 và không có fallback.")
    except ProviderError:
        pass
    assert fake_transcriptions.called_models == ["whisper-1"], (
        "KHÔNG được thử model thứ 2 nào -- fallback đang tắt mặc định."
    )
    print("OK: test_transcribe_khong_fallback_model_mac_dinh_429_raise_thang")


def test_transcribe_wrap_loi_thanh_provider_error():
    fake_client = _FakeClient(
        audio=_FakeAudio(_FakeAudioTranscriptions(error=openai.APIConnectionError(request=None)))
    )
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi API lỗi.")
    except ProviderError:
        pass
    print("OK: test_transcribe_wrap_loi_thanh_provider_error")


def test_translate_dung_duoc_qua_openai_provider_dung_model_mac_dinh():
    # Test "đại diện" duy nhất cho phần chat -- xác nhận OpenAIProvider
    # THỰC SỰ kế thừa & gọi được OpenAICompatProvider.translate() đúng
    # model mặc định "gpt-5-mini" (logic prompt/retry/parse đã test đầy đủ
    # qua GroqProvider, KHÔNG lặp lại ở đây).
    captured = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured["model"] = kwargs["model"]
            return _FakeChatResponse(content="Xin chào")

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.translate("Hello", source_lang="en", target_lang="vi")
    assert result == "Xin chào"
    assert captured["model"] == "gpt-5-mini"
    print("OK: test_translate_dung_duoc_qua_openai_provider_dung_model_mac_dinh")


def test_auth_error_hint_nhac_dung_url_openai_khong_phai_groq():
    # 🔒 SỬA (02/09/2026, cùng lý do đã sửa ở trên) -- response=None làm
    # SDK mới lỗi TypeError/AttributeError ngay lúc TẠO exception giả,
    # không phải lỗi thật đang test -- dùng httpx.Response thật.
    fake_message = "Invalid API Key"
    fake_resp = httpx.Response(
        status_code=401,
        request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
    )
    fake_client = _FakeClient(
        audio=_FakeAudio(_FakeAudioTranscriptions(
            error=openai.AuthenticationError(
                fake_message, response=fake_resp,
                body={"error": {"message": fake_message, "type": "invalid_request_error", "code": "invalid_api_key"}},
            )
        ))
    )
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi 401.")
    except ProviderError as exc:
        assert "platform.openai.com" in str(exc), "Message lỗi phải trỏ đúng URL OpenAI, không phải Groq."
        assert "console.groq.com" not in str(exc), "KHÔNG được lẫn URL Groq vào message lỗi của OpenAI."
    print("OK: test_auth_error_hint_nhac_dung_url_openai_khong_phai_groq")


if __name__ == "__main__":
    test_init_doc_key_tu_bien_moi_truong_openai_api_key()
    test_init_thieu_key_raise_provider_error_voi_huong_dan_openai()
    test_init_doc_key_tu_config_store_dung_provider_openai()
    test_client_timeout_mac_dinh_30_giay_khong_phai_600_giay_cua_sdk()
    test_client_timeout_tham_so_va_env_hoat_dong_dung_uu_tien()
    test_transcribe_retry_ket_noi_mang_giu_nguyen_model_khong_fallback()
    test_transcribe_dung_model_whisper_1_va_parse_dung()
    test_transcribe_khong_fallback_model_mac_dinh_429_raise_thang()
    test_transcribe_wrap_loi_thanh_provider_error()
    test_translate_dung_duoc_qua_openai_provider_dung_model_mac_dinh()
    test_auth_error_hint_nhac_dung_url_openai_khong_phai_groq()
    print("\n=== TẤT CẢ TEST OPENAI_PROVIDER (OFFLINE/MOCK) PASS ===")
