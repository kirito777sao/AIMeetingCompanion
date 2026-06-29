"""Implementation AIProvider dùng Groq API (OpenAI-compatible SDK).

base_url cố định theo PROJECT_SPEC.md mục 8:
https://api.groq.com/openai/v1

⚠️ Đã chạy thật trên Windows với GROQ_API_KEY thật (xem CONTRACTS.md mục
"Đã verify bằng dữ liệu thật" để biết log thay đổi) — phát hiện 1 điểm lệch
hợp đồng quan trọng: Groq Whisper (`response.language` của verbose_json)
trả về TÊN NGÔN NGỮ ĐẦY ĐỦ (ví dụ "English"), KHÔNG phải mã ISO 639-1 như
CONTRACTS.md Mục 4 đã chốt ("en"). Đã thêm `_normalize_language_to_iso()`
để chuẩn hoá ngay tại transcribe(), trước khi trả `TranscriptionResult` —
mọi module phía sau (pipeline.py, translate(), UI) tiếp tục nhận đúng mã
ISO như hợp đồng, không cần biết chi tiết lệch này của Groq API.

Công thức _estimate_confidence() đã verify khớp với dữ liệu thật (range
quan sát được: 0.46-0.93 trên 1 đoạn podcast tiếng Anh rõ ràng) — số thấp
nhất (0.46) đúng vào 1 từ đơn lẻ ("Human.") tách lẻ do VAD cắt giữa câu,
hợp lý với trực giác (câu càng ngắn/cụt thì model càng kém tự tin).

🔒 REFACTOR (đợt thêm multi-provider — Groq/OpenAI/Gemini, xem
CONTRACTS.md Mục 17): phần translate()/suggest_answer()/summarize() (CHUNG
với OpenAI/Gemini vì cùng đi qua SDK `openai`) đã chuyển sang
`app/ai/openai_compat_base.py` (`OpenAICompatProvider`, `GroqProvider` kế
thừa lớp này). Phần parse response Whisper (CHUNG với OpenAI vì model
`whisper-1` của OpenAI trả cùng hình dạng response) đã chuyển sang
`app/ai/whisper_utils.py`. File này CHỦ Ý import lại (re-export) mọi tên
mà `tests/test_groq_provider_offline.py` cần — file test đó KHÔNG sửa gì,
vẫn import trực tiếp từ `app.ai.groq_provider` như trước, vẫn PASS 100%
(đã tự chạy lại để xác nhận, xem README mục liên quan). Hành vi/text
prompt GIỮ NGUYÊN TUYỆT ĐỐI — đây là di chuyển code (move), không phải
viết lại (rewrite).
"""

from __future__ import annotations

import os

import openai
from openai import OpenAI

from app import config_store
from app.ai.base_provider import ProviderError, TranscriptionResult
from app.ai.openai_compat_base import (  # noqa: F401 - re-export cho test cũ
    OpenAICompatProvider,
    _auth_error_hint,
    _call_with_rate_limit_fallback,
    _coerce_to_string_list,
    _language_name,
    _looks_like_wrong_script,
    _script_char_counts,
)
from app.ai.whisper_utils import (  # noqa: F401 - re-export cho test cũ
    _WHISPER_NAME_TO_ISO,
    _encode_wav_bytes,
    _estimate_confidence,
    _estimate_no_speech_prob,
    _normalize_language_to_iso,
)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_KEYS_URL = "https://console.groq.com/keys"


