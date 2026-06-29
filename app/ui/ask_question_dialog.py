"""
ui/ask_question_dialog.py
---------------------------
Phase 2 (mở rộng theo phản hồi test thật): cuộc họp không phải 1 chiều —
người dùng cũng cần CHỦ ĐỘNG hỏi/đặt vấn đề ngược lại với phía bên kia, chứ
không chỉ ngồi đợi bị hỏi rồi mới nhờ AI gợi ý trả lời. Đây gần như là chiều
NGƯỢC LẠI của SuggestionDrawer: ở đây người dùng đã biết rõ mình muốn nói gì
(tự nhập bằng tiếng mẹ đẻ), nên KHÔNG cần bước AI soạn nội dung (suggest_answer)
— chỉ cần dịch sang ngôn ngữ đối phương rồi đọc lên, đơn giản hơn
SuggestionDrawer 1 bước.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

_LANG_OPTIONS = [("en", "English"), ("vi", "Tiếng Việt"), ("zh", "中文")]


class AskQuestionDialog(QDialog):
    """Không-modal (show(), không exec()), cùng pattern với SuggestionDrawer."""

    translate_requested = Signal(str, str)  # (nội dung gốc, mã ngôn ngữ đích)

    def __init__(self, default_target_lang: str = "en", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tôi muốn hỏi")
        self.resize(480, 360)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Nhập câu bạn muốn hỏi/đặt vấn đề (bằng tiếng mẹ đẻ):"))
        self._input_edit = QTextEdit()
        # Cùng fix với suggestion_drawer.py -- xem ghi chú đầy đủ ở đó.
        self._input_edit.setFont(QFont("Segoe UI", 11))
        self._input_edit.setPlaceholderText("Ví dụ: Anh/chị có thể nói rõ hơn về deadline dự án không?")
        layout.addWidget(self._input_edit, stretch=1)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Dịch sang ngôn ngữ đối phương đang dùng:"))
        self._lang_combo = QComboBox()
        for code, label in _LANG_OPTIONS:
            self._lang_combo.addItem(label, userData=code)
        idx = self._lang_combo.findData(default_target_lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch(1)
        layout.addLayout(lang_row)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        self._translate_button = QPushButton("Dịch & Sẵn sàng hỏi")
        self._translate_button.setObjectName("PrimaryButton")
        self._translate_button.clicked.connect(self._on_translate_clicked)
        layout.addWidget(self._translate_button)

        self._readback_label = QLabel("")
        self._readback_label.setObjectName("OriginalText")
        self._readback_label.setWordWrap(True)
        self._readback_label.setStyleSheet("font-size: 20px; padding: 12px;")
        self._readback_label.setVisible(False)
        layout.addWidget(self._readback_label)

    def _on_translate_clicked(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text:
            self.set_error("Bạn chưa nhập nội dung cần hỏi.")
            return
        target_lang = self._lang_combo.currentData()
        self.set_translating()
        self.translate_requested.emit(text, target_lang)

    # -- state hiển thị, gọi từ MainWindow -----------------------------

    def set_translating(self) -> None:
        self._translate_button.setEnabled(False)
        self._status_label.setText("Đang dịch...")
        self._status_label.setProperty("isError", False)
        self._readback_label.setVisible(False)

    def set_error(self, message: str) -> None:
        self._translate_button.setEnabled(True)
        self._status_label.setText(message)
        self._status_label.setProperty("isError", True)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    def show_readback(self, translated_text: str) -> None:
        self._translate_button.setEnabled(True)
        self._readback_label.setText(translated_text)
        self._readback_label.setVisible(True)
        self._status_label.setText("Đọc đoạn dưới để hỏi:")
        self._status_label.setProperty("isError", False)
