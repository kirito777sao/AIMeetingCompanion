import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from app.ai.base_provider import AIProvider, ProviderError, TranscriptionResult  # noqa: E402
from app.audio.vad import VadSegmenter  # noqa: E402
from app.pipeline import MeetingPipeline  # noqa: E402
from app.storage.db import MeetingStore  # noqa: E402

from test_vad import FakeVad  # noqa: E402 (tái dùng FakeVad đã viết cho test_vad.py)


class FakeProvider(AIProvider):
    """Provider giả: transcribe/translate trả giá trị định trước, không gọi
    network. Có thể bật cờ lỗi để test nhánh xử lý lỗi của pipeline."""

    def __init__(self, transcript_text="Hello world", language="en",
                 confidence=0.9, translated="Xin chào thế giới",
                 fail_transcribe=False, fail_translate=False, no_speech_prob=0.0):
        self.transcript_text = transcript_text
        self.language = language
        self.confidence = confidence
        self.translated = translated
        self.fail_transcribe = fail_transcribe
        self.fail_translate = fail_translate
        self.no_speech_prob = no_speech_prob
        self.transcribe_calls = 0
        self.translate_calls = 0

    def transcribe(self, audio, samplerate):
        self.transcribe_calls += 1
        if self.fail_transcribe:
            raise ProviderError("giả lập lỗi network khi transcribe")
        return TranscriptionResult(text=self.transcript_text, language=self.language,
                                   confidence=self.confidence, no_speech_prob=self.no_speech_prob)

    def translate(self, text, source_lang, target_lang, context_text=""):
        self.translate_calls += 1
        self.last_context_text = context_text  # để test kiểm tra pipeline có truyền context đúng không
        if self.fail_translate:
            raise ProviderError("giả lập lỗi network khi translate")
        return self.translated

    def suggest_answer(self, *a, **k):
        raise NotImplementedError

    def summarize(self, *a, **k):
        raise NotImplementedError


def _make_segmenter_with_one_segment(n_speech_frames=20):
    """Tạo VadSegmenter đã ghi đè VAD giả, feed sẵn đủ frame để chốt đúng 1
    segment khi gọi feed_chunk() lần cuối (frame im lặng kết thúc)."""
    seg = VadSegmenter(samplerate=16000, frame_ms=20, silence_ms=600,
                       min_speech_ms=250, padding_ms=200)
    pattern = [True] * n_speech_frames + [False] * 30
    seg._vad = FakeVad(pattern)
    return seg, len(pattern)


def test_pipeline_full_happy_path_luu_dung_db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = MeetingStore(db_path)
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(transcript_text="Hello world", language="en",
                                    translated="Xin chào thế giới")
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            all_events = []
            for _ in range(n_frames):
                frame = np.zeros(320, dtype=np.float32)  # frame_size = 16000*20/1000
                all_events += pipeline.feed_chunk(frame)

            assert len(all_events) == 1, f"Phải có đúng 1 event, nhận {len(all_events)}"
            ev = all_events[0]
            assert ev.error is None
            assert ev.original_text == "Hello world"
            assert ev.translated_text == "Xin chào thế giới"
            assert ev.target_lang == "vi"
            assert ev.segment_id is not None

            # Xác nhận đã thực sự lưu vào DB, không chỉ trả event suông.
            db_segments = store.get_segments(meeting_id)
            assert len(db_segments) == 1
            assert db_segments[0].translated_text == "Xin chào thế giới"

            pipeline.close()
            meetings = store.list_meetings()
            assert meetings[0][2] is not None, "close() phải gọi end_meeting()"
        finally:
            store.close()
    print("OK: test_pipeline_full_happy_path_luu_dung_db")


def test_pipeline_khong_dich_neu_cung_ngon_ngu_me_de():
    # source_lang == user_native_lang -> KHÔNG gọi translate() (tiết kiệm quota).
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(transcript_text="Xin chào", language="vi")
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            events = []
            for _ in range(n_frames):
                events += pipeline.feed_chunk(np.zeros(320, dtype=np.float32))

            assert len(events) == 1
            assert provider.translate_calls == 0, "Không nên gọi translate() khi source==target."
            assert events[0].translated_text is None
        finally:
            store.close()
    print("OK: test_pipeline_khong_dich_neu_cung_ngon_ngu_me_de")


