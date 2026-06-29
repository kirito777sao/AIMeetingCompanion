"""
ui/history_dialog.py
---------------------
🔒 MỚI (F13 — PROJECT_SPEC.md mục 4, Phase 3 Bước 4/4, xem CONTRACTS.md
Mục 13) — màn hình "Lịch sử phiên họp".

Bối cảnh phát hiện (test thật, xem README.md Vòng 6): trước khi có dialog
này, nút "📄 Xem báo cáo" CHỈ hoạt động với phiên họp ĐANG/VỪA chạy trong
session app hiện tại (`MainWindow._current_meeting_id`) — đóng app, mở lại,
hoặc bắt đầu 1 phiên ghi MỚI, là MẤT HẲN khả năng xem lại báo cáo/transcript
của các phiên cũ, dù dữ liệu vẫn còn nguyên trong `meetings.db` (`MeetingStore`
đã có `list_meetings()` từ Phase 1, chỉ là chưa có UI nào gọi tới). Dialog
này lấp đúng lỗ hổng đó.

KHÔNG tự gọi AI (summarize) ở đây — chỉ liệt kê/tìm kiếm. Khi người dùng bấm
"Xem báo cáo" cho 1 phiên, dialog emit `report_requested(meeting_id,
user_native_lang)`, `MainWindow` tái dùng NGUYÊN VẸN luồng
`_open_report_for_meeting()` (đã có, dùng chung với phiên hiện tại) để mở
`ReportDialog` — không viết lại logic gọi AI/cache lần thứ 2.

Threading: mọi query DB ở đây chạy TRỰC TIẾP trên main thread (mở 1
`MeetingStore` riêng, dùng xong đóng ngay) — ĐÚNG tiền lệ đã có ở
`MainWindow._on_action_item_toggled()` (xem docstring `set_action_item_done()`
trong storage/db.py): đọc/tìm SQLite cục bộ là việc cực nhẹ, KHÔNG gọi
network/AI, không cần OneShotAIWorker riêng. Danh sách phiên họp của 1
người dùng cá nhân (PROJECT_SPEC.md mục 2: không phải SaaS nhiều người
dùng) thực tế chỉ vài chục–vài trăm dòng, không đáng lo hiệu năng.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.storage.db import MeetingSummary, MeetingStore, StorageError


def _format_dt(iso_str: Optional[str]) -> str:
    """ISO 8601 UTC (`_utcnow_iso()` ở storage/db.py) -> chuỗi dễ đọc.

    Cố tình GIỮ giờ UTC nguyên (KHÔNG tự đổi sang giờ máy người dùng) --
    đơn giản cho V1, tránh sai lệch nếu sau này đồng bộ dữ liệu giữa nhiều
    máy ở timezone khác nhau. ⚠️ Có thể gây khó hiểu nhẹ cho người dùng VN
    (giờ UTC lệch 7h so giờ VN) -- cân nhắc đổi nếu phản hồi test thật cho
    thấy gây nhầm lẫn thật.
    """
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d/%m/%Y %H:%M") + " UTC"
    except ValueError:
        return iso_str  # dữ liệu lạ -- hiện thô còn hơn crash


class _MeetingRow(QFrame):
    """1 dòng trong danh sách lịch sử."""

    report_clicked = Signal(int, str)  # (meeting_id, user_native_lang)

    def __init__(self, summary: MeetingSummary, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryRow")
        self._summary = summary

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        top_row = QHBoxLayout()
        status = "đang diễn ra" if summary.ended_at is None else _format_dt(summary.ended_at)
        title = QLabel(f"Phiên #{summary.id} — bắt đầu {_format_dt(summary.started_at)} ({status})")
        title.setObjectName("OriginalText")
        top_row.addWidget(title, stretch=1)

        if summary.has_report:
            badge = QLabel("✅ Đã có báo cáo")
            badge.setObjectName("StatusLabel")
            top_row.addWidget(badge)
        layout.addLayout(top_row)

        meta = QLabel(
            f"{summary.segment_count} đoạn hội thoại · tiếng mẹ đẻ: {summary.user_native_lang}"
        )
        meta.setObjectName("StatusLabel")
        layout.addWidget(meta)

        if summary.snippet:
            snippet_label = QLabel(f"… {summary.snippet} …")
            snippet_label.setWordWrap(True)
            snippet_label.setObjectName("TranslatedText")
            layout.addWidget(snippet_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        report_button = QPushButton("📄 Xem báo cáo")
        report_button.setObjectName("AskAiButton")
        report_button.clicked.connect(
            lambda: self.report_clicked.emit(summary.id, summary.user_native_lang)
        )
        button_row.addWidget(report_button)
        layout.addLayout(button_row)


class MeetingHistoryDialog(QDialog):
    """Không-modal (show(), không exec()) — cùng pattern với các dialog
    khác trong app (AskQuestionDialog, ReportDialog, SuggestionDrawer)."""

    report_requested = Signal(int, str)  # (meeting_id, user_native_lang)

    def __init__(self, db_path: str, parent=None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self.setWindowTitle("Lịch sử phiên họp")
        self.resize(560, 640)

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Tìm theo nội dung đã nói (transcript)...")
        self._search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self._search_edit, stretch=1)
        refresh_button = QPushButton("🔄")
        refresh_button.setToolTip("Làm mới danh sách")
        refresh_button.clicked.connect(self._reload)
        search_row.addWidget(refresh_button)
        layout.addLayout(search_row)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.addStretch(1)
        self._scroll_area.setWidget(self._list_container)
        layout.addWidget(self._scroll_area, stretch=1)

        self._reload()

    def _on_search_changed(self, _text: str) -> None:
        self._reload()

    def _reload(self) -> None:
        query = self._search_edit.text()
        try:
            with MeetingStore(self._db_path) as store:
                results = store.search_meetings(query)
        except StorageError as exc:
            self._status_label.setText(f"Không đọc được lịch sử: {exc}")
            self._status_label.setProperty("isError", True)
            self._status_label.style().unpolish(self._status_label)
            self._status_label.style().polish(self._status_label)
            return

        # Xoá toàn bộ row cũ (giữ lại addStretch ở cuối) trước khi vẽ lại.
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not results:
            self._status_label.setText(
                "Chưa có phiên họp nào." if not query.strip()
                else "Không tìm thấy phiên họp nào khớp."
            )
        else:
            self._status_label.setText(f"{len(results)} phiên họp.")
        self._status_label.setProperty("isError", False)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

        for summary in results:
            row = _MeetingRow(summary)
            row.report_clicked.connect(self.report_requested.emit)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
