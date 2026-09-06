"""
ui/main_window.py
------------------
Cửa sổ chính. Phase 1: banner consent ghi âm (F8), vùng transcript song ngữ
realtime (F1-F4), nút Bắt đầu/Kết thúc, lưu DB (F9). Phase 2 (F5-F7): nút
"Nhờ AI trả lời" trên bubble câu hỏi + `SuggestionDrawer` (soạn gợi ý, cho
sửa, dịch ngược) + "Tôi muốn hỏi" (AskQuestionDialog). Phase 3 Bước 2/4
(F10-F11): nút "📄 Xem báo cáo" + `ReportDialog` — gọi `summarize()` qua
`OneShotAIWorker` đã có sẵn từ Phase 2. Phase 3 Bước 3/4 (F11, MỚI): báo
cáo được LƯU vào DB (`meeting_reports`) — mở lại dialog không gọi lại AI
nếu đã có cache, nút "🔄 Tạo báo cáo mới" để bỏ cache khi cần, tick action
item lưu ngay, 2 nút xuất ".docx"/".pdf" (app/report_export.py).

Quy ước threading (CONTRACTS.md Mục 3, đã áp dụng đúng ở đây):
    - `AudioWorker` (QThread) tự tạo `MeetingStore` và `AIProvider` (qua
      `provider_factory.create_provider()` — Groq/OpenAI/Gemini tuỳ người
      dùng chọn ở Settings, xem CONTRACTS.md Mục 17) BÊN TRONG run() của
      chính nó, KHÔNG nhận instance đã tạo sẵn từ main thread truyền vào. Lý do bắt buộc: sqlite3 connection bị "khoá" vào
      đúng thread đã gọi connect() (check_same_thread=True mặc định) -- nếu
      tạo MeetingStore ở main thread (vd lúc bấm nút) rồi đưa cho worker
      thread dùng, mọi lệnh add_segment() sẽ raise lỗi runtime. Đây là lỗi
      rất dễ mắc khi mới ghép Qt threading với SQLite, nên cố tình thiết kế
      để không thể mắc lỗi này (worker tự quản lý toàn bộ vòng đời store).
    - main thread (UI) CHỈ nhận dữ liệu qua Signal, không bao giờ tự gọi
      AIProvider/MeetingStore trực tiếp.
    - Phase 2/3: suggest_answer()/translate()/summarize() do người dùng bấm
      nút kích hoạt chạy qua `OneShotAIWorker` RIÊNG (xem app/ui/ai_worker.py)
      — KHÔNG tái dùng `AudioWorker` đang chạy vòng lặp audio (lý do kỹ thuật
      chi tiết nằm trong docstring đầu file ai_worker.py).
    - Phase 3 Bước 3/4: NGOẠI LỆ CÓ Ý cho `_on_action_item_toggled()` — ghi
      SQLite TRỰC TIẾP trên main thread (không qua OneShotAIWorker), vì đây
      không phải lệnh AI/network, chỉ 1 UPDATE cực nhỏ (xem docstring
      `set_action_item_done()` ở storage/db.py để biết lý do đầy đủ).
"""

from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import report_export
from app.ai.base_provider import ProviderError, SummaryResult
from app.ai.provider_factory import create_provider
from app.audio.capture import AudioCaptureError, AudioDeviceChangedError, stream_loopback_chunks
from app.audio.vad import create_vad_segmenter_from_env
from app.logging_setup import get_logger
from app.pipeline import MeetingPipeline, TranscriptEvent
from app.report import build_transcript_text
from app.report_export import ReportExportError
from app.storage.db import MeetingStore, ReportRecord, StorageError
from app.ui.ai_worker import OneShotAIWorker
from app.ui.ask_question_dialog import AskQuestionDialog
from app.ui.audio_only_bubble import AudioOnlyBubble
from app.ui.chat_dialog import ChatDialog
from app.ui.help_dialog import HelpDialog
from app.ui.history_dialog import MeetingHistoryDialog
from app.ui.meeting_context_dialog import MeetingContextDialog
from app.ui.report_view import ReportDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.suggestion_drawer import SuggestionDrawer
from app.ui.transcript_bubble import TranscriptBubble

_NATIVE_LANG_OPTIONS = [
    ("vi", "Tiếng Việt"), ("en", "English"), ("zh", "中文"),
    ("ja", "日本語"), ("ko", "한국어"),  # 🔒 MỚI (CONTRACTS.md Mục 22)
]
_DEFAULT_DB_PATH = "meetings.db"
_CONTEXT_HISTORY_SIZE = 5  # số dòng transcript gần nhất đưa làm ngữ cảnh cho suggest_answer()
# 🔒 MỚI -- giới hạn an toàn cho vòng tự-mở-lại stream khi gặp
# AudioDeviceChangedError LIÊN TỤC mà KHÔNG nhận được chunk thật nào ở
# giữa (xem AudioWorker.run()) -- tránh treo thread vô hạn nếu rơi vào case
# bệnh lý (lỗi nhận diện sai liên tục).
_MAX_CONSECUTIVE_DEVICE_RETRIES = 5

_logger = get_logger()  # 🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30)


