"""
Unit test cho app/ai/groq_provider.py — KHÔNG gọi API Groq thật (sandbox này
không có egress tới api.groq.com). Test 2 nhóm:

1. Hàm thuần (pure function) không cần network: _encode_wav_bytes,
   _estimate_confidence -- assert trực tiếp.
2. Logic transcribe()/translate() -- monkeypatch self._client bằng 1 fake
   client trả về response giả có đúng hình dạng attribute mà code thật kỳ
   vọng (response.text/.language/.segments, response.choices[0].message.content).
   Mục tiêu: xác nhận GroqProvider PARSE response đúng và WRAP lỗi đúng
   thành ProviderError -- không xác nhận được Groq API thật trả về đúng
   hình dạng đó hay không (phải tự chạy thật trên Windows để xác nhận điều
   này, như đã ghi rõ trong docstring đầu file groq_provider.py).
"""

import io
import json
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import httpx  # noqa: E402
import openai  # noqa: E402

from app.ai.base_provider import ProviderError  # noqa: E402
from app.ai.groq_provider import (  # noqa: E402
    GroqProvider,
    _encode_wav_bytes,
    _estimate_confidence,
    _estimate_no_speech_prob,
    _normalize_language_to_iso,
)


def test_normalize_language_voi_du_lieu_thuc_te_tu_groq():
    # Phát hiện thật từ file meetings.db do người dùng gửi: Groq trả
    # response.language = "English" (full word, viết hoa chữ đầu), KHÔNG
    # phải mã ISO "en" như CONTRACTS.md Mục 4 đã chốt.
    assert _normalize_language_to_iso("English") == "en"
    assert _normalize_language_to_iso("english") == "en"
    assert _normalize_language_to_iso("Vietnamese") == "vi"
    assert _normalize_language_to_iso("Chinese") == "zh"
    assert _normalize_language_to_iso("") == ""
    assert _normalize_language_to_iso("en") == "en", "Nếu API đổi hành vi, trả thẳng mã ISO vẫn phải qua được."
    assert _normalize_language_to_iso("Klingon") == "klingon", (
        "Ngôn ngữ lạ không có trong bảng: fallback lowercase, không raise lỗi."
    )
    print("OK: test_normalize_language_voi_du_lieu_thuc_te_tu_groq")


# --------------------------------------------------------------------------
# 1. Hàm thuần
# --------------------------------------------------------------------------

def test_encode_wav_bytes_dung_format():
    audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    wav_bytes = _encode_wav_bytes(audio, samplerate=16000)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1, "Phải encode mono."
        assert wf.getsampwidth() == 2, "Phải là PCM 16-bit."
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 5
    print("OK: test_encode_wav_bytes_dung_format")


def test_encode_wav_bytes_clip_dung_truoc_khi_quantize():
    # Giá trị > 1.0 hoặc < -1.0 phải bị clip, KHÔNG được overflow/wrap int16.
    audio = np.array([2.0, -2.0], dtype=np.float32)
    wav_bytes = _encode_wav_bytes(audio, samplerate=16000)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    assert samples[0] == 32767, f"Giá trị 2.0 sau clip+quantize phải là 32767, nhận {samples[0]}."
    assert samples[1] == -32767, f"Giá trị -2.0 sau clip+quantize phải là -32767, nhận {samples[1]}."
    print("OK: test_encode_wav_bytes_clip_dung_truoc_khi_quantize")


