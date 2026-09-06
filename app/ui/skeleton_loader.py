"""
ui/skeleton_loader.py
----------------------
🔒 MỚI (Backlog "Skeleton loading cho dialog AI", xem TASKS.md) — thay
placeholder TEXT tĩnh ("Đang soạn gợi ý...", "Đang dịch...") bằng khung
xương (skeleton) có animation mờ-đậm nhẹ nhàng, tạo cảm giác "đang xử lý"
rõ ràng hơn 1 dòng chữ đứng yên — pattern phổ biến ở Facebook/LinkedIn/
YouTube khi tải nội dung.

PHẠM VI đã chốt (xem TASKS.md để biết lý do): chỉ áp dụng cho
`SuggestionDrawer` (ô "Đang soạn gợi ý...") và `AskQuestionDialog` (vùng
readback đang chờ dịch xong) — 2 nơi CHÍNH XÁC được nêu trong mô tả
backlog gốc. KHÔNG đụng `ChatDialog` ("Đang trả lời...") — khác cấu trúc
(nội dung là 1 dòng LOG nối tiếp trong QTextEdit, không phải 1 vùng nội
dung "sắp xuất hiện" độc lập như 2 dialog kia — nhét skeleton vào giữa
log hội thoại phức tạp hơn nhiều, không đáng để làm trong task nhỏ này).

Thiết kế TỐI GIẢN, không thêm thư viện nào ngoài PySide6 sẵn có:
- `SkeletonBar`: 1 thanh chữ nhật bo góc (QSS), animate ĐỘ MỜ (opacity)
  qua `QGraphicsOpacityEffect` + `QPropertyAnimation` — KHÔNG vẽ gradient
  di chuyển ngang phức tạp (rủi ro cao hơn, khó test hơn trong headless/
  offscreen mode) — animate opacity đơn giản vẫn tạo cảm giác "đang tải"
  rõ ràng, an toàn hơn để verify bằng test tự động.
- `SkeletonLoadingWidget`: xếp 3 `SkeletonBar` độ rộng khác nhau (giống 3
  dòng chữ ngắn dần) theo chiều dọc, mỗi thanh bắt đầu animation TRỄ hơn
  thanh trước 150ms (staggered) để tạo hiệu ứng "sóng" — nhấp nháy ĐỒNG
  loạt trông giả/rẻ tiền hơn animation so le.
- Tự start()/stop() animation qua showEvent()/hideEvent() — nơi gọi
  (`SuggestionDrawer`/`AskQuestionDialog`) chỉ cần `setVisible(True/False)`
  như các widget khác trong 2 file đó (vd `_readback_label`), KHÔNG cần
  nhớ gọi thêm start()/stop() thủ công — giảm rủi ro quên gọi.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

# Độ rộng 3 thanh (px) -- giống 3 dòng chữ ngắn dần, vừa khung dialog
# 480px (xem SuggestionDrawer/AskQuestionDialog.resize(480, ...)).
_BAR_WIDTHS = (260, 220, 140)
_BAR_HEIGHT = 14
_STAGGER_MS = 150  # độ trễ bắt đầu animation giữa các thanh, tạo hiệu ứng sóng


class SkeletonBar(QWidget):
    """1 thanh khung xương, animate opacity 0.35↔0.85 liên tục (loop vô hạn)
    khi start(), đứng yên ở opacity thấp khi chưa start()/đã stop()."""

    def __init__(self, width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(width, _BAR_HEIGHT)
        self.setObjectName("SkeletonBar")
        # Style nhạt, khớp theme tối của app (xem style.qss) -- không đọc
        # file QSS ở đây để tránh phụ thuộc ngoài ý muốn, set trực tiếp.
        self.setStyleSheet(
            "#SkeletonBar { background-color: #3a3a3a; border-radius: 4px; }"
        )
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.35)
        self.setGraphicsEffect(self._opacity_effect)

        self._animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._animation.setDuration(1200)
        self._animation.setKeyValueAt(0.0, 0.35)
        self._animation.setKeyValueAt(0.5, 0.85)
        self._animation.setKeyValueAt(1.0, 0.35)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)  # lặp vô hạn tới khi stop()
        self._pending_start_timer: Optional[QTimer] = None

    def start(self, delay_ms: int = 0) -> None:
        """Bắt đầu animation, có thể trễ `delay_ms` (dùng để so le nhiều
        thanh — xem `SkeletonLoadingWidget`). Gọi lại khi đang chạy sẽ
        KHÔNG khởi động lại animation đang lặp -- an toàn khi showEvent()
        bị gọi nhiều lần."""
        if self._animation.state() == QPropertyAnimation.State.Running:
            return
        if delay_ms > 0:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._animation.start)
            timer.start(delay_ms)
            self._pending_start_timer = timer
        else:
            self._animation.start()

    def stop(self) -> None:
        if self._pending_start_timer is not None:
            self._pending_start_timer.stop()
            self._pending_start_timer = None
        self._animation.stop()
        self._opacity_effect.setOpacity(0.35)


class SkeletonLoadingWidget(QWidget):
    """3 `SkeletonBar` xếp dọc, độ rộng giảm dần, animation so le 150ms/thanh.

    Tự start() khi được show() (showEvent), tự stop() khi bị ẩn
    (hideEvent) -- nơi gọi chỉ cần `setVisible(True/False)` như mọi widget
    khác trong dialog, không cần quản lý animation thủ công.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SkeletonLoadingWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        self._bars = [SkeletonBar(width) for width in _BAR_WIDTHS]
        for bar in self._bars:
            layout.addWidget(bar)
        layout.addStretch(1)

    def start(self) -> None:
        for i, bar in enumerate(self._bars):
            bar.start(delay_ms=i * _STAGGER_MS)

    def stop(self) -> None:
        for bar in self._bars:
            bar.stop()

    def showEvent(self, event) -> None:  # noqa: N802 (tên hàm Qt override)
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.stop()
