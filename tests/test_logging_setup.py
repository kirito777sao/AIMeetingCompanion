"""
Unit test cho app/logging_setup.py (Backlog #3, CONTRACTS.md Mục 30) --
KHÔNG cần Qt/network thật, chỉ thao tác trên thư mục tạm + module chuẩn
`logging` của Python.
"""

import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path  # noqa: E402

from app.logging_setup import _LOGGER_NAME, get_log_path, get_logger, setup_logging  # noqa: E402


def _reset_logger_state():
    """Test tự dọn `logging.getLogger(_LOGGER_NAME)` VỀ TRẠNG THÁI SẠCH
    trước mỗi test -- module `logging` giữ logger instance DÙNG CHUNG
    toàn process (theo tên) -- nếu không reset, test chạy SAU sẽ thấy
    handler của test chạy TRƯỚC vẫn còn gắn (setup_logging() coi là "đã
    setup rồi", bỏ qua handler mới trỏ vào thư mục tạm CỦA TEST ĐÓ)."""
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_get_log_path_dung_chung_thu_muc_voi_config_dir():
    tmp_dir = Path(tempfile.mkdtemp())
    path = get_log_path(base_dir=tmp_dir)
    assert path == tmp_dir / "app.log"
    print("OK: test_get_log_path_dung_chung_thu_muc_voi_config_dir")


def test_setup_logging_tao_file_va_ghi_dung_noi_dung():
    _reset_logger_state()
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        logger = setup_logging(base_dir=tmp_dir)
        logger.info("dong log thu nghiem")
        logger.error("dong log loi thu nghiem")

        log_path = get_log_path(base_dir=tmp_dir)
        assert log_path.exists(), "setup_logging() phải tự tạo file app.log"
        content = log_path.read_text(encoding="utf-8")
        assert "dong log thu nghiem" in content
        assert "dong log loi thu nghiem" in content
        assert "[INFO]" in content
        assert "[ERROR]" in content
    finally:
        _reset_logger_state()
    print("OK: test_setup_logging_tao_file_va_ghi_dung_noi_dung")


def test_setup_logging_goi_2_lan_khong_them_handler_trung():
    _reset_logger_state()
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        logger1 = setup_logging(base_dir=tmp_dir)
        n_handlers_lan_1 = len(logger1.handlers)
        logger2 = setup_logging(base_dir=tmp_dir)
        n_handlers_lan_2 = len(logger2.handlers)

        assert n_handlers_lan_1 == 1, f"Lần đầu phải có đúng 1 handler, nhận {n_handlers_lan_1}"
        assert n_handlers_lan_2 == n_handlers_lan_1, (
            f"Gọi setup_logging() lần 2 KHÔNG được thêm handler trùng, "
            f"lần 1={n_handlers_lan_1}, lần 2={n_handlers_lan_2}"
        )

        logger2.info("chi xuat hien 1 lan")
        content = get_log_path(base_dir=tmp_dir).read_text(encoding="utf-8")
        assert content.count("chi xuat hien 1 lan") == 1, (
            "Log bị ghi LẶP nhiều lần -- dấu hiệu handler bị thêm trùng."
        )
    finally:
        _reset_logger_state()
    print("OK: test_setup_logging_goi_2_lan_khong_them_handler_trung")


def test_setup_logging_thu_muc_khong_tao_duoc_fallback_null_handler_khong_raise():
    # Mô phỏng "không tạo được thư mục log" bằng cách trỏ base_dir vào 1
    # ĐƯỜNG DẪN LÀ FILE (không phải thư mục) -- mkdir(parents=True) sẽ
    # raise FileExistsError/NotADirectoryError (đều là OSError).
    _reset_logger_state()
    tmp_dir = Path(tempfile.mkdtemp())
    blocking_file = tmp_dir / "day_la_file_khong_phai_thu_muc"
    blocking_file.write_text("chan duong", encoding="utf-8")
    try:
        logger = setup_logging(base_dir=blocking_file)  # base_dir trỏ vào 1 FILE
        # KHÔNG được raise -- chỉ fallback NullHandler, vẫn dùng logger
        # bình thường (gọi log KHÔNG lỗi, chỉ không ghi đi đâu cả).
        logger.info("khong duoc raise du khong ghi duoc file")
        assert any(isinstance(h, logging.NullHandler) for h in logger.handlers), (
            "Phải fallback về NullHandler khi không tạo được thư mục log."
        )
    finally:
        _reset_logger_state()
    print("OK: test_setup_logging_thu_muc_khong_tao_duoc_fallback_null_handler_khong_raise")


def test_get_logger_tra_ve_dung_logger_name_dung_setup_logging():
    _reset_logger_state()
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        setup_logging(base_dir=tmp_dir)
        logger_via_get = get_logger()
        assert logger_via_get.name == _LOGGER_NAME
        logger_via_get.warning("goi qua get_logger() cung phai ghi duoc")
        content = get_log_path(base_dir=tmp_dir).read_text(encoding="utf-8")
        assert "goi qua get_logger() cung phai ghi duoc" in content
    finally:
        _reset_logger_state()
    print("OK: test_get_logger_tra_ve_dung_logger_name_dung_setup_logging")


if __name__ == "__main__":
    test_get_log_path_dung_chung_thu_muc_voi_config_dir()
    test_setup_logging_tao_file_va_ghi_dung_noi_dung()
    test_setup_logging_goi_2_lan_khong_them_handler_trung()
    test_setup_logging_thu_muc_khong_tao_duoc_fallback_null_handler_khong_raise()
    test_get_logger_tra_ve_dung_logger_name_dung_setup_logging()
    print("\n=== TẤT CẢ TEST LOGGING_SETUP PASS ===")
