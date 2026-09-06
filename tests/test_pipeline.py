import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from app.ai.base_provider import AIProvider, ProviderError, TranscriptionResult  # noqa: E402
from app.audio.vad import VadSegmenter  # noqa: E402
import app.pipeline as pipeline_module  # noqa: E402
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
        self.received_language_hints = []  # 🔒 MỚI (Mục 38) -- assert pipeline truyền đúng language_hint

    def transcribe(self, audio, samplerate, language_hint=""):
        self.transcribe_calls += 1
        self.received_language_hints.append(language_hint)
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

    def chat(self, *a, **k):
        # 🔒 MỚI (CONTRACTS.md Mục 21) -- test_pipeline.py không test chat()
        # (không liên quan tới pipeline audio->transcribe->translate), chỉ
        # cần implement cho đủ để FakeProvider(AIProvider) khởi tạo được
        # (ABC bắt buộc đủ abstract method), cùng style với suggest_answer/
        # summarize ở trên.
        raise NotImplementedError


def _make_segmenter_with_one_segment(n_speech_frames=20):
    """Tạo VadSegmenter đã ghi đè VAD giả, feed sẵn đủ frame để chốt đúng 1
    segment khi gọi feed_chunk() lần cuối (frame im lặng kết thúc)."""
    seg = VadSegmenter(samplerate=16000, frame_ms=20, silence_ms=600,
                       min_speech_ms=250, padding_ms=200)
    pattern = [True] * n_speech_frames + [False] * 30
    seg._vad = FakeVad(pattern)
    return seg, len(pattern)


class _CaptureLogHandler(logging.Handler):
    """🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30) -- handler tạm để bắt log
    record phát ra từ `pipeline._logger`, KHÔNG phụ thuộc file thật trên
    đĩa (phần ghi file đã test riêng ở `tests/test_logging_setup.py`, ở
    đây CHỈ cần xác nhận `pipeline.py` THẬT SỰ gọi `_logger.error()/
    warning()` đúng chỗ, không chỉ trả `TranscriptEvent.error`)."""

    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_pipeline_truyen_dung_language_hint_xuong_transcribe():
    # 🔒 MỚI (CONTRACTS.md Mục 38) -- language_hint truyền vào MeetingPipeline()
    # phải được chuyển THẲNG xuống MỌI lần gọi provider.transcribe() trong
    # suốt phiên (không đổi giữa chừng, cùng tinh thần meeting_context).
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = MeetingStore(db_path)
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(transcript_text="Hello", language="en", translated="Xin chào")
            pipeline = MeetingPipeline(
                segmenter, provider, store, meeting_id, "vi", language_hint="ja",
            )

            for _ in range(n_frames):
                frame = np.zeros(320, dtype=np.float32)
                pipeline.feed_chunk(frame)

            assert provider.received_language_hints == ["ja"], (
                f"Phải truyền language_hint='ja' xuống transcribe(), "
                f"nhận {provider.received_language_hints!r}."
            )
        finally:
            store.close()
    print("OK: test_pipeline_truyen_dung_language_hint_xuong_transcribe")


def test_pipeline_language_hint_mac_dinh_rong_khong_doi_hanh_vi_cu():
    # 🔒 MỚI (Mục 38) -- không truyền language_hint (như mọi test cũ) phải
    # tương đương "" ("Tự động"), giữ NGUYÊN hành vi trước Mục 38.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = MeetingStore(db_path)
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(transcript_text="Hello", language="en", translated="Xin chào")
            pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")

            for _ in range(n_frames):
                frame = np.zeros(320, dtype=np.float32)
                pipeline.feed_chunk(frame)

            assert provider.received_language_hints == [""], (
                f"Mặc định phải là '' (Tự động), nhận {provider.received_language_hints!r}."
            )
        finally:
            store.close()
    print("OK: test_pipeline_language_hint_mac_dinh_rong_khong_doi_hanh_vi_cu")


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