class GroqProvider(OpenAICompatProvider):
    """AIProvider implementation dùng Groq Whisper (STT) + Groq Llama (dịch
    + gợi ý trả lời + tổng hợp biên bản).

    Cả 4 method (transcribe, translate, suggest_answer, summarize) ĐÃ CHỐT
    theo CONTRACTS.md Mục 4, đã implement đầy đủ. translate/suggest_answer/
    summarize giờ kế thừa từ `OpenAICompatProvider` (xem
    `openai_compat_base.py`) — chỉ `transcribe()` được implement riêng ở
    đây.

    ⚠️ **Fallback model tự động theo rate limit (sau phản hồi test thật +
    dashboard log người dùng gửi)**:
    - STT: ưu tiên `whisper-large-v3` (đầy đủ, chính xác hơn turbo — đúng
      phản hồi test "nghe sai/sót từ"); fallback `whisper-large-v3-turbo`
      CHỈ KHI gặp 429 (hết quota free tier ở model đầy đủ ngay lúc đó).
    - Chat (translate/suggest_answer/summarize): ưu tiên
      `llama-3.3-70b-versatile`; fallback `llama-3.1-8b-instant` CHỈ KHI
      429.
    """

    _provider_label = "Groq"

    # Giá trị mẫu trong .env.example -- nếu người dùng quên thay bằng key
    # thật, Groq sẽ trả 401 "Invalid API Key" rất khó hiểu nếu không check
    # trước. Phát hiện sớm để báo lỗi rõ ràng hơn nhiều.
    _PLACEHOLDER_KEY = "your_groq_api_key_here"

    def __init__(
        self,
        api_key: str | None = None,
        stt_model: str = "whisper-large-v3",
        stt_fallback_model: str = "whisper-large-v3-turbo",
        translate_model: str = "llama-3.3-70b-versatile",
        translate_fallback_model: str = "llama-3.1-8b-instant",
    ) -> None:
        """Khởi tạo provider, kết nối tới Groq qua SDK OpenAI-compatible.

        Args:
            api_key: Groq API key. Nếu None, đọc theo thứ tự ưu tiên: (1)
                `app.config_store.load_api_key(provider="groq")` — key
                người dùng CUỐI tự nhập qua Settings UI
                (`ui/settings_dialog.py`, F14, xem CONTRACTS.md Mục 12) —
                đây là đường BẮT BUỘC cho bản đóng gói `.exe` phân phối,
                KHÔNG có `.env` đi kèm; (2) biến môi trường `GROQ_API_KEY`
                (nạp qua `python-dotenv` ở `app/main.py`, đường DEV hiện
                tại của bạn đang dùng, VẪN hoạt động bình thường, không bị
                thay thế) — chỉ dùng khi config_store chưa lưu gì (vd vừa
                đóng gói lần đầu).
            stt_model: Model STT ưu tiên, mặc định "whisper-large-v3" (đầy
                đủ, chính xác hơn turbo).
            stt_fallback_model: Model STT dự phòng, dùng tự động khi
                `stt_model` bị Groq trả 429 (hết quota free tier ngay lúc
                đó) — mặc định "whisper-large-v3-turbo". Đặt "" hoặc bằng
                `stt_model` để TẮT fallback (lỗi 429 sẽ raise thẳng).
            translate_model: Model dịch/sinh text ưu tiên, mặc định
                "llama-3.3-70b-versatile".
            translate_fallback_model: Model dự phòng cho translate()/
                suggest_answer()/summarize(), dùng tự động khi
                `translate_model` bị 429 — mặc định "llama-3.1-8b-instant".
                Đặt "" hoặc bằng `translate_model` để TẮT fallback.

        Raises:
            ProviderError: nếu không tìm được api_key ở CẢ 3 nguồn trên,
                hoặc key vẫn là giá trị mẫu trong .env.example chưa được thay.
        """
        resolved_key = (
            api_key
            or config_store.load_api_key(provider="groq")
            or os.environ.get("GROQ_API_KEY")
        )
        if resolved_key:
            # Dọn whitespace/quote thừa hay gặp khi copy-paste key vào .env
            # (vd lỡ kèm dấu " hoặc xuống dòng) -- KHÔNG đổi nội dung key
            # thật, chỉ bỏ ký tự rác ở 2 đầu.
            resolved_key = resolved_key.strip().strip('"').strip("'")
        if not resolved_key:
            raise ProviderError(
                "Thiếu Groq API key — vào ⚙️ Cài đặt trong app để nhập API "
                "key của bạn (lấy tại https://console.groq.com/keys), hoặc "
                "(nếu đang chạy từ source code để dev) truyền api_key= hoặc "
                "set biến môi trường GROQ_API_KEY trong file .env."
            )
        if resolved_key == self._PLACEHOLDER_KEY:
            raise ProviderError(
                "GROQ_API_KEY trong .env vẫn là giá trị MẪU "
                f"('{self._PLACEHOLDER_KEY}'), chưa được thay bằng key THẬT. "
                "Lấy key thật tại https://console.groq.com/keys, mở file .env "
                "(KHÔNG phải .env.example), sửa dòng GROQ_API_KEY=... rồi lưu lại."
            )
        self._client = OpenAI(api_key=resolved_key, base_url=GROQ_BASE_URL)
        self._stt_model = stt_model
        self._stt_fallback_model = stt_fallback_model
        self._translate_model = translate_model
        self._translate_fallback_model = translate_fallback_model

    def _auth_error_hint(self, api_label: str, exc: Exception) -> str:
        return _auth_error_hint("Groq", api_label, "GROQ_API_KEY", _GROQ_KEYS_URL, exc)

    def transcribe(self, audio, samplerate: int) -> TranscriptionResult:
        """Xem docstring đầy đủ ở AIProvider.transcribe()."""
        wav_bytes = _encode_wav_bytes(audio, samplerate)

        def _call(model: str):
            return self._client.audio.transcriptions.create(
                model=model,
                file=("segment.wav", wav_bytes, "audio/wav"),
                response_format="verbose_json",
            )

        try:
            response, _used_model = _call_with_rate_limit_fallback(
                _call, self._stt_model, self._stt_fallback_model, "STT",
            )
        except openai.AuthenticationError as exc:
            raise ProviderError(self._auth_error_hint("STT", exc)) from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"Groq STT API lỗi: {exc}") from exc
        except Exception as exc:  # phòng lỗi ngoài phạm vi SDK (parse, v.v.)
            raise ProviderError(f"Groq STT lỗi không xác định: {exc}") from exc

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
