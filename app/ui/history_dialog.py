"""
ui/history_dialog.py
---------------------
🔒 MỚI (F13 — PROJECT_SPEC.md mục 4, Phase 3 Bước 4/4, xem CONTRACTS.md
Mục 13) — màn hình "Lịch sử phiên họp".

🔒 MỞ RỘNG (Vòng 10, CONTRACTS.md Mục 24) — chọn (1 hoặc nhiều) + XOÁ VĨNH
VIỄN phiên họp cũ. Yêu cầu người dùng đã chốt: (a) chọn được nhiều dòng cùng
lúc để dọn bớt dữ liệu/giảm nặng DB theo thời gian, (b) trước khi xoá PHẢI
cảnh báo + khuyến nghị xuất báo cáo ra máy cá nhân trước, và người dùng phải
XÁC NHẬN đã kiểm tra/xuất xong mới cho xoá, (c) xoá là xoá CỨNG — KHÔNG có
thùng rác/cờ xoá mềm/khôi phục. Xem `MeetingStore.delete_meetings()`
(storage/db.py) cho phần xoá dữ liệu thật; dialog này CHỈ lo phần chọn +
cảnh báo + xác nhận, KHÔNG tự ý xoá gì nếu chưa qua bước xác nhận.

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
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
    selection_changed = Signal(int, bool)  # (meeting_id, checked) -- Vòng 10

    def __init__(
        self, summary: MeetingSummary, is_protected: bool = False, parent=None,
    ) -> None:
        """`is_protected`: 🔒 MỚI (Vòng 10) -- True khi đây CHÍNH LÀ phiên
        họp đang ghi âm trong session hiện tại (`MainWindow._current_meeting_id`
        lúc mở dialog). Phiên đang ghi KHÔNG được phép chọn để xoá -- xoá 1
        phiên đang có worker audio còn sống sẽ khiến `add_segment()` sau đó
        vi phạm FOREIGN KEY (meeting_id không còn tồn tại). `pipeline.py`
        đã bọc `try/except StorageError` quanh `add_segment()` nên KHÔNG
        crash app, nhưng vẫn mất dữ liệu ghi âm đang diễn ra một cách âm
        thầm -- disable checkbox ngay từ đầu an toàn hơn nhiều so với chỉ
        dựa vào lớp phòng vệ đó. ⚠️ Giới hạn đã biết: `is_protected` chỉ
        đúng tại THỜI ĐIỂM mở dialog (dialog không-modal, không tự cập nhật
        nếu người dùng bấm "Dừng ghi"/bắt đầu phiên mới trong lúc dialog
        này vẫn đang mở) -- chấp nhận cho V1, cùng tinh thần đơn giản hoá
        đã áp dụng ở nhiều chỗ khác trong CONTRACTS.md (vd Mục 13.3 giờ UTC
        không tự đổi timezone)."""
        super().__init__(parent)
        self.setObjectName("HistoryRow")
        self._summary = summary
        self._is_protected = is_protected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        top_row = QHBoxLayout()

        self._select_checkbox = QCheckBox()
        self._select_checkbox.setObjectName("HistorySelectCheckbox")
        if is_protected:
            self._select_checkbox.setEnabled(False)
            self._select_checkbox.setToolTip(
                "Phiên đang ghi âm — không thể chọn để xoá lúc này."
            )
        else:
            self._select_checkbox.toggled.connect(
                lambda checked: self.selection_changed.emit(summary.id, checked)
            )
        top_row.addWidget(self._select_checkbox)

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

    # -- API cho MeetingHistoryDialog (Vòng 10 — chọn/xoá) ------------------

    @property
    def meeting_id(self) -> int:
        return self._summary.id

    @property
    def is_selectable(self) -> bool:
        return not self._is_protected

    @property
    def has_report(self) -> bool:
        return self._summary.has_report

    def set_selected(self, checked: bool) -> None:
        """Dùng bởi nút "Chọn tất cả" -- không tác dụng gì với dòng bị
        `is_protected` (checkbox đã disable, `setChecked()` trên checkbox
        disabled không emit `toggled` một cách bất ngờ nên vẫn an toàn, nhưng
        chặn tường minh ở đây cho rõ ý)."""
        if not self._is_protected:
            self._select_checkbox.setChecked(checked)


class MeetingHistoryDialog(QDialog):
    """Không-modal (show(), không exec()) — cùng pattern với các dialog
    khác trong app (AskQuestionDialog, ReportDialog, SuggestionDrawer)."""

    report_requested = Signal(int, str)  # (meeting_id, user_native_lang)

    def __init__(
        self, db_path: str, current_meeting_id: Optional[int] = None, parent=None,
    ) -> None:
        """`current_meeting_id`: 🔒 MỚI (Vòng 10) -- id phiên họp ĐANG ghi
        âm tại thời điểm mở dialog (`MainWindow._current_meeting_id`), hoặc
        `None` nếu không có phiên nào đang chạy. Dùng để disable checkbox
        chọn xoá cho ĐÚNG dòng đó (xem docstring `_MeetingRow.__init__`) --
        `None` mặc định giữ nguyên hành vi cũ cho chỗ gọi nào chưa truyền
        tham số này (không phá vỡ tương thích ngược)."""
        super().__init__(parent)
        self._db_path = db_path
        self._current_meeting_id = current_meeting_id
        self._selected_ids: set[int] = set()
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

        # 🔒 MỚI (Vòng 10) -- hàng công cụ chọn/xoá hàng loạt.
        select_row = QHBoxLayout()
        self._select_all_checkbox = QCheckBox("Chọn tất cả")
        self._select_all_checkbox.setObjectName("HistorySelectAllCheckbox")
        self._select_all_checkbox.toggled.connect(self._on_select_all_toggled)
        select_row.addWidget(self._select_all_checkbox)
        select_row.addStretch(1)
        self._delete_button = QPushButton("🗑️ Xoá đã chọn")
        # "DangerButton" -- tái dùng style đỏ/cảnh báo đã có sẵn trong
        # theme.qss (nút "⏹ Dừng ghi") thay vì tạo object name/rule QSS mới,
        # đúng hành động phá huỷ-không-thể-hoàn-tác cần nổi bật cùng ngôn
        # ngữ hình ảnh với nút dừng ghi.
        self._delete_button.setObjectName("DangerButton")
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        select_row.addWidget(self._delete_button)
        layout.addLayout(select_row)

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

        # summary.id -> _MeetingRow đang hiển thị, dùng để tra has_report
        # khi soạn cảnh báo xoá (xem _on_delete_clicked) mà không cần query
        # DB lại lần nữa.
        self._rows_by_id: dict[int, _MeetingRow] = {}

        self._reload()

    def refresh(self, current_meeting_id: Optional[int]) -> None:
        """🔒 MỚI (Mục 34) -- gọi khi `MainWindow` TÁI SỬ DỤNG (singleton)
        dialog này thay vì tạo instance mới: cập nhật lại phiên "đang ghi âm
        cần bảo vệ" (có thể đã đổi từ lần mở trước, xem giới hạn đã biết ở
        CONTRACTS.md Mục 24.4) rồi tải lại danh sách mới nhất từ DB, giữ
        nguyên nội dung ô tìm kiếm hiện có (KHÔNG xoá query người dùng đang
        gõ dở)."""
        self._current_meeting_id = current_meeting_id
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

        # 🔒 MỚI (Vòng 10) -- reload luôn nghĩa là danh sách/id có thể đã
        # đổi (vd vừa xoá xong) -- reset lựa chọn cũ về rỗng, tránh giữ id
        # đã không còn tồn tại/không còn hiển thị trong _selected_ids.
        self._selected_ids.clear()
        self._rows_by_id = {}
        self._select_all_checkbox.blockSignals(True)
        self._select_all_checkbox.setChecked(False)
        self._select_all_checkbox.blockSignals(False)
        self._update_delete_button()

        for summary in results:
            is_protected = summary.id == self._current_meeting_id
            row = _MeetingRow(summary, is_protected=is_protected)
            row.report_clicked.connect(self.report_requested.emit)
            row.selection_changed.connect(self._on_row_selection_changed)
            self._rows_by_id[summary.id] = row
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    # -- Chọn/xoá hàng loạt (Vòng 10) ---------------------------------------

    def _on_row_selection_changed(self, meeting_id: int, checked: bool) -> None:
        if checked:
            self._selected_ids.add(meeting_id)
        else:
            self._selected_ids.discard(meeting_id)
        self._update_delete_button()

    def _on_select_all_toggled(self, checked: bool) -> None:
        for row in self._rows_by_id.values():
            row.set_selected(checked)
        # `set_selected()` bỏ qua dòng `is_protected` -- `_selected_ids` đã
        # tự đồng bộ đúng qua từng `selection_changed` emit ở trên, không
        # cần gán thủ công lại ở đây.

    def _update_delete_button(self) -> None:
        count = len(self._selected_ids)
        self._delete_button.setEnabled(count > 0)
        self._delete_button.setText(
            "🗑️ Xoá đã chọn" if count == 0 else f"🗑️ Xoá đã chọn ({count})"
        )

    def _on_delete_clicked(self) -> None:
        if not self._selected_ids:
            return  # phòng vệ -- nút chỉ enable khi có lựa chọn

        selected_ids = sorted(self._selected_ids)
        without_report = [
            mid for mid in selected_ids
            if mid in self._rows_by_id and not self._rows_by_id[mid].has_report
        ]

        warning_lines = [
            f"Bạn sắp XOÁ VĨNH VIỄN {len(selected_ids)} phiên họp đã chọn "
            "(toàn bộ transcript, gợi ý AI và báo cáo đi kèm).",
            "",
            "Việc xoá này KHÔNG THỂ khôi phục — không có thùng rác, không có "
            "cách lấy lại sau khi đã xoá.",
            "",
            "Khuyến nghị: hãy XUẤT báo cáo (.docx/.pdf) ra máy cá nhân và "
            "kiểm tra lại đầy đủ nội dung TRƯỚC KHI xoá.",
        ]
        if without_report:
            ids_text = ", ".join(f"#{mid}" for mid in without_report)
            warning_lines += [
                "",
                f"⚠️ Các phiên {ids_text} CHƯA có báo cáo nào được tạo — chắc "
                "chắn sẽ không thể xuất báo cáo cho các phiên này sau khi xoá.",
            ]

        confirm_box = QMessageBox(self)
        confirm_box.setIcon(QMessageBox.Warning)
        confirm_box.setWindowTitle("Xác nhận xoá vĩnh viễn")
        confirm_box.setText("\n".join(warning_lines))
        cancel_button = confirm_box.addButton("Huỷ", QMessageBox.RejectRole)
        confirm_button = confirm_box.addButton(
            "Tôi đã kiểm tra/xuất xong — XOÁ VĨNH VIỄN", QMessageBox.AcceptRole
        )
        confirm_box.setDefaultButton(cancel_button)  # an toàn: Enter/mặc định = Huỷ
        confirm_box.exec()

        if confirm_box.clickedButton() is not confirm_button:
            return

        try:
            with MeetingStore(self._db_path) as store:
                deleted_count = store.delete_meetings(selected_ids)
        except StorageError as exc:
            QMessageBox.critical(self, "Không xoá được", f"Đã xảy ra lỗi khi xoá: {exc}")
            return

        QMessageBox.information(
            self, "Đã xoá", f"Đã xoá vĩnh viễn {deleted_count} phiên họp.",
        )
        self._reload()