def test_encode_wav_bytes_reject_khong_phai_mono():
    audio = np.zeros((10, 2), dtype=np.float32)
    try:
        _encode_wav_bytes(audio, samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi audio không phải mono 1D.")
    except ProviderError:
        pass
    print("OK: test_encode_wav_bytes_reject_khong_phai_mono")


class _FakeSegment:
    def __init__(self, avg_logprob, no_speech_prob):
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


def test_estimate_confidence_rong_tra_0():
    assert _estimate_confidence(None) == 0.0
    assert _estimate_confidence([]) == 0.0
    print("OK: test_estimate_confidence_rong_tra_0")


def test_estimate_confidence_nam_trong_0_1():
    segs = [_FakeSegment(avg_logprob=-0.1, no_speech_prob=0.05),
            _FakeSegment(avg_logprob=-0.2, no_speech_prob=0.1)]
    conf = _estimate_confidence(segs)
    assert 0.0 <= conf <= 1.0, f"confidence phải trong [0,1], nhận {conf}."
    assert conf > 0.7, f"Với logprob gần 0 và no_speech_prob thấp, confidence phải cao, nhận {conf}."
    print("OK: test_estimate_confidence_nam_trong_0_1")


def test_estimate_no_speech_prob_rong_tra_0():
    assert _estimate_no_speech_prob(None) == 0.0
    assert _estimate_no_speech_prob([]) == 0.0
    print("OK: test_estimate_no_speech_prob_rong_tra_0")


def test_estimate_no_speech_prob_la_trung_binh_tho_khong_nhan_logprob():
    segs = [_FakeSegment(avg_logprob=-5.0, no_speech_prob=0.8),
            _FakeSegment(avg_logprob=-5.0, no_speech_prob=0.9)]
    no_speech = _estimate_no_speech_prob(segs)
    assert abs(no_speech - 0.85) < 1e-9, (
        f"Phải là trung bình THÔ của no_speech_prob (0.85), nhận {no_speech}."
    )
    print("OK: test_estimate_no_speech_prob_la_trung_binh_tho_khong_nhan_logprob")


def test_no_speech_prob_la_tin_hieu_chat_hon_confidence_cho_cau_ngan_nhung_thuc():
    # 🔒 Test này CHỨNG MINH lý do tách no_speech_prob riêng (CONTRACTS.md
    # Mục 11): 1 câu/từ NGẮN NHƯNG THẬT (vd "Human." bị VAD cắt lẻ) có thể
    # có confidence THẤP (model không chắc avg_logprob) NHƯNG no_speech_prob
    # vẫn THẤP (model biết chắc CÓ giọng nói) -- pipeline.py PHẢI giữ lại
    # segment này, KHÔNG được dùng confidence thấp để lọc bỏ.
    cau_ngan_nhung_thuc = [_FakeSegment(avg_logprob=-0.9, no_speech_prob=0.02)]
    confidence = _estimate_confidence(cau_ngan_nhung_thuc)
    no_speech = _estimate_no_speech_prob(cau_ngan_nhung_thuc)
    assert confidence < 0.5, f"Case minh hoạ cần confidence thấp, nhận {confidence}."
    assert no_speech < 0.1, f"Nhưng no_speech_prob phải vẫn thấp (CÓ giọng nói thật), nhận {no_speech}."
    print("OK: test_no_speech_prob_la_tin_hieu_chat_hon_confidence_cho_cau_ngan_nhung_thuc")


# --------------------------------------------------------------------------
# 2. transcribe()/translate() với fake client (không gọi network thật)
# --------------------------------------------------------------------------

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

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


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


class _FakeSequencedCompletions:
    """Trả lần lượt theo `outcomes` (mỗi phần tử là response HOẶC 1
    Exception instance để raise) — đồng thời ghi lại model được gọi mỗi
    lần vào `called_models`, dùng để test ĐÚNG thứ tự fallback (model nào
    gọi trước/sau), không chỉ kết quả cuối."""

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.called_models: list[str] = []

    def create(self, **kwargs):
        self.called_models.append(kwargs.get("model"))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeSequencedTranscriptions:
    """Tương tự `_FakeSequencedCompletions` nhưng cho audio.transcriptions."""

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.called_models: list[str] = []

    def create(self, **kwargs):
        self.called_models.append(kwargs.get("model"))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, audio=None, chat=None):
        self.audio = audio
        self.chat = chat


def _make_provider_with_fake_client(fake_client, **provider_kwargs):
    provider = GroqProvider(api_key="fake-key-for-test", **provider_kwargs)
    provider._client = fake_client  # ghi đè client thật bằng fake, không gọi network
    return provider


