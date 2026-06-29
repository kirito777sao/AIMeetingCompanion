"""
ui/transcript_bubble.py
------------------------
1 "bubble" = 1 segment transcript đã xử lý xong (PROJECT_SPEC.md mục 10.4).

Phase 1: CHỈ hiển thị, không có nút hành động nào (nút "Nhờ AI trả lời" là
F5, thuộc Phase 2 -- cố tình CHƯA thêm ở đây để không lấn sang Phase 2).
Bubble có chip nhỏ "?" để báo đây là câu hỏi (chuẩn bị sẵn cho Phase 2 dùng,
nhưng ở Phase 1 chip này chỉ mang tính thông tin, không bấm được).
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# Ngưỡng confidence dưới mức này thì coi là "độ tin cậy thấp" -- hiển thị
# viền cảnh báo (PROJECT_SPEC.md mục 10.4). Giá trị tạm 0.5, CHƯA được
# verify bằng dữ liệu Groq Whisper thật (xem cảnh báo trong groq_provider.py
# về _estimate_confidence) -- có thể cần điều chỉnh sau khi chạy thật.
LOW_CONFIDENCE_THRESHOLD = 0.5

_LANGUAGE_LABELS = {"en": "EN", "vi": "VI", "zh": "ZH"}


def _language_label(code: str) -> str:
    if not code:
        return "?"
    return _LANGUAGE_LABELS.get(code, code.upper())


class TranscriptBubble(QWidget):
    """Widget hiển thị 1 segment: timestamp + chip ngôn ngữ + text gốc, và
    (nếu có) dòng bản dịch thụt vào bên dưới.

    ⚠️ Đã sửa 1 bug phát hiện từ test thật trên Windows: ban đầu cảnh báo
    "độ tin cậy thấp" chỉ dựa vào dynamic property `setProperty("lowConfidence",
    ...)` + selector QSS `#TranscriptBubble[lowConfidence="true"]` -- nhưng
    rule này nằm SAU rule `border: 1px solid ...` (set cả border-left) trong
    theme.qss, và việc Qt style-sheet engine có polish lại đúng lúc hay
    không (đặc biệt khi setProperty() được gọi TRƯỚC khi widget hiện ra lần
    đầu) không đủ tin cậy để kiểm chứng chỉ bằng đọc code -- người dùng xác
    nhận thực tế KHÔNG thấy cảnh báo hiện ra dù DB có segment confidence
    0.46 (< ngưỡng 0.5). Sửa bằng 2 lớp, không phụ thuộc QSS cascade nữa:
    (1) set style trực tiếp lên đúng instance này (luôn thắng, không qua
    selector), (2) thêm hẳn 1 chip CHỮ "Độ tin cậy thấp" -- không chỉ dựa
    vào màu viền tinh tế dễ bị bỏ qua. Đã verify bằng test thật trên Windows
    (cảnh báo 39%/33% hiện đúng).

    ⚠️ Đã đổi sau phản hồi test thật: nút "Nhờ AI trả lời" ban đầu chỉ hiện
    khi `is_question=True` (heuristic dấu "?"). Test thật cho thấy heuristic
    này miss nhiều câu hỏi thật trong hội thoại nói nhanh/liền mạch (VAD có
    thể cắt câu hỏi vắt qua 2 segment). Quyết định (đã thống nhất với người
    dùng): nút hiện ở MỌI bubble, không gate theo is_question nữa — không
    tốn thêm API call nào cho pipeline chính (suggest_answer() vẫn chỉ gọi
    khi bấm nút), bền hơn với hội thoại thực tế. Chip "Câu hỏi" (is_question)
    vẫn giữ làm gợi ý hiển thị MIỄN PHÍ (không cần API), không còn liên quan
    gì tới việc hiện/ẩn nút nữa.
    """

    # Phase 2 (F5): emit (question_text, context_text, source_lang) khi
    # người dùng bấm nút "Nhờ AI trả lời". context_text được TRUYỀN VÀO lúc
    # tạo bubble (snapshot tại đúng thời điểm đó), KHÔNG tính lại lúc bấm
    # nút -- để ngữ cảnh luôn đúng với những gì đã nói TRƯỚC câu hỏi này, dù
    # người dùng bấm nút muộn sau khi transcript đã trôi xa thêm.
    answer_requested = Signal(str, str, str)

    def __init__(
        self,
        original_text: str,
        source_lang: str,
        confidence: float,
        translated_text: str | None = None,
        is_question: bool = False,
        context_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TranscriptBubble")
        self._original_text = original_text
        self._source_lang = source_lang
        self._context_text = context_text
        is_low_confidence = 0.0 < confidence < LOW_CONFIDENCE_THRESHOLD

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        ts_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        ts_label.setObjectName("BubbleTimestamp")
        header.addWidget(ts_label)

        lang_chip = QLabel(_language_label(source_lang))
        lang_chip.setObjectName("LanguageChip")
        header.addWidget(lang_chip)

        if is_question:
            q_chip = QLabel("Câu hỏi")
            q_chip.setObjectName("QuestionChip")
            header.addWidget(q_chip)

        if is_low_confidence:
            warn_chip = QLabel(f"⚠ Độ tin cậy thấp ({confidence:.0%})")
            warn_chip.setObjectName("WarningChip")
            warn_chip.setToolTip(
                "Model nhận diện giọng nói không chắc chắn với đoạn này — "
                "có thể do nói nhanh/nhỏ/lẫn tiếng ồn. Nên đọc lại bản gốc "
                "kỹ hơn bình thường."
            )
            header.addWidget(warn_chip)

        header.addStretch(1)
        outer.addLayout(header)

        original_label = QLabel(original_text)
        original_label.setObjectName("OriginalText")
        original_label.setWordWrap(True)
        original_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(original_label)

        if translated_text:
            translated_label = QLabel(translated_text)
            translated_label.setObjectName("TranslatedText")
            translated_label.setWordWrap(True)
            translated_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            outer.addWidget(translated_label)

        ask_ai_button = QPushButton("💬 Nhờ AI trả lời")
        ask_ai_button.setObjectName("AskAiButton")
        ask_ai_button.setToolTip(
            "Soạn gợi ý phản hồi cho điều vừa nói — dùng được cho cả câu hỏi "
            "rõ, câu hỏi bị cắt cụt, hay chỉ là 1 câu cần nối lời."
        )
        ask_ai_button.clicked.connect(self._on_ask_ai_clicked)
        button_row = QHBoxLayout()
        button_row.addStretch(1)  # đẩy nút về bên phải, không chiếm hết chiều ngang
        button_row.addWidget(ask_ai_button)
        outer.addLayout(button_row)

        # Set TRỰC TIẾP lên instance này (luôn thắng style toàn cục, không
        # phụ thuộc property-selector/cascade trong theme.qss) -- xem lý do
        # ở docstring class.
        if is_low_confidence:
            self.setStyleSheet(
                "QWidget#TranscriptBubble {"
                " border: 1px solid #232938;"
                " border-left: 3px solid #F5A623;"
                " border-radius: 12px;"
                " background-color: #131722;"
                " }"
            )

    def _on_ask_ai_clicked(self) -> None:
        self.answer_requested.emit(self._original_text, self._context_text, self._source_lang)

    @classmethod
    def from_event(cls, event, context_text: str = "", parent: QWidget | None = None) -> "TranscriptBubble":
        """Tiện ích tạo bubble trực tiếp từ `app.pipeline.TranscriptEvent`,
        để main_window.py không phải tự bóc từng field. `context_text` do
        MainWindow tự tính (vài dòng transcript TRƯỚC event này) và truyền
        vào ngay lúc tạo — xem giải thích ở docstring class."""
        return cls(
            original_text=event.original_text,
            source_lang=event.source_lang,
            confidence=event.confidence,
            translated_text=event.translated_text,
            is_question=event.is_question,
            context_text=context_text,
            parent=parent,
        )
