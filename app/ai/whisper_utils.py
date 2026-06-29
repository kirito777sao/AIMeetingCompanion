"""app/ai/whisper_utils.py
--------------------------
🔒 MỚI (đợt thêm multi-provider, xem CONTRACTS.md Mục 17) — tách từ
`groq_provider.py` (KHÔNG đổi 1 dòng logic nào, chỉ đổi vị trí file) các
hàm thuần xử lý response dạng "Whisper verbose_json" (segments có
avg_logprob/no_speech_prob).

Vì sao tách riêng: OpenAI có model `whisper-1` trả về ĐÚNG hình dạng
response này (đã xác nhận qua tài liệu chính thức của OpenAI — cùng field
avg_logprob/no_speech_prob/segments, vì Groq chỉ host lại chính model
Whisper gốc của OpenAI). `OpenAIProvider.transcribe()` (`openai_provider.py`)
dùng LẠI 100% các hàm này thay vì copy-paste — tránh lệch logic giữa 2
provider khi 1 bên sửa mà quên sửa bên kia.

⚠️ Gemini KHÔNG có endpoint tương đương (xem `gemini_provider.py`) — không
dùng module này.

`groq_provider.py` import lại (re-export) các tên ở đây để
`tests/test_groq_provider_offline.py` (import trực tiếp từ
`app.ai.groq_provider`) tiếp tục hoạt động KHÔNG cần sửa.
"""

from __future__ import annotations

import io
import math
import wave
from typing import Any, Sequence

import numpy as np

from app.ai.base_provider import ProviderError

# Whisper (OpenAI gốc, Groq host lại model này) trả `language` trong
# response verbose_json là TÊN ĐẦY ĐỦ bằng tiếng Anh (ví dụ "english"),
# không phải mã ISO 639-1 -- xác nhận qua dữ liệu thật (Groq) + tài liệu
# Whisper gốc (cùng danh sách ngôn ngữ chuẩn). Dùng để chuẩn hoá NGAY tại
# transcribe(), không để lệch hợp đồng CONTRACTS.md Mục 4 lan ra module khác.
_WHISPER_NAME_TO_ISO: dict[str, str] = {
    "english": "en", "chinese": "zh", "german": "de", "spanish": "es",
    "russian": "ru", "korean": "ko", "french": "fr", "japanese": "ja",
    "portuguese": "pt", "turkish": "tr", "polish": "pl", "catalan": "ca",
    "dutch": "nl", "arabic": "ar", "swedish": "sv", "italian": "it",
    "indonesian": "id", "hindi": "hi", "finnish": "fi", "vietnamese": "vi",
    "hebrew": "he", "ukrainian": "uk", "greek": "el", "malay": "ms",
    "czech": "cs", "romanian": "ro", "danish": "da", "hungarian": "hu",
    "tamil": "ta", "norwegian": "no", "thai": "th", "urdu": "ur",
    "croatian": "hr", "bulgarian": "bg", "lithuanian": "lt", "latin": "la",
    "maori": "mi", "malayalam": "ml", "welsh": "cy", "slovak": "sk",
    "telugu": "te", "persian": "fa", "latvian": "lv", "bengali": "bn",
    "serbian": "sr", "azerbaijani": "az", "slovenian": "sl", "kannada": "kn",
    "estonian": "et", "macedonian": "mk", "basque": "eu", "icelandic": "is",
    "armenian": "hy", "nepali": "ne", "mongolian": "mn", "bosnian": "bs",
    "kazakh": "kk", "albanian": "sq", "swahili": "sw", "galician": "gl",
    "marathi": "mr", "punjabi": "pa", "sinhala": "si", "khmer": "km",
}


def _normalize_language_to_iso(language: str) -> str:
    """Chuẩn hoá string ngôn ngữ Whisper-shaped API trả về thành mã ISO 639-1.

    - "" hoặc None -> "" (không xác định được, giữ nguyên hợp đồng cũ).
    - Đã là mã 2 ký tự (vd "en") -> giữ nguyên, lowercase.
    - Tên đầy đủ (vd "English", "english") -> tra bảng, trả "en".
    - Tên lạ không có trong bảng -> fallback: lowercase nguyên chuỗi (KHÔNG
      đúng chuẩn ISO, nhưng còn hơn để lẫn chữ hoa/thường gây so sánh sai
      ở pipeline.py) — log để biết mà bổ sung bảng sau.
    """
    if not language:
        return ""
    normalized = language.strip().lower()
    if len(normalized) <= 3:
        return normalized
    return _WHISPER_NAME_TO_ISO.get(normalized, normalized)


