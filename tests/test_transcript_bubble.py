import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app.ui.transcript_bubble import LOW_CONFIDENCE_THRESHOLD, TranscriptBubble  # noqa: E402


def test_confidence_thuc_te_0_46_phai_hien_canh_bao(app):
    # Giá trị THẬT lấy từ meetings.db người dùng gửi (segment "Human.",
    # confidence=0.4637421464883028) -- bug đã gặp: cảnh báo không hiện ra.
    bubble = TranscriptBubble(
        original_text="Human.", source_lang="en", confidence=0.4637421464883028,
        translated_text="Con người",
    )
    assert 0.4637421464883028 < LOW_CONFIDENCE_THRESHOLD
    # set trực tiếp lên instance -- phải có "border-left: 3px solid #F5A623"
    # trong styleSheet() của CHÍNH widget này (không phụ thuộc QSS toàn cục).
    assert "F5A623" in bubble.styleSheet(), (
        "Bubble confidence thấp phải tự set border cảnh báo trực tiếp lên instance."
    )
    # Phải có chip CHỮ cảnh báo, tìm theo objectName "WarningChip".
    warning_labels = [c for c in bubble.findChildren(QLabel) if c.objectName() == "WarningChip"]
    assert len(warning_labels) == 1, "Phải có đúng 1 chip chữ cảnh báo 'Độ tin cậy thấp'."
    assert "thấp" in warning_labels[0].text().lower()
    print("OK: test_confidence_thuc_te_0_46_phai_hien_canh_bao")


def test_confidence_cao_khong_hien_canh_bao(app):
    bubble = TranscriptBubble(
        original_text="Every human has", source_lang="en", confidence=0.82,
        translated_text="Mỗi con người đều có",
    )
    assert bubble.styleSheet() == "", "Confidence cao thì KHÔNG được tự set style cảnh báo."
    print("OK: test_confidence_cao_khong_hien_canh_bao")


def test_confidence_0_khong_hien_canh_bao_vi_khong_xac_dinh():
    # confidence=0.0 nghĩa là "không xác định được" (xem TranscriptionResult
    # docstring), KHÔNG phải "chắc chắn sai" -- không nên gắn cảnh báo nhầm.
    app = QApplication.instance() or QApplication(sys.argv)
    bubble = TranscriptBubble(original_text="x", source_lang="en", confidence=0.0)
    assert bubble.styleSheet() == ""
    print("OK: test_confidence_0_khong_hien_canh_bao_vi_khong_xac_dinh")


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_confidence_thuc_te_0_46_phai_hien_canh_bao(app)
    test_confidence_cao_khong_hien_canh_bao(app)
    test_confidence_0_khong_hien_canh_bao_vi_khong_xac_dinh()
    print("\n=== TẤT CẢ TEST TRANSCRIPT_BUBBLE PASS ===")
