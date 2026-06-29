"""
Unit test cho app/ai/gemini_provider.py — KHÔNG gọi network thật.

🔒 Khác `test_groq_provider_offline.py`/`test_openai_provider_offline.py`:
`transcribe()` của Gemini KHÔNG đi qua SDK `openai` (xem docstring đầu file
`gemini_provider.py`) nên KHÔNG monkeypatch `provider._client` cho phần
này -- monkeypatch trực tiếp `provider._post_generate_content` (method
tách riêng đúng để test làm việc này), tránh phải giả lập `httpx.Response`
đầy đủ.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from app import config_store  # noqa: E402
from app.ai.base_provider import ProviderError  # noqa: E402
from app.ai.gemini_provider import GeminiProvider  # noqa: E402


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


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, chat=None):
        self.chat = chat


def _make_provider(**kwargs) -> GeminiProvider:
    return GeminiProvider(api_key="fake-gemini-key-for-test", **kwargs)


def test_init_doc_key_tu_bien_moi_truong_gemini_api_key():
    os.environ.pop("GEMINI_API_KEY", None)
    try:
        os.environ["GEMINI_API_KEY"] = "fake-from-env"
        provider = GeminiProvider()
        assert provider._api_key == "fake-from-env"
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
    print("OK: test_init_doc_key_tu_bien_moi_truong_gemini_api_key")


def test_init_thieu_key_raise_provider_error_voi_huong_dan_gemini():
    os.environ.pop("GEMINI_API_KEY", None)
    original_load = config_store.load_api_key
    config_store.load_api_key = lambda provider="groq", base_dir=None: None  # noqa: E731
    try:
        try:
            GeminiProvider(api_key=None)
            raise AssertionError("Phải raise ProviderError khi thiếu key.")
        except ProviderError as exc:
            assert "Gemini" in str(exc)
            assert "aistudio.google.com" in str(exc)
    finally:
        config_store.load_api_key = original_load
    print("OK: test_init_thieu_key_raise_provider_error_voi_huong_dan_gemini")


def test_transcribe_parse_dung_khi_co_giong_noi_thuc():
    provider = _make_provider()
    captured = {}

    def fake_post(model, payload):
        captured["model"] = model
        captured["payload"] = payload
        return {
            "transcript": "Hello world",
            "language_iso639_1": "en",
            "is_silence_or_nonspeech": False,
        }

    provider._post_generate_content = fake_post
    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)

    assert result.text == "Hello world"
    assert result.language == "en"
    assert result.no_speech_prob == 0.0, "is_silence_or_nonspeech=False -> no_speech_prob phải là 0.0."
    assert 0.0 <= result.confidence <= 1.0
    assert captured["model"] == "gemini-2.5-flash", "Phải dùng đúng stt_model mặc định."
    # responseSchema phải có đủ 3 field để model bị BẮT trả đúng cấu trúc.
    schema_props = captured["payload"]["generationConfig"]["responseSchema"]["properties"]
    assert set(schema_props.keys()) == {"transcript", "language_iso639_1", "is_silence_or_nonspeech"}
    print("OK: test_transcribe_parse_dung_khi_co_giong_noi_thuc")


def test_transcribe_im_lang_tra_no_speech_prob_1_khong_bia_text():
    # 🔒 Tương đương "lọc hallucination" của Whisper (CONTRACTS.md Mục 11)
    # nhưng bằng tự-báo-cáo của Gemini (xem mục 3 docstring đầu
    # gemini_provider.py) -- pipeline.py lọc dựa vào no_speech_prob >= 0.6,
    # nên is_silence_or_nonspeech=True PHẢI map thành đúng 1.0 (rõ về phía
    # "lọc bỏ" của ngưỡng đó), không phải 1 số mơ hồ ở giữa.
    provider = _make_provider()
    provider._post_generate_content = lambda model, payload: {
        "transcript": "",
        "language_iso639_1": "",
        "is_silence_or_nonspeech": True,
    }
    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    assert result.no_speech_prob == 1.0
    assert result.text == ""
    print("OK: test_transcribe_im_lang_tra_no_speech_prob_1_khong_bia_text")


def test_transcribe_wrap_loi_thanh_provider_error():
    provider = _make_provider()

    def fake_post(model, payload):
        raise ProviderError("Gemini STT API lỗi (HTTP 500): giả lập lỗi server")

    provider._post_generate_content = fake_post
    try:
        provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi API lỗi.")
    except ProviderError:
        pass
    print("OK: test_transcribe_wrap_loi_thanh_provider_error")


def test_translate_dung_duoc_qua_gemini_provider_dung_model_mac_dinh():
    # Test "đại diện" cho phần chat (qua lớp tương thích OpenAI của
    # Google) -- xác nhận GeminiProvider kế thừa OpenAICompatProvider
    # đúng, gọi đúng model mặc định "gemini-2.5-flash". Logic prompt/
    # retry/parse đã test đầy đủ qua GroqProvider, không lặp lại ở đây.
    captured = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured["model"] = kwargs["model"]
            return _FakeChatResponse(content="Xin chào")

    provider = _make_provider()
    provider._client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))

    result = provider.translate("Hello", source_lang="en", target_lang="vi")
    assert result == "Xin chào"
    assert captured["model"] == "gemini-2.5-flash"
    print("OK: test_translate_dung_duoc_qua_gemini_provider_dung_model_mac_dinh")


def test_post_generate_content_429_raise_provider_error_khong_co_fallback():
    # Gemini KHÔNG có model STT dự phòng (khác Groq/OpenAI) -- xác nhận
    # 429 ở REST endpoint thật raise ProviderError ngay, không cố thử lại
    # model nào khác (chỉ verify message rõ ràng, KHÔNG gọi network thật:
    # monkeypatch toàn bộ httpx.Client bằng fake trả response status 429).
    import app.ai.gemini_provider as gemini_provider_module

    class _FakeResponse429:
        status_code = 429
        text = "RESOURCE_EXHAUSTED"

    class _FakeHttpxClient:
        def __init__(self, timeout=None):
            pass

        def post(self, url, json=None, headers=None, **kwargs):
            return _FakeResponse429()

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

    original_client_cls = gemini_provider_module.httpx.Client
    gemini_provider_module.httpx.Client = _FakeHttpxClient
    try:
        provider = _make_provider()
        try:
            provider._post_generate_content("gemini-2.5-flash", {"contents": []})
            raise AssertionError("Phải raise ProviderError khi 429.")
        except ProviderError as exc:
            assert "429" in str(exc) or "giới hạn tần suất" in str(exc)
    finally:
        gemini_provider_module.httpx.Client = original_client_cls
    print("OK: test_post_generate_content_429_raise_provider_error_khong_co_fallback")


if __name__ == "__main__":
    test_init_doc_key_tu_bien_moi_truong_gemini_api_key()
    test_init_thieu_key_raise_provider_error_voi_huong_dan_gemini()
    test_transcribe_parse_dung_khi_co_giong_noi_thuc()
    test_transcribe_im_lang_tra_no_speech_prob_1_khong_bia_text()
    test_transcribe_wrap_loi_thanh_provider_error()
    test_translate_dung_duoc_qua_gemini_provider_dung_model_mac_dinh()
    test_post_generate_content_429_raise_provider_error_khong_co_fallback()
    print("\n=== TẤT CẢ TEST GEMINI_PROVIDER (OFFLINE/MOCK) PASS ===")
