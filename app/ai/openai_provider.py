"""app/ai/openai_provider.py
-----------------------------
🔒 MỚI (đợt thêm multi-provider — Groq/OpenAI/Gemini, xem CONTRACTS.md Mục
17) — implementation `AIProvider` dùng API CỦA CHÍNH OPENAI (KHÁC Groq —
Groq chỉ HOST LẠI model Whisper/Llama qua endpoint của Groq, còn đây là
api.openai.com thật, dùng model GPT + Whisper gốc của OpenAI).

Vì sao đáng làm provider RIÊNG (không chỉ đổi `base_url` của
`GroqProvider`): người dùng cuối có thể chỉ có sẵn API key của OpenAI (vd
đã trả phí ChatGPT Plus/Team từ trước) thay vì key Groq — mục tiêu (đã bàn
với người dùng) là "dán key của BẤT KỲ provider nào vào Settings, app
chạy được NGAY, không cần biết khái niệm AIProvider/base_url là gì".

**STT dùng `whisper-1`, KHÔNG dùng `gpt-4o-transcribe`/`gpt-4o-mini-
transcribe`** — đã kiểm tra tài liệu chính thức OpenAI (06/2026): CHỈ
`whisper-1` hỗ trợ `response_format="verbose_json"` kèm `segments` có
`avg_logprob`/`no_speech_prob` — ĐÚNG hình dạng response mà
`whisper_utils.py` (dùng chung với Groq) cần để tính `confidence`/
`no_speech_prob` cho `TranscriptionResult`. `gpt-4o(-mini)-transcribe` chỉ
trả `json`/`text` (không có segments dạng này), sẽ phải viết lại HẲN logic
ước lượng confidence — KHÔNG làm ở đây để giữ hành vi NHẤT QUÁN với Groq
(cùng 1 model gốc Whisper, cùng công thức), tránh 2 provider "cảm giác"
khác nhau về độ tin cậy/lọc hallucination chỉ vì chọn nhầm model STT.

⚠️ **Giá** (cần bạn tự xác nhận lại trước khi launch — tự đổi liên tục,
không cam kết ở đây): API OpenAI KHÔNG miễn phí như Groq free tier
(PROJECT_SPEC.md mục 8) — người dùng tự trả theo usage của CHÍNH HỌ qua
API key của họ. Đây ĐÚNG NHƯ Ý ĐỊNH (mỗi người tự chịu trách nhiệm dùng
model AI của mình — xem `config_store.py`), nhưng Settings UI PHẢI nói rõ
điều này cho người dùng (KHÔNG để họ tưởng nhầm "free như Groq").

⚠️ **Tên model chat** (`gpt-5-mini`/`gpt-5-nano`, cập nhật 06/2026) đổi
RẤT nhanh ở OpenAI — đã chọn 2 model RẺ/NHANH (phù hợp dịch/gợi ý trả lời
thời gian thực hơn là model "thinking" đắt/chậm), nhưng đây KHÔNG phải
quyết định vĩnh viễn. Nếu OpenAI deprecate model này sau khi bạn đọc dòng
này, truyền `chat_model=`/`chat_fallback_model=` khi khởi tạo
(`OpenAIProvider(chat_model="...")`) — KHÔNG cần sửa code nơi khác, đúng
tinh thần "lớp abstraction AIProvider" PROJECT_SPEC.md mục 8 đã đề ra.
"""

from __future__ import annotations

import os

import openai
from openai import OpenAI

