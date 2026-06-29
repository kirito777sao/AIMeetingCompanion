"""app/ai/gemini_provider.py
-----------------------------
🔒 MỚI (đợt thêm multi-provider — Groq/OpenAI/Gemini, xem CONTRACTS.md Mục
17) — implementation `AIProvider` dùng Google Gemini API.

⚠️ **KHÁC BIỆT KIẾN TRÚC QUAN TRỌNG so với Groq/OpenAI — đọc kỹ trước khi
sửa**: Google CÓ lớp tương thích OpenAI cho Gemini
(`https://generativelanguage.googleapis.com/v1beta/openai/`, dùng được
NGUYÊN SDK `openai` cho `chat.completions.create` — xác nhận qua tài liệu
chính thức Google 05/2026) NHƯNG lớp tương thích đó CHỈ phủ chat
completions/embeddings/image generation, **KHÔNG phủ
`audio.transcriptions`** (xác nhận qua tài liệu Gemini "Audio
understanding": Gemini xử lý audio qua `generateContent` đa phương thức —
gửi audio như 1 phần nội dung kèm prompt văn bản — KHÔNG có endpoint dạng
Whisper trả `segments`/`avg_logprob`/`no_speech_prob`).

Hệ quả thiết kế (CỐ Ý, không phải thiếu sót):
1. `translate()`/`suggest_answer()`/`summarize()` (chat) dùng LẠI
   `OpenAICompatProvider` (`self._client` trỏ `base_url` tương thích OpenAI
   của Gemini) — y hệt Groq/OpenAI.
2. `transcribe()` viết RIÊNG HOÀN TOÀN — gọi REST `generateContent` trực
   tiếp qua `httpx` (KHÔNG qua SDK `openai`, vì SDK đó không áp dụng được
   cho endpoint native của Google), yêu cầu model trả JSON có cấu trúc
   (`responseSchema`) gồm transcript + ngôn ngữ + cờ "có phải im
   lặng/non-speech".
3. **`confidence` là SỐ CỐ ĐỊNH (placeholder), KHÔNG phải số đo được** —
   nói thật, không nhận vơ (cùng tinh thần PROJECT_SPEC.md mục 5 NFR về
   "mã hoá" ở `config_store.py`): Gemini KHÔNG expose avg_logprob/segments
   theo kiểu Whisper qua đường này, nên không có cách tính confidence
   liên tục đáng tin cậy mà không tốn thêm 1 lớp phức tạp (vd
   `response_logprobs` của Gemini đo độ chắc của TOKEN sinh ra, không
   phải độ chắc "đây có đúng là âm thanh gốc" — khác ý nghĩa avg_logprob
   của Whisper). `no_speech_prob` thay vào đó dùng tín hiệu NHỊ PHÂN (0.0
   hoặc 1.0) dựa trên model TỰ BÁO CÁO qua `is_silence_or_nonspeech` —
   vẫn hoạt động ĐÚNG với ngưỡng lọc `NO_SPEECH_PROB_DROP_THRESHOLD=0.6`
   của `pipeline.py` (0.0/1.0 đều nằm rõ về 1 phía ngưỡng), nhưng kém
   "mịn" hơn no_speech_prob liên tục thật của Whisper — CHƯA verify được
   độ chính xác của tín hiệu tự-báo-cáo này bằng audio Gemini thật trong
   sandbox này (không network), cần bạn tự test lại với đoạn im
   lặng/nhạc nền đã dùng để verify Groq (CONTRACTS.md Mục 11) để đối
   chứng.
4. **Rate-limit (429)**: lớp tương thích OpenAI của Google trả lỗi qua
   CÙNG SDK `openai` nên `_call_with_rate_limit_fallback()` (dùng cho
   phần chat) hoạt động được — nhưng đường REST riêng của `transcribe()`
   (mục 2) KHÔNG đi qua SDK đó, nên tự xử lý 429 riêng ở
   `_post_generate_content()` dưới đây, KHÔNG có model dự phòng để
   fallback (Gemini không có "STT model rẻ hơn" tương đương
   whisper-turbo) — 429 ở transcribe() raise thẳng ProviderError, báo rõ
   nguyên nhân.

⚠️ Tên model (`gemini-2.5-flash` chat + STT, fallback chat
`gemini-2.0-flash`) đổi NHANH như mọi provider AI khác — xem cảnh báo
tương tự ở `openai_provider.py`, truyền `stt_model=`/`translate_model=`/
`translate_fallback_model=` khi khởi tạo nếu cần đổi, KHÔNG sửa code.
"""

