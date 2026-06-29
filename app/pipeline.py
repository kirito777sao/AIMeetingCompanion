"""
app/pipeline.py
----------------
Ghép nối VAD -> AIProvider (transcribe + translate) -> MeetingStore, hoàn
toàn KHÔNG biết gì về Qt/threading thật (đúng nguyên tắc CONTRACTS.md Mục 3:
worker thread gọi `feed_chunk()`, nhận về list `TranscriptEvent` rồi TỰ đẩy
qua Qt Signal — pipeline.py không tự emit signal nào).

Tách riêng module này (thay vì viết thẳng trong main.py/QThread) để có thể
unit test toàn bộ logic ghép nối bằng dữ liệu giả lập, không cần audio thật
hay GUI thật — giống cách vad.py và groq_provider.py đã được test ở các
file tests/test_vad.py, tests/test_groq_provider_offline.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.ai.base_provider import AIProvider, ProviderError
from app.audio.vad import VadSegmenter
from app.storage.db import MeetingStore, StorageError

# Số câu nói gần nhất (cùng ngôn ngữ gốc) đưa làm ngữ cảnh cho translate() —
# giúp model chọn từ ngữ nhất quán với mạch chuyện, đỡ máy móc (xem
# CONTRACTS.md Mục 4, thêm sau phản hồi test thật lần 3). Cùng giá trị với
# _CONTEXT_HISTORY_SIZE ở ui/main_window.py (dùng cho suggest_answer) —
# không bắt buộc phải giống nhau, nhưng dùng chung 1 con số cho dễ nhớ.
_TRANSLATE_CONTEXT_SIZE = 5

# Cả 2 dạng dấu hỏi (ASCII "?" và full-width "?" hay gặp trong văn bản tiếng
# Trung) đều được coi là dấu hiệu câu hỏi — heuristic đơn giản cho Phase 1,
# đủ dùng để set cờ is_question trong DB (CONTRACTS.md Mục 5), CHƯA dùng để
# hiện nút "Nhờ AI trả lời" (đó là Phase 2, F5).
_QUESTION_MARKS = ("?", "\uFF1F")

# 🔒 MỚI (CONTRACTS.md Mục 11) -- xem chi tiết bối cảnh phát hiện ở
# app/ai/base_provider.py (docstring TranscriptionResult.no_speech_prob) và
# app/ai/groq_provider.py (_estimate_no_speech_prob). Tóm tắt: Whisper KHÔNG
# có cách trả "rỗng" đúng nghĩa khi audio không có giọng nói thật (im lặng/
# nhạc nền) -- nó vẫn sinh ra text nghe rất tự nhiên (hallucination nổi
# tiếng của Whisper, ví dụ thực tế gặp khi test: "Hãy subscribe cho kênh...",
# "Soul Tech Care of the Garden", "Me and you" -- xuất hiện lặp lại GIỐNG
# NHAU ở nhiều mốc thời gian khác nhau trong cùng video, không phải nội
# dung thật đang được nói). no_speech_prob là tín hiệu RIÊNG (không nhân
# với avg_logprob như confidence) cho biết Whisper TỰ ĐÁNH GIÁ đoạn audio
# gốc có giọng nói hay không -- đáng tin hơn confidence cho việc lọc này
# (xem test_no_speech_prob_la_tin_hieu_chat_hon_confidence_cho_cau_ngan_nhung_thuc
# trong tests/test_groq_provider_offline.py để thấy rõ vì sao KHÔNG dùng
# confidence cho mục đích này -- sẽ lọc nhầm cả câu/từ ngắn nhưng THẬT).
#
# 0.6 là ngưỡng phổ biến cộng đồng hay dùng để lọc hallucination của
# Whisper dựa trên no_speech_prob (vd faster-whisper, whisper.cpp đều có
# tuỳ chọn tương tự quanh mức này). ⚠️ CHƯA verify bằng số liệu Groq thật
# trong sandbox này (không gọi network được) -- cần bạn quan sát lại trên
# Windows: nếu vẫn còn lọt rác, hoặc ngược lại mất câu nói thật, chỉnh số
# này (file này, KHÔNG cần sửa ở đâu khác).
NO_SPEECH_PROB_DROP_THRESHOLD = 0.6


def _looks_like_question(text: str) -> bool:
    return text.rstrip().endswith(_QUESTION_MARKS)


@dataclass
class TranscriptEvent:
    """1 sự kiện hoàn chỉnh để UI hiển thị — đẩy qua Qt Signal nguyên cục này.

    `error` khác None nghĩa là segment audio đã thu được nhưng xử lý AI lỗi
    (network/rate-limit) — UI nên hiện trạng thái lỗi cho ĐÚNG segment đó,
    KHÔNG phải lỗi toàn cục làm crash cả phiên họp.
    """

    segment_id: Optional[int]
    original_text: str
    source_lang: str
    confidence: float
    translated_text: Optional[str]
    target_lang: str
    is_question: bool
    error: Optional[str] = None


class MeetingPipeline:
    """1 instance gắn với 1 phiên họp (1 meeting_id) đang diễn ra.

    Vòng đời: worker thread tạo 1 MeetingPipeline khi bắt đầu ghi, gọi
    `feed_chunk()` liên tục cho mỗi chunk audio, gọi `flush()` đúng 1 lần khi
    dừng ghi (để không mất câu nói cuối còn dở), rồi gọi `close()`.
    """

    def __init__(
        self,
        segmenter: VadSegmenter,
        provider: AIProvider,
        store: MeetingStore,
        meeting_id: int,
        user_native_lang: str,
        samplerate: int = 16000,
    ) -> None:
        self._segmenter = segmenter
        self._provider = provider
        self._store = store
        self._meeting_id = meeting_id
        self._user_native_lang = user_native_lang
        self._samplerate = samplerate
        self._recent_originals: List[str] = []  # ngữ cảnh cho translate(), xem _TRANSLATE_CONTEXT_SIZE

    def feed_chunk(self, chunk: np.ndarray) -> List[TranscriptEvent]:
        """Đẩy 1 chunk audio mới vào. Trả về list TranscriptEvent (thường
        rỗng — phần lớn chunk chưa đủ để chốt segment nào)."""
        finished_segments = self._segmenter.feed(chunk)
        return [self._process_segment(seg) for seg in finished_segments]

    def flush(self) -> Optional[TranscriptEvent]:
        """Gọi đúng 1 lần khi dừng ghi, để xử lý câu nói còn dở (nếu có)."""
        seg_audio = self._segmenter.flush()
        if seg_audio is None:
            return None
        return self._process_segment(seg_audio)

    def close(self) -> None:
        """Đóng phiên họp trong DB. KHÔNG đóng `self._store` (connection) ở
        đây — main.py/worker thread chịu trách nhiệm đóng connection, vì
        store có thể được dùng tiếp cho việc khác (vd đọc lại lịch sử)."""
        try:
            self._store.end_meeting(self._meeting_id)
        except StorageError:
            # Không để lỗi đóng phiên họp làm crash luồng dừng ghi — phiên
            # họp coi như đã dừng ở phía audio, dữ liệu segment đã lưu rồi
            # vẫn còn nguyên, chỉ thiếu mốc ended_at.
            pass

    # -- nội bộ ----------------------------------------------------------

    def _process_segment(self, seg_audio: np.ndarray) -> TranscriptEvent:
        try:
            stt_result = self._provider.transcribe(seg_audio, self._samplerate)
        except ProviderError as exc:
            # Lỗi NGAY ở bước transcribe -> không có text gì để lưu/hiển thị
            # ngoài thông báo lỗi. segment_id=None vì chưa từng ghi vào DB.
            return TranscriptEvent(
                segment_id=None, original_text="", source_lang="",
                confidence=0.0, translated_text=None,
                target_lang=self._user_native_lang, is_question=False,
                error=f"Lỗi nhận diện giọng nói: {exc}",
            )

        text = stt_result.text
        if not text:
            # Segment VAD coi là "có nói" nhưng STT trả text rỗng (vd tiếng ồn
            # lọt qua VAD) -> không lưu DB, không hiện bubble rỗng trên UI.
            return TranscriptEvent(
                segment_id=None, original_text="", source_lang=stt_result.language,
                confidence=stt_result.confidence, translated_text=None,
                target_lang=self._user_native_lang, is_question=False,
            )

        if stt_result.no_speech_prob >= NO_SPEECH_PROB_DROP_THRESHOLD:
            # 🔒 MỚI (CONTRACTS.md Mục 11) -- Whisper SINH RA text (không
            # rỗng) nhưng tự đánh giá đoạn audio gốc rất có thể KHÔNG có
            # giọng nói (im lặng/nhạc nền) -> coi như hallucination, xử lý
            # GIỐNG HỆT nhánh "STT trả text rỗng" ở trên: không lưu DB,
            # không hiện bubble, KHÔNG set error (đây là tình huống XẢY RA
            # BÌNH THƯỜNG suốt cuộc họp mỗi khi có khoảng lặng/nhạc nền,
            # không phải lỗi cần cảnh báo người dùng mỗi lần). Cố tình
            # KHÔNG dùng `confidence` cho điều kiện này -- xem
            # NO_SPEECH_PROB_DROP_THRESHOLD ở trên để biết lý do đầy đủ.
            return TranscriptEvent(
                segment_id=None, original_text="", source_lang=stt_result.language,
                confidence=stt_result.confidence, translated_text=None,
                target_lang=self._user_native_lang, is_question=False,
            )

        is_question = _looks_like_question(text)
        translated_text: Optional[str] = None
        translate_error: Optional[str] = None

        # Lấy context TRƯỚC khi text hiện tại được thêm vào buffer (không
        # tự lấy chính nó làm ngữ cảnh của nó).
        context_text = "\n".join(self._recent_originals[-_TRANSLATE_CONTEXT_SIZE:])

        # Nếu ngôn ngữ gốc đã chính là ngôn ngữ mẹ đẻ người dùng -> không cần
        # dịch, tránh tốn quota free-tier vô ích.
        if stt_result.language and stt_result.language != self._user_native_lang:
            try:
                translated_text = self._provider.translate(
                    text, stt_result.language, self._user_native_lang,
                    context_text=context_text,
                )
            except ProviderError as exc:
                translate_error = f"Lỗi dịch (đã lưu bản gốc): {exc}"

        # Cập nhật buffer SAU khi đã dùng context (không lẫn câu hiện tại
        # vào ngữ cảnh của chính nó). Giữ ngữ cảnh kể cả khi không cần dịch
        # (vd source==target) -- vẫn có giá trị cho CÂU TIẾP THEO.
        self._recent_originals.append(text)

        try:
            segment_id = self._store.add_segment(
                meeting_id=self._meeting_id,
                original_text=text,
                source_lang=stt_result.language,
                confidence=stt_result.confidence,
                translated_text=translated_text,
                target_lang=self._user_native_lang if translated_text else None,
                is_question=is_question,
            )
        except StorageError as exc:
            # Lưu DB lỗi vẫn trả TranscriptEvent để UI hiện được transcript
            # ngay (UX quan trọng hơn), kèm cảnh báo mất khả năng lưu lại.
            return TranscriptEvent(
                segment_id=None, original_text=text, source_lang=stt_result.language,
                confidence=stt_result.confidence, translated_text=translated_text,
                target_lang=self._user_native_lang, is_question=is_question,
                error=f"Lưu transcript lỗi (chỉ hiện tạm, không lưu lại): {exc}",
            )

        return TranscriptEvent(
            segment_id=segment_id, original_text=text, source_lang=stt_result.language,
            confidence=stt_result.confidence, translated_text=translated_text,
            target_lang=self._user_native_lang, is_question=is_question,
            error=translate_error,
        )