def test_pipeline_loi_transcribe_khong_lam_sap_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(fail_transcribe=True)
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            events = []
            for _ in range(n_frames):
                events += pipeline.feed_chunk(np.zeros(320, dtype=np.float32))

            assert len(events) == 1
            assert events[0].error is not None
            assert events[0].segment_id is None
            # Không có dòng nào lưu vào DB vì transcribe lỗi ngay từ đầu.
            assert len(store.get_segments(meeting_id)) == 0
        finally:
            store.close()
    print("OK: test_pipeline_loi_transcribe_khong_lam_sap_pipeline")


def test_pipeline_loi_translate_van_luu_duoc_ban_goc():
    # CONTRACTS.md Mục 5: dịch lỗi KHÔNG được làm mất original_text.
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(transcript_text="Hello", language="en", fail_translate=True)
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            events = []
            for _ in range(n_frames):
                events += pipeline.feed_chunk(np.zeros(320, dtype=np.float32))

            assert len(events) == 1
            ev = events[0]
            assert ev.error is not None and "dịch" in ev.error.lower()
            assert ev.original_text == "Hello"
            assert ev.segment_id is not None, "Vẫn phải lưu được original_text vào DB."

            db_segments = store.get_segments(meeting_id)
            assert db_segments[0].original_text == "Hello"
            assert db_segments[0].translated_text is None
        finally:
            store.close()
    print("OK: test_pipeline_loi_translate_van_luu_duoc_ban_goc")


def test_pipeline_is_question_duoc_danh_dau_dung():
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(transcript_text="What do you think?", language="en")
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            events = []
            for _ in range(n_frames):
                events += pipeline.feed_chunk(np.zeros(320, dtype=np.float32))

            assert events[0].is_question is True
        finally:
            store.close()
    print("OK: test_pipeline_is_question_duoc_danh_dau_dung")


def test_flush_xu_ly_cau_noi_con_do():
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            # Speech liên tục, KHÔNG có khoảng lặng theo sau -> feed_chunk()
            # không trả event nào, phải dùng flush().
            seg = VadSegmenter(samplerate=16000, frame_ms=20, min_speech_ms=250)
            seg._vad = FakeVad([True] * 20)
            provider = FakeProvider(transcript_text="...", language="en")
            pipeline = MeetingPipeline(seg, provider, store, meeting_id, "vi")

            events = []
            for _ in range(20):
                events += pipeline.feed_chunk(np.zeros(320, dtype=np.float32))
            assert events == [], "Chưa có khoảng lặng thì feed_chunk() chưa được trả event."

            flushed = pipeline.flush()
            assert flushed is not None
            assert flushed.original_text == "..."
        finally:
            store.close()
    print("OK: test_flush_xu_ly_cau_noi_con_do")


def test_pipeline_truyen_dung_context_cho_translate_khong_lan_cau_hien_tai():
    # Thêm sau phản hồi test thật lần 3 (dịch máy móc do thiếu ngữ cảnh).
    # Mô phỏng 2 segment liên tiếp, xác nhận: segment 1 có context rỗng
    # (chưa có gì trước đó), segment 2 có context = đúng text của segment 1
    # (KHÔNG lẫn chính text của segment 2 vào).
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            provider = FakeProvider(transcript_text="placeholder", language="en")
            pipeline = MeetingPipeline(
                VadSegmenter(samplerate=16000, frame_ms=20, min_speech_ms=1),
                provider, store, meeting_id, "vi",
            )

            # Gọi _process_segment() trực tiếp 2 lần (bỏ qua VAD, test thẳng
            # logic context của pipeline) với text khác nhau mỗi lần.
            provider.transcript_text = "Hello"
            ev1 = pipeline._process_segment(np.zeros(320, dtype=np.float32))
            assert provider.last_context_text == "", "Segment đầu tiên chưa có gì trước đó."

            provider.transcript_text = "How are you"
            ev2 = pipeline._process_segment(np.zeros(320, dtype=np.float32))
            assert provider.last_context_text == "Hello", (
                f"Context của segment 2 phải đúng = text segment 1, "
                f"nhận {provider.last_context_text!r}."
            )
            assert "How are you" not in provider.last_context_text, (
                "KHÔNG được lẫn chính text hiện tại vào context của nó."
            )
        finally:
            store.close()
    print("OK: test_pipeline_truyen_dung_context_cho_translate_khong_lan_cau_hien_tai")


