"""
ui/chat_dialog.py
------------------
🔒 MỚI (CONTRACTS.md Mục 21) — hỏi-đáp tự do đa lượt (multi-turn) với AI,
dùng kiến thức nội tại của model (KHÔNG tra cứu web thật — xem quyết định
chốt đầy đủ ở CONTRACTS.md Mục 21). Tái dùng ĐÚNG pattern
`SuggestionDrawer` (QDialog không-modal, `QTextEdit` + `QPushButton`) —
KHÔNG thêm thư viện UI nào, đúng tinh thần "rất nhẹ" đã thảo luận.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class ChatDialog(QDialog):
    """Không-modal (show(), không exec()), cùng pattern với SuggestionDrawer/
    AskQuestionDialog.

    Tự giữ `self._history` (lịch sử hội thoại cho `AIProvider.chat()`) —
    KHÁC `SuggestionDrawer` (không giữ state đa lượt). `MainWindow` giữ
    ĐÚNG 1 instance của dialog này (xem CONTRACTS.md Mục 21) nên lịch sử
    được giữ liên tục suốt phiên làm việc, không mất khi đóng/mở lại.
    """

    message_sent = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("💬 Hỏi AI")
        self.resize(480, 560)

        self._history: list[dict] = []

        layout = QVBoxLayout(self)

        disclaimer = QLabel(
            "AI trả lời bằng kiến thức có sẵn, KHÔNG tra cứu web/tin tức "
            "mới — kiểm tra lại số liệu/sự kiện gần đây trước khi dùng."
        )
        disclaimer.setObjectName("BubbleTimestamp")  # tái dùng style nhạt có sẵn
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        self._conversation_view = QTextEdit()
        # Cùng fix font với suggestion_drawer.py/ask_question_dialog.py —
        # xem ghi chú đầy đủ ở suggestion_drawer.py (QSS font-family không
        # đáng tin cậy với QTextEdit + dấu tiếng Việt trên nhiều bản Qt).
        self._conversation_view.setFont(QFont("Segoe UI", 11))
        self._conversation_view.setReadOnly(True)
        self._conversation_view.setPlaceholderText("Bắt đầu cuộc trò chuyện với AI...")
        layout.addWidget(self._conversation_view, stretch=1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        input_row = QHBoxLayout()
        self._input_edit = QTextEdit()
        self._input_edit.setFont(QFont("Segoe UI", 11))
        self._input_edit.setPlaceholderText("Nhập câu hỏi... (Enter để xuống dòng)")
        self._input_edit.setFixedHeight(72)
        input_row.addWidget(self._input_edit, stretch=1)

        self._send_button = QPushButton("Gửi")
        self._send_button.setObjectName("PrimaryButton")
        self._send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._send_button)
        layout.addLayout(input_row)

    # -- gửi tin nhắn --------------------------------------------------

    def _on_send_clicked(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text:
            return
        self._history.append({"role": "user", "content": text})
        self._append_line("Bạn", text)
        self._input_edit.clear()
        self.set_loading()
        self.message_sent.emit()

    def snapshot_messages(self) -> list[dict]:
        """Trả BẢN SAO lịch sử hội thoại hiện tại — gọi từ MAIN THREAD
        ngay lúc kết nối worker (cùng quy ước snapshot context_text/
        meeting_context ở main_window.py), KHÔNG để worker thread đọc
        trực tiếp `self._history` đang có thể bị UI thread sửa cùng lúc."""
        return [dict(m) for m in self._history]

    # -- các state hiển thị, gọi từ MainWindow theo tiến trình xử lý ----

    def set_loading(self) -> None:
        self._send_button.setEnabled(False)
        self._input_edit.setEnabled(False)
        self._status_label.setText("Đang trả lời...")
        self._set_status_error(False)

    def set_answer(self, text: str) -> None:
        self._history.append({"role": "assistant", "content": text})
        self._append_line("AI", text)
        self._send_button.setEnabled(True)
        self._input_edit.setEnabled(True)
        self._status_label.setText("")
        self._input_edit.setFocus()

    def set_error(self, message: str) -> None:
        # KHÔNG append vào self._history — lượt trả lời lỗi này chưa từng
        # thật sự xảy ra, giữ lịch sử sạch để lần gửi lại (thử lại) không
        # gửi kèm 1 "câu trả lời rỗng" giả vào ngữ cảnh cho model.
        self._send_button.setEnabled(True)
        self._input_edit.setEnabled(True)
        self._status_label.setText(message)
        self._set_status_error(True)

    def _set_status_error(self, is_error: bool) -> None:
        self._status_label.setProperty("isError", is_error)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    def _append_line(self, speaker: str, text: str) -> None:
        cursor = self._conversation_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._conversation_view.toPlainText():
            cursor.insertBlock()
            cursor.insertBlock()
        escaped = html.escape(text).replace("\n", "<br>")
        cursor.insertHtml(f"<b>{html.escape(speaker)}:</b><br>{escaped}")
        self._conversation_view.setTextCursor(cursor)
        self._conversation_view.ensureCursorVisible()