def test_transcribe_parse_dung_khi_thanh_cong():
    fake_response = _FakeTranscriptionResponse(
        text="  Hello world  ", language="en",
        segments=[_FakeSegment(avg_logprob=-0.1, no_speech_prob=0.0)],
    )
    fake_client = _FakeClient(audio=_FakeAudio(_FakeAudioTranscriptions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    assert result.text == "Hello world", f"Phải strip() khoảng trắng, nhận {result.text!r}."
    assert result.language == "en"
    assert 0.0 <= result.confidence <= 1.0
    assert result.no_speech_prob == 0.0, (
        f"segments có no_speech_prob=0.0 -- phải wire đúng vào TranscriptionResult, "
        f"nhận {result.no_speech_prob}."
    )
    print("OK: test_transcribe_parse_dung_khi_thanh_cong")


def test_transcribe_wire_dung_no_speech_prob_cao_tu_segments():
    # 🔒 MỚI -- xác nhận transcribe() KHÔNG bỏ sót no_speech_prob khi Groq
    # trả về cao (trường hợp im lặng/nhạc nền/hallucination thật đã gặp khi
    # test trên Windows -- xem CONTRACTS.md Mục 11).
    fake_response = _FakeTranscriptionResponse(
        text="Hãy subscribe cho kênh Ghiền Mì Gõ", language="vi",
        segments=[_FakeSegment(avg_logprob=-0.3, no_speech_prob=0.85)],
    )
    fake_client = _FakeClient(audio=_FakeAudio(_FakeAudioTranscriptions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    assert result.no_speech_prob > 0.8, (
        f"Phải wire đúng no_speech_prob cao từ segments, nhận {result.no_speech_prob}."
    )
    print("OK: test_transcribe_wire_dung_no_speech_prob_cao_tu_segments")


def test_transcribe_wrap_loi_thanh_provider_error():
    fake_client = _FakeClient(
        audio=_FakeAudio(_FakeAudioTranscriptions(
            error=openai.APIConnectionError(request=None)
        ))
    )
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi API lỗi.")
    except ProviderError:
        pass
    print("OK: test_transcribe_wrap_loi_thanh_provider_error")


# --------------------------------------------------------------------------
# 2b. Fallback model tự động khi gặp 429 rate limit (ưu tiên chính xác
#     nhất ở model chính, vẫn linh hoạt/free khi hết quota tạm thời) --
#     xem docstring GroqProvider + _call_with_rate_limit_fallback.
# --------------------------------------------------------------------------

def test_chat_complete_fallback_sang_model_phu_khi_429():
    completions = _FakeSequencedCompletions([
        openai.RateLimitError(response=None, body=None),
        _FakeChatResponse(content="ok tu fallback"),
    ])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(
        fake_client, translate_model="model-chinh", translate_fallback_model="model-phu",
    )
    result = provider.translate("hi", source_lang="en", target_lang="vi")
    assert result == "ok tu fallback"
    assert completions.called_models == ["model-chinh", "model-phu"], (
        f"Phải gọi model-chinh trước, model-phu sau khi 429, nhận {completions.called_models}."
    )
    print("OK: test_chat_complete_fallback_sang_model_phu_khi_429")


def test_chat_complete_khong_fallback_cho_loi_khac_429():
    completions = _FakeSequencedCompletions([
        _make_fake_auth_error(),
    ])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(
        fake_client, translate_model="model-chinh", translate_fallback_model="model-phu",
    )
    try:
        provider.translate("hi", source_lang="en", target_lang="vi")
        raise AssertionError("Phải raise ProviderError khi lỗi không phải 429.")
    except ProviderError:
        pass
    assert completions.called_models == ["model-chinh"], (
        "KHÔNG được thử model-phu khi lỗi không phải 429 (đổi model không "
        f"sửa được lỗi auth), nhận {completions.called_models}."
    )
    print("OK: test_chat_complete_khong_fallback_cho_loi_khac_429")


def test_chat_complete_ca_2_model_deu_429_raise_provider_error():
    completions = _FakeSequencedCompletions([
        openai.RateLimitError(response=None, body=None),
        openai.RateLimitError(response=None, body=None),
    ])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(
        fake_client, translate_model="model-chinh", translate_fallback_model="model-phu",
    )
    try:
        provider.translate("hi", source_lang="en", target_lang="vi")
        raise AssertionError("Phải raise ProviderError khi cả 2 model đều 429.")
    except ProviderError:
        pass
    assert completions.called_models == ["model-chinh", "model-phu"]
    print("OK: test_chat_complete_ca_2_model_deu_429_raise_provider_error")


def test_chat_complete_khong_fallback_khi_fallback_model_trung_model_chinh():
    completions = _FakeSequencedCompletions([
        openai.RateLimitError(response=None, body=None),
    ])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(
        fake_client, translate_model="model-chinh", translate_fallback_model="model-chinh",
    )
    try:
        provider.translate("hi", source_lang="en", target_lang="vi")
        raise AssertionError("Phải raise ProviderError ngay, không lặp lại model giống nhau.")
    except ProviderError:
        pass
    assert completions.called_models == ["model-chinh"], (
        f"fallback_model == model chính -> KHÔNG gọi lại lần 2, nhận {completions.called_models}."
    )
    print("OK: test_chat_complete_khong_fallback_khi_fallback_model_trung_model_chinh")


def test_transcribe_fallback_sang_model_phu_khi_429():
    fake_transcription = _FakeTranscriptionResponse(
        text="hello", language="en",
        segments=[_FakeSegment(avg_logprob=-0.1, no_speech_prob=0.0)],
    )
    transcriptions = _FakeSequencedTranscriptions([
        openai.RateLimitError(response=None, body=None),
        fake_transcription,
    ])
    fake_client = _FakeClient(audio=_FakeAudio(transcriptions))
    provider = _make_provider_with_fake_client(
        fake_client, stt_model="stt-chinh", stt_fallback_model="stt-phu",
    )
    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    assert result.text == "hello"
    assert transcriptions.called_models == ["stt-chinh", "stt-phu"]
    print("OK: test_transcribe_fallback_sang_model_phu_khi_429")


def test_translate_tra_dung_content():
    fake_response = _FakeChatResponse(content="  Xin chào thế giới  ")
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.translate("Hello world", source_lang="en", target_lang="vi")
    assert result == "Xin chào thế giới", f"Phải strip() khoảng trắng, nhận {result!r}."
    print("OK: test_translate_tra_dung_content")


def test_translate_prompt_yeu_cau_giu_dung_ngoi_xung_ho():
    # Bug thật phát hiện qua test: "Can you tell us about yourself?" (hỏi
    # ỨNG VIÊN) bị dịch thành "Tôi có thể kể về bản thân mình không?" -- lật
    # ngôi "bạn" thành "tôi". Prompt PHẢI có yêu cầu rõ chặn lỗi này.
    captured_messages = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured_messages["messages"] = kwargs["messages"]
            return _FakeChatResponse(content="ok")

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))
    provider = _make_provider_with_fake_client(fake_client)
    provider.translate("Can you tell us about yourself?", "en", "vi")

    system_msg = captured_messages["messages"][0]["content"].lower()
    assert "grammatical person" in system_msg or "direction of address" in system_msg
    assert "never shift" in system_msg
    print("OK: test_translate_prompt_yeu_cau_giu_dung_ngoi_xung_ho")


def test_translate_response_rong_raise_provider_error():
    fake_response = _FakeChatResponse(content=None)
    fake_response.choices = []  # giả lập response không có choices
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.translate("Hello", source_lang="en", target_lang="vi")
        raise AssertionError("Phải raise ProviderError khi response không có choices.")
    except ProviderError:
        pass
    print("OK: test_translate_response_rong_raise_provider_error")


def test_init_thieu_api_key_raise_provider_error():
    os.environ.pop("GROQ_API_KEY", None)
    try:
        GroqProvider(api_key=None)
        raise AssertionError("Phải raise ProviderError khi không có api_key và không có env var.")
    except ProviderError:
        pass
    print("OK: test_init_thieu_api_key_raise_provider_error")


def test_transcribe_chuan_hoa_language_tu_full_word_nhu_du_lieu_thuc():
    # Mô phỏng ĐÚNG hành vi thật của Groq (response.language="English", full
    # word) đã phát hiện qua meetings.db -- xác nhận transcribe() trả về mã
    # ISO "en", không phải "English", để pipeline.py so sánh source/target
    # lang đúng.
    fake_response = _FakeTranscriptionResponse(
        text="Hello", language="English",
        segments=[_FakeSegment(avg_logprob=-0.1, no_speech_prob=0.0)],
    )
    fake_client = _FakeClient(audio=_FakeAudio(_FakeAudioTranscriptions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
    assert result.language == "en", f"Phải chuẩn hoá 'English' -> 'en', nhận {result.language!r}."
    print("OK: test_transcribe_chuan_hoa_language_tu_full_word_nhu_du_lieu_thuc")


def test_suggest_answer_tra_dung_content_va_dung_prompt_yeu_cau_khong_bia_so_lieu():
    fake_response = _FakeChatResponse(content="  Cảm ơn câu hỏi, tôi sẽ kiểm tra lại [số liệu cụ thể] và phản hồi sớm.  ")
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.suggest_answer(
        question_text="What's our Q3 churn rate?",
        context_text="Boss: Let's review the quarterly numbers.",
        user_native_lang="vi",
    )
    assert result == "Cảm ơn câu hỏi, tôi sẽ kiểm tra lại [số liệu cụ thể] và phản hồi sớm."
    print("OK: test_suggest_answer_tra_dung_content_va_dung_prompt_yeu_cau_khong_bia_so_lieu")


def test_suggest_answer_prompt_co_canh_bao_khong_bia_so_lieu():
    # Không gọi network -- chỉ assert hệ thống prompt GỬI ĐI có chứa hướng
    # dẫn chống bịa số liệu (đúng yêu cầu PROJECT_SPEC.md mục 2 rủi ro #2).
    captured_messages = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured_messages["messages"] = kwargs["messages"]
            return _FakeChatResponse(content="ok")

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))
    provider = _make_provider_with_fake_client(fake_client)
    provider.suggest_answer("Q?", "ctx", "vi")

    system_msg = captured_messages["messages"][0]["content"]
    assert "do not invent them" in system_msg.lower() or "not invent" in system_msg.lower()
    assert "placeholder" in system_msg.lower()
    print("OK: test_suggest_answer_prompt_co_canh_bao_khong_bia_so_lieu")


def test_suggest_answer_prompt_cam_lan_man_va_yeu_cau_tra_loi_truc_tiep():
    # Bug thật phát hiện sau test: câu trả lời mở đầu kiểu "I appreciate
    # this question..." rồi mới lan man vào ý -- prompt phải CẤM rõ kiểu mở
    # đầu này và yêu cầu trả lời trực tiếp kiến thức chung khi model biết.
    captured_messages = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured_messages["messages"] = kwargs["messages"]
            return _FakeChatResponse(content="ok")

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))
    provider = _make_provider_with_fake_client(fake_client)
    provider.suggest_answer("Q?", "ctx", "vi")

    system_msg = captured_messages["messages"][0]["content"]
    assert "i appreciate this question" in system_msg.lower(), (
        "Prompt phải nêu rõ VÍ DỤ câu mở đầu lan man cần cấm, để model dễ tránh."
    )
    assert "directly" in system_msg.lower() and "accurately" in system_msg.lower(), (
        "Prompt phải yêu cầu trả lời trực tiếp/chính xác với kiến thức chung model biết."
    )
    assert "1-3" in system_msg, "Phải giới hạn độ dài ngắn, tránh lan man."
    print("OK: test_suggest_answer_prompt_cam_lan_man_va_yeu_cau_tra_loi_truc_tiep")