def _encode_wav_bytes(audio: np.ndarray, samplerate: int) -> bytes:
    """Encode mono float32 [-1,1] audio thành WAV PCM16 bytes trong RAM.

    Dùng io.BytesIO làm buffer ảo — KHÔNG ghi ra đĩa, KHÔNG dùng tempfile.

    Raises:
        ProviderError: nếu audio không phải 1D (không đúng quy ước mono
            của dự án — xem CONTRACTS.md).
    """
    if audio.ndim != 1:
        raise ProviderError(
            f"transcribe() chỉ nhận audio mono 1D, nhận được shape {audio.shape}."
        )

    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(samplerate)
        wav_file.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def _estimate_confidence(segments: Sequence[Any] | None) -> float:
    """Suy confidence tổng quát từ segments verbose_json kiểu Whisper.

    Whisper không trả 1 con số "confidence" trực tiếp. Ước lượng ở đây:
    trung bình của exp(avg_logprob) * (1 - no_speech_prob) qua các
    sub-segment nội bộ provider trả về, kẹp về [0.0, 1.0].

    ⚠️ Vì công thức này NHÂN no_speech_prob vào avg_logprob, 1 con số
    confidence thấp KHÔNG phân biệt được 2 nguyên nhân rất khác nhau — (a)
    model không chắc chắn TỪ NÀO đúng (nhưng vẫn CÓ giọng nói thật, vd
    câu/từ ngắn bị VAD cắt lẻ) và (b) model nghĩ ĐOẠN NÀY không có ai nói
    (im lặng/nhạc nền) nhưng vẫn "bịa" ra text nghe rất tự nhiên (hành vi
    hallucination NỔI TIẾNG của Whisper khi gặp input không có giọng nói).
    Dùng SAI confidence để lọc rác sẽ vô tình lọc mất cả câu nói NGẮN NHƯNG
    THẬT của người dùng. Đây là lý do `_estimate_no_speech_prob()` (dưới
    đây) được tách THÀNH 1 HÀM RIÊNG, KHÔNG gộp chung vào confidence — xem
    TranscriptionResult.no_speech_prob.

    Args:
        segments: list các object/segment có attribute avg_logprob và
            no_speech_prob, hoặc None nếu provider không trả segments.

    Returns:
        float trong [0.0, 1.0]. 0.0 nếu segments rỗng/None.
    """
    if not segments:
        return 0.0

    scores: list[float] = []
    for seg in segments:
        avg_logprob = getattr(seg, "avg_logprob", -1.0)
        no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
        score = math.exp(avg_logprob) * (1.0 - no_speech_prob)
        scores.append(score)

    confidence = sum(scores) / len(scores)
    return float(min(max(confidence, 0.0), 1.0))


def _estimate_no_speech_prob(segments: Sequence[Any] | None) -> float:
    """🔒 (CONTRACTS.md Mục 11) — trung bình no_speech_prob THÔ (KHÔNG nhân
    với avg_logprob) qua các sub-segment provider trả về.

    Vì sao cần hàm RIÊNG, không tái dùng/đọc lại từ _estimate_confidence():
    đây là tín hiệu "model tự đánh giá đoạn audio gốc có giọng nói hay
    không", độc lập với "model chắc chắn tới đâu về CHỮ đã sinh ra" — gộp 2
    thứ này (như confidence đang làm) che mất chính xác tín hiệu cần để lọc
    hallucination-trên-im-lặng.

    Returns:
        float trong [0.0, 1.0]. 0.0 (mặc định "chắc chắn có giọng nói") nếu
        segments rỗng/None — KHÁC _estimate_confidence() (trả 0.0 nghĩa là
        "không chắc chắn gì cả"), ở đây 0.0 là lựa chọn AN TOÀN: thiếu
        thông tin thì KHÔNG tự suy đoán "có thể là im lặng" để tránh lọc
        nhầm nội dung thật khi response không có segments.
    """
    if not segments:
        return 0.0

    probs = [float(getattr(seg, "no_speech_prob", 0.0)) for seg in segments]
    avg = sum(probs) / len(probs)
    return float(min(max(avg, 0.0), 1.0))
