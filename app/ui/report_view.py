"""
ui/report_view.py
-------------------
Phase 3 Bước 2/4 (F10-F11): màn hình hiện báo cáo cuộc họp.
Phase 3 Bước 3/4 (F11, MỚI): action items thành checkbox tick được
(PROJECT_SPEC.md Mục 10.4), nút "🔄 Tạo báo cáo mới" (bỏ cache, gọi lại
summarize() — tách riêng khỏi "Thử lại" vốn chỉ xuất hiện khi LỖI), 2 nút
xuất ".docx"/".pdf" (gọi app/report_export.py).

Quyết định thiết kế (Bước 2 — vẫn giữ):
- Hiện 3 mục TÁCH RIÊNG (Tóm tắt / Quyết định / Việc cần làm), mỗi mục có
  heading riêng.
- Dùng `QLabel` (wordWrap=True) cho Tóm tắt/Quyết định — widget ĐÃ XÁC NHẬN
  hiển thị đúng dấu tiếng Việt trong dự án này (xem transcript_bubble.py).
  `QCheckBox` (Qt built-in, không phải QTextEdit) dùng cho action items —
  KHÔNG cùng loại widget từng dính bug font (CONTRACTS.md Mục 4), nhưng vẫn
  set font "Segoe UI" trực tiếp cho chắc (cùng cách đã áp dụng ở
  suggestion_drawer.py/ask_question_dialog.py), không phụ thuộc QSS cascade.
- Không-modal (`show()`, không `exec()`).
- List rỗng hiện rõ "(Không có)" — KHÔNG hiện trống trơn.

Quyết định thiết kế MỚI (Bước 3/4):
- `set_result()` nhận `ReportRecord` (app/storage/db.py — ĐÃ LƯU, có
  `generated_at` + action items có `done`), KHÔNG còn nhận `SummaryResult`
  thô từ AIProvider (xem main_window.py — nơi gọi summarize() rồi
  `store.save_report()` để có ReportRecord trước khi đưa vào đây). Tách
  bạch tầng AI (SummaryResult, action_items: list[str], 🔒 đã chốt) khỏi
  tầng hiển thị/lưu trữ (ReportRecord, action_items: list[ActionItemRecord]
  có done) — KHÔNG đổi contract AIProvider chỉ vì UI cần thêm 1 cờ trạng
  thái không liên quan tới việc tổng hợp nội dung.
- Action item checkboxes REBUILD lại mỗi lần set_result() (số lượng/nội
  dung item đổi giữa các lần tổng hợp, không thể tái dùng widget cũ) —
  dùng 1 QVBoxLayout riêng (`_action_items_layout`) để add/clear dễ dàng,
  KHÔNG lồng trực tiếp vào `_content_layout` chung (nếu lồng chung, xoá
  đúng N widget action item cũ mỗi lần rebuild dễ lẫn với widget khác).
- Toggle 1 checkbox emit `action_item_toggled(index, done)` NGAY (main_window
  lưu vào DB ngay, không cần nút "Lưu" riêng — đúng tinh thần tick-là-lưu
  của 1 checklist thật).
- Nút xuất .docx/.pdf + "Tạo báo cáo mới" CHỈ hiện khi đã có kết quả thành
  công (ẩn lúc loading/lỗi) — xuất file dựa trên dữ liệu ĐANG hiện, xuất
  lúc chưa có gì sẵn không có ý nghĩa.
- `_export_status_label` TÁCH RIÊNG khỏi `_status_label` (dùng cho lỗi
  tổng hợp/rỗng transcript) — báo lỗi/thành công của HÀNH ĐỘNG XUẤT FILE
  không được làm mất nội dung báo cáo đang hiện (set_error() ẩn hết
  section, không phù hợp dùng lại cho lỗi xuất file).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _format_list_for_display(items: list[str]) -> str:
    """[] -> '(Không có)' (xác nhận thật không có gì, KHÔNG phải lỗi/rỗng
    do chưa tải). Ngược lại, mỗi phần tử 1 dòng bullet "•"."""
    if not items:
        return "(Không có)"
    return "\n".join(f"•  {item}" for item in items)


class ReportDialog(QDialog):
    """Không-modal, cùng pattern với SuggestionDrawer/AskQuestionDialog."""

    retry_requested = Signal()              # bấm "Thử lại" sau khi LỖI
    regenerate_requested = Signal()         # bấm "🔄 Tạo báo cáo mới" sau khi đã có kết quả
    action_item_toggled = Signal(int, bool)  # (index, done) — tick/bỏ tick 1 action item
    export_requested = Signal(str)          # "docx" | "pdf"

    def __init__(self, meeting_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._meeting_id = meeting_id
        self._last_report = None  # ReportRecord gần nhất hiện thành công — dùng khi export
        self.setWindowTitle(f"Báo cáo cuộc họp #{meeting_id}")
        self.resize(560, 700)

        outer = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("ReportScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(14)

        self._loading_label = QLabel("Đang tải báo cáo — có thể mất vài giây...")
        self._loading_label.setObjectName("BubbleTimestamp")
        self._loading_label.setWordWrap(True)
        self._content_layout.addWidget(self._loading_label)

        self._generated_at_label = QLabel("")
        self._generated_at_label.setObjectName("BubbleTimestamp")
        self._generated_at_label.setWordWrap(True)
        self._content_layout.addWidget(self._generated_at_label)

        self._overview_heading, self._overview_body = self._build_section("📝  Tóm tắt")
        self._decisions_heading, self._decisions_body = self._build_section("✅  Quyết định")

        # Action items: heading riêng + container layout riêng để rebuild
        # checkbox mỗi lần set_result() (xem docstring đầu file).
        self._action_heading = QLabel("📌  Việc cần làm")
        self._action_heading.setObjectName("ReportSectionHeading")
        self._content_layout.addWidget(self._action_heading)

        self._action_items_container = QWidget()
        self._action_items_layout = QVBoxLayout(self._action_items_container)
        self._action_items_layout.setContentsMargins(0, 0, 0, 0)
        self._action_items_layout.setSpacing(6)
        self._content_layout.addWidget(self._action_items_container)

        self._action_empty_label = QLabel("(Không có)")
        self._action_empty_label.setObjectName("OriginalText")
        self._action_empty_label.setVisible(False)
        self._content_layout.addWidget(self._action_empty_label)

        self._content_layout.addStretch(1)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area, stretch=1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.setWordWrap(True)
        outer.addWidget(self._status_label)

        self._export_status_label = QLabel("")
        self._export_status_label.setObjectName("StatusLabel")
        self._export_status_label.setWordWrap(True)
        outer.addWidget(self._export_status_label)

        button_row = QHBoxLayout()
        self._retry_button = QPushButton("Thử lại")
        self._retry_button.setObjectName("PrimaryButton")
        self._retry_button.setVisible(False)
        self._retry_button.clicked.connect(self._on_retry_clicked)
        button_row.addWidget(self._retry_button)

        self._regenerate_button = QPushButton("🔄 Tạo báo cáo mới")
        self._regenerate_button.setObjectName("AskAiButton")
        self._regenerate_button.setVisible(False)
        self._regenerate_button.setToolTip(
            "Bỏ báo cáo đã lưu, gọi AI tổng hợp lại từ đầu (action items sẽ "
            "về trạng thái chưa tick)."
        )
        self._regenerate_button.clicked.connect(self._on_regenerate_clicked)
        button_row.addWidget(self._regenerate_button)

        self._export_docx_button = QPushButton("💾 Xuất .docx")
        self._export_docx_button.setObjectName("AskAiButton")
        self._export_docx_button.setVisible(False)
        self._export_docx_button.clicked.connect(lambda: self.export_requested.emit("docx"))
        button_row.addWidget(self._export_docx_button)

        self._export_pdf_button = QPushButton("💾 Xuất .pdf")
        self._export_pdf_button.setObjectName("AskAiButton")
        self._export_pdf_button.setVisible(False)
        self._export_pdf_button.clicked.connect(lambda: self.export_requested.emit("pdf"))
        button_row.addWidget(self._export_pdf_button)

        button_row.addStretch(1)
        close_button = QPushButton("Đóng")
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)
        outer.addLayout(button_row)

        self._set_sections_visible(False)

    def _build_section(self, heading_text: str) -> tuple[QLabel, QLabel]:
        heading = QLabel(heading_text)
        heading.setObjectName("ReportSectionHeading")
        body = QLabel("")
        body.setObjectName("OriginalText")  # tái dùng style đã xác nhận hiện đúng dấu tiếng Việt
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._content_layout.addWidget(heading)
        self._content_layout.addWidget(body)
        return heading, body

    def _set_sections_visible(self, visible: bool) -> None:
        for widget in (
            self._generated_at_label,
            self._overview_heading, self._overview_body,
            self._decisions_heading, self._decisions_body,
            self._action_heading, self._action_items_container,
        ):
            widget.setVisible(visible)
        if not visible:
            self._action_empty_label.setVisible(False)

    def _clear_action_item_checkboxes(self) -> None:
        while self._action_items_layout.count():
            item = self._action_items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_action_items(self, action_items) -> None:  # action_items: list[ActionItemRecord]
        self._clear_action_item_checkboxes()
        if not action_items:
            self._action_empty_label.setVisible(True)
            self._action_items_container.setVisible(False)
            return
        self._action_empty_label.setVisible(False)
        self._action_items_container.setVisible(True)
        for index, item in enumerate(action_items):
            checkbox = QCheckBox(item.text)
            checkbox.setChecked(item.done)
            # Set font trực tiếp, KHÔNG phụ thuộc QSS cascade — cùng lý do
            # đã áp dụng ở suggestion_drawer.py (CONTRACTS.md Mục 4).
            checkbox.setFont(QFont("Segoe UI"))
            checkbox.setObjectName("ActionItemCheckbox")
            checkbox.toggled.connect(lambda done, idx=index: self.action_item_toggled.emit(idx, done))
            self._action_items_layout.addWidget(checkbox)

    # -- state hiển thị, gọi từ MainWindow theo tiến trình xử lý -----------

    def set_loading(self) -> None:
        self._loading_label.setText("Đang tải báo cáo — có thể mất vài giây...")
        self._loading_label.setVisible(True)
        self._set_sections_visible(False)
        self._retry_button.setVisible(False)
        self._regenerate_button.setVisible(False)
        self._export_docx_button.setVisible(False)
        self._export_pdf_button.setVisible(False)
        self._status_label.setText("")
        self._export_status_label.setText("")

    def set_result(self, report) -> None:  # report: ReportRecord — xem app/storage/db.py
        self._last_report = report
        self._loading_label.setVisible(False)
        self._retry_button.setVisible(False)
        self._regenerate_button.setVisible(True)
        self._export_docx_button.setVisible(True)
        self._export_pdf_button.setVisible(True)
        self._status_label.setText("")
        self._export_status_label.setText("")
        self._generated_at_label.setText(f"Tạo lúc (UTC): {report.generated_at}")
        self._overview_body.setText(report.overview or "(Không có)")
        self._decisions_body.setText(_format_list_for_display(report.decisions))
        self._rebuild_action_items(report.action_items)
        self._set_sections_visible(True)
        self._generated_at_label.setVisible(True)

    def set_error(self, message: str) -> None:
        self._last_report = None
        self._loading_label.setVisible(False)
        self._set_sections_visible(False)
        self._regenerate_button.setVisible(False)
        self._export_docx_button.setVisible(False)
        self._export_pdf_button.setVisible(False)
        self._status_label.setText(message)
        self._status_label.setProperty("isError", True)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._retry_button.setVisible(True)

    def set_export_status(self, message: str, is_error: bool) -> None:
        """Báo kết quả hành động XUẤT FILE — KHÔNG đụng tới `_status_label`/
        section nội dung báo cáo (xem docstring đầu file)."""
        self._export_status_label.setText(message)
        self._export_status_label.setProperty("isError", is_error)
        self._export_status_label.style().unpolish(self._export_status_label)
        self._export_status_label.style().polish(self._export_status_label)

    def _on_retry_clicked(self) -> None:
        self.set_loading()
        self.retry_requested.emit()

    def _on_regenerate_clicked(self) -> None:
        self.set_loading()
        self.regenerate_requested.emit()