def test_suggest_answer_wrap_loi_thanh_provider_error():
    fake_client = _FakeClient(
        chat=_FakeChat(_FakeChatCompletions(error=openai.APIConnectionError(request=None)))
    )
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.suggest_answer("Q?", "ctx", "vi")
        raise AssertionError("Phải raise ProviderError khi API lỗi.")
    except ProviderError:
        pass
    print("OK: test_suggest_answer_wrap_loi_thanh_provider_error")


# --------------------------------------------------------------------------
# 2c. 🔒 MỚI (CONTRACTS.md Mục 15) — suggest_answer() retry khi model trả
#     lời SAI ngôn ngữ (mirror theo hội thoại CJK thay vì user_native_lang).
# --------------------------------------------------------------------------

def test_looks_like_wrong_script_phat_hien_dung_case_thuc_te_da_gap():
    from app.ai.groq_provider import _looks_like_wrong_script

    # Case thật từ ảnh chụp UI người dùng gửi: native_lang="vi" nhưng model
    # trả lời nguyên bằng tiếng Hàn (Hangul).
    korean_answer = "과탑이세요? 그러면 오늘은 과탑 교수님으로 보이네요."
    assert _looks_like_wrong_script(korean_answer, "vi") is True

    japanese_answer = "それは大切なことだと思いますね、自分自身を受け入れることができると。"
    assert _looks_like_wrong_script(japanese_answer, "vi") is True

    chinese_answer = "假设这句话是在描述一个人态度很冷漠，可能会说这个人很冷漠。"
    assert _looks_like_wrong_script(chinese_answer, "vi") is True

    # Đối chứng: trả lời ĐÚNG tiếng Việt -- KHÔNG được báo nhầm.
    vietnamese_answer = "Để giải quyết vấn đề máy tính chạy chậm, tôi sẽ kiểm tra nguồn điện."
    assert _looks_like_wrong_script(vietnamese_answer, "vi") is False

    # Đối chứng: native_lang="en", trả lời tiếng Anh đúng -- không báo nhầm.
    english_answer = "I'll check the power supply and update the drivers first."
    assert _looks_like_wrong_script(english_answer, "en") is False

    # Đối chứng: native_lang="zh", trả lời ĐÚNG tiếng Trung (toàn chữ Hán)
    # -- KHÔNG được báo nhầm chỉ vì có chữ Hán (đó là script đúng của zh).
    assert _looks_like_wrong_script(chinese_answer, "zh") is False

    # native_lang="zh" nhưng model lại trả lời tiếng Hàn -- vẫn phải bắt được.
    assert _looks_like_wrong_script(korean_answer, "zh") is True

    # Vài ký tự CJK lẫn vào (trích dẫn ngắn) trong câu trả lời tiếng Việt
    # DÀI -- tỉ lệ nhỏ, không được vượt ngưỡng báo nhầm.
    mixed_mostly_vietnamese = (
        "Ý anh muốn nói '你好' đúng không? Tôi nghĩ chúng ta nên xác nhận lại "
        "với khách hàng trước khi gửi báo giá chính thức cho họ."
    )
    assert _looks_like_wrong_script(mixed_mostly_vietnamese, "vi") is False

    # native_lang lạ (chưa hỗ trợ chính thức) -- không đủ thông tin, không báo.
    assert _looks_like_wrong_script(korean_answer, "fr") is False
    print("OK: test_looks_like_wrong_script_phat_hien_dung_case_thuc_te_da_gap")


