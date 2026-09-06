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

import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.ai.base_provider import AIProvider, ProviderError
from app.audio.vad import VadSegmenter
from app.logging_setup import get_logger
from app.storage.db import MeetingStore, StorageError

_logger = get_logger()

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
# này qua biến môi trường `NO_SPEECH_PROB_DROP_THRESHOLD` trong `.env`
# (🔒 MỚI, Mục 27 — trước đây chỉ sửa được bằng cách sửa hằng số này rồi
# chạy lại app từ source; giờ đọc qua env theo đúng tinh thần 3 tầng ưu
# tiên đã dùng ở GroqProvider: tham số truyền vào MeetingPipeline() > env
# var > hardcode default dưới đây). Giá trị dưới đây VẪN LÀ default cuối
# cùng khi không có gì override -- KHÔNG đổi hành vi mặc định hiện tại.
NO_SPEECH_PROB_DROP_THRESHOLD = 0.6

# 🔒 MỚI (Mục 36 — người dùng CHỦ ĐỘNG xin xét lại quyết định cũ ở Mục 27/
# TASKS.md, sau khi báo lại tạp âm/nhạc nền KHÔNG lời vẫn bị bịa chữ rồi
# dịch loạn cả hội thoại). Quyết định CŨ (Mục 27, giữ nguyên trong docstring
# `_estimate_confidence()` ở whisper_utils.py) là KHÔNG lọc bằng confidence
# vì nó lẫn 2 nguyên nhân khác nhau (câu ngắn-nhưng-thật không chắc chữ nào
# đúng, VS hallucination-trên-im-lặng) -- lọc theo confidence CÓ THỂ mất câu
# nói ngắn nhưng THẬT của người dùng.
#
# ⚠️ RỦI RO NÀY VẪN ĐÚNG VÀ CHƯA ĐƯỢC GIẢI QUYẾT bằng lớp lọc dưới đây --
# đây KHÔNG phải bản sửa triệt để, chỉ là 1 công tắc THÊM để người dùng tự
# cân nhắc đánh đổi theo tình huống thật của họ:
#   - `None` (mặc định, giữ nguyên hành vi hiện tại KHÔNG đổi gì) -- lớp
#     lọc này TẮT hoàn toàn trừ khi tự đặt biến môi trường
#     `CONFIDENCE_DROP_THRESHOLD` trong `.env`.
#   - Khi BẬT (đặt 1 số float, vd 0.15): segment nào đã QUA được ải
#     no_speech_prob (Whisper "tin" là có giọng nói) NHƯNG confidence vẫn
#     THẤP HƠN NGƯỠNG NÀY sẽ bị coi như audio-only (không lưu DB, không
#     dịch) -- tương tự nhánh no_speech_prob cao. Đây là lớp lọc THỨ 2, ĐỘC
#     LẬP, KHÔNG thay thế no_speech_prob (2 điều kiện dùng OR: bị lọc nếu
#     no_speech_prob CAO **hoặc** confidence THẤP).
#   - Nên đặt số THẬT THẤP (vd 0.10-0.20) để giảm rủi ro lọc nhầm câu ngắn
#     thật -- số càng cao, rủi ro lọc nhầm câu thật càng lớn. CHƯA có số
#     "đúng" -- cần bạn tự quan sát trên dữ liệu thật của bạn (audio dài,
#     nhiều tạp âm) rồi tinh chỉnh qua `.env`, không cần sửa code/build lại.
#   - CHƯA verify bằng audio thật trong sandbox này (không network) -- xem
#     CONTRACTS.md Mục 36 cho checklist bạn cần tự làm trên Windows.
CONFIDENCE_DROP_THRESHOLD: Optional[float] = None


def _looks_like_question(text: str) -> bool:
    return text.rstrip().endswith(_QUESTION_MARKS)


