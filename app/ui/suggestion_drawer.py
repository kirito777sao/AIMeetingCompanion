"""
ui/suggestion_drawer.py
------------------------
Phase 2 (F5-F7): panel hiện gợi ý trả lời do AI soạn, cho người dùng SỬA TRỰC
TIẾP trước khi dịch ngược — đây là bước an toàn bắt buộc đã nhấn mạnh từ
PROJECT_SPEC.md (không có chế độ "auto-send", người dùng luôn là người
quyết định cuối).

Đơn giản hoá so với mô tả "bottom sheet trượt lên" ở PROJECT_SPEC.md mục
10.4: dùng QDialog không-modal thay vì animation trượt — đúng tinh thần làm
đúng chức năng trước, polish animation sau nếu cần (tránh over-engineer ở
bước đầu của Phase 2).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.ui.skeleton_loader import SkeletonLoadingWidget


class SuggestionDrawer(QDialog):
    """Không-modal (show(), không exec()) để transcript phía sau vẫn tiếp
    tục cập nhật trong lúc panel này đang mở."""

    regenerate_requested = Signal()
    translate_requested = Signal(str)  # nội dung đã sửa, lúc bấm "Dịch & Sẵn sàng nói"

    def __init__(self, question_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nhờ AI trả lời")
        self.resize(480, 360)

        layout = QVBoxLayout(self)

        question_label = QLabel(f"Câu hỏi: {question_text}")
        question_label.setWordWrap(True)
        question_label.setObjectName("BubbleTimestamp")  # tái dùng style nhạt có sẵn
        layout.addWidget(question_label)

        layout.addWidget(QLabel("Gợi ý trả lời (sửa tự do trước khi dùng):"))
        self._answer_edit = QTextEdit()
        # ⚠️ Bug thật phát hiện qua test: chữ tiếng Việt mất dấu RIÊNG ở
        # QTextEdit này (đã xác nhận bằng cách đọc thẳng dữ liệu trong DB —
        # dữ liệu lưu ĐÚNG 100%, lỗi chỉ xảy ra lúc hiển thị). QSS
        # font-family cascade vào QTextEdit không đáng tin cậy ở nhiều
        # phiên bản Qt (QTextEdit dùng QTextDocument riêng, không luôn ăn
        # theo `font` của widget cha qua stylesheet) — set TRỰC TIẾP bằng
        # code để chắc chắn, không phụ thuộc QSS nữa.
        self._answer_edit.setFont(QFont("Segoe UI", 11))
        self._answer_edit.setReadOnly(True)
        self._answer_edit.setPlaceholderText("Đang soạn gợi ý...")
        layout.addWidget(self._answer_edit, stretch=1)

        # 🔒 MỚI (Backlog "Skeleton loading") -- hiện thay cho _answer_edit
        # TRONG lúc đang chờ AI soạn gợi ý (set_loading()), ẩn lại khi có
        # kết quả/lỗi. Cùng vị trí + cùng stretch=1 trong layout để không
        # đổi kích thước dialog lúc chuyển qua lại.
        self._skeleton = SkeletonLoadingWidget()
        self._skeleton.setVisible(False)
        layout.addWidget(self._skeleton, stretch=1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        button_row = QHBoxLayout()
        self._regenerate_button = QPushButton("Tạo lại")
        self._regenerate_button.clicked.connect(self.regenerate_requested.emit)
        button_row.addWidget(self._regenerate_button)

        self._translate_button = QPushButton("Dịch & Sẵn sàng nói")
        self._translate_button.setObjectName("PrimaryButton")
        self._translate_button.setEnabled(False)
        self._translate_button.clicked.connect(
            lambda: self.translate_requested.emit(self._answer_edit.toPlainText())
        )
        button_row.addWidget(self._translate_button)
        layout.addLayout(button_row)

        self._readback_label = QLabel("")
        self._readback_label.setObjectName("OriginalText")
        self._readback_label.setWordWrap(True)
        self._readback_label.setStyleSheet("font-size: 20px; padding: 12px;")
        self._readback_label.setVisible(False)
        layout.addWidget(self._readback_label)

    # -- các state hiển thị, gọi từ MainWindow theo tiến trình xử lý -------

    def set_loading(self) -> None:
        self._answer_edit.setReadOnly(True)
        self._answer_edit.clear()
        self._answer_edit.setPlaceholderText("Đang soạn gợi ý...")
        self._answer_edit.setVisible(False)  # 🔒 MỚI -- nhường chỗ cho skeleton
        self._skeleton.setVisible(True)
        self._translate_button.setEnabled(False)
        self._status_label.setText("")
        self._readback_label.setVisible(False)

    def set_answer(self, text: str) -> None:
        self._skeleton.setVisible(False)  # 🔒 MỚI
        self._answer_edit.setVisible(True)
        self._answer_edit.setReadOnly(False)
        self._answer_edit.setPlainText(text)
        self._translate_button.setEnabled(True)
        self._status_label.setText("")

    def set_error(self, message: str) -> None:
        self._skeleton.setVisible(False)  # 🔒 MỚI
        self._answer_edit.setVisible(True)
        self._status_label.setText(message)
        self._status_label.setProperty("isError", True)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._answer_edit.setReadOnly(False)  # vẫn cho sửa tay nếu lỗi lúc soạn

    def set_translating(self) -> None:
        self._translate_button.setEnabled(False)
        self._status_label.setText("Đang dịch...")
        self._status_label.setProperty("isError", False)

    def show_readback(self, translated_text: str) -> None:
        self._readback_label.setText(translated_text)
        self._readback_label.setVisible(True)
        self._status_label.setText("Đọc đoạn dưới để phản hồi:")
        self._translate_button.setEnabled(True)