from app import config_store
from app.ai.base_provider import ProviderError, TranscriptionResult
from app.ai.openai_compat_base import (
    OpenAICompatProvider,
    _auth_error_hint,
    _call_with_fallback,
    _resolve_client_timeout_seconds,
    _TRANSIENT_NETWORK_MAX_RETRIES,
)
from app.ai.whisper_utils import (
    _encode_wav_bytes,
    _estimate_confidence,
    _estimate_no_speech_prob,
    _normalize_language_to_iso,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
_OPENAI_KEYS_URL = "https://platform.openai.com/api-keys"

# Giá trị mẫu trong .env.example -- cùng lý do/cách xử lý như
# GroqProvider._PLACEHOLDER_KEY (xem groq_provider.py).
_PLACEHOLDER_KEY = "your_openai_api_key_here"


class OpenAIProvider(OpenAICompatProvider):
    """AIProvider implementation dùng API thật của OpenAI:
    `whisper-1` cho STT, GPT cho dịch/gợi ý trả lời/tổng hợp biên bản.

    translate/suggest_answer/summarize kế thừa từ `OpenAICompatProvider`
    (xem `openai_compat_base.py`) — y hệt logic/prompt đã verify với Groq,
    chỉ khác `base_url` + tên model. `transcribe()` viết riêng (dùng
    `whisper-1`, xem docstring đầu file) nhưng TÁI DÙNG các hàm parse
    response ở `whisper_utils.py` — KHÔNG sao chép lại logic của
    `groq_provider.py`.
    """

    _provider_label = "OpenAI"

    def __init__(
        self,
        api_key: str | None = None,
        stt_model: str = "whisper-1",
        # whisper-1 không có model "rẻ hơn" để fallback khi 429 (khác Groq
        # có turbo) -- để trống nghĩa là TẮT fallback (lỗi 429 raise thẳng,
        # đúng tinh thần "không fallback giả" của _call_with_fallback).
        stt_fallback_model: str = "",
        translate_model: str = "gpt-5-mini",
        translate_fallback_model: str = "gpt-5-nano",
        client_timeout_seconds: float | None = None,
    ) -> None:
        """Khởi tạo provider, kết nối tới OpenAI qua SDK `openai` chính chủ.

        Args:
            api_key: OpenAI API key (dạng "sk-..."). Nếu None, đọc theo thứ
                tự ưu tiên: (1)
                `app.config_store.load_api_key(provider="openai")` — key
                người dùng cuối nhập qua Settings UI; (2) biến môi trường
                `OPENAI_API_KEY` (dev, đọc qua `.env`).
            stt_model: mặc định "whisper-1" — xem docstring đầu file vì
                sao KHÔNG dùng gpt-4o-transcribe.
            stt_fallback_model: mặc định "" (KHÔNG fallback).
            translate_model: model chat ưu tiên cho dịch/gợi ý/tóm tắt,
                mặc định "gpt-5-mini".
            translate_fallback_model: model chat dự phòng khi 429, mặc
                định "gpt-5-nano".
            client_timeout_seconds: 🔒 MỚI (Backlog #1, CONTRACTS.md Mục
                28) — timeout (giây) cho `self._client` (transcribe() +
                chat), 3 tầng ưu tiên: tham số > biến môi trường
                `OPENAI_CLIENT_TIMEOUT_SECONDS` > default 30.0s. Xem lý do
                đầy đủ ở `_resolve_client_timeout_seconds()`
                (`openai_compat_base.py`).

        Raises:
            ProviderError: thiếu api_key ở mọi nguồn, hoặc key vẫn là giá
                trị mẫu trong .env.example.
        """
        resolved_key = (
            api_key
            or config_store.load_api_key(provider="openai")
            or os.environ.get("OPENAI_API_KEY")
        )
        if resolved_key:
            resolved_key = resolved_key.strip().strip('"').strip("'")
        if not resolved_key:
            raise ProviderError(
                "Thiếu OpenAI API key — vào ⚙️ Cài đặt trong app, chọn provider "
                "OpenAI và dán key của bạn (lấy tại "
                f"{_OPENAI_KEYS_URL}), hoặc (nếu đang chạy từ source code để "
                "dev) truyền api_key= hoặc set biến môi trường OPENAI_API_KEY "
                "trong file .env."
            )
        if resolved_key == _PLACEHOLDER_KEY:
            raise ProviderError(
                "OPENAI_API_KEY trong .env vẫn là giá trị MẪU, chưa được thay "
                f"bằng key THẬT. Lấy key thật tại {_OPENAI_KEYS_URL}."
            )
        self._client_timeout_seconds = _resolve_client_timeout_seconds(
            client_timeout_seconds, "OPENAI_CLIENT_TIMEOUT_SECONDS",
        )
        self._client = OpenAI(
            api_key=resolved_key, base_url=OPENAI_BASE_URL, timeout=self._client_timeout_seconds,
        )
        self._stt_model = stt_model
        self._stt_fallback_model = stt_fallback_model
        self._translate_model = translate_model
        self._translate_fallback_model = translate_fallback_model

    def _auth_error_hint(self, api_label: str, exc: Exception) -> str:
        return _auth_error_hint("OpenAI", api_label, "OPENAI_API_KEY", _OPENAI_KEYS_URL, exc)

    def transcribe(self, audio, samplerate: int, language_hint: str = "") -> TranscriptionResult:
        """Xem docstring đầy đủ ở AIProvider.transcribe().

        Cùng pattern hệt `GroqProvider.transcribe()` (CHỦ Ý — cùng SDK,
        cùng model gốc Whisper) — chỉ khác model name + dùng hàm
        `whisper_utils` thay vì định nghĩa lại. `language_hint` (Mục 38)
        cùng cơ chế/lý do với Groq — xem docstring ở đó."""
        wav_bytes = _encode_wav_bytes(audio, samplerate)

        def _call(model: str):
            kwargs = {"language": language_hint} if language_hint else {}
            return self._client.audio.transcriptions.create(
                model=model,
                file=("segment.wav", wav_bytes, "audio/wav"),
                response_format="verbose_json",
                **kwargs,
            )

        try:
            response, _used_model = _call_with_fallback(
                _call, self._stt_model, self._stt_fallback_model, "STT",
            )
        except openai.AuthenticationError as exc:
            raise ProviderError(self._auth_error_hint("STT", exc)) from exc
        except openai.APIConnectionError as exc:
            # 🔒 MỚI (Backlog #2, CONTRACTS.md Mục 29) -- cùng lý do Groq,
            # xem _chat_complete() (openai_compat_base.py).
            raise ProviderError(
                f"OpenAI STT lỗi kết nối mạng (đã tự động thử lại "
                f"{_TRANSIENT_NETWORK_MAX_RETRIES} lần, không thành công) — "
                f"kiểm tra lại kết nối Internet rồi thử lại: {exc}"
            ) from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI STT API lỗi: {exc}") from exc
        except Exception as exc:  # phòng lỗi ngoài phạm vi SDK (parse, v.v.)
            raise ProviderError(f"OpenAI STT lỗi không xác định: {exc}") from exc

        text = getattr(response, "text", "") or ""
        language_raw = getattr(response, "language", "") or ""
        language = _normalize_language_to_iso(language_raw)
        segments = getattr(response, "segments", None)
        confidence = _estimate_confidence(segments)
        no_speech_prob = _estimate_no_speech_prob(segments)

        return TranscriptionResult(
            text=text.strip(), language=language, confidence=confidence,
            no_speech_prob=no_speech_prob,
        )