def test_pipeline_bo_qua_segment_hallucination_no_speech_prob_cao():
    # 🔒 MỚI (CONTRACTS.md Mục 11) -- mô phỏng ĐÚNG case thật đã gặp khi
    # test trên Windows: khoảng lặng/nhạc nền nhưng Whisper vẫn "bịa" ra
    # text nghe tự nhiên, kèm no_speech_prob cao. Pipeline PHẢI bỏ qua
    # hoàn toàn -- không hiện bubble, không lưu DB.
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(
                transcript_text="Hãy subscribe cho kênh Ghiền Mì Gõ",
                language="vi", confidence=0.46, no_speech_prob=0.85,
            )
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
            all_events = []
            for _ in range(n_frames):
                all_events.extend(pipeline.feed_chunk(chunk))

            non_empty = [e for e in all_events if e.original_text]
            assert len(non_empty) == 0, (
                f"no_speech_prob=0.85 phải bị lọc, KHÔNG hiện bubble nào, "
                f"nhận {len(non_empty)} bubble."
            )
            segments_in_db = store.get_segments(meeting_id)
            assert len(segments_in_db) == 0, (
                f"Segment hallucination KHÔNG được lưu vào DB, nhận "
                f"{len(segments_in_db)} dòng."
            )
            assert provider.translate_calls == 0, (
                "Đã bị lọc trước translate() -- không nên tốn quota dịch rác."
            )
        finally:
            store.close()
    print("OK: test_pipeline_bo_qua_segment_hallucination_no_speech_prob_cao")


def test_pipeline_giu_lai_cau_ngan_du_confidence_thap_neu_no_speech_prob_thap():
    # 🔒 MỚI -- ĐỐI CHIẾU với test ở trên: câu/từ NGẮN NHƯNG THẬT (confidence
    # thấp do bị VAD cắt lẻ, KHÔNG phải vì im lặng -- no_speech_prob vẫn
    # thấp) PHẢI được giữ lại, KHÔNG bị lọc nhầm. Đây chính là lý do
    # NO_SPEECH_PROB_DROP_THRESHOLD dùng no_speech_prob, KHÔNG dùng confidence.
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(
                transcript_text="Human.", language="en",
                confidence=0.46, no_speech_prob=0.02,
            )
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
            all_events = []
            for _ in range(n_frames):
                all_events.extend(pipeline.feed_chunk(chunk))

            non_empty = [e for e in all_events if e.original_text]
            assert len(non_empty) == 1, (
                f"Câu ngắn nhưng THẬT (no_speech_prob thấp) phải được giữ lại, "
                f"nhận {len(non_empty)} bubble."
            )
            assert non_empty[0].original_text == "Human."
            segments_in_db = store.get_segments(meeting_id)
            assert len(segments_in_db) == 1, "Phải được lưu vào DB như bình thường."
        finally:
            store.close()
    print("OK: test_pipeline_giu_lai_cau_ngan_du_confidence_thap_neu_no_speech_prob_thap")


if __name__ == "__main__":
    test_pipeline_full_happy_path_luu_dung_db()
    test_pipeline_khong_dich_neu_cung_ngon_ngu_me_de()
    test_pipeline_loi_transcribe_khong_lam_sap_pipeline()
    test_pipeline_loi_translate_van_luu_duoc_ban_goc()
    test_pipeline_is_question_duoc_danh_dau_dung()
    test_flush_xu_ly_cau_noi_con_do()
    test_pipeline_truyen_dung_context_cho_translate_khong_lan_cau_hien_tai()
    test_pipeline_bo_qua_segment_hallucination_no_speech_prob_cao()
    test_pipeline_giu_lai_cau_ngan_du_confidence_thap_neu_no_speech_prob_thap()
    print("\n=== TẤT CẢ TEST PIPELINE PASS ===")
