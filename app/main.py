"""
app/main.py
-----------
Entry point Phase 1. Chạy:

    python -m app.main

(Không chạy `python app/main.py` trực tiếp -- sẽ lỗi import `from app...`
vì khi đó Python không coi `app/` là 1 package nằm trong project root.)

🔒 SỬA (02/09/2026, CONTRACTS.md Mục 18.4) — TẮT `qt_material` MẶC ĐỊNH.
Đã bật thử ở Vòng 9 (18/08-đầu 09/2026) nhưng người dùng báo 2 vấn đề thật
sau khi dùng:
1. Dialog/cửa sổ mở lên đúng kích thước, sau ~1-2s TỰ NHẢY to hơn (nghi
   `qt_material` nạp font riêng bất đồng bộ, làm Qt tính lại kích thước
   widget theo font mới SAU lần vẽ đầu -- CHƯA verify được 100% nguyên
   nhân chính xác trong sandbox này, không có PySide6/màn hình thật để tái
   hiện, nhưng đây là hiện tượng có bằng chứng trong cộng đồng qt-material,
   xem CONTRACTS.md Mục 18.4).
2. Giao diện "lộn xộn" hơn TRƯỚC khi thêm `qt_material` — vì rất nhiều nút
   bấm/ô nhập trong dự án CHƯA từng được style riêng trong `theme.qss`
   (chỉ style những chỗ hay dùng nhất: PrimaryButton, DangerButton,
   AskAiButton) — trước Vòng 9, các chỗ đó đơn giản dùng nguyên style Qt
   mặc định (đồng nhất dù "mộc"). `qt_material` chỉ tô lại NHỮNG CHỖ ĐÓ
   (vì rule cụ thể theo object-name trong theme.qss vẫn thắng), tạo ra 2
   "ngôn ngữ thiết kế" khác nhau cùng lúc trên 1 màn hình (nút Material bo
   tròn/màu khác cạnh nút theme.qss thiết kế riêng) -- ĐÂY mới là nguyên
   nhân chính của cảm giác "lộn xộn", không phải bảng màu.

Giải pháp: TẮT `qt_material` mặc định (an toàn, hết rủi ro nhảy kích
thước), thay vào đó tự HOÀN THIỆN `theme.qss` để MỌI widget (kể cả những
chỗ trước đây bỏ sót) đều có style nhất quán trong CÙNG 1 ngôn ngữ thiết
kế (xem `theme.qss`, mục "Fallback mặc định cho MỌI nút/ô nhập"). Vẫn GIỮ
code tích hợp `qt_material` (không xoá) — bật lại được qua biến môi trường
`AI_MEETING_UI_SKIN=qt_material` trong `.env` cho ai muốn tự thử nghiệm,
nhưng KHÔNG khuyến khích cho tới khi vấn đề #1 được xác nhận rõ nguyên
nhân + có bản vá.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.logging_setup import get_logger, setup_logging
from app.ui.capture_protection import install as install_capture_protection
from app.ui.main_window import MainWindow

_THEME_PATH = Path(__file__).parent / "ui" / "theme.qss"

# 1 nguồn DUY NHẤT cho tên theme qt_material đang dùng nếu người dùng tự
# bật qua AI_MEETING_UI_SKIN=qt_material -- đổi ở đây nếu muốn thử theme
# màu khác (xem danh sách trong package qt_material, thư mục
# qt_material/themes/*.xml).
_QT_MATERIAL_THEME = "dark_teal.xml"


def _apply_theme(app: QApplication) -> None:
    """Áp `theme.qss` của dự án -- style DUY NHẤT + MẶC ĐỊNH kể từ
    02/09/2026 (xem docstring module ở trên, CONTRACTS.md Mục 18.4).

    `qt_material` CHỈ áp khi người dùng CHỦ ĐỘNG bật qua biến môi trường
    `AI_MEETING_UI_SKIN=qt_material` (trong `.env`) -- KHÔNG khuyến khích,
    xem cảnh báo ở docstring module. Không raise -- lỗi ở bước nào cũng chỉ
    cảnh báo ra console và tiếp tục chạy app với style còn lại (thà xấu hơn
    1 chút còn hơn không mở được app)."""
    # setFont() Ở ĐÂY, TRƯỚC khi tạo bất kỳ widget nào (kể cả trước
    # QApplication.setStyleSheet) -- cùng font "Segoe UI" đã dùng xuyên
    # suốt theme.qss + code (suggestion_drawer.py, ask_question_dialog.py,
    # meeting_context_dialog.py) -- đặt tường minh 1 LẦN DUY NHẤT ở tầng
    # app, phòng trường hợp bất kỳ theme/thư viện ngoài nào (kể cả
    # qt_material nếu người dùng tự bật) đổi font mặc định SAU khi 1 vài
    # widget đã kịp layout theo font cũ -- đây chính xác là dạng bug gây
    # hiện tượng "nhảy kích thước sau 1-2s" đã báo (xem docstring module).
    app.setFont(QFont("Segoe UI", 10))

    if os.environ.get("AI_MEETING_UI_SKIN", "").strip().lower() == "qt_material":
        try:
            import qt_material

            qt_material.apply_stylesheet(app, theme=_QT_MATERIAL_THEME)
        except ImportError:
            msg = (
                "AI_MEETING_UI_SKIN=qt_material nhưng chưa cài package "
                "này (pip install qt-material) -- dùng theme.qss mặc định."
            )
            print(f"Cảnh báo: {msg}")
            get_logger().warning(msg)
        except Exception as exc:  # noqa: BLE001 - lỗi lạ từ qt_material không được làm app không mở được
            msg = f"không áp được skin qt_material ({exc}), dùng theme.qss mặc định."
            print(f"Cảnh báo: {msg}")
            get_logger().warning(msg)

    try:
        # NỐI THÊM vào cuối (không xoá style qt_material nếu vừa áp ở
        # trên) -- Qt gộp toàn bộ stylesheet đã set qua mọi lần gọi
        # setStyleSheet() theo thứ tự, rule sau thắng rule trước nếu cùng
        # độ ưu tiên/selector -- theme.qss LUÔN áp SAU CÙNG nên luôn thắng.
        existing = app.styleSheet()
        theme_qss = _THEME_PATH.read_text(encoding="utf-8")
        app.setStyleSheet(f"{existing}\n{theme_qss}" if existing else theme_qss)
    except OSError as exc:
        msg = f"không đọc được theme.qss ({exc}), dùng style mặc định."
        print(f"Cảnh báo: {msg}")
        get_logger().warning(msg)


def main() -> int:
    # 🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30) -- setup_logging() PHẢI
    # chạy TRƯỚC MỌI thứ khác (kể cả QApplication) để bắt được log ngay
    # cả lỗi xảy ra sớm nhất (vd load_dotenv()/tạo QApplication lỗi).
    logger = setup_logging()
    logger.info("=== App khởi động ===")

    # 🔒 MỚI -- log MỌI exception KHÔNG được bắt ở đâu khác (crash thật)
    # trước khi để Python xử lý mặc định (in traceback ra stderr, thường
    # KHÔNG hiện được gì với bản .exe đóng gói không có terminal, xem
    # docstring module logging_setup.py) -- log ra file là cách DUY NHẤT
    # còn lại để biết app đã crash vì sao trên máy người dùng cuối.
    def _log_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error(
            "Lỗi KHÔNG được xử lý (crash) -- app có thể đã đóng ngay sau đây:",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = _log_uncaught_exception

    load_dotenv()  # đọc GROQ_API_KEY/OPENAI_API_KEY/GEMINI_API_KEY/AI_PROVIDER từ .env (xem .env.example)

    app = QApplication(sys.argv)
    _apply_theme(app)

    # Ẩn cửa sổ khỏi screen share: bật/tắt lúc đang chạy qua ⚙️ Cài đặt hoặc
    # phím tắt toàn cục (xem app/ui/capture_protection.py). Trạng thái khởi
    # động = lựa chọn đã lưu, hoặc AI_MEETING_HIDE_FROM_CAPTURE=1 nếu chưa
    # từng chọn. PHẢI cài TRƯỚC window.show() và GIỮ tham chiếu để không bị GC.
    _capture_controller = install_capture_protection(app)  # noqa: F841

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    logger.info("=== App đóng (exit_code=%s) ===", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
