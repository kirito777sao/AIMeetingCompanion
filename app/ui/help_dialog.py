"""
ui/help_dialog.py
------------------
🔒 MỚI (Mục 37 — người dùng CHỦ ĐỘNG yêu cầu, phản hồi test thật) — dialog
"❓ Trợ giúp" liệt kê 7 tổ hợp phím tắt Alt+chữ cái đã có sẵn (Mục 22,
`ui/main_window.py`) + luồng dùng cơ bản của app theo đúng thứ tự thao tác
thật (ghi -> hỏi/dịch trong lúc họp -> kết thúc -> xem lại).

Bối cảnh phát hiện (phản hồi test thật của người dùng): các nút bấm/tổ hợp
phím ĐÃ hoạt động đúng như mô tả trong CONTRACTS.md/TASKS.md, nhưng KHÔNG
có chỗ nào trong CHÍNH APP nói cho người dùng MỚI biết những tổ hợp đó tồn
tại — thông tin trước đây chỉ nằm trong tooltip từng nút riêng lẻ (phải rê
chuột qua từng nút mới thấy) và trong tài liệu dev (CONTRACTS.md/README),
người dùng cuối (bản `.exe`, không đọc code) không tiếp cận được. Dialog
này gom lại 1 CHỖ DUY NHẤT, mở được ngay từ màn hình chính.

Thiết kế: dialog TĨNH (không đọc/ghi DB, không gọi AI, không có state cần
refresh() khi tái mở) — do đó KHÔNG cần `refresh()`/`showEvent()` như
`SettingsDialog`/`MeetingHistoryDialog` (Mục 34): nội dung cố định, đúng
tinh thần đơn giản hoá đã áp dụng nhiều nơi khác trong dự án. Singleton
show()/raise()/activateWindow() qua `MainWindow._help_dialog`, CÙNG pattern
tái dùng với `_settings_dialog` (không tạo cửa sổ mới nếu bấm nhiều lần).

Không-modal (show(), không exec()) — cùng pattern với mọi dialog phụ khác
trong app (SettingsDialog, MeetingHistoryDialog, AskQuestionDialog).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# 🔒 MỚI (Mục 37) -- PHẢI khớp CHÍNH XÁC 7 tổ hợp đã gán ở `main_window.py`
# (Mục 22). Đây là bảng liệt kê CHO NGƯỜI DÙNG ĐỌC, không phải nguồn định
# nghĩa mnemonic thật (nguồn thật vẫn là ký tự `&` trong text từng
# QPushButton ở main_window.py) -- nếu sau này đổi mnemonic ở đó, PHẢI sửa
# lại bảng này theo, không có cơ chế tự đồng bộ 2 chỗ.
_SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Alt+B", "Bắt đầu ghi — bắt đầu 1 phiên họp mới."),
    ("Alt+K", "Kết thúc họp — dừng ghi âm phiên đang chạy."),
    ("Alt+T", "❓ Tôi muốn hỏi — soạn câu hỏi, dịch sang ngôn ngữ đối phương."),
    ("Alt+X", "📄 Xem báo cáo — tóm tắt/quyết định/việc cần làm của phiên hiện tại."),
    ("Alt+L", "🕓 Lịch sử — xem/tìm/xoá lại các phiên họp đã ghi trước đây."),
    ("Alt+A", "💬 Hỏi AI — hỏi-đáp tự do, không liên quan phiên họp đang ghi."),
    ("Alt+C", "⚙️ Cài đặt — nhập/đổi API key, chọn provider AI."),
)

_USAGE_STEPS: tuple[str, ...] = (
    "1. Chọn ngôn ngữ mẹ đẻ của bạn ở góc trên, rồi bấm \"Bắt đầu ghi\" (Alt+B) "
    "để bắt đầu 1 phiên họp mới.",
    "2. Trong lúc họp, transcript song ngữ hiện tự động theo thời gian thực. "
    "Câu nào là câu hỏi sẽ có nút \"Nhờ AI trả lời\" riêng ngay bên cạnh.",
    "3. Muốn CHỦ ĐỘNG hỏi/phát biểu bằng tiếng mẹ đẻ và dịch sang ngôn ngữ "
    "đối phương ngay lập tức, dùng \"Tôi muốn hỏi\" (Alt+T).",
    "4. Xong việc, bấm \"Kết thúc họp\" (Alt+K). Ngay sau đó có thể bấm luôn "
    "\"Xem báo cáo\" (Alt+X) để AI tổng hợp tóm tắt/quyết định/việc cần làm.",
    "5. Muốn xem/tìm lại các phiên họp CŨ (kể cả sau khi tắt app, mở lại), "
    "dùng \"Lịch sử\" (Alt+L) — cũng là nơi xoá vĩnh viễn các phiên không cần nữa.",
    "6. \"Hỏi AI\" (Alt+A) dùng được BẤT KỲ lúc nào, không cần đang ghi âm — "
    "hỏi-đáp tự do không liên quan tới phiên họp.",
    "7. Lần đầu dùng, hoặc khi cần đổi API key/provider AI (Groq/OpenAI/Gemini), "
    "vào \"Cài đặt\" (Alt+C).",
)


class HelpDialog(QDialog):
    """Không-modal, singleton (tái dùng qua `MainWindow._help_dialog`)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trợ giúp")
        self.resize(520, 560)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Toàn bộ thao tác chính đều bấm được bằng CHUỘT hoặc bằng BÀN "
            "PHÍM (giữ Alt + chữ cái gạch chân trên tên nút)."
        )
        intro.setWordWrap(True)
        intro.setObjectName("StatusLabel")
        layout.addWidget(intro)

        shortcuts_title = QLabel("Phím tắt (giữ Alt):")
        shortcuts_title.setObjectName("OriginalText")
        layout.addWidget(shortcuts_title)

        # Scroll area vì nội dung (7 phím tắt + 7 bước dùng) có thể dài hơn
        # chiều cao dialog trên màn hình nhỏ.
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        for key, desc in _SHORTCUTS:
            row = QLabel(f"<b>{key}</b> — {desc}")
            row.setWordWrap(True)
            content_layout.addWidget(row)

        usage_title = QLabel("Quy trình dùng cơ bản:")
        usage_title.setObjectName("OriginalText")
        content_layout.addWidget(usage_title)

        for step in _USAGE_STEPS:
            step_label = QLabel(step)
            step_label.setWordWrap(True)
            content_layout.addWidget(step_label)

        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area, stretch=1)

        close_button = QPushButton("Đóng")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