def test_suggest_answer_system_prompt_co_output_language_rule_ro_rang():
    # Không gọi network -- chỉ assert system prompt GỬI ĐI có nêu RÕ quy
    # tắc ngôn ngữ đầu ra ngay từ đầu (CONTRACTS.md Mục 15 -- fix prompt).
    captured_messages = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured_messages["messages"] = kwargs["messages"]
            return _FakeChatResponse(content="ok")

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))
    provider = _make_provider_with_fake_client(fake_client)
    provider.suggest_answer("Q?", "ctx", "vi")

    system_msg = captured_messages["messages"][0]["content"]
    assert system_msg.lower().startswith("output language rule"), (
        "Quy tắc ngôn ngữ đầu ra phải là câu ĐẦU TIÊN của system prompt -- "
        "vị trí model 'chú ý' nhiều nhất, xem CONTRACTS.md Mục 15."
    )
    assert "never mirror" in system_msg.lower()
    user_msg = captured_messages["messages"][1]["content"]
    assert "reminder" in user_msg.lower(), (
        "User message cũng phải có dòng nhắc lại ngôn ngữ đầu ra, gần nhất "
        "với điểm model bắt đầu sinh token."
    )
    print("OK: test_suggest_answer_system_prompt_co_output_language_rule_ro_rang")


def test_suggest_answer_tu_dong_retry_1_lan_khi_phat_hien_sai_script():
    # Mô phỏng ĐÚNG bug thật: lần gọi đầu model trả lời bằng tiếng Hàn (sai),
    # lần retry trả lời đúng tiếng Việt -- suggest_answer() phải tự retry và
    # trả về kết quả ĐÃ ĐÚNG của lần 2, KHÔNG trả thẳng kết quả sai của lần 1.
    wrong = "과탑이세요? 그러면 오늘은 과탑 교수님으로 보이네요."
    correct = "Vậy hôm nay là giáo sư chủ nhiệm đúng không? Nói về đời sinh viên thì vui thật đấy."
    completions = _FakeSequencedCompletions([
        _FakeChatResponse(content=wrong),
        _FakeChatResponse(content=correct),
    ])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.suggest_answer("질문?", "맥락", "vi")
    assert result == correct, f"Phải trả về kết quả ĐÃ retry đúng script, nhận {result!r}."
    assert len(completions.called_models) == 2, "Phải gọi đúng 2 lần (1 lần gốc + 1 lần retry)."
    print("OK: test_suggest_answer_tu_dong_retry_1_lan_khi_phat_hien_sai_script")


