"""Interface trừu tượng cho AI provider (Groq/Gemini/local).

UI/wiring layer CHỈ được gọi qua interface này (AIProvider), không gọi
trực tiếp API/provider cụ thể — xem PROJECT_SPEC.md mục 8 và CONTRACTS.md
Mục 4. Mục đích: đổi qua lại giữa Groq/Gemini/local khi một bên thay đổi
chính sách free tier mà không phải sửa UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


class ProviderError(RuntimeError):
    """Lỗi khi gọi AI provider: network, auth, rate limit, response không hợp lệ.

    Mọi provider cụ thể (groq_provider.py, ...) phải wrap exception gốc của
    SDK/HTTP client vào ProviderError trước khi raise ra ngoài interface —
    không để leak exception thô của thư viện thứ ba ra UI/wiring layer.
    """


@dataclass
class TranscriptionResult:
    """Kết quả transcribe 1 segment audio.

    Attributes:
        text: Transcript gốc (chưa dịch).
        language: Mã ngôn ngữ ISO 639-1 do model nhận diện, ví dụ "en",
            "vi", "zh". Có thể là chuỗi rỗng nếu provider không xác định được.
        confidence: Độ tin cậy ước lượng, trong khoảng [0.0, 1.0]. 0.0
            nghĩa là không xác định được / model không chắc chắn.
        no_speech_prob: 🔒 THÊM sau phản hồi test thật (xem CONTRACTS.md Mục
            11) — xác suất [0.0, 1.0] đoạn audio này KHÔNG CÓ giọng nói thật
            (im lặng/nhiễu/nhạc nền), lấy TRỰC TIẾP từ no_speech_prob nội bộ
            của Whisper — KHÁC với `confidence` (vốn đã NHÂN no_speech_prob
            vào avg_logprob nên không tách bạch được 2 nguyên nhân: "model
            không chắc TỪ NÀO" và "model nghĩ ĐOẠN NÀY không có ai nói").
            Tách riêng field này vì confidence thấp có thể do CHÍNH ĐÁNG
            (câu/từ ngắn bị VAD cắt lẻ, vẫn là giọng nói thật — xem ví dụ
            "Human." confidence 0.46 trong groq_provider.py) — không nên
            dùng confidence để quyết định ẨN bớt nội dung người dùng thực sự
            đã nói. no_speech_prob cao mới là tín hiệu ĐÚNG cho "rất có thể
            đây là hallucination trên im lặng/nhạc nền", dùng ở pipeline.py
            để lọc, KHÔNG dùng confidence cho việc đó. Optional, mặc định
            0.0 ("chắc chắn có giọng nói") để KHÔNG phá vỡ provider khác
            (vd Gemini/local Whisper sau này) chưa trả được giá trị này.
    """

    text: str
    language: str
    confidence: float
    no_speech_prob: float = 0.0


@dataclass
class SummaryResult:
    """Kết quả tổng hợp biên bản 1 phiên họp (Phase 3, F10-F11).

    `overview` là 1 đoạn văn (string). `decisions`/`action_items` là
    **list[str]** — mỗi phần tử 1 ý gọn, KHÔNG phải 1 string lớn chứa
    nhiều dòng/dấu "-". List RỖNG nghĩa là model xác nhận không có
    quyết định/action item rõ ràng (KHÁC None — None nghĩa là chưa
    chạy/lỗi, [] nghĩa là đã chạy và xác nhận "không có gì").

    ⚠️ **Đổi từ `str` sang `list[str]` sau khi phát hiện lỗi thật**: thiết
    kế ban đầu (1 string lớn, các dòng nối bằng "\\n" + tự thêm "- ") khiến
    Groq (`response_format={"type":"json_object"}`) nhiều lần trả JSON
    KHÔNG hợp lệ — model cố nhúng cả 1 đoạn nhiều dòng có gạch đầu dòng vào
    làm GIÁ TRỊ của 1 field JSON, đôi khi quên bọc dấu ngoặc kép cho cả
    field đó (lỗi 400 "Failed to generate JSON" từ Groq, xem CONTRACTS.md
    Mục 4). Mỗi phần tử list là 1 string NGẮN, không xuống dòng nội bộ —
    dễ cho model encode đúng cú pháp JSON hơn nhiều so với 1 blob nhiều
    dòng. Tách 3 field riêng (thay vì 1 string lớn duy nhất) để Phase 3
    Bước 2 (UI report) render được từng mục có heading riêng — không cần
    parse lại text.
    """

    overview: str                # Tóm tắt — 1 đoạn văn
    decisions: list[str]          # Quyết định — mỗi phần tử 1 ý, [] nếu không có
    action_items: list[str]        # Việc cần làm — mỗi phần tử 1 ý, [] nếu không có


class AIProvider(ABC):
    """Interface trừu tượng cho mọi AI provider (Groq/Gemini/local).

    Trạng thái chốt (xem CONTRACTS.md Mục 4):
        - transcribe(), translate(): ĐÃ CHỐT, đã chạy thật trên Windows
          (translate() vừa thêm context_text optional sau phản hồi test).
        - suggest_answer(): 🔒 ĐÃ CHỐT (Phase 2, F5-F7) — chốt khi bắt đầu
          Phase 2, sau khi xác nhận translate() dùng lại được cho bước dịch
          ngược, không cần method riêng.
        - summarize(): 🔒 ĐÃ CHỐT (Phase 3, F10-F11) — chốt khi bắt đầu
          Phase 3 Bước 1.
    """

    @abstractmethod
    def transcribe(self, audio: np.ndarray, samplerate: int) -> TranscriptionResult:
        """Chuyển 1 segment audio thành text + ngôn ngữ + độ tin cậy.

        Args:
            audio: Mono float32, 1D, range [-1.0, 1.0] (quy ước chung của
                dự án — xem CONTRACTS.md). KHÔNG nhận audio đa kênh.
            samplerate: Sample rate thật của `audio` (Hz). Bắt buộc truyền
                rõ — KHÔNG hardcode — vì `audio` có thể đến từ
                stream_loopback_chunks() (luôn 16000Hz) HOẶC từ
                record_system_audio() (mặc định 48000Hz, phụ thuộc device).

        Returns:
            TranscriptionResult. Implementation tự ghi WAV PCM16 vào buffer
            RAM (io.BytesIO) trước khi gửi API, KHÔNG ghi tempfile ra đĩa.
            Ngôn ngữ phát hiện lấy gộp luôn từ cùng 1 lần gọi STT (ví dụ
            response_format="verbose_json" của Whisper), KHÔNG gọi thêm
            request riêng chỉ để detect ngôn ngữ.

        Raises:
            ProviderError: network/auth/API lỗi, hoặc response không hợp lệ.

        Note:
            Đồng bộ (blocking). Caller tự chạy trên thread riêng nếu không
            muốn block UI thread (cùng lý do threading như VadSegmenter,
            xem CONTRACTS.md Mục 3).
        """
        ...

    @abstractmethod
    def translate(
        self, text: str, source_lang: str, target_lang: str, context_text: str = ""
    ) -> str:
        """Dịch text từ source_lang sang target_lang.

        Args:
            text: Văn bản gốc cần dịch.
            source_lang: Mã ISO 639-1 của ngôn ngữ gốc, ví dụ "en".
            target_lang: Mã ISO 639-1 của ngôn ngữ đích, ví dụ "vi".
            context_text: 🔒 THÊM sau phản hồi test thật (bản dịch ban đầu
                dịch từng câu riêng lẻ, không biết ngữ cảnh trước/sau, ra
                văn cứng/máy móc, đôi khi gây hiểu sai). Vài câu nói TRƯỚC
                `text` (cùng `source_lang`), giúp model chọn từ/cách diễn
                đạt nhất quán với mạch chuyện đang nói — KHÔNG được tự dịch
                phần context này, chỉ dùng để hiểu bối cảnh. Optional, mặc
                định "" (không có context) để KHÔNG phá vỡ các lời gọi cũ.

        Returns:
            Văn bản đã dịch sang target_lang (chỉ phần `text`, không gồm context).

        Raises:
            ProviderError: network/auth/API lỗi, hoặc response không hợp lệ.

        Note:
            Đồng bộ (blocking), cùng quy ước với transcribe().
        """
        ...

    @abstractmethod
    def suggest_answer(
        self, question_text: str, context_text: str, user_native_lang: str
    ) -> str:
        """🔒 ĐÃ CHỐT (Phase 2, F5-F7) — soạn gợi ý trả lời cho 1 câu hỏi.

        Dùng khi người dùng nhấn nút "Nhờ AI trả lời" trên 1 bubble được
        đánh dấu `is_question=True` (pipeline.py mục heuristic
        `_looks_like_question`). Trả lời LUÔN bằng `user_native_lang` để
        người dùng đọc/sửa thoải mái — việc dịch ngược sang ngôn ngữ người
        hỏi là bước RIÊNG, dùng lại `translate()` đã có sẵn từ Phase 1
        (không cần thêm method mới cho bước đó — xem PROJECT_SPEC.md mục 9
        Phase 2 bước 3).

        Args:
            question_text: Câu hỏi gốc (NGUYÊN NGÔN NGỮ người hỏi, KHÔNG
                phải bản đã dịch) — vd "What's our Q3 churn rate?".
            context_text: Vài câu transcript ngay trước đó (cùng ngôn ngữ
                với question_text, ghép bằng "\\n"), giúp model hiểu ngữ
                cảnh đang nói về gì. Caller (pipeline/UI) tự quyết lấy bao
                nhiêu câu — khuyến nghị 3-5 câu gần nhất, KHÔNG đẩy toàn bộ
                transcript phiên họp vào (tốn token, không cần thiết).
            user_native_lang: Mã ISO 639-1 ngôn ngữ mẹ đẻ người dùng, vd "vi".

        Returns:
            Gợi ý trả lời bằng `user_native_lang`. Implementation PHẢI tự
            tránh bịa số liệu/sự kiện cụ thể model không thể biết (xem
            PROJECT_SPEC.md mục 2 rủi ro #2) — chỗ cần số liệu thật, trả về
            placeholder dạng `[số liệu cụ thể]` để người dùng tự điền,
            KHÔNG tự sinh số ảo trông có vẻ hợp lý.

        Raises:
            ProviderError: network/auth/API lỗi, hoặc response không hợp lệ.

        Note:
            Đồng bộ (blocking), cùng quy ước threading với transcribe()/
            translate() — gọi từ worker thread, không gọi từ Qt main thread.
        """
        ...

    @abstractmethod
    def summarize(self, transcript_text: str, user_native_lang: str) -> "SummaryResult":
        """🔒 ĐÃ CHỐT (Phase 3, F10-F11) — tổng hợp biên bản cuộc họp.

        Args:
            transcript_text: Toàn bộ transcript phiên họp, ghép từ
                `MeetingStore.get_segments()` — mỗi dòng 1 segment
                `original_text` (ngôn ngữ gốc, KHÔNG phải bản dịch — tránh
                cộng dồn lỗi nếu dùng bản đã dịch), theo đúng thứ tự thời
                gian. Caller (report generator, sẽ làm ở Bước 2) tự lo việc
                ghép — summarize() không tự đọc DB.
            user_native_lang: Mã ISO 639-1, summary LUÔN trả về bằng ngôn
                ngữ này dù transcript gốc là ngôn ngữ gì/nhiều ngôn ngữ.

        Returns:
            `SummaryResult` — `decisions`/`action_items` là list[str] (mỗi
            phần tử 1 ý ngắn, KHÔNG phải 1 string nhiều dòng — xem lý do ở
            docstring `SummaryResult`). Không tự bịa thông tin không có
            trong transcript; nếu 1 mục (vd "Quyết định") không có gì rõ
            ràng, trả về list RỖNG `[]` và nói thật KHÔNG có ở `overview`
            nếu cần, không cố "sáng tạo" 1 quyết định cho có.

        Raises:
            ProviderError: network/auth/API lỗi, hoặc response không hợp lệ
                (vd JSON trả về không parse được).
        """
        ...
