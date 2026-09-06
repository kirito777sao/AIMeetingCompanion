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
    _call_with_fallback,
    _coerce_to_string_list,
    _DEFAULT_CLIENT_TIMEOUT_SECONDS,
    _language_name,
    _looks_like_wrong_script,
    _resolve_client_timeout_seconds,
    _retry_with_backoff,
    _script_char_counts,
    _sleep_backoff,
    _TRANSIENT_NETWORK_MAX_RETRIES,
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
      `openai/gpt-oss-120b`; fallback `openai/gpt-oss-20b` CHỈ KHI 429.

    🔒 SỬA (02/09/2026, phát hiện từ log lỗi thật của người dùng — KHÔNG
    thuộc phạm vi Vòng 9/Mục 18, sửa riêng vì chặn cả translate/
    suggest_answer/summarize hoàn toàn): Groq đã **decommission**
    `llama-3.3-70b-versatile` VÀ `llama-3.1-8b-instant` từ 16/08/2026 (thông
    báo từ 17/06/2026, xem https://console.groq.com/docs/deprecations) —
    gọi 2 model này giờ trả lỗi 404 `model_not_found` cho MỌI request, kể cả
    API key hợp lệ (dễ nhầm là lỗi API key vì message không rõ ràng — xem
    log người dùng gửi: STT vẫn chạy tốt qua Whisper, chỉ chat model lỗi).
    Đổi default sang model Groq khuyến nghị thay thế: `openai/gpt-oss-120b`
    (thay `llama-3.3-70b-versatile`) và `openai/gpt-oss-20b` (thay
    `llama-3.1-8b-instant`) — cả 2 đều nằm trong danh sách khuyến nghị
    chính thức của Groq. CHƯA tự test THẬT với API key thật trong sandbox
    này (không có mạng ra ngoài tới Groq) — cần bạn xác nhận lại 2 model
    mới hoạt động đúng trên máy bạn.
    """

    _provider_label = "Groq"

    # Giá trị mẫu trong .env.example -- nếu người dùng quên thay bằng key
    # thật, Groq sẽ trả 401 "Invalid API Key" rất khó hiểu nếu không check
    # trước. Phát hiện sớm để báo lỗi rõ ràng hơn nhiều.
    _PLACEHOLDER_KEY = "your_groq_api_key_here"

    def __init__(
        self,
        api_key: str | None = None,
        stt_model: str | None = None,
        stt_fallback_model: str | None = None,
        translate_model: str | None = None,
        translate_fallback_model: str | None = None,
        client_timeout_seconds: float | None = None,
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
            stt_model / stt_fallback_model / translate_model /
                translate_fallback_model: 🔒 SỬA (02/09/2026, CONTRACTS.md
                Mục 19) — GIỮ NGUYÊN Ý NGHĨA như trước (model STT/chat ưu
                tiên + dự phòng khi 429/404), nhưng đổi default từ hardcode
                CỨNG sang **3 tầng ưu tiên**: (1) tham số truyền trực tiếp
                khi gọi hàm này (kể cả `""` để TẮT fallback — GIỮ NGUYÊN
                hành vi cũ) > (2) biến môi trường tương ứng
                (`GROQ_STT_MODEL`, `GROQ_STT_FALLBACK_MODEL`,
                `GROQ_TRANSLATE_MODEL`, `GROQ_TRANSLATE_FALLBACK_MODEL`
                trong `.env`) > (3) hardcode mặc định trong code
                (`"whisper-large-v3"`, `"whisper-large-v3-turbo"`,
                `"openai/gpt-oss-120b"`, `"openai/gpt-oss-20b"`).
                **Lý do thêm tầng (2)**: đây là lần THỨ 2 Groq decommission
                model chat mặc định (lần 1: không rõ, lần 2: 16/08/2026,
                xem CONTRACTS.md Mục 19) — nếu xảy ra LẦN NỮA trước khi kịp
                cập nhật code, người dùng tự sửa được NGAY qua `.env`
                (không cần chờ code mới), không bị KHOÁ CỨNG chờ code như
                lần này.
            client_timeout_seconds: 🔒 MỚI (Backlog #1, CONTRACTS.md Mục
                28) — timeout (giây) cho MỌI lời gọi qua `self._client`
                (cả `transcribe()` lẫn translate/suggest_answer/summarize/
                chat) — SDK `openai` mặc định KHÔNG set timeout tường minh,
                rơi vào default ~600s (gần 10 phút) của `httpx` bên dưới,
                treo cả pipeline nếu mạng "treo" (xem
                `_resolve_client_timeout_seconds()` ở `openai_compat_base.py`
                để biết đầy đủ lý do). 3 tầng ưu tiên giống hệt các tham số
                model ở trên: (1) tham số này (kể cả giá trị bất kỳ được
                truyền tường minh) > (2) biến môi trường
                `GROQ_CLIENT_TIMEOUT_SECONDS` (chỉ nhận số thực > 0, sai
                định dạng fallback default, không raise) > (3) hardcode
                `_DEFAULT_CLIENT_TIMEOUT_SECONDS` (30.0s).

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
        self._client_timeout_seconds = _resolve_client_timeout_seconds(
            client_timeout_seconds, "GROQ_CLIENT_TIMEOUT_SECONDS",
        )
        self._client = OpenAI(
            api_key=resolved_key, base_url=GROQ_BASE_URL, timeout=self._client_timeout_seconds,
        )
        # 🔒 SỬA (02/09/2026, CONTRACTS.md Mục 19) -- 3 tầng ưu tiên, xem
        # docstring __init__ ở trên. `is not None` (KHÔNG dùng `or`) để
        # phân biệt đúng "không truyền gì" (None -> đọc tiếp env/default)
        # với "truyền rỗng có chủ đích" ("" -> TẮT fallback, GIỮ NGUYÊN
        # hành vi cũ, KHÔNG bị ghi đè bởi env/default).
        self._stt_model = (
            stt_model if stt_model is not None
            else os.environ.get("GROQ_STT_MODEL") or "whisper-large-v3"
        )
        self._stt_fallback_model = (
            stt_fallback_model if stt_fallback_model is not None
            # KHÔNG dùng `or` ở đây (khác _stt_model/_translate_model phía
            # trên) -- env var đặt "" có chủ đích (TẮT fallback qua .env)
            # phải được TÔN TRỌNG, không bị "or" âm thầm thay bằng default.
            else os.environ.get("GROQ_STT_FALLBACK_MODEL", "whisper-large-v3-turbo")
        )
        self._translate_model = (
            translate_model if translate_model is not None
            else os.environ.get("GROQ_TRANSLATE_MODEL") or "openai/gpt-oss-120b"
        )
        self._translate_fallback_model = (
            translate_fallback_model if translate_fallback_model is not None
            else os.environ.get("GROQ_TRANSLATE_FALLBACK_MODEL", "openai/gpt-oss-20b")
        )

    def _auth_error_hint(self, api_label: str, exc: Exception) -> str:
        return _auth_error_hint("Groq", api_label, "GROQ_API_KEY", _GROQ_KEYS_URL, exc)

    def transcribe(self, audio, samplerate: int, language_hint: str = "") -> TranscriptionResult:
        """Xem docstring đầy đủ ở AIProvider.transcribe()."""
        wav_bytes = _encode_wav_bytes(audio, samplerate)

        def _call(model: str):
            # 🔒 MỚI (CONTRACTS.md Mục 38) -- `language` là tham số CHÍNH
            # THỨC của Whisper API (Groq/OpenAI) để HINT ngôn ngữ, KHÔNG
            # phải tự chế. Chỉ truyền khi người dùng CHỦ ĐỘNG chọn (khác
            # rỗng) -- rỗng nghĩa là "Tự động", giữ NGUYÊN hành vi cũ (tự
            # đoán ngôn ngữ), không truyền field không cần thiết.
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
            # 🔒 MỚI (Backlog #2, CONTRACTS.md Mục 29) -- xem giải thích
            # đầy đủ ở _chat_complete() (openai_compat_base.py); ở đây lặp
            # lại cho transcribe() vì method này KHÔNG đi qua _chat_complete.
            raise ProviderError(
                f"Groq STT lỗi kết nối mạng (đã tự động thử lại "
                f"{_TRANSIENT_NETWORK_MAX_RETRIES} lần, không thành công) — "
                f"kiểm tra lại kết nối Internet rồi thử lại: {exc}"
            ) from exc
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
