"""
Smoke test cho UI Phase 1 — chạy MainWindow + AudioWorker THẬT (không mock),
chỉ chạy ở chế độ headless (QT_QPA_PLATFORM=offscreen) vì sandbox này không
có display thật.

Mục tiêu: xác nhận toàn bộ wiring (UI <-> QThread <-> pipeline <-> DB) không
crash, signal/slot nối đúng, và 2 nhánh lỗi sớm (thiếu API key / không phải
Windows) được xử lý đúng KHÔNG làm treo app -- đây là 2 lỗi chắc chắn sẽ gặp
khi tự chạy thật nếu quên set GROQ_API_KEY hoặc chạy nhầm trên Linux/Mac.

KHÔNG test được: audio loopback thật, gọi Groq API thật (cần Windows +
network + API key thật -- phải tự làm trên máy Windows của bạn).
"""

import os
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.ai.base_provider import SummaryResult  # noqa: E402
from app.storage.db import MeetingStore  # noqa: E402
from app.ui.history_dialog import MeetingHistoryDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

os.environ.pop("GROQ_API_KEY", None)  # đảm bảo test 1 chạy đúng nhánh "thiếu key"

# 🔒 SỬA (02/09/2026) -- CÁCH LY khỏi config.json THẬT của máy đang chạy
# test. Phát hiện từ log lỗi thật của người dùng: `create_provider()` (gọi
# bên trong AudioWorker.run(), xem main_window.py) đọc key theo thứ tự (1)
# config_store (`%APPDATA%\AIMeetingCompanion\config.json`) TRƯỚC (2) biến
# môi trường GROQ_API_KEY -- dòng `os.environ.pop("GROQ_API_KEY", ...)` ở
# trên CHỈ xoá được nguồn (2), KHÔNG xoá được nguồn (1). Trên máy DEV THẬT
# đã từng dùng Settings UI để lưu 1 Groq key thật (rất có thể xảy ra sau
# khi tự chạy `python -m app.main` để test thủ công như hướng dẫn ở
# HUONG_DAN_TEST.md) -- `test_thieu_api_key_khong_lam_treo_app` không còn
# ở trạng thái "thiếu key" như tên gọi nữa (tìm thấy key thật qua nguồn 1),
# AudioWorker chạy audio THẬT thay vì lỗi ngay -> timeout 5s giả (KHÔNG
# phải bug app, mà là bài test không cách ly khỏi máy dev).
#
# `config_store.get_config_dir()` đọc thư mục qua biến môi trường APPDATA
# (xem app/config_store.py) -- trỏ nó sang 1 thư mục tạm TRỐNG cho TOÀN BỘ
# file test này (mọi test ở đây đều tạo MainWindow/AudioWorker, không test
# nào nên phụ thuộc config.json thật của máy chạy test) đảm bảo LUÔN chạy
# đúng nhánh "chưa lưu key nào" bất kể máy dev đã dùng Settings UI trước đó
# hay chưa.
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ai_meeting_test_appdata_")