from __future__ import annotations

import base64
import json
import os

import httpx
from openai import OpenAI

from app import config_store
from app.ai.base_provider import ProviderError, TranscriptionResult
from app.ai.openai_compat_base import OpenAICompatProvider, _auth_error_hint
from app.ai.whisper_utils import _encode_wav_bytes, _normalize_language_to_iso

# Lớp tương thích OpenAI của Google -- CHỈ dùng cho phần chat (xem mục 1
# docstring đầu file). transcribe() dùng GEMINI_NATIVE_BASE_URL bên dưới.
GEMINI_OPENAI_COMPAT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_NATIVE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_KEYS_URL = "https://aistudio.google.com/apikey"

_PLACEHOLDER_KEY = "your_gemini_api_key_here"

# Xem mục 3 docstring đầu file -- KHÔNG phải số đo được, là 1 giá trị
# trung bình hợp lý để TranscriptionResult.confidence không rỗng/gây nhầm
# là "0.0 = không chắc chắn gì cả" (xem ý nghĩa 0.0 ở base_provider.py).
_GEMINI_FIXED_CONFIDENCE_PLACEHOLDER = 0.75

_GEMINI_TRANSCRIBE_PROMPT = (
    "Transcribe the speech in this audio clip EXACTLY as spoken, in the "
    "ORIGINAL language(s) actually spoken -- do NOT translate. If the clip "
    "mixes languages, transcribe each part in its own original script. If "
    "the clip is silence, background music/noise only, or otherwise "
    "contains no intelligible speech, set is_silence_or_nonspeech to true "
    "and leave transcript as an empty string -- do NOT invent "
    "plausible-sounding text for audio that has no real speech in it. "
    "Detect the single PRIMARY spoken language of this clip and return its "
    "ISO 639-1 two-letter code (e.g. 'en', 'vi', 'zh') in "
    "language_iso639_1; if genuinely undetermined, return an empty string."
)

_GEMINI_TRANSCRIBE_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "transcript": {"type": "STRING"},
        "language_iso639_1": {"type": "STRING"},
        "is_silence_or_nonspeech": {"type": "BOOLEAN"},
    },
    "required": ["transcript", "language_iso639_1", "is_silence_or_nonspeech"],
}


