"""
app/logging_setup.py
---------------------
🔒 MỚI (Backlog #3, CONTRACTS.md Mục 30) — cấu hình `logging` chuẩn của
Python để ghi log RA FILE. Trước đây lỗi CHỈ hiện trên UI (QMessageBox/
label `error_occurred`) hoặc `print()` ra console (`main.py::_apply_theme`)
— không có cách nào tự chẩn đoán khi người dùng cuối report lỗi từ xa
(không chụp được màn hình đúng lúc lỗi xảy ra, hoặc console đã đóng
trước khi kịp đọc). Bản `.exe` đóng gói (Mục 18.x) KHÔNG có terminal hiện
ra để xem `print()` — log ra file là cách DUY NHẤT khả thi để lấy được
thông tin lỗi từ máy người dùng cuối.

Vị trí file log: DÙNG CHUNG thư mục với `config.json`
(`app.config_store.get_config_dir()` — `%APPDATA%\\AIMeetingCompanion\\`
trên Windows) — 1 thư mục DUY NHẤT cho MỌI dữ liệu app tự tạo ra (config,
log), không thêm 1 khái niệm "chỗ lưu" thứ 2. Khi cần debug từ xa, chỉ
cần nói người dùng "vào %APPDATA%\\AIMeetingCompanion\\ gửi file
app.log" — 1 câu hướng dẫn duy nhất, không phải nhớ 2 đường dẫn khác
nhau.

Dùng `RotatingFileHandler` (không phải file lớn dần vô hạn) — giới hạn
kích thước mỗi file (2MB) + số file backup (3, tổng tối đa ~8MB) — tự
xoay vòng, tránh chiếm hết ổ đĩa nếu app chạy nhiều ngày liền không tắt.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from app.config_store import get_config_dir

_LOG_FILE_NAME = "app.log"
_LOGGER_NAME = "ai_meeting_companion"
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB/file
_BACKUP_COUNT = 3  # app.log + app.log.1/.2/.3 -- tổng tối đa ~8MB


def get_log_path(base_dir: Optional[Path] = None) -> Path:
    """`base_dir`: CHỈ dùng để test trỏ vào 1 thư mục tạm, KHÔNG dùng ở
    code thật -- cùng quy ước với `config_store.get_config_dir()` (tái
    dùng thẳng hàm đó để LUÔN ra CÙNG 1 thư mục với config.json, xem
    docstring module ở trên)."""
    return get_config_dir(base_dir) / _LOG_FILE_NAME


def setup_logging(base_dir: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """Gọi 1 LẦN DUY NHẤT lúc khởi động app (`app/main.py`, TRƯỚC khi tạo
    `QApplication` -- để bắt được log ngay cả lỗi xảy ra sớm nhất). Idempotent:
    gọi lại nhiều lần (vd lỡ gọi 2 lần, hoặc trong test) sẽ KHÔNG thêm
    handler trùng lặp -- kiểm tra `logger.handlers` trước khi add, tránh
    mỗi dòng log bị ghi lặp N lần nếu setup_logging() lỡ chạy N lần.

    KHÔNG raise nếu tạo thư mục/file log thất bại (quyền ghi, ổ đĩa lỗi,
    ổ đĩa đầy...) -- gắn `NullHandler` thay vào, app vẫn phải mở được dù
    không ghi log ra file được, cùng nguyên tắc "lỗi phụ trợ không được
    chặn app chạy" đã áp dụng cho `_apply_theme()` ở `main.py` (theme.qss
    đọc lỗi vẫn chỉ cảnh báo, không raise).
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)

    if logger.handlers:
        # Đã setup rồi (gọi lần 2 trở đi) -- không thêm handler trùng.
        return logger

    log_dir = get_config_dir(base_dir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_dir / _LOG_FILE_NAME, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        logger.addHandler(logging.NullHandler())
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # KHÔNG propagate lên root logger -- tránh log bị in trùng ra console
    # nếu 1 thư viện khác (PySide6, qt_material...) lỡ tự cấu hình root
    # logger riêng in ra stderr -- file log này là NGUỒN DUY NHẤT.
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """Lấy logger đã cấu hình -- gọi ở BẤT KỲ module nào cần log
    (`pipeline.py`, `ai_worker.py`, `main_window.py`...) SAU khi
    `setup_logging()` đã chạy ở `main.py`. Nếu gọi TRƯỚC khi
    `setup_logging()` chạy (vd trong unit test KHÔNG qua `app/main.py`)
    -- vẫn trả về 1 `Logger` hợp lệ, chỉ là CHƯA có handler nào (log gọi
    ra sẽ không ghi vào đâu cả, KHÔNG raise/crash -- hành vi mặc định
    chuẩn của module `logging`)."""
    return logging.getLogger(_LOGGER_NAME)