def test_suggest_answer_khong_retry_khi_lan_dau_da_dung_script():
    # Đối chứng quan trọng: lần đầu ĐÃ đúng tiếng Việt (case tiếng Anh đã
    # hoạt động tốt từ trước) -- KHÔNG được tốn thêm 1 lượt gọi API vô ích.
    correct = "Để giải quyết vấn đề máy tính chạy chậm, tôi sẽ kiểm tra nguồn điện."
    completions = _FakeSequencedCompletions([_FakeChatResponse(content=correct)])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.suggest_answer("How would you fix a slow computer?", "ctx", "vi")
    assert result == correct
    assert len(completions.called_models) == 1, (
        "KHÔNG được retry nếu lần đầu đã đúng script -- tốn quota free-tier vô ích."
    )
    print("OK: test_suggest_answer_khong_retry_khi_lan_dau_da_dung_script")


def test_suggest_answer_retry_van_sai_script_thi_van_tra_ve_khong_raise():
    # Trường hợp xấu nhất: CẢ 2 lần đều sai script -- KHÔNG raise lỗi chặn
    # hẳn người dùng giữa cuộc họp, vẫn trả về kết quả lần retry (có thêm áp
    # lực đúng hướng hơn so với không retry) để người dùng còn có gì đó đọc.
    wrong_1 = "과탑이세요?"
    wrong_2 = "それは大切なことだと思いますね。"
    completions = _FakeSequencedCompletions([
        _FakeChatResponse(content=wrong_1),
        _FakeChatResponse(content=wrong_2),
    ])
    fake_client = _FakeClient(chat=_FakeChat(completions))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.suggest_answer("질문?", "맥락", "vi")
    assert result == wrong_2, "Vẫn phải trả về (không raise), dùng kết quả của lần retry."
    assert len(completions.called_models) == 2, "Vẫn chỉ retry ĐÚNG 1 lần, không lặp vô hạn."
    print("OK: test_suggest_answer_retry_van_sai_script_thi_van_tra_ve_khong_raise")


def test_suggest_answer_retry_dung_temperature_thap_hon_va_co_nhac_loi_sai():
    captured_calls = []

    class _CapturingCompletions:
        def __init__(self, contents):
            self._contents = list(contents)

        def create(self, **kwargs):
            captured_calls.append(kwargs)
            return _FakeChatResponse(content=self._contents.pop(0))

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions([
        "과탑이세요?",  # lần 1: sai script
        "Vậy hôm nay là giáo sư chủ nhiệm.",  # lần 2 (retry): đúng
    ])))
    provider = _make_provider_with_fake_client(fake_client)
    provider.suggest_answer("질문?", "맥락", "vi")

    assert len(captured_calls) == 2
    assert captured_calls[0]["temperature"] == 0.4, "Lần gọi gốc giữ temperature như cũ (0.4)."
    assert captured_calls[1]["temperature"] < captured_calls[0]["temperature"], (
        "Lần retry PHẢI dùng temperature thấp hơn -- ít 'sáng tạo'/lệch hướng hơn."
    )
    retry_user_msg = captured_calls[1]["messages"][1]["content"].lower()
    assert "critical correction needed" in retry_user_msg or "rejected" in retry_user_msg, (
        "User message của lần retry phải nêu rõ lần trước bị từ chối vì sai ngôn ngữ."
    )
    print("OK: test_suggest_answer_retry_dung_temperature_thap_hon_va_co_nhac_loi_sai")


def test_summarize_parse_dung_json_thanh_summary_result():
    fake_response = _FakeChatResponse(content=json.dumps({
        "overview": "Hai bên thảo luận về tiến độ dự án.",
        "decisions": ["Dời deadline sang tuần sau"],
        "action_items": ["An gửi lại báo cáo trước thứ 6"],
    }))
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.summarize("A: ...\nB: ...", user_native_lang="vi")
    assert result.overview == "Hai bên thảo luận về tiến độ dự án."
    assert result.decisions == ["Dời deadline sang tuần sau"]
    assert result.action_items == ["An gửi lại báo cáo trước thứ 6"]
    print("OK: test_summarize_parse_dung_json_thanh_summary_result")