class AudioWorker(QThread):
    """Chạy audio loopback + VAD + AIProvider + DB trên 1 thread riêng,
    KHÔNG block UI. Xem ghi chú threading ở đầu file."""

    meeting_started = Signal(int)          # meeting_id
    new_event = Signal(object)              # TranscriptEvent
    error_occurred = Signal(str)            # message lỗi hiển thị cho người dùng
    finished_recording = Signal()

    def __init__(
        self,
        user_native_lang: str,
        db_path: str = _DEFAULT_DB_PATH,
        meeting_context: str = "",
        language_hint: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._user_native_lang = user_native_lang
        self._db_path = db_path
        # 🔒 MỚI (CONTRACTS.md Mục 38) — "" = "Tự động" (mặc định, giữ
        # nguyên hành vi cũ). Xem AIProvider.transcribe() docstring.
        self._language_hint = language_hint
        # 🔒 MỚI (Vòng 9, CONTRACTS.md Mục 18) — bối cảnh TĨNH người dùng tự
        # nhập ở MeetingContextDialog trước khi bấm "Bắt đầu ghi". Chỉ dùng
        # để LƯU vào DB (start_meeting()) ở đây — suggest_answer() lại đọc
        # meeting_context từ MainWindow._current_meeting_context (giữ trên
        # main thread), KHÔNG đọc lại từ đây, vì suggest_answer() chạy qua
        # OneShotAIWorker riêng, không qua AudioWorker này (xem ai_worker.py).
        self._meeting_context = meeting_context
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        """Gọi từ main thread khi người dùng bấm 'Kết thúc họp'. Dừng trong
        khoảng ~chunk_ms (mặc định 100ms) -- không tức thời tuyệt đối vì
        generator audio đang block chờ chunk hiện tại."""
        self._stop_event.set()

    def run(self) -> None:  # noqa: C901 - luồng chính worker, giữ trong 1 hàm cho dễ theo dõi
        store: MeetingStore | None = None
        try:
            provider = create_provider()  # đọc provider+key đang dùng (Settings UI hoặc .env khi dev — xem provider_factory.py)
        except ProviderError as exc:
            _logger.error("Không khởi tạo được AI provider: %s", exc)
            self.error_occurred.emit(f"Không khởi tạo được AI provider: {exc}")
            self.finished_recording.emit()
            return

        try:
            store = MeetingStore(self._db_path)  # tạo trên CHÍNH worker thread này
            meeting_id = store.start_meeting(self._user_native_lang, self._meeting_context)
        except StorageError as exc:
            _logger.error("Không tạo được phiên họp trong database: %s", exc)
            self.error_occurred.emit(f"Không tạo được phiên họp trong database: {exc}")
            self.finished_recording.emit()
            return

        _logger.info("Bắt đầu phiên họp mới (meeting_id=%s)", meeting_id)
        self.meeting_started.emit(meeting_id)

        # 🔒 MỚI (Mục 27) -- đọc override qua .env (VAD_AGGRESSIVENESS,
        # VAD_SILENCE_MS, ...) thay vì hardcode cứng, xem
        # app/audio/vad.py::create_vad_segmenter_from_env().
        segmenter = create_vad_segmenter_from_env(samplerate=16000)
        pipeline = MeetingPipeline(
            segmenter=segmenter, provider=provider, store=store,
            meeting_id=meeting_id, user_native_lang=self._user_native_lang,
            samplerate=16000, language_hint=self._language_hint,
        )

        try:
            # 🔒 MỚI -- vòng `while True` BÊN NGOÀI để tự mở lại
            # stream_loopback_chunks() khi gặp AudioDeviceChangedError
            # (Windows đổi default playback device giữa lúc đang ghi, xem
            # docstring đầy đủ ở audio/capture.py) -- KHÔNG kết thúc phiên
            # họp, KHÔNG mất meeting_id/pipeline đang dùng, chỉ generator
            # audio cấp thấp được tạo lại (tự nhiên resolve đúng device
            # MỚI ngay khi gọi lại stream_loopback_chunks()). Mọi
            # AudioCaptureError KHÁC vẫn kết thúc phiên họp như cũ (coi là
            # lỗi không tự phục hồi được -- KHÔNG đổi hành vi cũ cho các
            # case này).
            device_change_retry_count = 0
            while not self._stop_event.is_set():
                try:
                    for chunk in stream_loopback_chunks(target_samplerate=16000):
                        if self._stop_event.is_set():
                            break
                        for event in pipeline.feed_chunk(chunk):
                            self.new_event.emit(event)
                        device_change_retry_count = 0  # đã nhận chunk thật -> reset bộ đếm an toàn
                    break  # generator kết thúc bình thường (vd break ở trên do stop_event)
                except AudioDeviceChangedError:
                    # ⚠️ CHƯA verify được trên Windows thật trong sandbox
                    # này (không có audio hardware) -- xem cảnh báo đầy đủ
                    # ở docstring AudioDeviceChangedError (audio/capture.py)
                    # về phạm vi CHÍNH XÁC lỗi này áp dụng (đổi DEVICE,
                    # không phải đổi app/tab nguồn phát). KHÔNG emit
                    # error_occurred ở đây -- đây là tình huống ĐÃ tự phục
                    # hồi được, không nên làm phiên họp bị đánh dấu "kết
                    # thúc có lỗi" ở _on_worker_finished() chỉ vì 1 lần đổi
                    # device thoáng qua giữa cuộc họp.
                    #
                    # An toàn phòng case bệnh lý (vd lỗi nhận diện sai liên
                    # tục, đổi device dồn dập bất thường): đếm số lần GẶP
                    # LIÊN TIẾP MÀ CHƯA NHẬN ĐƯỢC CHUNK THẬT NÀO ở giữa (xem
                    # reset ở trên) -- quá _MAX_CONSECUTIVE_DEVICE_RETRIES
                    # lần thì DỪNG hẳn (coi như lỗi thật, không tự phục hồi
                    # được nữa) thay vì xoay vòng vô hạn treo thread.
                    device_change_retry_count += 1
                    if device_change_retry_count > _MAX_CONSECUTIVE_DEVICE_RETRIES:
                        _logger.error(
                            "Thiết bị âm thanh đổi liên tục %s lần (meeting_id=%s) -- "
                            "dừng tự động mở lại.", device_change_retry_count, meeting_id,
                        )
                        self.error_occurred.emit(
                            "Thiết bị phát âm thanh đổi liên tục nhiều lần "
                            "bất thường -- đã dừng tự động mở lại để tránh "
                            "treo. Hãy kiểm tra lại thiết bị âm thanh rồi "
                            "bắt đầu ghi lại."
                        )
                        break
                    time.sleep(0.5)  # tránh xoay vòng dồn dập nếu lỗi lặp lại ngay
                    continue
        except AudioCaptureError as exc:
            _logger.error("Lỗi capture audio (meeting_id=%s): %s", meeting_id, exc)
            self.error_occurred.emit(str(exc))

        # Dù dừng do người dùng bấm Stop hay do lỗi audio giữa chừng, vẫn cố
        # flush() để không mất câu nói cuối đang dở (nếu có).
        try:
            flushed = pipeline.flush()
            if flushed is not None:
                self.new_event.emit(flushed)
        except Exception as exc:  # noqa: BLE001 - không để lỗi flush làm mất phiên đã ghi
            _logger.error("Lỗi khi xử lý đoạn nói cuối (meeting_id=%s): %s", meeting_id, exc, exc_info=True)
            self.error_occurred.emit(f"Lỗi khi xử lý đoạn nói cuối: {exc}")

        pipeline.close()
        store.close()
        _logger.info("Kết thúc phiên họp (meeting_id=%s)", meeting_id)
        self.finished_recording.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Meeting Companion")
        self.resize(720, 800)

        self._worker: AudioWorker | None = None
        self._current_meeting_id: int | None = None
        self._current_native_lang: str = "vi"
        # 🔒 MỚI (Vòng 9, CONTRACTS.md Mục 18) — bối cảnh TĨNH của phiên họp
        # hiện tại, đọc 1 lần từ MeetingContextDialog lúc bấm "Bắt đầu ghi",
        # dùng lại cho MỌI lần bấm "Nhờ AI trả lời" trong suốt phiên (xem
        # _start_suggest_worker). "" nghĩa là người dùng không nhập/bỏ qua.
        self._current_meeting_context: str = ""

        # Phase 2: ngữ cảnh gần nhất cho suggest_answer() + giữ tham chiếu
        # các OneShotAIWorker đang chạy (QThread bị garbage-collect giữa
        # chừng nếu không có ai giữ tham chiếu Python tới nó -> rất dễ crash
        # ngầm khó debug, nên PHẢI giữ list này).
        self._recent_originals: list[str] = []
        self._pending_autoscroll: bool = False
        self._recent_source_langs: list[str] = []
        self._ai_workers: list[OneShotAIWorker] = []
        self._last_error_in_session: str | None = None
        # 🔒 MỚI (CONTRACTS.md Mục 21) — "Hỏi AI": giữ ĐÚNG 1 instance dialog
        # (khác SuggestionDrawer có thể mở nhiều cái cùng lúc), tạo lười
        # (lazy) ở lần bấm nút đầu tiên, để lịch sử hội thoại giữ liên tục
        # suốt phiên làm việc thay vì mất khi đóng/mở lại.
        self._chat_dialog: ChatDialog | None = None
        # 🔒 MỚI (Mục 34 -- yêu cầu người dùng) -- CÙNG pattern singleton như
        # `_chat_dialog` ở trên, áp dụng thêm cho Cài đặt/Lịch sử/Tôi muốn
        # hỏi/Xem báo cáo: nhấn đúp hoặc nhấn nhiều lần liên tiếp vào 1 nút
        # trước đây tạo ra NHIỀU cửa sổ chồng lên nhau (mỗi lần bấm là 1
        # `QDialog` mới + `.show()`) -- rất bất tiện. Từ nay mỗi loại dialog
        # chỉ giữ ĐÚNG 1 instance đang sống; bấm thêm lần nữa chỉ
        # show()+raise_()+activateWindow() lại CHÍNH cửa sổ đó thay vì tạo
        # mới. Các dialog này KHÔNG bật `Qt.WA_DeleteOnClose` (đóng bằng X/
        # Esc chỉ ẩn đi, không huỷ instance) nên việc tái sử dụng an toàn --
        # đúng tiền lệ đã có sẵn của `_chat_dialog` (Mục 21), không phải kỹ
        # thuật mới trong dự án.
        self._settings_dialog: SettingsDialog | None = None
        self._help_dialog: HelpDialog | None = None
        self._history_dialog: MeetingHistoryDialog | None = None
        self._ask_question_dialog: AskQuestionDialog | None = None
        # meeting_id -> ReportDialog đang mở cho ĐÚNG phiên đó -- report có
        # trạng thái riêng theo TỪNG phiên họp (khác Settings/Lịch sử/Tôi
        # muốn hỏi chỉ cần 1 instance chung), nên khoá theo meeting_id thay
        # vì 1 biến duy nhất: xem báo cáo phiên #3 xong rồi xem phiên #5
        # vẫn là 2 cửa sổ khác nhau hợp lý (không phải "trùng"), CHỈ chặn
        # trùng khi bấm lại ĐÚNG PHIÊN đang mở sẵn.
        self._report_dialogs: dict[int, ReportDialog] = {}

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---- Banner consent ghi âm (F8) ----
        self._banner = QWidget()
        self._banner.setObjectName("RecordingBanner")
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)

        self._recording_dot = QLabel()
        self._recording_dot.setObjectName("RecordingDot")
        self._recording_dot.setFixedSize(10, 10)
        banner_layout.addWidget(self._recording_dot)

        banner_label = QLabel("Đang ghi âm cuộc họp này — chỉ lưu trên máy bạn.")
        banner_label.setObjectName("RecordingBannerLabel")
        banner_layout.addWidget(banner_label)
        banner_layout.addStretch(1)

        self._banner.setVisible(False)
        root_layout.addWidget(self._banner)

        # ---- Vùng transcript ----
        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("TranscriptScrollArea")
        self._scroll_area.setWidgetResizable(True)

        self._transcript_container = QWidget()
        self._transcript_container.setObjectName("TranscriptContainer")
        self._transcript_layout = QVBoxLayout(self._transcript_container)
        self._transcript_layout.setContentsMargins(12, 12, 12, 12)
        self._transcript_layout.setSpacing(8)
        self._transcript_layout.addStretch(1)  # giữ bubble luôn dồn lên trên

        self._scroll_area.setWidget(self._transcript_container)
        # Kết nối 1 LẦN duy nhất ở đây -- xem _on_scrollbar_range_changed()
        # để biết lý do dùng rangeChanged thay vì QTimer.singleShot(0, ...).
        self._scroll_area.verticalScrollBar().rangeChanged.connect(self._on_scrollbar_range_changed)
        root_layout.addWidget(self._scroll_area, stretch=1)

        # ---- Control bar ----
        control_bar = QWidget()
        control_bar.setObjectName("ControlBar")
        control_layout = QVBoxLayout(control_bar)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Ngôn ngữ mẹ đẻ của bạn:"))
        self._lang_combo = QComboBox()
        for code, label in _NATIVE_LANG_OPTIONS:
            self._lang_combo.addItem(label, userData=code)
        row1.addWidget(self._lang_combo)
        row1.addStretch(1)
        control_layout.addLayout(row1)

        row2 = QHBoxLayout()
        # 🔒 MỚI (Mục 32 -- yêu cầu người dùng) -- mỗi nút cơ bản có 1 chữ cái
        # mnemonic riêng (dấu &), cho phép thao tác THUẦN BÀN PHÍM: Alt+chữ
        # cái để kích hoạt nút mà KHÔNG cần chuột (vd Alt+B = Bắt đầu ghi),
        # kết hợp Tab/Shift+Tab để di chuyển giữa các nút + Enter/Space để
        # bấm nút đang focus (hành vi mặc định sẵn có của QPushButton, không
        # cần code thêm). 8 chữ cái B/K/T/X/L/A/C/G (thêm G ở Mục 37) KHÔNG
        # trùng nhau trong cùng cửa sổ chính -- Qt sẽ báo lỗi/mnemonic không
        # hoạt động đúng nếu 2 nút cùng cửa sổ trùng chữ cái, nên khi thêm
        # nút MỚI ở đây về sau PHẢI chọn chữ cái còn trống (xem danh sách đã
        # dùng ngay trên mỗi nút bên dưới) hoặc bỏ mnemonic cho nút đó.
        self._start_button = QPushButton("&Bắt đầu ghi")  # Alt+B
        self._start_button.setObjectName("PrimaryButton")
        self._start_button.setToolTip("Bắt đầu ghi âm cuộc họp mới. (Alt+B)")
        self._start_button.clicked.connect(self._on_start_clicked)
        row2.addWidget(self._start_button)

        self._stop_button = QPushButton("&Kết thúc họp")  # Alt+K
        self._stop_button.setObjectName("DangerButton")
        self._stop_button.setEnabled(False)
        self._stop_button.setToolTip("Kết thúc phiên họp đang ghi. (Alt+K)")
        self._stop_button.clicked.connect(self._on_stop_clicked)
        row2.addWidget(self._stop_button)

        self._ask_question_button = QPushButton("❓ &Tôi muốn hỏi")  # Alt+T
        self._ask_question_button.setObjectName("AskAiButton")
        self._ask_question_button.setEnabled(False)  # chỉ bật khi đang có phiên họp
        self._ask_question_button.setToolTip(
            "Nhập câu bạn muốn hỏi/đặt vấn đề bằng tiếng mẹ đẻ, dịch sang "
            "ngôn ngữ đối phương để chủ động hỏi lại — không chỉ ngồi đợi bị hỏi. "
            "(Alt+T)"
        )
        self._ask_question_button.clicked.connect(self._on_ask_question_clicked)
        row2.addWidget(self._ask_question_button)

        self._report_button = QPushButton("📄 &Xem báo cáo")  # Alt+X
        self._report_button.setObjectName("AskAiButton")
        self._report_button.setEnabled(False)  # chỉ bật khi đã có phiên họp (start/end đều dùng được)
        self._report_button.setToolTip(
            "Tổng hợp tóm tắt + quyết định + việc cần làm của phiên họp này bằng AI. "
            "(Alt+X)"
        )
        self._report_button.clicked.connect(self._on_report_clicked)
        row2.addWidget(self._report_button)

        self._history_button = QPushButton("🕓 &Lịch sử")  # Alt+L
        self._history_button.setObjectName("AskAiButton")
        # 🔒 MỚI (F13) -- CỐ TÌNH luôn bật, KHÔNG gate theo _current_meeting_id
        # như _report_button -- đây chính là sửa lỗi thật "không xem được
        # báo cáo phiên họp CŨ" (xem CONTRACTS.md Mục 13): phải mở được dù
        # chưa/không đang ghi âm gì trong session hiện tại.
        self._history_button.setToolTip(
            "Xem/tìm lại các phiên họp đã ghi trước đây, kể cả khi không "
            "đang ghi âm gì ngay lúc này. (Alt+L)"
        )
        self._history_button.clicked.connect(self._on_history_clicked)
        row2.addWidget(self._history_button)

        self._chat_button = QPushButton("💬 Hỏi &AI")  # Alt+A
        self._chat_button.setObjectName("AskAiButton")
        # 🔒 MỚI (CONTRACTS.md Mục 21) — CỐ Ý luôn bật, KHÔNG gate theo
        # meeting_started (khác _ask_question_button/_report_button) —
        # đây là trợ lý kiến thức chung, không phụ thuộc đang có phiên họp
        # hay không, cùng tinh thần với _history_button (Mục 13).
        self._chat_button.setToolTip(
            "Hỏi-đáp tự do với AI (dùng kiến thức có sẵn, không tra cứu web). "
            "(Alt+A)"
        )
        self._chat_button.clicked.connect(self._on_chat_clicked)
        row2.addWidget(self._chat_button)

        self._settings_button = QPushButton("⚙️ &Cài đặt")  # Alt+C
        self._settings_button.setObjectName("AskAiButton")
        self._settings_button.setToolTip("Nhập/đổi API key của bạn. (Alt+C)")
        self._settings_button.clicked.connect(self._on_settings_clicked)
        row2.addWidget(self._settings_button)

        # 🔒 MỚI (Mục 37 -- yêu cầu người dùng, phản hồi test thật: "không
        # biết nhấn phím/tổ hợp phím nào") -- gom toàn bộ phím tắt + quy
        # trình dùng cơ bản vào 1 dialog mở được ngay từ đây.
        self._help_button = QPushButton("❓ Trợ &Giúp")  # Alt+G
        self._help_button.setObjectName("AskAiButton")
        self._help_button.setToolTip(
            "Xem danh sách phím tắt (Alt+...) và quy trình dùng cơ bản. (Alt+G)"
        )
        self._help_button.clicked.connect(self._on_help_clicked)
        row2.addWidget(self._help_button)

        row2.addStretch(1)
        control_layout.addLayout(row2)

        self._status_label = QLabel("Sẵn sàng.")
        self._status_label.setObjectName("StatusLabel")
        control_layout.addWidget(self._status_label)

        root_layout.addWidget(control_bar)
        self.setCentralWidget(root)

    # -- UI handlers -------------------------------------------------------

    def _on_start_clicked(self) -> None:
        # 🔒 MỚI (Vòng 9, CONTRACTS.md Mục 18) — hỏi bối cảnh cuộc họp
        # TRƯỚC khi làm bất kỳ thay đổi trạng thái nào (reset list, disable
        # nút, tạo AudioWorker) — nếu người dùng bấm "Huỷ" ở dialog này,
        # màn hình chính phải giữ NGUYÊN như chưa bấm gì, không được nửa
        # vời (vd đã disable nút "Bắt đầu ghi" nhưng chưa có worker nào chạy).
        #
        # Tách riêng phần "hỏi bối cảnh" (ở đây) khỏi phần "thật sự bắt đầu
        # ghi" (_start_recording() bên dưới) CÓ CHỦ Ý: _start_recording()
        # cần tự test được KHÔNG phải tự động click qua 1 QDialog.exec()
        # modal thật (tests/test_ui_smoke.py gọi thẳng _start_recording()
        # với meeting_context="" để giữ nguyên hành vi test cũ — xem
        # docstring _start_recording()).
        context_dialog = MeetingContextDialog(parent=self)
        if context_dialog.exec() != QDialog.Accepted:
            return
        self._start_recording(context_dialog.context_text(), context_dialog.language_hint())

    def _start_recording(self, meeting_context: str, language_hint: str = "") -> None:
        """Thật sự khởi động 1 phiên ghi âm mới — tách riêng khỏi
        `_on_start_clicked()` (xem lý do ở đó) để test được KHÔNG cần đi
        qua `MeetingContextDialog` modal thật (tests/test_ui_smoke.py gọi
        `window._start_recording("")` thay cho `window._on_start_clicked()`
        cũ — hành vi bên trong hàm này GIỮ NGUYÊN 100% so với thân hàm
        `_on_start_clicked()` trước Vòng 9). `language_hint` (🔒 MỚI, Mục
        38) optional, mặc định "" ("Tự động") — test cũ gọi 1 tham số vẫn
        hoạt động y hệt trước."""
        native_lang = self._lang_combo.currentData()
        self._current_native_lang = native_lang
        self._current_meeting_context = meeting_context
        self._recent_originals = []  # reset ngữ cảnh cho phiên họp mới
        self._recent_source_langs = []
        self._last_error_in_session = None
        self._start_button.setEnabled(False)
        self._report_button.setEnabled(False)  # tránh dùng nhầm meeting_id CŨ trong lúc chờ meeting_started
        self._set_status("Đang khởi động...", is_error=False)

        self._worker = AudioWorker(
            user_native_lang=native_lang, meeting_context=meeting_context,
            language_hint=language_hint,
        )
        self._worker.meeting_started.connect(self._on_meeting_started)
        self._worker.new_event.connect(self._on_new_event)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.finished_recording.connect(self._on_worker_finished)
        self._worker.start()

    def _on_stop_clicked(self) -> None:
        if self._worker is not None:
            self._set_status("Đang dừng ghi âm...", is_error=False)
            self._stop_button.setEnabled(False)
            self._worker.request_stop()

    def _on_meeting_started(self, meeting_id: int) -> None:
        self._current_meeting_id = meeting_id
        self._banner.setVisible(True)
        self._stop_button.setEnabled(True)
        self._ask_question_button.setEnabled(True)
        self._report_button.setEnabled(True)
        self._set_status(f"Đang ghi âm — phiên họp #{meeting_id}.", is_error=False)

    def _on_new_event(self, event: TranscriptEvent) -> None:
        if event.is_audio_only:
            # 🔒 MỚI (CONTRACTS.md Mục 23) — audio thật nhưng không phải
            # giọng nói (nhạc không lời/tạp âm) -- hiện indicator NHẸ, KHÔNG
            # tạo TranscriptBubble (không có original_text/translated_text
            # thật), KHÔNG cập nhật _recent_originals/_recent_source_langs
            # (không phải 1 câu nói thật, không nên lẫn vào ngữ cảnh cho
            # suggest_answer()/translate() sau này).
            indicator = AudioOnlyBubble()
            if self._is_scrolled_to_bottom():
                self._pending_autoscroll = True
            self._transcript_layout.insertWidget(self._transcript_layout.count() - 1, indicator)
            return
        if event.original_text:
            # Lấy context TRƯỚC khi thêm event hiện tại vào lịch sử -- snapshot
            # này gắn cố định vào bubble (xem TranscriptBubble docstring), để
            # sau này bấm "Nhờ AI trả lời" luôn đúng ngữ cảnh TRƯỚC câu hỏi,
            # không bị lẫn các câu nói SAU câu hỏi nếu người dùng bấm muộn.
            context_text = "\n".join(self._recent_originals[-_CONTEXT_HISTORY_SIZE:])
            bubble = TranscriptBubble.from_event(event, context_text=context_text)
            bubble.answer_requested.connect(self._on_answer_requested)

            # Bug thật phát hiện qua test: phải nhớ "đang ở gần cuối" TRƯỚC
            # khi chèn bubble mới -- nếu người dùng đang chủ động cuộn LÊN
            # đọc lại lịch sử, không nên kéo họ xuống dưới mỗi khi có dòng
            # mới (giật, mất chỗ đang đọc). Set cờ này, KHÔNG tự cuộn ngay ở
            # đây -- xem _on_scrollbar_range_changed() để biết vì sao.
            if self._is_scrolled_to_bottom():
                self._pending_autoscroll = True

            # addStretch(1) luôn ở cuối layout -- chèn bubble mới NGAY TRƯỚC
            # stretch đó để bubble dồn lên trên, không bị đẩy xuống dưới.
            self._transcript_layout.insertWidget(self._transcript_layout.count() - 1, bubble)

            self._recent_originals.append(event.original_text)
            if event.source_lang:
                self._recent_source_langs.append(event.source_lang)
        if event.error:
            self._last_error_in_session = event.error
            self._set_status(event.error, is_error=True)

    def _is_scrolled_to_bottom(self, tolerance_px: int = 48) -> bool:
        bar = self._scroll_area.verticalScrollBar()
        return bar.value() >= bar.maximum() - tolerance_px

    def _on_scrollbar_range_changed(self, _min_value: int, max_value: int) -> None:
        """⚠️ Bug thật vẫn còn sau lần sửa trước: `QTimer.singleShot(0, ...)`
        KHÔNG đủ tin cậy để "đợi Qt tính lại layout" -- 1 timer 0ms vẫn có
        thể được xử lý TRƯỚC khi Qt thực sự polish/relayout xong, tuỳ thứ tự
        hàng đợi event nội bộ, nên scroll vẫn nhảy tới max CŨ trong nhiều
        trường hợp thực tế (đúng như báo cáo: vẫn phải cuộn tay).

        Cách đúng theo khuyến nghị Qt: lắng nghe trực tiếp signal
        `QScrollBar.rangeChanged(min, max)` — signal này CHỈ bắn ra đúng lúc
        Qt đã tính xong range mới sau khi nội dung scroll area thay đổi, và
        cấp sẵn giá trị `max_value` MỚI làm tham số — không cần đọc lại
        `maximum()` và đoán nó đã cập nhật hay chưa, không có race nào ở đây.
        """
        if self._pending_autoscroll:
            self._scroll_area.verticalScrollBar().setValue(max_value)
            self._pending_autoscroll = False

    def _on_worker_error(self, message: str) -> None:
        self._last_error_in_session = message
        self._set_status(message, is_error=True)

    # -- Phase 2: "Nhờ AI trả lời" -----------------------------------------

    def _on_answer_requested(self, question_text: str, context_text: str, source_lang: str) -> None:
        drawer = SuggestionDrawer(question_text, parent=self)
        drawer.set_loading()
        drawer.show()

        # Bind trực tiếp vào `drawer`/tham số tại đây (closure), KHÔNG qua
        # self._active_drawer -- người dùng có thể mở nhiều drawer (nhiều
        # câu hỏi khác nhau) cùng lúc, mỗi cái phải tự cập nhật đúng đời
        # mình, không lẫn sang drawer khác đang mở.
        drawer.regenerate_requested.connect(
            lambda: self._start_suggest_worker(question_text, context_text, drawer)
        )
        drawer.translate_requested.connect(
            lambda edited_text: self._start_translate_worker(
                question_text, context_text, edited_text, source_lang, drawer
            )
        )

        self._start_suggest_worker(question_text, context_text, drawer)

    def _start_suggest_worker(self, question_text: str, context_text: str, drawer: SuggestionDrawer) -> None:
        drawer.set_loading()
        native_lang = self._current_native_lang
        # 🔒 MỚI (Vòng 9, CONTRACTS.md Mục 18) — đọc trên main thread (chỉ
        # đọc 1 str), truyền vào closure, cùng quy ước với native_lang ở
        # trên -- KHÔNG đọc self._current_meeting_context từ bên trong
        # action() (đang chạy ở thread khác lúc đó).
        meeting_context = self._current_meeting_context

        def action() -> str:
            provider = create_provider()  # instance riêng cho thread này (xem ai_worker.py)
            return provider.suggest_answer(
                question_text, context_text, native_lang, meeting_context=meeting_context
            )

        worker = OneShotAIWorker(action)
        worker.succeeded.connect(drawer.set_answer)
        worker.failed.connect(drawer.set_error)
        self._register_worker(worker)
        worker.start()

    def _start_translate_worker(
        self, question_text: str, context_text: str, edited_text: str,
        target_lang: str, drawer: SuggestionDrawer,
    ) -> None:
        drawer.set_translating()
        native_lang = self._current_native_lang
        meeting_id = self._current_meeting_id  # đọc trên main thread, an toàn (chỉ đọc 1 int)

        def action() -> str:
            provider = create_provider()
            # context_text ở đây là vài câu transcript TRƯỚC câu hỏi (ngôn
            # ngữ người hỏi, vd "en"), KHÔNG cùng ngôn ngữ với edited_text
            # (native_lang, vd "vi") -- vẫn hữu ích: giúp model biết đúng
            # chủ đề/thuật ngữ đang dùng để chọn từ tiếng Anh nhất quán khi
            # dịch câu trả lời sang, dù khác ngôn ngữ với context.
            translated = provider.translate(
                edited_text, source_lang=native_lang, target_lang=target_lang,
                context_text=context_text,
            )
            self._persist_ai_assist(
                meeting_id=meeting_id, kind="suggest_answer", source_text=question_text,
                ai_output=edited_text, final_text=translated, target_lang=target_lang,
            )
            return translated

        worker = OneShotAIWorker(action)
        worker.succeeded.connect(drawer.show_readback)
        worker.failed.connect(drawer.set_error)
        self._register_worker(worker)
        worker.start()

    @staticmethod
    def _persist_ai_assist(
        meeting_id: int | None, kind: str, source_text: str,
        final_text: str, target_lang: str, ai_output: str | None = None,
    ) -> None:
        """Lưu 1 lần AI hỗ trợ vào DB (Phase 2 Bước 3/3) — gọi từ TRONG
        action() của OneShotAIWorker, nên đang chạy ĐÚNG trên thread đó. Tự
        mở 1 `MeetingStore` riêng (CONTRACTS.md Mục 3: mỗi thread tự mở
        connection riêng, không share), tự đóng ngay sau khi ghi xong qua
        context manager — KHÔNG giữ connection mở lâu dài ở thread này
        (thread chỉ sống trong đúng 1 lần hành động, không như AudioWorker).

        Lỗi lưu DB (StorageError) KHÔNG được làm mất kết quả dịch đã có —
        chỉ log-bỏ-qua, người dùng vẫn thấy/dùng được bản dịch ngay trong
        dialog, chỉ là không lưu lại lịch sử lần này.
        """
        if meeting_id is None:
            return
        try:
            with MeetingStore(_DEFAULT_DB_PATH) as store:
                store.add_ai_assist(
                    meeting_id=meeting_id, kind=kind, source_text=source_text,
                    ai_output=ai_output, final_text=final_text, target_lang=target_lang,
                )
        except StorageError:
            pass

    def _register_worker(self, worker: OneShotAIWorker) -> None:
        """Giữ tham chiếu Python tới worker đang chạy (tránh bị garbage-
        collect giữa chừng) + tự dọn khỏi list khi xong, dù thành công hay lỗi."""
        self._ai_workers.append(worker)

        def _cleanup() -> None:
            worker.wait()  # đảm bảo OS thread join hẳn trước khi drop tham chiếu (xem _on_worker_finished)
            if worker in self._ai_workers:
                self._ai_workers.remove(worker)

        worker.finished.connect(_cleanup)

    # -- "Tôi muốn hỏi": chiều ngược lại, người dùng tự soạn câu hỏi -------

    def _on_ask_question_clicked(self) -> None:
        default_target_lang = self._guess_other_party_lang()
        if self._ask_question_dialog is None:
            dialog = AskQuestionDialog(default_target_lang=default_target_lang, parent=self)
            dialog.translate_requested.connect(
                lambda text, target_lang: self._start_ask_translate_worker(text, target_lang, dialog)
            )
            self._ask_question_dialog = dialog
        else:
            # Dialog tái dùng (Mục 34) -- vẫn làm mới lại "đoán ngôn ngữ đối
            # phương" mỗi lần mở, vì đây là suy đoán phụ thuộc transcript
            # gần nhất, có thể đã đổi từ lần mở dialog trước.
            self._ask_question_dialog.set_default_target_lang(default_target_lang)
        self._ask_question_dialog.show()
        self._ask_question_dialog.raise_()
        self._ask_question_dialog.activateWindow()

    def _guess_other_party_lang(self) -> str:
        """Đoán ngôn ngữ đối phương đang dùng = ngôn ngữ KHÁC tiếng mẹ đẻ
        người dùng được phát hiện gần đây nhất trong transcript. Fallback
        "en" nếu chưa có dữ liệu (vd vừa bắt đầu họp, chưa ai nói gì)."""
        for lang in reversed(self._recent_source_langs):
            if lang and lang != self._current_native_lang:
                return lang
        return "en"

    def _start_ask_translate_worker(self, text: str, target_lang: str, dialog: AskQuestionDialog) -> None:
        native_lang = self._current_native_lang
        meeting_id = self._current_meeting_id
        context_text = "\n".join(self._recent_originals[-_CONTEXT_HISTORY_SIZE:])

        def action() -> str:
            provider = create_provider()
            translated = provider.translate(
                text, source_lang=native_lang, target_lang=target_lang,
                context_text=context_text,
            )
            self._persist_ai_assist(
                meeting_id=meeting_id, kind="ask_question", source_text=text,
                ai_output=None, final_text=translated, target_lang=target_lang,
            )
            return translated

        worker = OneShotAIWorker(action)
        worker.succeeded.connect(dialog.show_readback)
        worker.failed.connect(dialog.set_error)
        self._register_worker(worker)
        worker.start()

    # -- Phase 3 Bước 3/4: "Xem báo cáo" (đã có cache + regenerate + export) --
    # -- Phase 3 Bước 4/4 (F13): "Lịch sử" -- mở báo cáo cho BẤT KỲ meeting_id,
    #    không chỉ phiên đang chạy trong session hiện tại (xem CONTRACTS.md Mục 13).

    def _on_report_clicked(self) -> None:
        meeting_id = self._current_meeting_id
        if meeting_id is None:
            return  # phòng vệ -- nút chỉ enable khi có meeting_id, không nên xảy ra
        self._open_report_for_meeting(meeting_id, self._current_native_lang)

    def _on_history_clicked(self) -> None:
        # 🔒 SỬA (bugfix sau phản hồi test thật) -- TRƯỚC ĐÂY dùng thẳng
        # `self._current_meeting_id` để báo cho dialog Lịch sử biết phiên
        # nào "đang ghi âm cần khoá không cho xoá". SAI: `_current_meeting_id`
        # KHÔNG được reset về None trong `_on_worker_finished()` (cố ý, để
        # nút "📄 Xem báo cáo" vẫn dùng được ngay sau khi bấm "Kết thúc họp"
        # -- xem comment dòng 375). Hệ quả: phiên VỪA kết thúc vẫn bị
        # `_MeetingRow` coi là `is_protected=True` mãi mãi (cho tới khi bắt
        # đầu phiên ghi mới) -- checkbox của nó bị khoá, "Chọn tất cả" bỏ
        # qua nó, xoá "tất cả" không xoá được phiên mới nhất, và vì DB vẫn
        # còn ÍT NHẤT 1 dòng nên `sqlite_sequence` không bao giờ được reset
        # (xem `MeetingStore.delete_meetings()`) -- lỗi thật người dùng báo
        # lại đúng khớp cơ chế này.
        #
        # SỬA: chỉ coi là "đang ghi, cần khoá" khi có `self._worker` SỐNG
        # THẬT (AudioWorker) -- đúng tín hiệu "đang ghi", khác với
        # "_current_meeting_id vẫn còn nhớ phiên gần nhất để Xem báo cáo".
        # `self._worker` được set None ngay trong `_on_worker_finished()`
        # (dòng 950) nên tại thời điểm này nó phản ánh đúng trạng thái.
        protected_meeting_id = self._current_meeting_id if self._worker is not None else None
        if self._history_dialog is None:
            dialog = MeetingHistoryDialog(
                _DEFAULT_DB_PATH, current_meeting_id=protected_meeting_id, parent=self,
            )
            dialog.report_requested.connect(self._open_report_for_meeting)
            self._history_dialog = dialog
        else:
            # 🔒 MỚI (Mục 34) -- dialog tái dùng: phiên "đang ghi" có thể đã
            # đổi (vd đã dừng ghi/bắt đầu phiên mới) từ lần mở trước --
            # refresh() vừa cập nhật lại phiên "được bảo vệ" vừa tải lại
            # danh sách mới nhất (id/báo cáo có thể vừa được thêm/xoá).
            self._history_dialog.refresh(protected_meeting_id)
        self._history_dialog.show()
        self._history_dialog.raise_()
        self._history_dialog.activateWindow()

    def _on_settings_clicked(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(parent=self)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_help_clicked(self) -> None:
        # 🔒 MỚI (Mục 37) -- singleton, cùng pattern với _on_settings_clicked
        # ở trên. Dialog TĨNH (xem docstring HelpDialog), không cần refresh().
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(parent=self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    # -- "Hỏi AI": chat tự do đa lượt (CONTRACTS.md Mục 21) -----------------

    def _on_chat_clicked(self) -> None:
        if self._chat_dialog is None:
            self._chat_dialog = ChatDialog(parent=self)
            self._chat_dialog.message_sent.connect(self._on_chat_message_sent)
        self._chat_dialog.show()
        self._chat_dialog.raise_()
        self._chat_dialog.activateWindow()

    def _on_chat_message_sent(self) -> None:
        dialog = self._chat_dialog
        if dialog is None:
            return  # phòng vệ — signal chỉ emit từ dialog đang tồn tại
        # Đọc trên MAIN THREAD (xem docstring snapshot_messages()) rồi
        # truyền bản sao vào closure — cùng quy ước với native_lang/
        # meeting_context ở _start_suggest_worker().
        messages = dialog.snapshot_messages()
        native_lang = self._current_native_lang

        def action() -> str:
            provider = create_provider()  # instance riêng cho thread này (xem ai_worker.py)
            return provider.chat(messages, native_lang)

        worker = OneShotAIWorker(action)
        worker.succeeded.connect(dialog.set_answer)
        worker.failed.connect(dialog.set_error)
        self._register_worker(worker)
        worker.start()

    def _open_report_for_meeting(self, meeting_id: int, native_lang: str) -> None:
        """🔒 MỚI (F13) -- tách ra từ `_on_report_clicked()` cũ để dùng
        CHUNG cho cả 2 nguồn: (a) phiên họp ĐANG chạy trong session hiện tại
        (qua `_on_report_clicked()`, `native_lang` = `self._current_native_lang`
        -- đúng ngôn ngữ đang chọn trên combo box), và (b) phiên họp CŨ mở từ
        `MeetingHistoryDialog` (`native_lang` lấy từ CHÍNH `meetings.user_native_lang`
        đã lưu của phiên đó, KHÔNG dùng `self._current_native_lang` -- 2 giá
        trị này có thể KHÁC nhau, vd người dùng đổi ngôn ngữ mẹ đẻ giữa các
        lần dùng app, hoặc đang xem lịch sử mà không có phiên nào đang chạy).
        """
        # 🔒 MỚI (Mục 34) -- chặn mở TRÙNG cửa sổ báo cáo của ĐÚNG 1 phiên
        # họp (vd nhấn đúp nút "Xem báo cáo", hoặc bấm "Xem báo cáo" trong
        # Lịch sử 2 lần liên tiếp cho cùng 1 dòng): nếu đã có dialog đang mở
        # cho `meeting_id` này, chỉ raise/activate lại nó, KHÔNG gọi lại
        # AI/tạo report mới (tránh tốn API call vô ích + tránh nhấp nháy nội
        # dung đang hiển thị). Xem báo cáo của 2 phiên KHÁC NHAU vẫn mở 2
        # cửa sổ riêng biệt bình thường -- đó không phải "trùng".
        existing = self._report_dialogs.get(meeting_id)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return

        dialog = ReportDialog(meeting_id, parent=self)
        dialog._native_lang_for_export = native_lang  # xem _on_export_requested()
        dialog.retry_requested.connect(
            lambda: self._start_report_worker(meeting_id, dialog, force_regenerate=False, native_lang=native_lang)
        )
        dialog.regenerate_requested.connect(
            lambda: self._start_report_worker(meeting_id, dialog, force_regenerate=True, native_lang=native_lang)
        )
        dialog.action_item_toggled.connect(
            lambda index, done: self._on_action_item_toggled(meeting_id, index, done, dialog)
        )
        dialog.export_requested.connect(lambda fmt: self._on_export_requested(fmt, dialog))
        self._report_dialogs[meeting_id] = dialog
        dialog.finished.connect(lambda _result, mid=meeting_id: self._report_dialogs.pop(mid, None))
        dialog.show()
        self._start_report_worker(meeting_id, dialog, force_regenerate=False, native_lang=native_lang)

    def _start_report_worker(
        self, meeting_id: int, dialog: ReportDialog, force_regenerate: bool, native_lang: str,
    ) -> None:
        """Mở/làm mới báo cáo.

        `force_regenerate=False` (mở dialog lần đầu / bấm "Thử lại"): ưu
        tiên đọc `meeting_reports` đã lưu (KHÔNG gọi AI lại — tránh tốn
        quota free-tier + chậm vô ích khi nội dung transcript không đổi từ
        lần tổng hợp trước). Chỉ gọi `summarize()` khi CHƯA từng có báo cáo
        lưu cho meeting_id này.

        `force_regenerate=True` (bấm "🔄 Tạo báo cáo mới"): bỏ qua cache,
        luôn gọi `summarize()` mới — dùng khi người dùng biết transcript đã
        cập nhật thêm (vd đang xem báo cáo giữa lúc cuộc họp còn tiếp diễn)
        hoặc muốn 1 bản tổng hợp khác.

        `native_lang`: 🔒 SỬA (CONTRACTS.md Mục 13) -- trước đây đọc TRỰC
        TIẾP `self._current_native_lang` qua closure, SAI khi mở báo cáo
        của 1 phiên họp CŨ (từ Lịch sử) có ngôn ngữ mẹ đẻ KHÁC với lựa chọn
        hiện tại trên combo box -- nay PHẢI truyền rõ từ nơi gọi (xem
        `_open_report_for_meeting()`).

        Luôn trả về `ReportRecord` (KHÔNG phải `SummaryResult` thô) cho
        `dialog.set_result()` — xem lý do tách 2 kiểu dữ liệu ở docstring
        đầu report_view.py."""
        dialog.set_loading()

        def action() -> ReportRecord:
            with MeetingStore(_DEFAULT_DB_PATH) as store:
                if not force_regenerate:
                    cached = store.get_report(meeting_id)
                    if cached is not None:
                        return cached
                transcript_text = build_transcript_text(store, meeting_id)
            if not transcript_text:
                raise ProviderError(
                    "Phiên họp này chưa có nội dung transcript nào được ghi — "
                    "chưa thể tổng hợp báo cáo."
                )
            provider = create_provider()  # instance riêng cho thread này (xem ai_worker.py)
            result: SummaryResult = provider.summarize(transcript_text, native_lang)
            with MeetingStore(_DEFAULT_DB_PATH) as store:
                return store.save_report(
                    meeting_id, overview=result.overview,
                    decisions=result.decisions, action_items=result.action_items,
                )

        worker = OneShotAIWorker(action)
        worker.succeeded.connect(dialog.set_result)
        worker.failed.connect(dialog.set_error)
        self._register_worker(worker)
        worker.start()

    def _on_action_item_toggled(
        self, meeting_id: int, index: int, done: bool, dialog: ReportDialog,
    ) -> None:
        """Lưu trạng thái tick checkbox NGAY khi người dùng bấm.

        ⚠️ Gọi `MeetingStore` TRỰC TIẾP trên main thread — NGOẠI LỆ CÓ Ý so
        với quy ước threading chung (xem docstring `set_action_item_done()`
        trong storage/db.py để biết lý do đầy đủ): đây không phải lệnh AI,
        chỉ 1 UPDATE SQLite cực nhỏ, không đáng tạo thêm 1 OneShotAIWorker
        riêng cho mỗi lần tick."""
        try:
            with MeetingStore(_DEFAULT_DB_PATH) as store:
                store.set_action_item_done(meeting_id, index, done)
        except StorageError as exc:
            # Không revert lại UI -- checkbox người dùng vừa bấm vẫn đúng Ý
            # ĐỊNH của họ, chỉ là chưa lưu được; báo lỗi nhẹ để họ biết cần
            # thử lại (vd bấm "Tạo báo cáo mới" để đồng bộ lại), KHÔNG che
            # mất nội dung báo cáo đang xem.
            dialog.set_export_status(f"Không lưu được trạng thái tick: {exc}", is_error=True)

    def _on_export_requested(self, file_format: str, dialog: ReportDialog) -> None:
        report = dialog._last_report
        if report is None:
            return  # phòng vệ -- nút xuất chỉ hiện sau khi đã có report thành công
        meeting_id = dialog._meeting_id
        # 🔒 SỬA (CONTRACTS.md Mục 13) -- trước đây dùng self._current_native_lang,
        # SAI khi export báo cáo của 1 phiên họp CŨ mở từ Lịch sử (xem
        # _open_report_for_meeting()) -- nay đọc đúng ngôn ngữ của CHÍNH
        # phiên họp đang export, đã gắn vào dialog lúc tạo.
        native_lang = getattr(dialog, "_native_lang_for_export", self._current_native_lang)
        native_lang_label = next(
            (label for code, label in _NATIVE_LANG_OPTIONS if code == native_lang),
            native_lang,
        )

        default_name = f"bao_cao_phien_hop_{meeting_id}.{file_format}"
        filter_str = "Word (*.docx)" if file_format == "docx" else "PDF (*.pdf)"
        path, _selected_filter = QFileDialog.getSaveFileName(dialog, "Lưu báo cáo", default_name, filter_str)
        if not path:
            return  # người dùng bấm Hủy trên hộp thoại lưu file

        try:
            if file_format == "docx":
                report_export.export_to_docx(report, meeting_id, native_lang_label, path)
            else:
                report_export.export_to_pdf(report, meeting_id, native_lang_label, path)
        except ReportExportError as exc:
            dialog.set_export_status(f"Xuất file lỗi: {exc}", is_error=True)
            return
        dialog.set_export_status(f"Đã lưu file tại: {path}", is_error=False)

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            # Gọi wait() tường minh dù signal `finished` đã báo xong -- đây
            # là khuyến nghị chính thức của Qt để đảm bảo OS thread đã JOIN
            # HẲN trước khi Python drop tham chiếu cuối (self._worker = None
            # ở dưới) và để QThread bị garbage-collect. Thiếu bước này có
            # rủi ro hiếm gặp "QThread: Destroyed while thread still
            # running" (phát hiện qua chạy lại test nhiều lần, flaky ~25%).
            self._worker.wait()
        self._banner.setVisible(False)
        self._start_button.setEnabled(True)
        self._stop_button.setEnabled(False)
        self._ask_question_button.setEnabled(False)
        if self._current_meeting_id is not None:
            if self._last_error_in_session:
                # KHÔNG ghi đè mất lỗi -- bug thật phát hiện qua test: trước
                # đây message lỗi (vd "chỉ hỗ trợ Windows") bị thay ngay bằng
                # "Đã kết thúc phiên họp" khiến người dùng tưởng mọi thứ ổn.
                self._set_status(
                    f"Đã kết thúc phiên họp #{self._current_meeting_id} — "
                    f"CÓ LỖI xảy ra trong lúc ghi: {self._last_error_in_session}",
                    is_error=True,
                )
            else:
                self._set_status(f"Đã kết thúc phiên họp #{self._current_meeting_id}.", is_error=False)
        self._worker = None

    def _set_status(self, text: str, is_error: bool) -> None:
        self._status_label.setText(text)
        self._status_label.setProperty("isError", is_error)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    def closeEvent(self, event) -> None:  # noqa: N802 - tên hàm theo Qt convention
        """Đảm bảo dừng worker thread đúng cách khi đóng cửa sổ giữa lúc
        đang ghi -- tránh thread bị kill nửa chừng, mất nốt đoạn cuối/segment.
        Phase 2: cũng đợi các OneShotAIWorker (suggest_answer/translate) còn
        đang chạy, tránh Qt cảnh báo "QThread destroyed while still running"."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(3000)
        for worker in list(self._ai_workers):
            worker.wait(3000)
        super().closeEvent(event)