class GeminiProvider(OpenAICompatProvider):
    """AIProvider implementation dùng Google Gemini API -- xem cảnh báo
    kiến trúc đầy đủ ở docstring đầu file TRƯỚC khi sửa `transcribe()`."""

    _provider_label = "Gemini"

    def __init__(
        self,
        api_key: str | None = None,
        stt_model: str = "gemini-2.5-flash",
        translate_model: str = "gemini-2.5-flash",
        translate_fallback_model: str = "gemini-2.0-flash",
        http_timeout_seconds: float = 60.0,
    ) -> None:
        """Khởi tạo provider, kết nối tới Gemini.

        Args:
            api_key: Gemini API key. Nếu None, đọc theo thứ tự ưu tiên: (1)
                `app.config_store.load_api_key(provider="gemini")`; (2)
                biến môi trường `GEMINI_API_KEY` (dev, qua `.env`).
            stt_model: model dùng cho `transcribe()` (REST generateContent
                trực tiếp, KHÔNG qua SDK `openai`) — mặc định
                "gemini-2.5-flash". KHÔNG có fallback model riêng (xem mục
                4 docstring đầu file).
            translate_model / translate_fallback_model: model chat (qua
                lớp tương thích OpenAI) cho dịch/gợi ý/tóm tắt.
            http_timeout_seconds: timeout cho lời gọi REST `transcribe()`
                — STT mỗi segment audio ngắn (vài giây), 60s là dư thừa an
                toàn cho network chậm, không phải con số cần tinh chỉnh.

        Raises:
            ProviderError: thiếu api_key ở mọi nguồn, hoặc key vẫn là giá
                trị mẫu trong .env.example.
        """
        resolved_key = (
            api_key
            or config_store.load_api_key(provider="gemini")
            or os.environ.get("GEMINI_API_KEY")
        )
        if resolved_key:
            resolved_key = resolved_key.strip().strip('"').strip("'")
        if not resolved_key:
            raise ProviderError(
                "Thiếu Gemini API key — vào ⚙️ Cài đặt trong app, chọn provider "
                "Gemini và dán key của bạn (lấy miễn phí tại "
                f"{_GEMINI_KEYS_URL}), hoặc (nếu đang chạy từ source code để "
                "dev) truyền api_key= hoặc set biến môi trường GEMINI_API_KEY "
                "trong file .env."
            )
        if resolved_key == _PLACEHOLDER_KEY:
            raise ProviderError(
                "GEMINI_API_KEY trong .env vẫn là giá trị MẪU, chưa được thay "
                f"bằng key THẬT. Lấy key thật tại {_GEMINI_KEYS_URL}."
            )
        self._api_key = resolved_key
        self._client = OpenAI(api_key=resolved_key, base_url=GEMINI_OPENAI_COMPAT_BASE_URL)
        self._stt_model = stt_model
        self._translate_model = translate_model
        self._translate_fallback_model = translate_fallback_model
        self._http_timeout_seconds = http_timeout_seconds

    def _auth_error_hint(self, api_label: str, exc: Exception) -> str:
        return _auth_error_hint("Gemini", api_label, "GEMINI_API_KEY", _GEMINI_KEYS_URL, exc)

    def transcribe(self, audio, samplerate: int) -> TranscriptionResult:
        """Xem docstring đầy đủ ở AIProvider.transcribe() + mục 2/3 docstring
        đầu file này (KHÁC hẳn cách Groq/OpenAI làm — không có segments/
        avg_logprob thật)."""
        wav_bytes = _encode_wav_bytes(audio, samplerate)
        b64_audio = base64.b64encode(wav_bytes).decode("ascii")

        payload = {
            "contents": [{
                "parts": [
                    {"text": _GEMINI_TRANSCRIBE_PROMPT},
                    {"inlineData": {"mimeType": "audio/wav", "data": b64_audio}},
                ],
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _GEMINI_TRANSCRIBE_RESPONSE_SCHEMA,
            },
        }

        parsed = self._post_generate_content(self._stt_model, payload)

        transcript = str(parsed.get("transcript", "") or "").strip()
        language = _normalize_language_to_iso(str(parsed.get("language_iso639_1", "") or ""))
        is_silence = bool(parsed.get("is_silence_or_nonspeech", False))

        return TranscriptionResult(
            text=transcript,
            language=language,
            confidence=_GEMINI_FIXED_CONFIDENCE_PLACEHOLDER,
            no_speech_prob=1.0 if is_silence else 0.0,
        )

    def _post_generate_content(self, model: str, payload: dict) -> dict:
        """Thực hiện đúng 1 lần gọi REST `generateContent`, raise
        `ProviderError` khi lỗi, trả dict đã `json.loads()` từ phần text
        response (model trả 1 JSON STRING vì `responseMimeType=
        "application/json"`, KHÔNG phải JSON object lồng trực tiếp trong
        response REST — đây là 2 lớp JSON khác nhau, dễ nhầm khi sửa).

        Tách thành method RIÊNG (không inline trong `transcribe()`) để
        test tự monkeypatch trực tiếp method này — KHÔNG cần shim
        `httpx`/network thật, cùng tinh thần test
        `provider._client = fake_client` của Groq/OpenAI (xem
        `tests/test_gemini_provider_offline.py`).
        """
        url = f"{GEMINI_NATIVE_BASE_URL}/models/{model}:generateContent"
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=self._http_timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise ProviderError(f"Gemini STT lỗi kết nối: {exc}") from exc

        if response.status_code in (401, 403):
            raise ProviderError(
                self._auth_error_hint("STT", RuntimeError(response.text[:300]))
            )
        if response.status_code == 429:
            raise ProviderError(
                "Gemini STT bị giới hạn tần suất (429) — hết quota free tier "
                "ngay lúc này, đợi vài phút rồi thử lại. Gemini KHÔNG có model "
                f"STT dự phòng để tự fallback như Groq/OpenAI (model đang dùng: "
                f"{model})."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Gemini STT API lỗi (HTTP {response.status_code}): "
                f"{response.text[:300]}"
            ) from exc

        try:
            body = response.json()
            raw_text = body["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ProviderError(
                f"Gemini STT trả response không đúng định dạng kỳ vọng: {exc}. "
                f"Nội dung thô: {response.text[:300]!r}"
            ) from exc