def test_summarize_decisions_rong_nghia_la_khong_co_quyet_dinh():
    # [] PHẢI giữ nguyên là list rỗng (không có quyết định), KHÔNG bị hiểu
    # nhầm thành "thiếu field"/lỗi — đây là kết quả HỢP LỆ và MONG ĐỢI khi
    # cuộc họp/đoạn audio test không có quyết định rõ ràng nào.
    fake_response = _FakeChatResponse(content=json.dumps({
        "overview": "Chỉ là 1 đoạn podcast trò chuyện, không có nội dung họp.",
        "decisions": [],
        "action_items": [],
    }))
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.summarize("A: ...\nB: ...", user_native_lang="vi")
    assert result.decisions == []
    assert result.action_items == []
    print("OK: test_summarize_decisions_rong_nghia_la_khong_co_quyet_dinh")


def test_summarize_chap_nhan_string_cu_tuong_thich_nguoc():
    # Schema CHÍNH THỨC là JSON array, nhưng nếu model lỡ trả về string
    # nhiều dòng kiểu CŨ (trước khi sửa prompt) -- vẫn phải parse được,
    # không vô tình biến lỗi format nhỏ thành crash hoàn toàn.
    fake_response = _FakeChatResponse(content=json.dumps({
        "overview": "x",
        "decisions": "- Dời deadline sang tuần sau\n- Đổi nhà cung cấp",
        "action_items": "An gửi lại báo cáo trước thứ 6",
    }))
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)

    result = provider.summarize("A: ...\nB: ...", user_native_lang="vi")
    assert result.decisions == ["Dời deadline sang tuần sau", "Đổi nhà cung cấp"]
    assert result.action_items == ["An gửi lại báo cáo trước thứ 6"]
    print("OK: test_summarize_chap_nhan_string_cu_tuong_thich_nguoc")


def test_summarize_kieu_du_lieu_la_khong_doan_duoc_raise_provider_error():
    fake_response = _FakeChatResponse(content=json.dumps({
        "overview": "x", "decisions": 42, "action_items": [],
    }))
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.summarize("transcript", "vi")
        raise AssertionError("Phải raise ProviderError khi field là kiểu không đoán được (vd số).")
    except ProviderError:
        pass
    print("OK: test_summarize_kieu_du_lieu_la_khong_doan_duoc_raise_provider_error")


def test_summarize_dung_response_format_json_object():
    captured = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeChatResponse(content=json.dumps(
                {"overview": "x", "decisions": [], "action_items": []}
            ))

    fake_client = _FakeClient(chat=_FakeChat(_CapturingCompletions()))
    provider = _make_provider_with_fake_client(fake_client)
    provider.summarize("transcript", "vi")

    assert captured.get("response_format") == {"type": "json_object"}, (
        "Phải bắt Groq trả JSON qua response_format, không chỉ yêu cầu trong prompt."
    )
    system_msg = captured["messages"][0]["content"].lower()
    assert "array" in system_msg, (
        "Prompt phải yêu cầu rõ decisions/action_items là JSON ARRAY (lỗi thật đã "
        "gặp: yêu cầu cũ là 1 string nhiều dòng khiến Groq trả 400 'Failed to "
        "generate JSON' khi model nhúng list nhiều dòng vào 1 field string)."
    )
    print("OK: test_summarize_dung_response_format_json_object")


def test_summarize_json_khong_hop_le_raise_provider_error():
    fake_response = _FakeChatResponse(content="không phải JSON đâu")
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.summarize("transcript", "vi")
        raise AssertionError("Phải raise ProviderError khi JSON không parse được.")
    except ProviderError:
        pass
    print("OK: test_summarize_json_khong_hop_le_raise_provider_error")


def test_summarize_json_thieu_field_raise_provider_error():
    fake_response = _FakeChatResponse(content=json.dumps({"overview": "x"}))  # thiếu decisions, action_items
    fake_client = _FakeClient(chat=_FakeChat(_FakeChatCompletions(response=fake_response)))
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.summarize("transcript", "vi")
        raise AssertionError("Phải raise ProviderError khi JSON thiếu field.")
    except ProviderError:
        pass
    print("OK: test_summarize_json_thieu_field_raise_provider_error")


def _make_fake_auth_error(message: str = "Invalid API Key") -> openai.AuthenticationError:
    """Giả lập đúng lỗi 401 thật mà user đã gặp (xem ảnh chụp màn hình) để
    test message hint mới, không cần gọi network thật."""
    resp = httpx.Response(
        status_code=401,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions"),
    )
    return openai.AuthenticationError(
        message, response=resp,
        body={"error": {"message": message, "type": "invalid_request_error", "code": "invalid_api_key"}},
    )


def test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu():
    # Bug thật đã gặp: user để nguyên giá trị mẫu .env.example -> Groq trả
    # 401 chung, rất khó đoán nguyên nhân. Giờ phải chặn NGAY tại __init__.
    os.environ["GROQ_API_KEY"] = "your_groq_api_key_here"
    try:
        GroqProvider()
        raise AssertionError("Phải raise ProviderError khi key vẫn là giá trị mẫu.")
    except ProviderError as exc:
        assert "mẫu" in str(exc) or "console.groq.com" in str(exc)
    finally:
        os.environ.pop("GROQ_API_KEY", None)
    print("OK: test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu")