def _run_event_loop_until(condition_fn, timeout_ms=5000):
    """Chạy event loop Qt tới khi condition_fn() trả True hoặc hết timeout."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(False)
    timer.setInterval(20)

    def _check():
        if condition_fn():
            loop.quit()

    timer.timeout.connect(_check)
    timer.start()

    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(timeout_ms)

    loop.exec()
    timer.stop()
    watchdog.stop()
    return condition_fn()


def test_main_window_dung_duoc_khong_crash(app):
    window = MainWindow()
    assert window.windowTitle() == "AI Meeting Companion"
    assert window._start_button.isEnabled()
    assert not window._stop_button.isEnabled()
    assert not window._banner.isVisible()
    window.close()
    print("OK: test_main_window_dung_duoc_khong_crash")


def test_thieu_api_key_khong_lam_treo_app(app):
    window = MainWindow()
    window._worker = None  # đảm bảo sạch
    # 🔒 Vòng 9: gọi thẳng _start_recording() (KHÔNG qua _on_start_clicked())
    # để không phải tự động click qua MeetingContextDialog modal thật — xem
    # docstring _start_recording() ở main_window.py. meeting_context="" ==
    # người dùng bỏ qua bối cảnh, hành vi sau điểm này GIỮ NGUYÊN như cũ.
    window._start_recording(meeting_context="")  # đọc lang combo mặc định "vi", tự tạo AudioWorker thật + start() NGAY trong hàm này

    # ⚠️ KHÔNG connect thêm signal vào `window._worker` ở ĐÂY -- đây chính
    # là bug từng gặp: nếu worker thread chạy xong (lỗi ngay, gần như tức
    # thời) TRƯỚC khi dòng connect() này kịp chạy, signal đã emit xong cho
    # các slot nối từ TRƯỚC (bên trong _start_recording) mất rồi, connect
    # muộn sẽ không bao giờ nhận được signal đó nữa -> test treo giả (race
    # condition trong TEST, không phải bug app). Thay vào đó, poll qua STATE
    # quan sát được của MainWindow (đã nối an toàn từ bên trong
    # _start_recording TRƯỚC khi start()).
    ok = _run_event_loop_until(lambda: window._worker is None, timeout_ms=5000)
    assert ok, "Worker phải kết thúc (window._worker = None) trong vòng 5s (không treo)."

    error_message = window._status_label.text()
    assert error_message, "Phải có message lỗi hiển thị trên status label."
    assert "api" in error_message.lower() or "key" in error_message.lower(), (
        f"Lỗi phải nhắc tới API key, nhận: {error_message!r}"
    )
    window.close()
    print("OK: test_thieu_api_key_khong_lam_treo_app")
    print(f"    -> message thực tế: {error_message!r}")


def test_co_api_key_nhung_khong_phai_windows_van_dung_phien_hop(app):
    os.environ["GROQ_API_KEY"] = "fake-key-chi-de-qua-buoc-khoi-tao-khong-goi-network-thuc"
    window = MainWindow()

    # 🔒 SỬA (bug thật gặp lần đầu chạy trên Windows thật, xem CONTRACTS.md
    # Mục 20/21) -- test này PHẢI giả lập nhánh "KHÔNG PHẢI Windows"
    # (`_assert_windows()` trong app/audio/capture.py raise), nhưng trước
    # đây KHÔNG hề monkeypatch gì cả -- chỉ "ăn may" pass trong sandbox
    # Linux vì máy đó thật sự không phải Windows. Chạy trên Windows thật:
    # platform.system() == "Windows" thật -> _assert_windows() KHÔNG raise
    # -> AudioWorker cố ghi âm loopback thật -> không lỗi ngay -> timeout
    # 5s giả (KHÔNG phải bug app, bug ở TEST thiếu cách ly OS).
    #
    # Patch NGAY TẠI ĐIỂM app/audio/capture.py đọc platform.system() (module
    # được import 1 lần, dùng chung giữa main thread và QThread của
    # AudioWorker nên patch có hiệu lực cho cả 2) -- giữ patch xuyên suốt
    # toàn bộ vòng đợi worker chạy xong, KHÔNG chỉ lúc gọi
    # _start_recording(), vì AudioWorker chạy trên QThread riêng và có thể
    # chưa gọi tới _assert_windows() ngay lúc start() vừa trả về.
    with patch("app.audio.capture.platform.system", return_value="Linux"):
        window._start_recording(meeting_context="")  # 🔒 Vòng 9: xem ghi chú ở test phía trên

        # Đợi meeting_started trước (xảy ra sớm hơn finished) để xác nhận DB tạo
        # phiên họp thành công TRƯỚC khi audio capture lỗi -- vẫn poll qua state
        # MainWindow, không connect lại signal vào worker (lý do ở test trên).
        ok_started = _run_event_loop_until(lambda: window._current_meeting_id is not None, timeout_ms=5000)
        assert ok_started, "Phải tạo được phiên họp trong DB TRƯỚC khi chạm tới audio capture."
        meeting_id_at_start = window._current_meeting_id

        ok = _run_event_loop_until(lambda: window._worker is None, timeout_ms=5000)
        assert ok, "Worker phải kết thúc (window._worker = None) trong vòng 5s."

    error_message = window._status_label.text()
    assert meeting_id_at_start is not None
    assert "windows" in error_message.lower(), (
        f"Lỗi phải nhắc tới giới hạn Windows-only của loopback audio, nhận: {error_message!r}"
    )
    window.close()
    os.environ.pop("GROQ_API_KEY", None)
    print("OK: test_co_api_key_nhung_khong_phai_windows_van_dung_phien_hop")
    print(f"    -> message thực tế: {error_message!r}")


def test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y(app):
    from app.ai.base_provider import TranscriptionResult
    from app.pipeline import TranscriptEvent
    from app.ui import main_window as mw_module

    window = MainWindow()
    window._current_native_lang = "vi"

    # Giả lập create_provider() (provider_factory) TRẢ THẲNG kết quả, không gọi network thật -- chỉ
    # test đúng phần WIRING (bubble -> signal -> OneShotAIWorker -> drawer),
    # KHÔNG test chất lượng suggest_answer() thật (đã có test riêng ở
    # tests/test_groq_provider_offline.py). Patch thủ công + restore trong
    # finally (file này chạy như script thường, không có pytest fixture).
    class _FakeProviderForSuggest:
        def __init__(self, *a, **k):
            pass

        def suggest_answer(self, question_text, context_text, user_native_lang, meeting_context=""):
            return f"[gợi ý giả cho: {question_text}]"

        def translate(self, text, source_lang, target_lang, context_text=""):
            return f"[bản dịch giả của: {text}]"

    original_provider_cls = mw_module.create_provider
    mw_module.create_provider = _FakeProviderForSuggest
    try:
        # Tạo 1 event như pipeline.py sẽ tạo cho 1 câu hỏi thật, đẩy qua
        # đúng đường _on_new_event (không mock pipeline, chỉ mock provider).
        event = TranscriptEvent(
            segment_id=1, original_text="What's our churn rate?", source_lang="en",
            confidence=0.8, translated_text="Tỷ lệ rời bỏ của chúng ta là bao nhiêu?",
            target_lang="vi", is_question=True,
        )
        window._on_new_event(event)

        # Tìm bubble vừa thêm, lấy nút "Nhờ AI trả lời" bấm thử.
        from app.ui.transcript_bubble import TranscriptBubble
        bubbles = window._transcript_container.findChildren(TranscriptBubble)
        assert len(bubbles) == 1
        bubble = bubbles[0]

        from PySide6.QtWidgets import QPushButton
        ask_buttons = [b for b in bubble.findChildren(QPushButton) if b.objectName() == "AskAiButton"]
        assert len(ask_buttons) == 1, "Bubble câu hỏi phải có đúng 1 nút 'Nhờ AI trả lời'."
        ask_buttons[0].click()

        ok = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
        assert ok, "OneShotAIWorker phải chạy xong (tự dọn khỏi _ai_workers) trong 3s."

        from app.ui.suggestion_drawer import SuggestionDrawer
        drawers = [c for c in window.findChildren(SuggestionDrawer)]
        assert len(drawers) == 1
        drawer = drawers[0]
        assert "gợi ý giả" in drawer._answer_edit.toPlainText(), (
            f"Drawer phải hiện gợi ý từ provider giả, nhận: {drawer._answer_edit.toPlainText()!r}"
        )
        assert drawer._translate_button.isEnabled(), "Nút 'Dịch & Sẵn sàng nói' phải bật sau khi có gợi ý."

        # Bấm tiếp "Dịch & Sẵn sàng nói" -> phải gọi translate() giả, hiện readback.
        drawer._translate_button.click()
        ok2 = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
        assert ok2
        assert drawer._readback_label.isVisible()
        assert "bản dịch giả" in drawer._readback_label.text()

        window.close()
    finally:
        mw_module.create_provider = original_provider_cls
    print("OK: test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y")


def test_nut_nho_ai_tra_loi_hien_o_moi_bubble_ke_ca_khong_phai_cau_hoi(app):
    # Quyết định đã chốt sau phản hồi test thật: heuristic is_question (dấu
    # "?") miss nhiều câu hỏi thật trong hội thoại nói nhanh -- nút phải
    # hiện ở MỌI bubble, không gate theo is_question nữa.
    from app.pipeline import TranscriptEvent
    from app.ui.transcript_bubble import TranscriptBubble
    from PySide6.QtWidgets import QPushButton

    window = MainWindow()
    event = TranscriptEvent(
        segment_id=1, original_text="Just a regular statement, not a question",
        source_lang="en", confidence=0.8, translated_text="Chỉ là 1 câu nói bình thường",
        target_lang="vi", is_question=False,
    )
    window._on_new_event(event)

    bubbles = window._transcript_container.findChildren(TranscriptBubble)
    assert len(bubbles) == 1
    ask_buttons = [b for b in bubbles[0].findChildren(QPushButton) if b.objectName() == "AskAiButton"]
    assert len(ask_buttons) == 1, "Nút phải hiện cả khi is_question=False."
    window.close()
    print("OK: test_nut_nho_ai_tra_loi_hien_o_moi_bubble_ke_ca_khong_phai_cau_hoi")


def test_auto_scroll_xuong_cuoi_khi_bubble_tran_man_hinh(app):
    # Bug thật phát hiện qua test: setValue(maximum()) gọi NGAY sau khi
    # insert bubble không cuộn đúng vì Qt chưa kịp tính lại scrollbar range.
    # Test bằng cách thêm NHIỀU bubble (đủ tràn quá viewport nhỏ) rồi xử lý
    # event loop (để QTimer.singleShot(0, ...) trong _on_new_event chạy),
    # xác nhận scrollbar value cuối cùng = maximum.
    from app.pipeline import TranscriptEvent

    window = MainWindow()
    window.resize(400, 300)  # viewport nhỏ để chắc chắn bubble tràn màn hình
    window.show()
    app.processEvents()

    for i in range(25):
        event = TranscriptEvent(
            segment_id=i, original_text=f"Câu nói số {i} " * 5, source_lang="en",
            confidence=0.8, translated_text=f"Dòng dịch số {i}", target_lang="vi",
            is_question=False,
        )
        window._on_new_event(event)
        # Xử lý event loop sau MỖI lần thêm để QTimer.singleShot(0, ...) kịp
        # chạy, giống đúng nhịp thật (mỗi segment xử lý xong mới tới segment kế).
        app.processEvents()

    bar = window._scroll_area.verticalScrollBar()
    assert bar.maximum() > 0, "Phải có đủ nội dung để scrollbar xuất hiện (test setup sai nếu = 0)."
    assert bar.value() == bar.maximum(), (
        f"Phải tự cuộn xuống đúng cuối MỚI sau khi thêm bubble, "
        f"nhận value={bar.value()} maximum={bar.maximum()}."
    )
    window.close()
    print("OK: test_auto_scroll_xuong_cuoi_khi_bubble_tran_man_hinh")


def test_khong_tu_cuon_neu_dang_cuon_len_doc_lich_su(app):
    from app.pipeline import TranscriptEvent

    window = MainWindow()
    window.resize(400, 300)
    window.show()
    app.processEvents()

    for i in range(15):
        event = TranscriptEvent(
            segment_id=i, original_text=f"Câu nói số {i} " * 5, source_lang="en",
            confidence=0.8, translated_text=f"Dòng dịch số {i}", target_lang="vi",
            is_question=False,
        )
        window._on_new_event(event)
        app.processEvents()

    bar = window._scroll_area.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(0)  # giả lập người dùng tự cuộn LÊN đầu để đọc lại lịch sử
    app.processEvents()

    event = TranscriptEvent(
        segment_id=99, original_text="Câu mới nhất", source_lang="en",
        confidence=0.8, translated_text="Dòng dịch mới nhất", target_lang="vi",
        is_question=False,
    )
    window._on_new_event(event)
    app.processEvents()

    assert bar.value() == 0, (
        "Không được tự kéo người dùng xuống cuối nếu họ đang chủ động cuộn "
        f"lên đọc lịch sử, nhận value={bar.value()} (kỳ vọng vẫn là 0)."
    )
    window.close()
    print("OK: test_khong_tu_cuon_neu_dang_cuon_len_doc_lich_su")


def test_suggestion_drawer_skeleton_hien_luc_dang_tai_an_khi_co_ket_qua(app):
    """🔒 MỚI (Backlog "Skeleton loading") — set_loading() phải hiện
    SkeletonLoadingWidget + ẩn ô trả lời (_answer_edit); set_answer()/
    set_error() phải đảo lại (ẩn skeleton, hiện _answer_edit). Test TRỰC
    TIẾP trên widget (không qua worker/thread) để tránh timing-sensitive."""
    from app.ui.suggestion_drawer import SuggestionDrawer

    drawer = SuggestionDrawer("Câu hỏi test")
    drawer.show()  # bắt buộc show() -- Qt chỉ báo đúng isVisible() khi cây widget cha đã hiện

    drawer.set_loading()
    assert drawer._skeleton.isVisible(), "set_loading() phải hiện skeleton."
    assert not drawer._answer_edit.isVisible(), "set_loading() phải ẩn _answer_edit."

    drawer.set_answer("gợi ý trả lời")
    assert not drawer._skeleton.isVisible(), "set_answer() phải ẩn skeleton."
    assert drawer._answer_edit.isVisible(), "set_answer() phải hiện lại _answer_edit."

    drawer.set_loading()
    drawer.set_error("lỗi giả")
    assert not drawer._skeleton.isVisible(), "set_error() phải ẩn skeleton."
    assert drawer._answer_edit.isVisible(), "set_error() phải hiện lại _answer_edit."

    drawer.close()
    print("OK: test_suggestion_drawer_skeleton_hien_luc_dang_tai_an_khi_co_ket_qua")


def test_toi_muon_hoi_dich_va_hien_readback(app):
    from app.ui import main_window as mw_module

    window = MainWindow()
    window._current_native_lang = "vi"
    window._recent_source_langs = ["en", "en"]  # giả lập đã phát hiện đối phương nói tiếng Anh
    window._ask_question_button.setEnabled(True)  # giả lập đang trong phiên họp

    class _FakeProviderForAsk:
        def __init__(self, *a, **k):
            pass

        def translate(self, text, source_lang, target_lang, context_text=""):
            return f"[dịch giả ({source_lang}->{target_lang}): {text}]"

    original_provider_cls = mw_module.create_provider
    mw_module.create_provider = _FakeProviderForAsk
    try:
        window._on_ask_question_clicked()
        from app.ui.ask_question_dialog import AskQuestionDialog
        dialogs = window.findChildren(AskQuestionDialog)
        assert len(dialogs) == 1
        dialog = dialogs[0]

        # Mặc định ngôn ngữ đích phải đoán đúng = "en" (ngôn ngữ đối phương
        # gần nhất phát hiện được, khác tiếng mẹ đẻ "vi" của người dùng).
        assert dialog._lang_combo.currentData() == "en"

        dialog._input_edit.setPlainText("Deadline dự án là khi nào?")
        dialog._translate_button.click()

        ok = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
        assert ok
        assert dialog._readback_label.isVisible()
        assert "dịch giả" in dialog._readback_label.text()
        assert "vi->en" in dialog._readback_label.text()

        dialog.close()
        window.close()
    finally:
        mw_module.create_provider = original_provider_cls
    print("OK: test_toi_muon_hoi_dich_va_hien_readback")


def test_ask_question_dialog_skeleton_hien_luc_dang_dich_an_khi_co_readback(app):
    """🔒 MỚI (Backlog "Skeleton loading") — set_translating() phải hiện
    SkeletonLoadingWidget + ẩn readback; show_readback()/set_error() phải
    đảo lại (ẩn skeleton). Test TRỰC TIẾP trên widget."""
    from app.ui.ask_question_dialog import AskQuestionDialog

    dialog = AskQuestionDialog()
    dialog.show()

    dialog.set_translating()
    assert dialog._skeleton.isVisible(), "set_translating() phải hiện skeleton."
    assert not dialog._readback_label.isVisible(), "set_translating() phải ẩn readback."

    dialog.show_readback("bản dịch giả")
    assert not dialog._skeleton.isVisible(), "show_readback() phải ẩn skeleton."
    assert dialog._readback_label.isVisible(), "show_readback() phải hiện lại readback."

    dialog.set_translating()
    dialog.set_error("lỗi giả")
    assert not dialog._skeleton.isVisible(), "set_error() phải ẩn skeleton."

    dialog.close()
    print("OK: test_ask_question_dialog_skeleton_hien_luc_dang_dich_an_khi_co_readback")


def test_toi_muon_hoi_bao_loi_neu_chua_nhap_gi(app):
    window = MainWindow()
    window._ask_question_button.setEnabled(True)
    window._on_ask_question_clicked()
    from app.ui.ask_question_dialog import AskQuestionDialog
    dialog = window.findChildren(AskQuestionDialog)[0]

    dialog._translate_button.click()  # chưa nhập gì, bấm ngay
    assert "chưa nhập" in dialog._status_label.text().lower()
    dialog.close()
    window.close()
    print("OK: test_toi_muon_hoi_bao_loi_neu_chua_nhap_gi")


def test_auto_scroll_dung_khi_nhieu_bubble_den_lien_tiep_nhanh(app):
    # Mô phỏng đúng nghi vấn gây bug cũ: nhiều segment đến gần như cùng lúc
    # (không kịp xử lý layout giữa các lần insert) -- cơ chế rangeChanged
    # (queued tới khi Qt thực sự tính lại layout) phải vẫn đúng, khác với
    # QTimer.singleShot(0,...) cũ có thể bị mất đồng bộ trong tình huống này.
    from app.pipeline import TranscriptEvent

    window = MainWindow()
    window.resize(400, 300)
    window.show()
    app.processEvents()

    # KHÔNG gọi processEvents() giữa các lần -- đẩy hết 20 event vào liên
    # tiếp như thể chúng tới "dồn cục" trong cùng 1 lượt xử lý.
    for i in range(20):
        event = TranscriptEvent(
            segment_id=i, original_text=f"Dồn cục câu {i} " * 5, source_lang="en",
            confidence=0.8, translated_text=f"Dòng dịch {i}", target_lang="vi",
            is_question=False,
        )
        window._on_new_event(event)

    # Chỉ gọi processEvents() 1 LẦN không đủ -- 1 lần xử lý hết hàng đợi
    # HIỆN TẠI, nhưng xử lý layout request có thể tự sinh thêm event mới
    # (resize/paint kéo theo) cần thêm vòng nữa mới drain hết. Trong app
    # thật, `app.exec()` chạy event loop LIÊN TỤC nên tự nhiên đủ vòng;
    # ở đây phải tự lặp processEvents() vài lần để mô phỏng đúng điều đó
    # (đây là hạn chế của cách viết test, KHÔNG phải bug ở code app).
    for _ in range(10):
        app.processEvents()

    bar = window._scroll_area.verticalScrollBar()
    assert bar.maximum() > 0
    assert bar.value() == bar.maximum(), (
        f"Phải cuộn đúng tới đáy MỚI sau khi 20 bubble dồn cục cùng lúc, "
        f"nhận value={bar.value()} maximum={bar.maximum()}."
    )
    window.close()
    print("OK: test_auto_scroll_dung_khi_nhieu_bubble_den_lien_tiep_nhanh")


def test_phase2_buoc3_luu_ai_assist_vao_db_sau_khi_dich_xong(app):
    import tempfile

    from app.ai.base_provider import TranscriptionResult
    from app.pipeline import TranscriptEvent
    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module

    class _FakeProviderForSuggest:
        def __init__(self, *a, **k):
            pass

        def suggest_answer(self, question_text, context_text, user_native_lang, meeting_context=""):
            return f"[gợi ý giả cho: {question_text}]"

        def translate(self, text, source_lang, target_lang, context_text=""):
            return f"[bản dịch giả của: {text}]"

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase2_step3.db")

        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForSuggest
        try:
            # Tạo 1 meeting THẬT trong đúng file DB này, gán trực tiếp vào
            # window (mô phỏng đúng trạng thái sau khi AudioWorker thật đã
            # gọi start_meeting() -- không chạy AudioWorker thật ở đây vì
            # không cần thiết, chỉ test riêng phần lưu ai_assists).
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id

            # -- Luồng 1: "Nhờ AI trả lời" -> "Dịch & Sẵn sàng nói" --
            event = TranscriptEvent(
                segment_id=1, original_text="What's our churn rate?", source_lang="en",
                confidence=0.8, translated_text="Tỷ lệ rời bỏ là bao nhiêu?",
                target_lang="vi", is_question=True,
            )
            window._on_new_event(event)
            from app.ui.transcript_bubble import TranscriptBubble
            from PySide6.QtWidgets import QPushButton
            bubble = window._transcript_container.findChildren(TranscriptBubble)[0]
            ask_button = [b for b in bubble.findChildren(QPushButton) if b.objectName() == "AskAiButton"][0]
            ask_button.click()
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)

            from app.ui.suggestion_drawer import SuggestionDrawer
            drawer = window.findChildren(SuggestionDrawer)[0]
            drawer._translate_button.click()
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)

            # -- Luồng 2: "Tôi muốn hỏi" --
            window._ask_question_button.setEnabled(True)
            window._on_ask_question_clicked()
            from app.ui.ask_question_dialog import AskQuestionDialog
            dialog = window.findChildren(AskQuestionDialog)[0]
            dialog._input_edit.setPlainText("Deadline dự án là khi nào?")
            dialog._translate_button.click()
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)

            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls

        # Mở LẠI file DB (đã đóng connection cũ) để xác nhận đã lưu thật,
        # không chỉ tin vào UI không crash.
        with MeetingStore(db_path) as verify_store:
            rows = verify_store.get_ai_assists(meeting_id)
            assert len(rows) == 2, f"Phải có đúng 2 dòng ai_assists, nhận {len(rows)}."
            kinds = {r[2] for r in rows}
            assert kinds == {"suggest_answer", "ask_question"}
            suggest_row = next(r for r in rows if r[2] == "suggest_answer")
            assert suggest_row[3] == "What's our churn rate?"  # source_text
            assert "bản dịch giả" in suggest_row[5]  # final_text
            ask_row = next(r for r in rows if r[2] == "ask_question")
            assert ask_row[3] == "Deadline dự án là khi nào?"
            assert ask_row[4] is None  # ai_output phải NULL với ask_question

    print("OK: test_phase2_buoc3_luu_ai_assist_vao_db_sau_khi_dich_xong")


def test_phase3_buoc3_hien_checkbox_va_dung_cache_khong_goi_lai_ai(app):
    """Phase 3 Bước 3/4: action_items hiện thành `QCheckBox` (không còn
    `_action_body` text như Bước 2/4). Mở dialog 2 LẦN cho CÙNG 1
    meeting_id -> `summarize()` CHỈ được gọi ĐÚNG 1 LẦN (lần 2 phải đọc
    cache `meeting_reports`, không tốn quota/chậm vô ích)."""
    import tempfile

    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module
    from app.ui.report_view import ReportDialog
    from PySide6.QtWidgets import QCheckBox

    call_count = {"n": 0}

    class _FakeProviderForReport:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            assert "Deadline" in transcript_text  # đúng nội dung segment đã ghi ở dưới
            call_count["n"] += 1
            return SummaryResult(
                overview="Tóm tắt giả.",
                decisions=["Quyết định giả 1"],
                action_items=["Việc giả A", "Việc giả B"],
            )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase3_step3.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForReport
        try:
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")
                setup_store.add_segment(
                    meeting_id=meeting_id, original_text="Deadline is next Friday.",
                    source_lang="en", confidence=0.9,
                )

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id
            window._report_button.setEnabled(True)

            # -- Lần 1: chưa có cache -> PHẢI gọi summarize() --
            window._on_report_clicked()
            dialog1 = window.findChildren(ReportDialog)[0]
            assert dialog1._loading_label.isVisible()
            ok = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert ok
            assert call_count["n"] == 1
            assert not dialog1._loading_label.isVisible()
            assert dialog1._overview_body.text() == "Tóm tắt giả."
            assert "Quyết định giả 1" in dialog1._decisions_body.text()
            checkboxes = dialog1._action_items_container.findChildren(QCheckBox)
            assert [c.text() for c in checkboxes] == ["Việc giả A", "Việc giả B"]
            assert all(not c.isChecked() for c in checkboxes), "Action item MỚI tổng hợp phải chưa tick."
            dialog1.close()

            # -- Lần 2: mở lại CÙNG meeting -> phải đọc cache, KHÔNG gọi summarize() lần nữa --
            window._on_report_clicked()
            dialog2 = window.findChildren(ReportDialog)[-1]
            ok2 = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert ok2
            assert call_count["n"] == 1, "Mở lại dialog KHÔNG được gọi summarize() lần 2 (phải dùng cache)."
            assert dialog2._overview_body.text() == "Tóm tắt giả."

            dialog2.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls
    print("OK: test_phase3_buoc3_hien_checkbox_va_dung_cache_khong_goi_lai_ai")


def test_phase3_buoc3_tao_bao_cao_moi_goi_lai_ai_va_reset_tick(app):
    """Bấm "🔄 Tạo báo cáo mới" PHẢI bỏ cache, gọi `summarize()` lại, VÀ
    action items của báo cáo mới phải reset về chưa tick (xem docstring
    `save_report()` ở storage/db.py — không thể map đúng tick cũ sang nội
    dung mới hoàn toàn khác)."""
    import tempfile

    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module
    from app.ui.report_view import ReportDialog
    from PySide6.QtWidgets import QCheckBox

    call_count = {"n": 0}

    class _FakeProviderForReport:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            call_count["n"] += 1
            return SummaryResult(overview=f"Bản số {call_count['n']}", decisions=[], action_items=["Việc X"])

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase3_step3_regen.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForReport
        try:
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")
                setup_store.add_segment(
                    meeting_id=meeting_id, original_text="Hello world.", source_lang="en", confidence=0.9,
                )

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id
            window._report_button.setEnabled(True)

            window._on_report_clicked()
            dialog = window.findChildren(ReportDialog)[0]
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert call_count["n"] == 1
            assert dialog._overview_body.text() == "Bản số 1"
            assert dialog._regenerate_button.isVisible()

            checkbox = dialog._action_items_container.findChildren(QCheckBox)[0]
            checkbox.setChecked(True)  # giả lập người dùng tick -- toggled là DirectConnection cùng thread, chạy ngay

            dialog._regenerate_button.click()
            ok = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert ok
            assert call_count["n"] == 2, "Bấm 'Tạo báo cáo mới' PHẢI gọi summarize() lần nữa."
            assert dialog._overview_body.text() == "Bản số 2"
            new_checkbox = dialog._action_items_container.findChildren(QCheckBox)[0]
            assert not new_checkbox.isChecked(), "Báo cáo MỚI phải reset action item về chưa tick."

            dialog.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls
    print("OK: test_phase3_buoc3_tao_bao_cao_moi_goi_lai_ai_va_reset_tick")


def test_phase3_buoc3_tick_checkbox_luu_vao_db(app):
    """Tick 1 checkbox action item -> phải lưu vào `meeting_reports` NGAY
    (không cần nút 'Lưu' riêng), VÀ chỉ đúng item được tick, không đụng
    item khác. Mở LẠI file DB sau khi đóng window để xác nhận đã lưu THẬT."""
    import tempfile

    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module
    from app.ui.report_view import ReportDialog
    from PySide6.QtWidgets import QCheckBox

    class _FakeProviderForReport:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            return SummaryResult(overview="x", decisions=[], action_items=["Việc A", "Việc B"])

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase3_step3_tick.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForReport
        try:
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")
                setup_store.add_segment(meeting_id=meeting_id, original_text="x", source_lang="en", confidence=0.9)

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id
            window._report_button.setEnabled(True)

            window._on_report_clicked()
            dialog = window.findChildren(ReportDialog)[0]
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)

            checkboxes = dialog._action_items_container.findChildren(QCheckBox)
            checkboxes[1].setChecked(True)  # tick "Việc B" (index 1) -- KHÔNG đụng index 0

            dialog.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls

        with MeetingStore(db_path) as verify_store:
            report = verify_store.get_report(meeting_id)
            assert report.action_items[0].done is False, "Item KHÔNG được tick không được tự đổi theo."
            assert report.action_items[1].done is True
    print("OK: test_phase3_buoc3_tick_checkbox_luu_vao_db")


def test_phase3_buoc3_nut_xuat_file_goi_dung_report_export(app):
    """Bấm "💾 Xuất .docx"/".pdf" -> mở hộp thoại lưu file (giả lập qua
    `QFileDialog` đã patch) -> gọi ĐÚNG hàm `report_export.export_to_docx`/
    `export_to_pdf` với đúng `meeting_id`/nhãn ngôn ngữ/đường dẫn -> báo
    thành công qua `_export_status_label` (KHÔNG đụng `_status_label` nội
    dung báo cáo)."""
    import tempfile

    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module
    from app.ui.report_view import ReportDialog

    class _FakeProviderForReport:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            return SummaryResult(overview="Tóm tắt.", decisions=["QĐ"], action_items=["Việc A"])

    export_calls = []

    def _fake_export_to_docx(report, meeting_id, native_lang_label, path):
        export_calls.append(("docx", meeting_id, native_lang_label, path))

    def _fake_export_to_pdf(report, meeting_id, native_lang_label, path):
        export_calls.append(("pdf", meeting_id, native_lang_label, path))

    class _FakeQFileDialog:
        @staticmethod
        def getSaveFileName(parent, caption, default_name, filter_str):
            return (f"/tmp/{default_name}", filter_str)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase3_step3_export.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        original_export_docx = mw_module.report_export.export_to_docx
        original_export_pdf = mw_module.report_export.export_to_pdf
        original_file_dialog = mw_module.QFileDialog
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForReport
        mw_module.report_export.export_to_docx = _fake_export_to_docx
        mw_module.report_export.export_to_pdf = _fake_export_to_pdf
        mw_module.QFileDialog = _FakeQFileDialog
        try:
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")
                setup_store.add_segment(meeting_id=meeting_id, original_text="x", source_lang="en", confidence=0.9)

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id
            window._report_button.setEnabled(True)

            window._on_report_clicked()
            dialog = window.findChildren(ReportDialog)[0]
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert dialog._export_docx_button.isVisible()
            assert dialog._export_pdf_button.isVisible()

            dialog._export_docx_button.click()
            dialog._export_pdf_button.click()

            assert len(export_calls) == 2
            kinds = {c[0] for c in export_calls}
            assert kinds == {"docx", "pdf"}
            for kind, mid, label, path in export_calls:
                assert mid == meeting_id
                assert label == "Tiếng Việt"
                assert path.endswith(f".{kind}")
            assert "Đã lưu file" in dialog._export_status_label.text()

            dialog.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls
            mw_module.report_export.export_to_docx = original_export_docx
            mw_module.report_export.export_to_pdf = original_export_pdf
            mw_module.QFileDialog = original_file_dialog
    print("OK: test_phase3_buoc3_nut_xuat_file_goi_dung_report_export")


def test_phase3_buoc3_xuat_file_loi_hien_export_status_khong_mat_noi_dung(app):
    """`ReportExportError` (vd thiếu font/thiếu thư viện) PHẢI hiện qua
    `_export_status_label`, KHÔNG được ẩn mất nội dung báo cáo đang xem
    (khác `set_error()` -- xem docstring report_view.py)."""
    import tempfile

    from app.report_export import ReportExportError
    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module
    from app.ui.report_view import ReportDialog

    class _FakeProviderForReport:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            return SummaryResult(overview="Tóm tắt.", decisions=[], action_items=[])

    def _failing_export(report, meeting_id, native_lang_label, path):
        raise ReportExportError("Không tìm thấy font hệ thống (giả lập lỗi).")

    class _FakeQFileDialog:
        @staticmethod
        def getSaveFileName(parent, caption, default_name, filter_str):
            return (f"/tmp/{default_name}", filter_str)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase3_step3_export_loi.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        original_export_pdf = mw_module.report_export.export_to_pdf
        original_file_dialog = mw_module.QFileDialog
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForReport
        mw_module.report_export.export_to_pdf = _failing_export
        mw_module.QFileDialog = _FakeQFileDialog
        try:
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")
                setup_store.add_segment(meeting_id=meeting_id, original_text="x", source_lang="en", confidence=0.9)

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id
            window._report_button.setEnabled(True)

            window._on_report_clicked()
            dialog = window.findChildren(ReportDialog)[0]
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)

            dialog._export_pdf_button.click()
            assert "lỗi" in dialog._export_status_label.text().lower()
            assert dialog._overview_body.isVisible(), "Lỗi xuất file KHÔNG được làm ẩn mất nội dung báo cáo."
            assert dialog._overview_body.text() == "Tóm tắt."

            dialog.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls
            mw_module.report_export.export_to_pdf = original_export_pdf
            mw_module.QFileDialog = original_file_dialog
    print("OK: test_phase3_buoc3_xuat_file_loi_hien_export_status_khong_mat_noi_dung")


def test_phase3_buoc2_bao_loi_khi_chua_co_transcript(app):
    """Phiên họp chưa có segment nào -> ReportDialog phải hiện lỗi rõ ràng
    (qua nút "Thử lại"), KHÔNG crash, KHÔNG gọi summarize() với text rỗng."""
    import tempfile

    from app.storage.db import MeetingStore
    from app.ui import main_window as mw_module

    class _FakeProviderShouldNotBeCalled:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            raise AssertionError("KHÔNG được gọi summarize() khi transcript rỗng.")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_phase3_step2_empty.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderShouldNotBeCalled
        try:
            with MeetingStore(db_path) as setup_store:
                meeting_id = setup_store.start_meeting(user_native_lang="vi")  # KHÔNG add_segment

            window = MainWindow()
            window._current_native_lang = "vi"
            window._current_meeting_id = meeting_id
            window._report_button.setEnabled(True)

            window._on_report_clicked()
            from app.ui.report_view import ReportDialog
            dialog = window.findChildren(ReportDialog)[0]

            ok = _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert ok
            assert dialog._retry_button.isVisible()
            assert "chưa" in dialog._status_label.text().lower() or "rỗng" in dialog._status_label.text().lower()

            dialog.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls
    print("OK: test_phase3_buoc2_bao_loi_khi_chua_co_transcript")



def test_suggestion_drawer_va_ask_question_dung_font_segoe_ui_truc_tiep(app):
    # Bug thật phát hiện qua test: chữ tiếng Việt mất dấu RIÊNG ở QTextEdit
    # (đã xác nhận data lưu DB đúng 100% -- lỗi chỉ ở hiển thị). Set font
    # trực tiếp bằng code, không phụ thuộc QSS cascade -- test xác nhận
    # đúng font đã được set, KHÔNG verify được việc này có thật sự render
    # đúng dấu trên Windows hay không (cần bạn tự xác nhận lại bằng mắt).
    from app.ui.suggestion_drawer import SuggestionDrawer
    from app.ui.ask_question_dialog import AskQuestionDialog

    drawer = SuggestionDrawer("Câu hỏi mẫu")
    assert drawer._answer_edit.font().family() == "Segoe UI"
    drawer.close()

    dialog = AskQuestionDialog()
    assert dialog._input_edit.font().family() == "Segoe UI"
    dialog.close()
    print("OK: test_suggestion_drawer_va_ask_question_dung_font_segoe_ui_truc_tiep")


def test_on_start_clicked_huy_dialog_boi_canh_thi_khong_tao_worker(app):
    """🔒 MỚI (Vòng 9, CONTRACTS.md Mục 18) — bấm "Huỷ" ở MeetingContextDialog
    phải giữ nguyên trạng thái màn hình chính, KHÔNG tạo AudioWorker nào.
    Monkeypatch `MeetingContextDialog.exec` để không phải tự động click
    qua dialog modal thật trong headless test (không có input thật để
    "bấm")."""
    from PySide6.QtWidgets import QDialog
    from app.ui import main_window as mw_module

    window = MainWindow()
    original_exec = mw_module.MeetingContextDialog.exec
    mw_module.MeetingContextDialog.exec = lambda self: QDialog.Rejected
    try:
        window._on_start_clicked()
    finally:
        mw_module.MeetingContextDialog.exec = original_exec

    assert window._worker is None, "Huỷ dialog bối cảnh không được tạo AudioWorker."
    assert window._start_button.isEnabled(), "Nút 'Bắt đầu ghi' không được bị disable khi đã huỷ."
    window.close()
    print("OK: test_on_start_clicked_huy_dialog_boi_canh_thi_khong_tao_worker")


def test_on_start_clicked_truyen_dung_language_hint_da_chon(app):
    """🔒 MỚI (CONTRACTS.md Mục 38) — chọn "Ngôn ngữ nguồn dự kiến" khác
    "Tự động" ở MeetingContextDialog phải truyền ĐÚNG mã ISO xuống
    AudioWorker(language_hint=...). Monkeypatch AudioWorker để bắt kwargs
    constructor thay vì phải chờ worker chạy thật (cần API key)."""
    from PySide6.QtWidgets import QDialog
    from app.ui import main_window as mw_module

    window = MainWindow()
    window._worker = None

    captured = {}
    original_worker_cls = mw_module.AudioWorker

    class _CapturingAudioWorker(original_worker_cls):
        def __init__(self, *args, **kwargs):
            captured["language_hint"] = kwargs.get("language_hint")
            super().__init__(*args, **kwargs)

    def _fake_exec(self):
        idx = self._lang_hint_combo.findData("ja")
        assert idx >= 0, "Dropdown phải có option với userData='ja'."
        self._lang_hint_combo.setCurrentIndex(idx)
        return QDialog.Accepted

    original_exec = mw_module.MeetingContextDialog.exec
    mw_module.MeetingContextDialog.exec = _fake_exec
    mw_module.AudioWorker = _CapturingAudioWorker
    try:
        window._on_start_clicked()
    finally:
        mw_module.MeetingContextDialog.exec = original_exec
        mw_module.AudioWorker = original_worker_cls

    assert captured.get("language_hint") == "ja", (
        f"Phải truyền language_hint='ja' xuống AudioWorker, nhận {captured!r}."
    )
    ok = _run_event_loop_until(lambda: window._worker is None, timeout_ms=5000)
    assert ok, "Worker phải kết thúc (lỗi thiếu API key, như test đầu file) trong vòng 5s."
    window.close()
    print("OK: test_on_start_clicked_truyen_dung_language_hint_da_chon")


def test_on_start_clicked_khong_doi_dropdown_thi_language_hint_rong(app):
    """🔒 MỚI (Mục 38) — không đụng dropdown (giữ "🌐 Tự động" mặc định)
    phải truyền language_hint="" xuống AudioWorker, giữ NGUYÊN hành vi cũ."""
    from PySide6.QtWidgets import QDialog
    from app.ui import main_window as mw_module

    window = MainWindow()
    window._worker = None

    captured = {}
    original_worker_cls = mw_module.AudioWorker

    class _CapturingAudioWorker(original_worker_cls):
        def __init__(self, *args, **kwargs):
            captured["language_hint"] = kwargs.get("language_hint")
            super().__init__(*args, **kwargs)

    original_exec = mw_module.MeetingContextDialog.exec
    mw_module.MeetingContextDialog.exec = lambda self: QDialog.Accepted
    mw_module.AudioWorker = _CapturingAudioWorker
    try:
        window._on_start_clicked()
    finally:
        mw_module.MeetingContextDialog.exec = original_exec
        mw_module.AudioWorker = original_worker_cls

    assert captured.get("language_hint") == "", (
        f"Mặc định (không đổi dropdown) phải là '', nhận {captured!r}."
    )
    ok = _run_event_loop_until(lambda: window._worker is None, timeout_ms=5000)
    assert ok
    window.close()
    print("OK: test_on_start_clicked_khong_doi_dropdown_thi_language_hint_rong")


def test_on_start_clicked_dong_y_dialog_thi_dung_meeting_context_da_nhap(app):
    """🔒 MỚI (Vòng 9) — bấm "Bắt đầu ghi" ở MeetingContextDialog phải
    truyền ĐÚNG nội dung người dùng đã nhập xuống `_start_recording()`
    (window._current_meeting_context), không làm mất/đổi nội dung."""
    from PySide6.QtWidgets import QDialog
    from app.ui import main_window as mw_module

    window = MainWindow()
    window._worker = None

    def _fake_exec(self):
        self._context_edit.setPlainText("Buổi họp thảo luận roadmap quý tới.")
        return QDialog.Accepted

    original_exec = mw_module.MeetingContextDialog.exec
    mw_module.MeetingContextDialog.exec = _fake_exec
    try:
        window._on_start_clicked()
    finally:
        mw_module.MeetingContextDialog.exec = original_exec

    assert window._current_meeting_context == "Buổi họp thảo luận roadmap quý tới."

    ok = _run_event_loop_until(lambda: window._worker is None, timeout_ms=5000)
    assert ok, "Worker phải kết thúc (lỗi thiếu API key, như test đầu file) trong vòng 5s."
    window.close()
    print("OK: test_on_start_clicked_dong_y_dialog_thi_dung_meeting_context_da_nhap")


def test_history_dialog_khong_cho_chon_phien_dang_ghi(app):
    # Vòng 10 (CONTRACTS.md Mục 24) -- checkbox của phiên ĐANG ghi âm
    # (current_meeting_id) phải bị disable, "Chọn tất cả" không được đụng
    # tới nó, và nó không bao giờ lọt vào _selected_ids.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m_old = store.start_meeting(user_native_lang="vi")
            store.add_segment(m_old, "Hello", "en", 0.9, "Xin chào", "vi", is_question=False)
            m_active = store.start_meeting(user_native_lang="vi")
            store.add_segment(m_active, "Live", "en", 0.9, "Trực tiếp", "vi", is_question=False)

        dialog = MeetingHistoryDialog(db_path, current_meeting_id=m_active)
        active_row = dialog._rows_by_id[m_active]
        old_row = dialog._rows_by_id[m_old]
        assert active_row.is_selectable is False
        assert active_row._select_checkbox.isEnabled() is False
        assert old_row.is_selectable is True

        dialog._select_all_checkbox.setChecked(True)
        assert dialog._selected_ids == {m_old}
        assert active_row._select_checkbox.isChecked() is False
        dialog.close()
    print("OK: test_history_dialog_khong_cho_chon_phien_dang_ghi")


def test_history_dialog_chon_nhieu_va_xoa_vinh_vien_sau_xac_nhan(app):
    # Vòng 10 -- chọn nhiều dòng, bấm Xoá, PHẢI qua đúng hộp thoại cảnh báo/
    # xác nhận trước khi dữ liệu thật sự bị xoá khỏi DB (KHÔNG xoá mềm).
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m1, "Hello", "en", 0.9, "Xin chào", "vi", is_question=False)
            m2 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m2, "World", "en", 0.9, "Thế giới", "vi", is_question=False)
            m_keep = store.start_meeting(user_native_lang="vi")
            store.add_segment(m_keep, "Keep", "en", 0.9, "Giữ lại", "vi", is_question=False)

        dialog = MeetingHistoryDialog(db_path, current_meeting_id=None)
        dialog._rows_by_id[m1]._select_checkbox.setChecked(True)
        dialog._rows_by_id[m2]._select_checkbox.setChecked(True)
        assert dialog._selected_ids == {m1, m2}
        assert dialog._delete_button.isEnabled() is True

        # Giả lập người dùng bấm nút xác nhận "...XOÁ VĨNH VIỄN" trong
        # QMessageBox (không thể click chuột thật ở chế độ offscreen).
        def fake_exec(self):
            for button in self.buttons():
                if "XOÁ VĨNH VIỄN" in button.text():
                    self._clicked_for_test = button
            return 0

        with patch.object(QMessageBox, "exec", fake_exec), \
             patch.object(
                 QMessageBox, "clickedButton",
                 lambda self: getattr(self, "_clicked_for_test", None),
             ), \
             patch.object(QMessageBox, "information", staticmethod(lambda *a, **k: None)):
            dialog._on_delete_clicked()

        with MeetingStore(db_path) as store:
            remaining_ids = sorted(row[0] for row in store.list_meetings())
        assert remaining_ids == [m_keep], f"got {remaining_ids}"
        assert dialog._selected_ids == set(), "reload sau xoá phải reset lựa chọn"
        dialog.close()
    print("OK: test_history_dialog_chon_nhieu_va_xoa_vinh_vien_sau_xac_nhan")


def test_history_dialog_bam_huy_khong_xoa_gi(app):
    # Đối xứng với test trên -- bấm "Huỷ" trong hộp thoại xác nhận thì
    # KHÔNG được xoá bất kỳ dữ liệu nào.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m1, "Hello", "en", 0.9, "Xin chào", "vi", is_question=False)

        dialog = MeetingHistoryDialog(db_path, current_meeting_id=None)
        dialog._rows_by_id[m1]._select_checkbox.setChecked(True)

        def fake_exec_cancel(self):
            for button in self.buttons():
                if button.text() == "Huỷ":
                    self._clicked_for_test = button
            return 0

        with patch.object(QMessageBox, "exec", fake_exec_cancel), \
             patch.object(
                 QMessageBox, "clickedButton",
                 lambda self: getattr(self, "_clicked_for_test", None),
             ):
            dialog._on_delete_clicked()

        with MeetingStore(db_path) as store:
            remaining_ids = [row[0] for row in store.list_meetings()]
        assert remaining_ids == [m1], "bấm Huỷ không được xoá gì"
        dialog.close()
    print("OK: test_history_dialog_bam_huy_khong_xoa_gi")


def test_nut_chinh_co_mnemonic_rieng_biet_khong_trung(app):
    # 🔒 MỚI (Mục 32) -- mỗi nút cơ bản phải có 1 chữ cái mnemonic (&) RIÊNG,
    # không trùng nhau trong cùng cửa sổ chính -- cho phép thao tác thuần
    # bàn phím (Alt+chữ cái) mà không cần chuột.
    window = MainWindow()
    buttons = [
        window._start_button, window._stop_button, window._ask_question_button,
        window._report_button, window._history_button, window._chat_button,
        window._settings_button, window._help_button,
    ]
    mnemonics = []
    for b in buttons:
        text = b.text()
        idx = text.find("&")
        assert idx != -1 and idx + 1 < len(text), f"nút '{text}' phải có mnemonic (&)"
        mnemonics.append(text[idx + 1].upper())
    assert len(mnemonics) == len(set(mnemonics)), f"mnemonic bị trùng: {mnemonics}"
    window.close()
    print("OK: test_nut_chinh_co_mnemonic_rieng_biet_khong_trung")


def test_bam_nhieu_lan_nut_cai_dat_khong_mo_trung_cua_so(app):
    # 🔒 MỚI (Mục 34) -- bấm nút "Cài đặt" nhiều lần liên tiếp (giả lập
    # nhấn đúp/nhấn nhiều lần lỡ tay) KHÔNG được mở nhiều cửa sổ -- phải
    # TÁI SỬ DỤNG đúng 1 instance.
    window = MainWindow()
    window._on_settings_clicked()
    dialog1 = window._settings_dialog
    assert dialog1 is not None
    assert dialog1.isVisible()

    window._on_settings_clicked()
    window._on_settings_clicked()
    dialog2 = window._settings_dialog
    assert dialog2 is dialog1, "bấm nhiều lần phải tái dùng đúng 1 cửa sổ, không tạo cửa sổ mới"

    dialog1.close()
    window.close()
    print("OK: test_bam_nhieu_lan_nut_cai_dat_khong_mo_trung_cua_so")


def test_bam_nhieu_lan_nut_tro_giup_khong_mo_trung_cua_so(app):
    # 🔒 MỚI (Mục 37) -- cùng yêu cầu như Cài đặt: bấm nhiều lần chỉ tạo
    # ĐÚNG 1 cửa sổ HelpDialog.
    window = MainWindow()
    window._on_help_clicked()
    dialog1 = window._help_dialog
    assert dialog1 is not None
    assert dialog1.isVisible()

    window._on_help_clicked()
    window._on_help_clicked()
    dialog2 = window._help_dialog
    assert dialog2 is dialog1, "bấm nhiều lần phải tái dùng đúng 1 cửa sổ, không tạo cửa sổ mới"

    dialog1.close()
    window.close()
    print("OK: test_bam_nhieu_lan_nut_tro_giup_khong_mo_trung_cua_so")


def test_bam_nhieu_lan_nut_lich_su_khong_mo_trung_cua_so_va_tu_lam_moi(app):
    # 🔒 MỚI (Mục 34) -- cùng yêu cầu như Cài đặt, THÊM: mở lại lần 2 phải
    # tự refresh() danh sách (thấy được phiên họp vừa tạo sau lần mở đầu).
    from app.ui import main_window as mw_module

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        mw_module._DEFAULT_DB_PATH = db_path
        try:
            with MeetingStore(db_path) as store:
                m1 = store.start_meeting(user_native_lang="vi")

            window = MainWindow()
            window._on_history_clicked()
            dialog1 = window._history_dialog
            assert dialog1 is not None
            assert m1 in dialog1._rows_by_id

            with MeetingStore(db_path) as store:
                m2 = store.start_meeting(user_native_lang="vi")

            window._on_history_clicked()
            dialog2 = window._history_dialog
            assert dialog2 is dialog1, "bấm nhiều lần phải tái dùng đúng 1 cửa sổ"
            assert m2 in dialog2._rows_by_id, "mở lại phải refresh() tải danh sách mới nhất"

            dialog1.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
    print("OK: test_bam_nhieu_lan_nut_lich_su_khong_mo_trung_cua_so_va_tu_lam_moi")


def test_lich_su_khong_khoa_phien_da_ket_thuc_du_current_meeting_id_con_luu(app):
    # 🔒 MỚI (bugfix sau phản hồi test thật) -- `_current_meeting_id` CỐ Ý
    # không bị reset về None sau khi kết thúc phiên (để nút "Xem báo cáo"
    # dùng được ngay) -- nhưng dialog Lịch sử KHÔNG được coi phiên đã kết
    # thúc đó là "đang ghi âm cần khoá". Trước fix: `_on_history_clicked()`
    # truyền thẳng `_current_meeting_id` khiến checkbox phiên vừa kết thúc
    # bị disable vĩnh viễn -- "Chọn tất cả" bỏ qua nó, không xoá được, và
    # sqlite_sequence không bao giờ reset (xem T23, storage/db.py).
    from app.ui import main_window as mw_module

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        mw_module._DEFAULT_DB_PATH = db_path
        try:
            with MeetingStore(db_path) as store:
                m_finished = store.start_meeting(user_native_lang="vi")
                store.end_meeting(m_finished)

            window = MainWindow()
            # Mô phỏng đúng trạng thái SAU khi `_on_worker_finished()` chạy
            # xong cho phiên `m_finished`: worker đã bị drop (None) nhưng
            # `_current_meeting_id` vẫn còn giữ nguyên (cố ý, xem trên).
            window._current_meeting_id = m_finished
            window._worker = None

            window._on_history_clicked()
            dialog = window._history_dialog
            row = dialog._rows_by_id[m_finished]
            assert row.is_selectable is True, (
                "phiên ĐÃ kết thúc (worker=None) không được bị khoá chọn"
            )

            dialog._select_all_checkbox.setChecked(True)
            assert m_finished in dialog._selected_ids, (
                "'Chọn tất cả' phải chọn được cả phiên vừa kết thúc"
            )

            dialog.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
    print("OK: test_lich_su_khong_khoa_phien_da_ket_thuc_du_current_meeting_id_con_luu")


def test_bam_nhieu_lan_nut_toi_muon_hoi_khong_mo_trung_va_cap_nhat_doan_ngon_ngu(app):
    # 🔒 MỚI (Mục 34) -- cùng yêu cầu, THÊM: mở lại lần 2 phải cập nhật lại
    # "đoán ngôn ngữ đối phương" (phụ thuộc transcript gần nhất, có thể đã
    # đổi từ lần mở trước), KHÔNG đứng yên ở lần đoán đầu tiên.
    window = MainWindow()
    window._current_native_lang = "vi"
    window._recent_source_langs = []

    window._on_ask_question_clicked()
    dialog1 = window._ask_question_dialog
    assert dialog1 is not None
    assert dialog1._lang_combo.currentData() == "en"  # fallback khi chưa có dữ liệu

    window._recent_source_langs = ["vi", "zh"]
    window._on_ask_question_clicked()
    dialog2 = window._ask_question_dialog
    assert dialog2 is dialog1, "bấm nhiều lần phải tái dùng đúng 1 cửa sổ"
    assert dialog2._lang_combo.currentData() == "zh", "mở lại phải cập nhật lại đoán ngôn ngữ đối phương"

    dialog1.close()
    window.close()
    print("OK: test_bam_nhieu_lan_nut_toi_muon_hoi_khong_mo_trung_va_cap_nhat_doan_ngon_ngu")


def test_xem_bao_cao_cung_1_phien_khong_mo_trung_khac_phien_thi_mo_rieng(app):
    # 🔒 MỚI (Mục 34) -- báo cáo khoá singleton THEO meeting_id: bấm lại
    # ĐÚNG 1 phiên đang mở KHÔNG được tạo cửa sổ mới/gọi lại AI, nhưng xem
    # báo cáo phiên KHÁC vẫn phải mở cửa sổ riêng (không phải "trùng").
    from app.ui import main_window as mw_module

    call_count = {"n": 0}

    class _FakeProviderForReport:
        def __init__(self, *a, **k):
            pass

        def summarize(self, transcript_text, user_native_lang):
            call_count["n"] += 1
            return SummaryResult(overview=f"Bản {call_count['n']}", decisions=[], action_items=[])

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        original_db_path = mw_module._DEFAULT_DB_PATH
        original_provider_cls = mw_module.create_provider
        mw_module._DEFAULT_DB_PATH = db_path
        mw_module.create_provider = _FakeProviderForReport
        try:
            with MeetingStore(db_path) as store:
                m1 = store.start_meeting(user_native_lang="vi")
                store.add_segment(meeting_id=m1, original_text="Hello.", source_lang="en", confidence=0.9)
                m2 = store.start_meeting(user_native_lang="vi")
                store.add_segment(meeting_id=m2, original_text="World.", source_lang="en", confidence=0.9)

            window = MainWindow()

            window._open_report_for_meeting(m1, "vi")
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert call_count["n"] == 1
            dialog1 = window._report_dialogs[m1]

            # Bấm lại NGAY đúng phiên #m1 -- không được gọi lại AI/tạo mới.
            window._open_report_for_meeting(m1, "vi")
            assert call_count["n"] == 1, "bấm lại đúng phiên đang mở KHÔNG được gọi lại AI"
            assert window._report_dialogs[m1] is dialog1

            # Xem báo cáo phiên KHÁC (#m2) -- hợp lệ, mở cửa sổ riêng.
            window._open_report_for_meeting(m2, "vi")
            _run_event_loop_until(lambda: len(window._ai_workers) == 0, timeout_ms=3000)
            assert call_count["n"] == 2
            dialog2 = window._report_dialogs[m2]
            assert dialog2 is not dialog1, "phiên khác nhau phải là 2 cửa sổ riêng biệt"

            dialog1.close()
            dialog2.close()
            window.close()
        finally:
            mw_module._DEFAULT_DB_PATH = original_db_path
            mw_module.create_provider = original_provider_cls
    print("OK: test_xem_bao_cao_cung_1_phien_khong_mo_trung_khac_phien_thi_mo_rieng")


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_main_window_dung_duoc_khong_crash(app)
    test_thieu_api_key_khong_lam_treo_app(app)
    test_co_api_key_nhung_khong_phai_windows_van_dung_phien_hop(app)
    test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y(app)
    test_suggestion_drawer_skeleton_hien_luc_dang_tai_an_khi_co_ket_qua(app)
    test_nut_nho_ai_tra_loi_hien_o_moi_bubble_ke_ca_khong_phai_cau_hoi(app)
    test_auto_scroll_xuong_cuoi_khi_bubble_tran_man_hinh(app)
    test_auto_scroll_dung_khi_nhieu_bubble_den_lien_tiep_nhanh(app)
    test_khong_tu_cuon_neu_dang_cuon_len_doc_lich_su(app)
    test_toi_muon_hoi_dich_va_hien_readback(app)
    test_ask_question_dialog_skeleton_hien_luc_dang_dich_an_khi_co_readback(app)
    test_toi_muon_hoi_bao_loi_neu_chua_nhap_gi(app)
    test_phase2_buoc3_luu_ai_assist_vao_db_sau_khi_dich_xong(app)
    test_phase3_buoc3_hien_checkbox_va_dung_cache_khong_goi_lai_ai(app)
    test_phase3_buoc3_tao_bao_cao_moi_goi_lai_ai_va_reset_tick(app)
    test_phase3_buoc3_tick_checkbox_luu_vao_db(app)
    test_phase3_buoc3_nut_xuat_file_goi_dung_report_export(app)
    test_phase3_buoc3_xuat_file_loi_hien_export_status_khong_mat_noi_dung(app)
    test_phase3_buoc2_bao_loi_khi_chua_co_transcript(app)
    test_suggestion_drawer_va_ask_question_dung_font_segoe_ui_truc_tiep(app)
    test_on_start_clicked_huy_dialog_boi_canh_thi_khong_tao_worker(app)
    test_on_start_clicked_dong_y_dialog_thi_dung_meeting_context_da_nhap(app)
    test_on_start_clicked_truyen_dung_language_hint_da_chon(app)
    test_on_start_clicked_khong_doi_dropdown_thi_language_hint_rong(app)
    test_history_dialog_khong_cho_chon_phien_dang_ghi(app)
    test_history_dialog_chon_nhieu_va_xoa_vinh_vien_sau_xac_nhan(app)
    test_history_dialog_bam_huy_khong_xoa_gi(app)
    test_nut_chinh_co_mnemonic_rieng_biet_khong_trung(app)
    test_bam_nhieu_lan_nut_cai_dat_khong_mo_trung_cua_so(app)
    test_bam_nhieu_lan_nut_tro_giup_khong_mo_trung_cua_so(app)
    test_bam_nhieu_lan_nut_lich_su_khong_mo_trung_cua_so_va_tu_lam_moi(app)
    test_lich_su_khong_khoa_phien_da_ket_thuc_du_current_meeting_id_con_luu(app)
    test_bam_nhieu_lan_nut_toi_muon_hoi_khong_mo_trung_va_cap_nhat_doan_ngon_ngu(app)
    test_xem_bao_cao_cung_1_phien_khong_mo_trung_khac_phien_thi_mo_rieng(app)
    print("\n=== TẤT CẢ SMOKE TEST UI PASS (chế độ headless) ===")