def test_pipeline_log_loi_transcribe_ra_logger():
    handler = _CaptureLogHandler()
    pipeline_module._logger.addHandler(handler)
    pipeline_module._logger.setLevel(logging.DEBUG)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                segmenter, n_frames = _make_segmenter_with_one_segment()
                provider = FakeProvider(fail_transcribe=True)
                pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")
                for _ in range(n_frames):
                    pipeline.feed_chunk(np.zeros(320, dtype=np.float32))
            finally:
                store.close()
    finally:
        pipeline_module._logger.removeHandler(handler)

    assert any(
        "transcribe" in msg and str(meeting_id) in msg for msg in handler.messages
    ), f"Phải log lỗi transcribe() kèm meeting_id, nhận: {handler.messages}"
    print("OK: test_pipeline_log_loi_transcribe_ra_logger")


def test_pipeline_log_loi_translate_ra_logger():
    handler = _CaptureLogHandler()
    pipeline_module._logger.addHandler(handler)
    pipeline_module._logger.setLevel(logging.DEBUG)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                segmenter, n_frames = _make_segmenter_with_one_segment()
                provider = FakeProvider(
                    transcript_text="Hello", language="en", fail_translate=True,
                )
                pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")
                for _ in range(n_frames):
                    pipeline.feed_chunk(np.zeros(320, dtype=np.float32))
            finally:
                store.close()
    finally:
        pipeline_module._logger.removeHandler(handler)

    assert any(
        "translate" in msg and str(meeting_id) in msg for msg in handler.messages
    ), f"Phải log lỗi translate() kèm meeting_id, nhận: {handler.messages}"
    print("OK: test_pipeline_log_loi_translate_ra_logger")


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
    # KHÔNG hiện bubble transcript thật, không lưu DB -- nhưng (🔒 CẬP NHẬT,
    # CONTRACTS.md Mục 23) PHẢI đánh dấu is_audio_only=True để UI hiện
    # indicator "🔊 [Âm thanh]" thay vì im lặng hoàn toàn.
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
                f"no_speech_prob=0.85 phải bị lọc, KHÔNG hiện bubble transcript thật, "
                f"nhận {len(non_empty)} bubble có text."
            )
            audio_only_events = [e for e in all_events if e.is_audio_only]
            assert len(audio_only_events) == 1, (
                f"Phải có ĐÚNG 1 event is_audio_only=True để UI hiện '🔊 [Âm thanh]', "
                f"nhận {len(audio_only_events)}."
            )
            assert audio_only_events[0].segment_id is None, (
                "Event is_audio_only KHÔNG được gắn segment_id thật (không lưu DB)."
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


def test_pipeline_doc_nguong_no_speech_prob_tu_env_khi_khong_truyen_tham_so():
    # 🔒 MỚI (Mục 27) -- không truyền no_speech_prob_drop_threshold=  ->
    # PHẢI đọc biến môi trường NO_SPEECH_PROB_DROP_THRESHOLD nếu có đặt.
    # Đặt env=0.3 (thấp hơn default 0.6) rồi feed segment có
    # no_speech_prob=0.4 -- PHẢI bị lọc (vượt ngưỡng 0.3), dù với default
    # 0.6 thì KHÔNG bị lọc -- xác nhận đúng là đọc từ env, không phải
    # trùng hợp default.
    os.environ["NO_SPEECH_PROB_DROP_THRESHOLD"] = "0.3"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                segmenter, n_frames = _make_segmenter_with_one_segment()
                provider = FakeProvider(
                    transcript_text="tạp âm nghe nhầm", language="vi",
                    confidence=0.5, no_speech_prob=0.4,
                )
                pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")
                chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
                all_events = []
                for _ in range(n_frames):
                    all_events.extend(pipeline.feed_chunk(chunk))
                non_empty = [e for e in all_events if e.original_text]
                assert len(non_empty) == 0, (
                    "Với NO_SPEECH_PROB_DROP_THRESHOLD=0.3 (env) và "
                    "no_speech_prob=0.4, PHẢI bị lọc -- pipeline không đọc "
                    "đúng giá trị từ env."
                )
            finally:
                store.close()
    finally:
        os.environ.pop("NO_SPEECH_PROB_DROP_THRESHOLD", None)
    print("OK: test_pipeline_doc_nguong_no_speech_prob_tu_env_khi_khong_truyen_tham_so")


def test_pipeline_tham_so_truyen_truc_tiep_uu_tien_hon_env():
    # 🔒 MỚI (Mục 27) -- 3 tầng ưu tiên: tham số > env > hardcode default.
    # Đặt env=0.3 NHƯNG truyền tham số 0.9 trực tiếp -- PHẢI dùng 0.9 (giữ
    # lại segment có no_speech_prob=0.4, vì 0.4 < 0.9), KHÔNG dùng 0.3 từ
    # env (nếu dùng nhầm 0.3 thì 0.4 >= 0.3 sẽ bị lọc sai).
    os.environ["NO_SPEECH_PROB_DROP_THRESHOLD"] = "0.3"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                segmenter, n_frames = _make_segmenter_with_one_segment()
                provider = FakeProvider(
                    transcript_text="câu thật ngắn", language="vi",
                    confidence=0.5, no_speech_prob=0.4,
                )
                pipeline = MeetingPipeline(
                    segmenter, provider, store, meeting_id, "vi",
                    no_speech_prob_drop_threshold=0.9,
                )
                chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
                all_events = []
                for _ in range(n_frames):
                    all_events.extend(pipeline.feed_chunk(chunk))
                non_empty = [e for e in all_events if e.original_text]
                assert len(non_empty) == 1, (
                    "Tham số truyền trực tiếp (0.9) phải ưu tiên hơn env "
                    "(0.3) -- pipeline đọc sai thứ tự ưu tiên."
                )
            finally:
                store.close()
    finally:
        os.environ.pop("NO_SPEECH_PROB_DROP_THRESHOLD", None)
    print("OK: test_pipeline_tham_so_truyen_truc_tiep_uu_tien_hon_env")


def test_pipeline_env_sai_dinh_dang_fallback_default_0_6():
    os.environ["NO_SPEECH_PROB_DROP_THRESHOLD"] = "not-a-float"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                pipeline = MeetingPipeline(
                    VadSegmenter(samplerate=16000), FakeProvider(), store, meeting_id, "vi",
                )
                assert pipeline._no_speech_prob_drop_threshold == 0.6, (
                    "Env sai định dạng phải fallback về default 0.6, "
                    f"nhận {pipeline._no_speech_prob_drop_threshold!r}."
                )
            finally:
                store.close()
    finally:
        os.environ.pop("NO_SPEECH_PROB_DROP_THRESHOLD", None)
    print("OK: test_pipeline_env_sai_dinh_dang_fallback_default_0_6")


# 🔒 MỚI (Mục 36) -- lớp lọc THỨ 2 dựa confidence, người dùng CHỦ ĐỘNG xin
# xét lại quyết định cũ (Mục 27) sau khi báo tạp âm/nhạc nền bị bịa chữ +
# dịch loạn. TẮT MẶC ĐỊNH (opt-in qua .env) -- xem cảnh báo rủi ro đầy đủ ở
# docstring hằng số CONFIDENCE_DROP_THRESHOLD trong app/pipeline.py.

def test_pipeline_mac_dinh_khong_bat_loc_confidence():
    # Mặc định (không truyền tham số, không đặt env) -- lớp lọc PHẢI tắt
    # (None), giữ NGUYÊN hành vi hiện tại cho người chưa yêu cầu.
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            pipeline = MeetingPipeline(
                VadSegmenter(samplerate=16000), FakeProvider(), store, meeting_id, "vi",
            )
            assert pipeline._confidence_drop_threshold is None, (
                f"Mặc định phải TẮT (None), nhận {pipeline._confidence_drop_threshold!r}."
            )
        finally:
            store.close()
    print("OK: test_pipeline_mac_dinh_khong_bat_loc_confidence")


def test_pipeline_loc_confidence_khi_bat_qua_tham_so_truc_tiep():
    # Bật qua tham số trực tiếp: segment ĐÃ qua ải no_speech_prob (thấp)
    # NHƯNG confidence <= ngưỡng -- PHẢI bị lọc giống nhánh no_speech_prob,
    # KHÔNG lưu DB, KHÔNG gọi translate().
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(
                transcript_text="Cảm ơn các bạn đã xem video",
                language="vi", confidence=0.10, no_speech_prob=0.05,
            )
            pipeline = MeetingPipeline(
                segmenter, provider, store, meeting_id, "vi",
                confidence_drop_threshold=0.15,
            )
            chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
            all_events = []
            for _ in range(n_frames):
                all_events.extend(pipeline.feed_chunk(chunk))

            non_empty = [e for e in all_events if e.original_text]
            assert len(non_empty) == 0, (
                f"confidence=0.10 <= ngưỡng 0.15 phải bị lọc dù no_speech_prob "
                f"thấp, nhận {len(non_empty)} bubble có text."
            )
            audio_only_events = [e for e in all_events if e.is_audio_only]
            assert len(audio_only_events) == 1
            assert store.get_segments(meeting_id) == []
            assert provider.translate_calls == 0, (
                "Đã bị lọc trước translate() -- không nên tốn quota dịch rác."
            )
        finally:
            store.close()
    print("OK: test_pipeline_loc_confidence_khi_bat_qua_tham_so_truc_tiep")


def test_pipeline_khong_loc_confidence_neu_tren_nguong():
    # ĐỐI CHIẾU: confidence CAO HƠN ngưỡng -- KHÔNG bị lọc, câu thật vẫn
    # được giữ lại bình thường dù đã bật lớp lọc này.
    with tempfile.TemporaryDirectory() as tmp:
        store = MeetingStore(os.path.join(tmp, "test.db"))
        try:
            meeting_id = store.start_meeting(user_native_lang="vi")
            segmenter, n_frames = _make_segmenter_with_one_segment()
            provider = FakeProvider(
                transcript_text="Human.", language="en",
                confidence=0.20, no_speech_prob=0.02,
            )
            pipeline = MeetingPipeline(
                segmenter, provider, store, meeting_id, "vi",
                confidence_drop_threshold=0.15,
            )
            chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
            all_events = []
            for _ in range(n_frames):
                all_events.extend(pipeline.feed_chunk(chunk))

            non_empty = [e for e in all_events if e.original_text]
            assert len(non_empty) == 1, (
                f"confidence=0.20 > ngưỡng 0.15 KHÔNG được lọc, nhận "
                f"{len(non_empty)} bubble."
            )
            assert len(store.get_segments(meeting_id)) == 1
        finally:
            store.close()
    print("OK: test_pipeline_khong_loc_confidence_neu_tren_nguong")


def test_pipeline_doc_nguong_confidence_tu_env_khi_khong_truyen_tham_so():
    os.environ["CONFIDENCE_DROP_THRESHOLD"] = "0.15"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                segmenter, n_frames = _make_segmenter_with_one_segment()
                provider = FakeProvider(
                    transcript_text="tạp âm bịa chữ", language="vi",
                    confidence=0.10, no_speech_prob=0.05,
                )
                pipeline = MeetingPipeline(segmenter, provider, store, meeting_id, "vi")
                chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
                all_events = []
                for _ in range(n_frames):
                    all_events.extend(pipeline.feed_chunk(chunk))
                non_empty = [e for e in all_events if e.original_text]
                assert len(non_empty) == 0, (
                    "Với CONFIDENCE_DROP_THRESHOLD=0.15 (env) và confidence=0.10, "
                    "PHẢI bị lọc -- pipeline không đọc đúng giá trị từ env."
                )
            finally:
                store.close()
    finally:
        os.environ.pop("CONFIDENCE_DROP_THRESHOLD", None)
    print("OK: test_pipeline_doc_nguong_confidence_tu_env_khi_khong_truyen_tham_so")


def test_pipeline_tham_so_confidence_truc_tiep_uu_tien_hon_env():
    os.environ["CONFIDENCE_DROP_THRESHOLD"] = "0.15"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                segmenter, n_frames = _make_segmenter_with_one_segment()
                provider = FakeProvider(
                    transcript_text="câu thật ngắn", language="vi",
                    confidence=0.10, no_speech_prob=0.05,
                )
                # Tham số trực tiếp None nghĩa là "không override" theo hợp
                # đồng chung (None -> đọc env) -- test ưu tiên đúng nghĩa
                # bằng cách truyền số CAO hơn confidence để xác nhận KHÔNG
                # bị lọc theo env 0.15 nữa.
                pipeline = MeetingPipeline(
                    segmenter, provider, store, meeting_id, "vi",
                    confidence_drop_threshold=0.05,
                )
                chunk = np.zeros(int(16000 * 0.02), dtype=np.float32)
                all_events = []
                for _ in range(n_frames):
                    all_events.extend(pipeline.feed_chunk(chunk))
                non_empty = [e for e in all_events if e.original_text]
                assert len(non_empty) == 1, (
                    "Tham số truyền trực tiếp (0.05) phải ưu tiên hơn env "
                    "(0.15) -- confidence=0.10 > 0.05 nên KHÔNG được lọc."
                )
            finally:
                store.close()
    finally:
        os.environ.pop("CONFIDENCE_DROP_THRESHOLD", None)
    print("OK: test_pipeline_tham_so_confidence_truc_tiep_uu_tien_hon_env")


def test_pipeline_env_confidence_sai_dinh_dang_fallback_tat():
    os.environ["CONFIDENCE_DROP_THRESHOLD"] = "not-a-float"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = MeetingStore(os.path.join(tmp, "test.db"))
            try:
                meeting_id = store.start_meeting(user_native_lang="vi")
                pipeline = MeetingPipeline(
                    VadSegmenter(samplerate=16000), FakeProvider(), store, meeting_id, "vi",
                )
                assert pipeline._confidence_drop_threshold is None, (
                    "Env sai định dạng phải fallback về TẮT (None), khác "
                    f"no_speech_prob (fallback về 0.6) -- nhận "
                    f"{pipeline._confidence_drop_threshold!r}."
                )
            finally:
                store.close()
    finally:
        os.environ.pop("CONFIDENCE_DROP_THRESHOLD", None)
    print("OK: test_pipeline_env_confidence_sai_dinh_dang_fallback_tat")


if __name__ == "__main__":
    test_pipeline_full_happy_path_luu_dung_db()
    test_pipeline_truyen_dung_language_hint_xuong_transcribe()
    test_pipeline_language_hint_mac_dinh_rong_khong_doi_hanh_vi_cu()
    test_pipeline_khong_dich_neu_cung_ngon_ngu_me_de()
    test_pipeline_loi_transcribe_khong_lam_sap_pipeline()
    test_pipeline_loi_translate_van_luu_duoc_ban_goc()
    test_pipeline_log_loi_transcribe_ra_logger()
    test_pipeline_log_loi_translate_ra_logger()
    test_pipeline_is_question_duoc_danh_dau_dung()
    test_flush_xu_ly_cau_noi_con_do()
    test_pipeline_truyen_dung_context_cho_translate_khong_lan_cau_hien_tai()
    test_pipeline_bo_qua_segment_hallucination_no_speech_prob_cao()
    test_pipeline_giu_lai_cau_ngan_du_confidence_thap_neu_no_speech_prob_thap()
    test_pipeline_doc_nguong_no_speech_prob_tu_env_khi_khong_truyen_tham_so()
    test_pipeline_tham_so_truyen_truc_tiep_uu_tien_hon_env()
    test_pipeline_env_sai_dinh_dang_fallback_default_0_6()
    test_pipeline_mac_dinh_khong_bat_loc_confidence()
    test_pipeline_loc_confidence_khi_bat_qua_tham_so_truc_tiep()
    test_pipeline_khong_loc_confidence_neu_tren_nguong()
    test_pipeline_doc_nguong_confidence_tu_env_khi_khong_truyen_tham_so()
    test_pipeline_tham_so_confidence_truc_tiep_uu_tien_hon_env()
    test_pipeline_env_confidence_sai_dinh_dang_fallback_tat()
    print("\n=== TẤT CẢ TEST PIPELINE PASS ===")