@dataclass
class TranscriptEvent:
    """1 sự kiện hoàn chỉnh để UI hiển thị — đẩy qua Qt Signal nguyên cục này.

    `error` khác None nghĩa là segment audio đã thu được nhưng xử lý AI lỗi
    (network/rate-limit) — UI nên hiện trạng thái lỗi cho ĐÚNG segment đó,
    KHÔNG phải lỗi toàn cục làm crash cả phiên họp.

    `is_audio_only=True` (🔒 MỚI, CONTRACTS.md Mục 23): Whisper tự đánh giá
    đoạn audio gốc RẤT CÓ THỂ không có giọng nói thật (no_speech_prob cao —
    nhạc không lời/tạp âm), thay vì bị âm thầm bỏ qua hoàn toàn như trước
    đây. Khi True: `original_text`/`translated_text` LUÔN rỗng/None (không
    có nội dung thật để hiện), `segment_id` LUÔN None (KHÔNG lưu DB — chỉ
    là chỉ báo UI tạm thời, không phải 1 câu nói thật cần lưu lại). UI nên
    hiện 1 indicator NHẸ (vd "🔊 [Âm thanh]") thay vì bubble transcript
    bình thường, để người dùng biết pipeline vẫn đang nghe được audio,
    không tưởng app bị treo/im lặng bất thường.
    """

    segment_id: Optional[int]
    original_text: str
    source_lang: str
    confidence: float
    translated_text: Optional[str]
    target_lang: str
    is_question: bool
    error: Optional[str] = None
    is_audio_only: bool = False


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
        no_speech_prob_drop_threshold: Optional[float] = None,
        confidence_drop_threshold: Optional[float] = None,
        language_hint: str = "",
    ) -> None:
        """
        no_speech_prob_drop_threshold: 🔒 MỚI (Mục 27). Nếu `None` (mặc
            định -- KHÔNG đổi hành vi cũ khi caller không truyền gì), đọc
            biến môi trường `NO_SPEECH_PROB_DROP_THRESHOLD` (float); nếu
            biến đó cũng không đặt HOẶC đặt sai định dạng (không parse
            được số), fallback về hằng số `NO_SPEECH_PROB_DROP_THRESHOLD`
            ở đầu file (0.6) -- KHÔNG BAO GIỜ raise lỗi chỉ vì 1 giá trị
            `.env` gõ sai.
        confidence_drop_threshold: 🔒 MỚI (Mục 36, xem cảnh báo rủi ro ở
            hằng số `CONFIDENCE_DROP_THRESHOLD` đầu file). Cùng 3 tầng ưu
            tiên như trên: tham số này > biến môi trường
            `CONFIDENCE_DROP_THRESHOLD` > hằng số mặc định (`None` = TẮT).
        language_hint: 🔒 MỚI (Mục 38) — mã ISO 639-1 người dùng chọn ở
            MeetingContextDialog TRƯỚC khi ghi ("" = "Tự động", giữ
            NGUYÊN hành vi cũ). Truyền THẲNG xuống MỌI lần gọi
            `AIProvider.transcribe()` trong suốt phiên họp (không đổi
            giữa chừng — cùng tinh thần `meeting_context`, 1 lựa chọn
            TĨNH cho cả phiên, xem CONTRACTS.md Mục 38).
        """
        self._segmenter = segmenter
        self._provider = provider
        self._store = store
        self._meeting_id = meeting_id
        self._user_native_lang = user_native_lang
        self._samplerate = samplerate
        self._no_speech_prob_drop_threshold = (
            no_speech_prob_drop_threshold
            if no_speech_prob_drop_threshold is not None
            else self._resolve_no_speech_prob_drop_threshold_from_env()
        )
        self._confidence_drop_threshold = (
            confidence_drop_threshold
            if confidence_drop_threshold is not None
            else self._resolve_confidence_drop_threshold_from_env()
        )
        self._language_hint = language_hint
        self._recent_originals: List[str] = []  # ngữ cảnh cho translate(), xem _TRANSLATE_CONTEXT_SIZE
        # 🔒 MỚI (Mục 38, T33) -- CHỈ để log chẩn đoán, KHÔNG dùng để lọc/
        # đổi hành vi UI (xem _log_if_language_outlier() bên dưới).
        self._recent_detected_langs: List[str] = []

    @staticmethod
    def _resolve_no_speech_prob_drop_threshold_from_env() -> float:
        raw = os.environ.get("NO_SPEECH_PROB_DROP_THRESHOLD")
        if raw is None or not raw.strip():
            return NO_SPEECH_PROB_DROP_THRESHOLD
        try:
            return float(raw.strip())
        except ValueError:
            return NO_SPEECH_PROB_DROP_THRESHOLD

    @staticmethod
    def _resolve_confidence_drop_threshold_from_env() -> Optional[float]:
        """🔒 MỚI (Mục 36). Khác hàm no_speech_prob ở trên: mặc định KHÔNG
        đặt (`None`, nghĩa là TẮT lọc) khi biến môi trường trống/không có
        -- CỐ Ý không có 1 số mặc định "an toàn" nào ở đây, vì bật lớp lọc
        này LUÔN có rủi ro lọc nhầm câu ngắn-nhưng-thật (xem docstring hằng
        số `CONFIDENCE_DROP_THRESHOLD`) -- phải là lựa chọn TƯỜNG MINH của
        người dùng qua `.env`, không âm thầm bật sẵn cho ai chưa yêu cầu."""
        raw = os.environ.get("CONFIDENCE_DROP_THRESHOLD")
        if raw is None or not raw.strip():
            return None
        try:
            return float(raw.strip())
        except ValueError:
            return None

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

    def _log_if_language_outlier(self, text: str, language: str, confidence: float) -> None:
        """🔒 MỚI (Mục 38, T33) -- CHỈ ghi log (mức WARNING), KHÔNG lọc/ẩn
        bubble nào -- khác hẳn 2 lớp lọc no_speech_prob/confidence ở
        `_process_segment()` (Mục 11/36), vốn ẩn hẳn segment khỏi UI.

        Mục đích: cho bạn 1 nguồn dữ liệu THẬT (qua file log, Mục 30) để
        trả lời câu hỏi "ngôn ngữ có thật sự bị nhảy loạn nhiều không, bao
        nhiêu lần, đúng lúc nào" mà KHÔNG cần đoán qua mắt thường xem lại
        UI -- và KHÔNG có rủi ro lọc nhầm câu thật (vì không ẩn gì cả).
        CỐ TÌNH không tự động lọc dựa trên tín hiệu này -- 1 phiên họp
        code-switch thật (nhiều ngôn ngữ xen kẽ hợp lệ) sẽ có NHIỀU ngôn
        ngữ "khác đa số" một cách CHÍNH ĐÁNG, tự lọc theo tín hiệu này sẽ
        lặp lại đúng rủi ro đã cân nhắc kỹ ở Mục 27/36.

        So sánh với `language_hint` (nếu có) TRƯỚC (đáng tin hơn -- người
        dùng đã tự xác nhận ngôn ngữ dự kiến của phiên), chỉ so với đa số
        gần đây (`_recent_detected_langs`) khi KHÔNG có hint.
        """
        expected = self._language_hint or (
            max(set(self._recent_detected_langs), key=self._recent_detected_langs.count)
            if self._recent_detected_langs
            else ""
        )
        if expected and language and language != expected:
            _logger.warning(
                "Ngôn ngữ phát hiện lệch (meeting_id=%s): '%s' (kỳ vọng '%s', "
                "confidence=%.2f) — text=%r",
                self._meeting_id, language, expected, confidence, text[:80],
            )
        self._recent_detected_langs.append(language)
        if len(self._recent_detected_langs) > _TRANSLATE_CONTEXT_SIZE:
            self._recent_detected_langs.pop(0)

    def _process_segment(self, seg_audio: np.ndarray) -> TranscriptEvent:
        try:
            stt_result = self._provider.transcribe(
                seg_audio, self._samplerate, language_hint=self._language_hint,
            )
        except ProviderError as exc:
            # 🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30) -- log lại lỗi
            # transcribe() ra file, kèm meeting_id để tra cứu được đúng
            # phiên họp nào bị ảnh hưởng khi người dùng report lỗi từ xa.
            _logger.error("transcribe() lỗi (meeting_id=%s): %s", self._meeting_id, exc)
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
            # lọt qua VAD) -> không lưu DB. 🔒 MỚI (CONTRACTS.md Mục 23) —
            # cùng bản chất với nhánh no_speech_prob cao ngay dưới đây (audio
            # có thật nhưng không phải giọng nói) -> cũng set is_audio_only=True
            # để UI hiện "🔊 [Âm thanh]" thay vì bubble rỗng không hiện gì.
            return TranscriptEvent(
                segment_id=None, original_text="", source_lang=stt_result.language,
                confidence=stt_result.confidence, translated_text=None,
                target_lang=self._user_native_lang, is_question=False,
                is_audio_only=True,
            )

        if stt_result.no_speech_prob >= self._no_speech_prob_drop_threshold:
            # 🔒 MỚI (CONTRACTS.md Mục 23) — trước đây bỏ qua hoàn toàn
            # GIỐNG HỆT nhánh "STT trả text rỗng" ở trên; giờ set
            # is_audio_only=True để UI hiện 1 indicator nhẹ "🔊 [Âm thanh]"
            # thay vì im lặng hoàn toàn (người dùng phản hồi: cần biết
            # pipeline vẫn đang nghe được audio khi gặp nhạc/tạp âm, không
            # phải app bị treo). VẪN không lưu DB, VẪN không set error —
            # đây là tình huống XẢY RA BÌNH THƯỜNG suốt cuộc họp mỗi khi có
            # khoảng lặng/nhạc nền, không phải lỗi cần cảnh báo người dùng.
            return TranscriptEvent(
                segment_id=None, original_text="", source_lang=stt_result.language,
                confidence=stt_result.confidence, translated_text=None,
                target_lang=self._user_native_lang, is_question=False,
                is_audio_only=True,
            )

        # 🔒 MỚI (Mục 36) -- lớp lọc THỨ 2, ĐỘC LẬP, CHỈ chạy khi người dùng
        # tự bật qua `.env` (mặc định `_confidence_drop_threshold is None`
        # = TẮT, KHÔNG đổi hành vi hiện tại). Bắt case Whisper "tin" đoạn
        # audio CÓ giọng nói (no_speech_prob thấp, qua được ải trên) nhưng
        # vẫn bịa chữ với độ tự tin thấp (confidence thấp) -- xem cảnh báo
        # rủi ro đầy đủ ở docstring hằng số `CONFIDENCE_DROP_THRESHOLD`:
        # CÓ THỂ lọc nhầm câu ngắn-nhưng-thật, người dùng đã được cảnh báo
        # và tự chọn đánh đổi này qua `.env`.
        if (
            self._confidence_drop_threshold is not None
            and stt_result.confidence <= self._confidence_drop_threshold
        ):
            return TranscriptEvent(
                segment_id=None, original_text="", source_lang=stt_result.language,
                confidence=stt_result.confidence, translated_text=None,
                target_lang=self._user_native_lang, is_question=False,
                is_audio_only=True,
            )

        is_question = _looks_like_question(text)
        self._log_if_language_outlier(text, stt_result.language, stt_result.confidence)
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
                # 🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30) -- log lỗi
                # translate() -- KHÔNG mất bản gốc (vẫn lưu DB bên dưới
                # như cũ), chỉ log để biết tần suất/nguyên nhân lỗi dịch
                # khi debug từ xa.
                _logger.warning(
                    "translate() lỗi, đã lưu bản gốc (meeting_id=%s): %s",
                    self._meeting_id, exc,
                )
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
            # 🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30) -- lỗi lưu DB đáng
            # log ở mức ERROR (dữ liệu THẬT SỰ mất, không phải chỉ hiện
            # tạm), khác 2 nhánh WARNING/ERROR ở trên.
            _logger.error("Lưu segment vào DB lỗi (meeting_id=%s): %s", self._meeting_id, exc)
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
