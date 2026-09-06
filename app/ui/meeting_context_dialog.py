"""
ui/meeting_context_dialog.py
------------------------------
🔒 MỚI (Vòng 9 — xem CONTRACTS.md Mục 18) — hộp thoại "Bối cảnh cuộc họp",
hiện ra NGAY KHI người dùng bấm "Bắt đầu ghi", TRƯỚC khi `AudioWorker` thật
sự khởi động. Cho phép người dùng mô tả trước bối cảnh của phiên họp/phỏng
vấn/trò chơi... (ai nói với ai, trong hoàn cảnh nào, mục đích gì) để
`suggest_answer()` ("Nhờ AI trả lời") gợi ý sát tình huống hơn — xem
`AIProvider.suggest_answer()` tham số `meeting_context` (MỚI).

Khác với `context_text` đã có từ Phase 2 (vài câu transcript gần nhất, tự
động, KHÔNG cần người dùng làm gì): đây là 1 khối văn bản TĨNH, người dùng
CHỦ ĐỘNG cung cấp 1 lần trước khi ghi, không đổi trong suốt phiên.

2 cách nhập, DÙNG ĐƯỢC CẢ HAI CÙNG LÚC (theo đúng yêu cầu gốc — không bắt
buộc chọn 1 trong 2):
    1. Gõ tay trực tiếp vào ô mô tả.
    2. Bấm "Tải tệp lên" — chọn 1 file .txt/.md (ưu tiên V1, xem CONTRACTS.md
       Mục 18 lý do CHƯA hỗ trợ .docx/.pdf/.doc ở bản này), nội dung file
       được CHÈN THÊM vào cuối ô mô tả (không ghi đè), để người dùng vẫn có
       thể tự gõ thêm/sửa lại sau khi tải — vd dán nguyên văn CV/JD rồi tự
       thêm 1 dòng ghi chú ngắn bên dưới.

Modal (dùng `exec()`, KHÁC với SuggestionDrawer/AskQuestionDialog — 2 cái đó
show() không-modal vì phải để transcript phía sau tiếp tục chạy). Ở đây
KHÔNG có AudioWorker nào đang chạy phía sau lúc dialog này mở (dialog hiện
ra TRƯỚC khi AudioWorker được tạo) nên chặn màn hình chính không sao,
không có rủi ro treo audio loopback như ai_worker.py đã cảnh báo.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

# 🔒 MỚI (CONTRACTS.md Mục 38) -- "Tự động" PHẢI là lựa chọn ĐẦU TIÊN/mặc
# định (userData="") -- giữ NGUYÊN hành vi cũ (model tự đoán ngôn ngữ) cho
# bất kỳ ai không chủ động đổi dropdown này. Danh sách ngôn ngữ dùng lại
# ĐÚNG các mã đã hỗ trợ ở _NATIVE_LANG_OPTIONS (main_window.py) + "Khác" để
# không hứa hỗ trợ ngôn ngữ chưa có tên hiển thị/lưới an toàn script riêng.
_SOURCE_LANGUAGE_HINT_OPTIONS = [
    ("", "🌐 Tự động (không ép ngôn ngữ — như trước đây)"),
    ("vi", "Tiếng Việt"), ("en", "English"), ("zh", "中文"),
    ("ja", "日本語"), ("ko", "한국어"),
]

# 🔒 Ưu tiên V1 (CONTRACTS.md Mục 18): CHỈ .txt/.md — python-docx đã có sẵn
# trong requirements (dùng cho export) nên .docx RẺ để thêm sau, nhưng CHƯA
# làm ở Vòng 9 này để giữ phạm vi nhỏ, đúng tinh thần "nhẹ, không cài thêm
# gì". .doc (Word 97-2003 nhị phân cũ) và .pdf CHỦ Ý chưa hỗ trợ — xem
# CONTRACTS.md Mục 18 lý do chi phí thư viện.
_SUPPORTED_FILE_FILTER = "Văn bản (*.txt *.md)"
_MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB — phòng vệ chọn nhầm file rất lớn


class MeetingContextDialog(QDialog):
    """Modal — gọi `exec()`, đọc `context_text()` sau khi trả về `Accepted`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bối cảnh cuộc họp (tuỳ chọn)")
        self.resize(560, 480)
        self.setModal(True)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Mô tả trước bối cảnh cuộc trò chuyện sắp diễn ra để AI gợi ý "
            "trả lời sát tình huống hơn — không bắt buộc, có thể bỏ qua."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        tips = QLabel(
            "Gợi ý nên mô tả: người nói và người nghe là ai (vai trò, quan "
            "hệ), bối cảnh diễn ra ở đâu/trong tình huống gì (phỏng vấn "
            "xin việc, họp công việc, trò chơi, gặp gỡ xã giao...), và mục "
            "đích của cuộc trò chuyện là gì."
        )
        tips.setWordWrap(True)
        tips.setObjectName("BubbleTimestamp")  # tái dùng style chữ nhạt có sẵn
        layout.addWidget(tips)

        # 🔒 MỚI (CONTRACTS.md Mục 38) -- "Ngôn ngữ nguồn dự kiến", khác hẳn
        # ô mô tả bối cảnh bên dưới: đây là HINT kỹ thuật gửi thẳng cho
        # Whisper (tham số `language`) để giảm hallucination "nhảy ngôn
        # ngữ" khi audio có tạp âm/nhạc nền/hiệu ứng âm thanh (vd phim
        # hành động, game, video có nhạc). Đặt Ở TRÊN ô mô tả (độc lập,
        # không phụ thuộc bối cảnh gõ tay) vì đây là lựa chọn ĐƠN GIẢN,
        # người dùng thường biết ngay ngôn ngữ chính của audio sắp ghi.
        lang_hint_row = QHBoxLayout()
        lang_hint_label = QLabel("Ngôn ngữ nguồn dự kiến của audio:")
        lang_hint_row.addWidget(lang_hint_label)
        self._lang_hint_combo = QComboBox()
        for code, label in _SOURCE_LANGUAGE_HINT_OPTIONS:
            self._lang_hint_combo.addItem(label, userData=code)
        self._lang_hint_combo.setToolTip(
            "Chọn ĐÚNG ngôn ngữ chính của audio sắp ghi (vd video/phim chủ "
            "yếu tiếng Nhật) để giảm việc AI tự nhận nhầm sang ngôn ngữ "
            "khác khi gặp tạp âm/nhạc nền/hiệu ứng âm thanh. Nếu cuộc họp "
            "có NHIỀU ngôn ngữ xen kẽ, để 'Tự động' như trước đây."
        )
        lang_hint_row.addWidget(self._lang_hint_combo, stretch=1)
        layout.addLayout(lang_hint_row)

        self._context_edit = QTextEdit()
        # Cùng fix font tiếng Việt đã áp dụng ở suggestion_drawer.py/
        # ask_question_dialog.py — xem ghi chú đầy đủ ở suggestion_drawer.py.
        self._context_edit.setFont(QFont("Segoe UI", 11))
        self._context_edit.setPlaceholderText(
            "Ví dụ: Đây là buổi phỏng vấn xin việc vị trí Backend Developer. "
            "Tôi là ứng viên, người phỏng vấn là trưởng nhóm kỹ thuật. Họ có "
            "thể hỏi về kinh nghiệm làm việc, dự án cũ, và kỹ năng kỹ thuật."
        )
        layout.addWidget(self._context_edit, stretch=1)

        file_row = QHBoxLayout()
        self._file_button = QPushButton("📄 Tải tệp lên (.txt/.md)")
        self._file_button.setToolTip(
            "Chọn 1 file .txt hoặc .md (vd CV, JD, mô tả kịch bản) — nội "
            "dung sẽ được chèn vào cuối ô mô tả bên trên, bạn vẫn sửa/thêm "
            "tay được sau khi tải."
        )
        self._file_button.clicked.connect(self._on_load_file_clicked)
        file_row.addWidget(self._file_button)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        button_row = QHBoxLayout()
        self._skip_button = QPushButton("Huỷ")
        self._skip_button.clicked.connect(self.reject)
        button_row.addWidget(self._skip_button)
        button_row.addStretch(1)

        self._start_button = QPushButton("Bắt đầu ghi")
        self._start_button.setObjectName("PrimaryButton")
        self._start_button.clicked.connect(self.accept)
        button_row.addWidget(self._start_button)
        layout.addLayout(button_row)

    def _on_load_file_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Chọn file bối cảnh", "", _SUPPORTED_FILE_FILTER
        )
        if not path_str:
            return  # người dùng bấm Huỷ trong hộp thoại chọn file

        path = Path(path_str)
        try:
            size = path.stat().st_size
        except OSError as exc:
            self._show_file_error(f"Không đọc được thông tin file: {exc}")
            return

        if size > _MAX_FILE_SIZE_BYTES:
            self._show_file_error(
                f"File quá lớn ({size // 1024} KB) — vui lòng chọn file dưới "
                f"{_MAX_FILE_SIZE_BYTES // 1024 // 1024}MB (bối cảnh chỉ cần "
                f"vài đoạn mô tả, không cần file lớn)."
            )
            return

        try:
            # encoding="utf-8-sig" tự bỏ BOM nếu file .txt được lưu từ
            # Notepad Windows (mặc định thường kèm BOM UTF-8) -- tránh 3
            # ký tự lạ "\ufeff" chèn vào đầu nội dung.
            file_content = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            self._show_file_error(f"Không đọc được nội dung file: {exc}")
            return

        file_content = file_content.strip()
        if not file_content:
            self._show_file_error("File này không có nội dung văn bản.")
            return

        current = self._context_edit.toPlainText()
        if current.strip():
            merged = f"{current}\n\n[Nội dung từ file {path.name}]\n{file_content}"
        else:
            merged = file_content
        self._context_edit.setPlainText(merged)
        self._status_label.setProperty("isError", False)
        self._status_label.setText(f"Đã chèn nội dung từ {path.name}.")

    def _show_file_error(self, message: str) -> None:
        # QMessageBox thay vì chỉ _status_label -- lỗi đọc file (vd file bị
        # xoá giữa chừng, sai encoding nặng) đáng chú ý hơn lỗi trạng thái
        # AI thông thường, không nên chỉ là 1 dòng chữ nhỏ dễ bị bỏ qua.
        QMessageBox.warning(self, "Không tải được file", message)

    def context_text(self) -> str:
        """Gọi SAU khi `exec()` trả về `QDialog.Accepted`. Trả về chuỗi đã
        `strip()` — chuỗi rỗng nghĩa là người dùng bỏ qua bối cảnh."""
        return self._context_edit.toPlainText().strip()

    def language_hint(self) -> str:
        """🔒 MỚI (CONTRACTS.md Mục 38). Gọi SAU khi `exec()` trả về
        `QDialog.Accepted`. Trả về mã ISO 639-1 đã chọn, hoặc "" nếu đang
        chọn "Tự động" (mặc định, giữ nguyên hành vi cũ)."""
        return self._lang_hint_combo.currentData() or ""