def test_init_tu_dong_strip_quote_va_whitespace_thua():
    os.environ["GROQ_API_KEY"] = '  "gsk_fake_key_for_test"  \n'
    try:
        provider = GroqProvider()
        assert provider._client.api_key == "gsk_fake_key_for_test", (
            f"Phải dọn sạch quote/whitespace, nhận: {provider._client.api_key!r}"
        )
    finally:
        os.environ.pop("GROQ_API_KEY", None)
    print("OK: test_init_tu_dong_strip_quote_va_whitespace_thua")


def test_transcribe_401_tra_message_huong_dan_ro_rang():
    fake_client = _FakeClient(
        audio=_FakeAudio(_FakeAudioTranscriptions(error=_make_fake_auth_error()))
    )
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.transcribe(np.zeros(1600, dtype=np.float32), samplerate=16000)
        raise AssertionError("Phải raise ProviderError khi 401.")
    except ProviderError as exc:
        msg = str(exc).lower()
        assert "401" in str(exc)
        assert ".env" in str(exc)
        assert "console.groq.com" in str(exc)
        assert "cấu hình" in msg, "Phải nói rõ đây là lỗi cấu hình, không phải lỗi audio/code."
    print("OK: test_transcribe_401_tra_message_huong_dan_ro_rang")


def test_translate_401_tra_message_huong_dan_ro_rang():
    fake_client = _FakeClient(
        chat=_FakeChat(_FakeChatCompletions(error=_make_fake_auth_error()))
    )
    provider = _make_provider_with_fake_client(fake_client)
    try:
        provider.translate("Hello", "en", "vi")
        raise AssertionError("Phải raise ProviderError khi 401.")
    except ProviderError as exc:
        assert "401" in str(exc)
        assert "console.groq.com" in str(exc)
    print("OK: test_translate_401_tra_message_huong_dan_ro_rang")


if __name__ == "__main__":
    test_encode_wav_bytes_dung_format()
    test_encode_wav_bytes_clip_dung_truoc_khi_quantize()
    test_encode_wav_bytes_reject_khong_phai_mono()
    test_estimate_confidence_rong_tra_0()
    test_estimate_confidence_nam_trong_0_1()
    test_estimate_no_speech_prob_rong_tra_0()
    test_estimate_no_speech_prob_la_trung_binh_tho_khong_nhan_logprob()
    test_no_speech_prob_la_tin_hieu_chat_hon_confidence_cho_cau_ngan_nhung_thuc()
    test_transcribe_parse_dung_khi_thanh_cong()
    test_transcribe_wire_dung_no_speech_prob_cao_tu_segments()
    test_transcribe_chuan_hoa_language_tu_full_word_nhu_du_lieu_thuc()
    test_normalize_language_voi_du_lieu_thuc_te_tu_groq()
    test_transcribe_wrap_loi_thanh_provider_error()
    test_chat_complete_fallback_sang_model_phu_khi_429()
    test_chat_complete_khong_fallback_cho_loi_khac_429()
    test_chat_complete_ca_2_model_deu_429_raise_provider_error()
    test_chat_complete_khong_fallback_khi_fallback_model_trung_model_chinh()
    test_transcribe_fallback_sang_model_phu_khi_429()
    test_translate_tra_dung_content()
    test_translate_prompt_yeu_cau_giu_dung_ngoi_xung_ho()
    test_translate_response_rong_raise_provider_error()
    test_init_thieu_api_key_raise_provider_error()
    test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu()
    test_init_tu_dong_strip_quote_va_whitespace_thua()
    test_transcribe_401_tra_message_huong_dan_ro_rang()
    test_translate_401_tra_message_huong_dan_ro_rang()
    test_suggest_answer_tra_dung_content_va_dung_prompt_yeu_cau_khong_bia_so_lieu()
    test_suggest_answer_prompt_co_canh_bao_khong_bia_so_lieu()
    test_suggest_answer_prompt_cam_lan_man_va_yeu_cau_tra_loi_truc_tiep()
    test_suggest_answer_wrap_loi_thanh_provider_error()
    test_looks_like_wrong_script_phat_hien_dung_case_thuc_te_da_gap()
    test_suggest_answer_system_prompt_co_output_language_rule_ro_rang()
    test_suggest_answer_tu_dong_retry_1_lan_khi_phat_hien_sai_script()
    test_suggest_answer_khong_retry_khi_lan_dau_da_dung_script()
    test_suggest_answer_retry_van_sai_script_thi_van_tra_ve_khong_raise()
    test_suggest_answer_retry_dung_temperature_thap_hon_va_co_nhac_loi_sai()
    test_summarize_parse_dung_json_thanh_summary_result()
    test_summarize_decisions_rong_nghia_la_khong_co_quyet_dinh()
    test_summarize_chap_nhan_string_cu_tuong_thich_nguoc()
    test_summarize_kieu_du_lieu_la_khong_doan_duoc_raise_provider_error()
    test_summarize_dung_response_format_json_object()
    test_summarize_json_khong_hop_le_raise_provider_error()
    test_summarize_json_thieu_field_raise_provider_error()
    print("\n=== TẤT CẢ TEST GROQ_PROVIDER (OFFLINE/MOCK) PASS ===")
