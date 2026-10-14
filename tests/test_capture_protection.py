"""Test offline cho capture_protection (controller), global_hotkey, ui_prefs
(config_store) và checkbox trong SettingsDialog -- dùng `user32` GIẢ (ghi lại
lời gọi), KHÔNG kiểm chứng được hành vi thật của Windows/Zoom/Teams (xem
docstring các module)."""

import ctypes
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ctypes import wintypes  # noqa: E402

from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from app import config_store  # noqa: E402
from app.ui import capture_protection as cp  # noqa: E402
from app.ui import global_hotkey as gh  # noqa: E402


class FakeUser32:
    def __init__(self, result=1, raises=None, hotkey_ok=1):
        self.calls = []  # (hwnd, affinity)
        self.hotkeys = []  # ("reg"|"unreg", args)
        self._result = result
        self._raises = raises
        self._hotkey_ok = hotkey_ok
        outer = self

        class _Affinity:
            def __call__(self, hwnd, affinity):
                if outer._raises:
                    raise outer._raises
                outer.calls.append((hwnd, affinity))
                return outer._result

        class _Reg:
            def __call__(self, hwnd, id_, mods, vk):
                outer.hotkeys.append(("reg", hwnd, id_, mods, vk))
                return outer._hotkey_ok

        class _Unreg:
            def __call__(self, hwnd, id_):
                outer.hotkeys.append(("unreg", hwnd, id_))
                return 1

        self.SetWindowDisplayAffinity = _Affinity()
        self.RegisterHotKey = _Reg()
        self.UnregisterHotKey = _Unreg()


def _app():
    return QApplication.instance() or QApplication(sys.argv)


# ---------------------------------------------------------------- env / title

def test_env_mac_dinh_tat_va_nhan_dung_gia_tri_bat():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(cp.ENV_VAR, None)
        assert cp.is_enabled_from_env() is False
    for v in ("1", "true", "YES", " on "):
        with patch.dict(os.environ, {cp.ENV_VAR: v}):
            assert cp.is_enabled_from_env() is True
    with patch.dict(os.environ, {cp.ENV_VAR: "0"}):
        assert cp.is_enabled_from_env() is False


def test_window_title_suffix():
    assert cp.window_title_suffix(False, True) == ""
    assert "🛡" in cp.window_title_suffix(True, True)
    assert "⚠" in cp.window_title_suffix(True, False)


# ----------------------------------------------------------------- controller

def test_chua_tung_bat_thi_hoan_toan_khong_goi_api():
    app = _app()
    fake = FakeUser32()
    ctrl = cp.CaptureProtectionController(fake, enabled=False)
    app.installEventFilter(ctrl)
    w = QWidget()
    try:
        w.show()
        ctrl.apply_to_visible_windows()
        assert fake.calls == []
    finally:
        app.removeEventFilter(ctrl)
        w.close()


def test_bat_san_show_top_level_goi_dung_hwnd_va_co_0x11_con_widget_con_thi_khong():
    app = _app()
    fake = FakeUser32()
    ctrl = cp.CaptureProtectionController(fake, enabled=True)
    app.installEventFilter(ctrl)
    win, dlg = QWidget(), QDialog()
    child = QWidget(win)
    try:
        win.show()
        dlg.show()
        hwnds = {c[0] for c in fake.calls}
        assert hwnds == {int(win.winId()), int(dlg.winId())}  # child không bị áp riêng
        assert child.isWindow() is False
        assert all(c[1] == cp.WDA_EXCLUDEFROMCAPTURE == 0x11 for c in fake.calls)
    finally:
        app.removeEventFilter(ctrl)
        win.close()
        dlg.close()


def test_set_enabled_ap_ngay_cho_cua_so_dang_hien_roi_go_bang_wda_none():
    app = _app()
    fake = FakeUser32()
    saved = []
    ctrl = cp.CaptureProtectionController(fake, enabled=False, persist=saved.append)
    app.installEventFilter(ctrl)
    emitted = []
    ctrl.changed.connect(lambda e, ok: emitted.append((e, ok)))
    w = QWidget()
    w.show()
    try:
        assert ctrl.set_enabled(True) is True
        assert (int(w.winId()), 0x11) in fake.calls
        fake.calls.clear()
        assert ctrl.set_enabled(False) is True
        assert (int(w.winId()), cp.WDA_NONE) in fake.calls
        assert saved == [True, False]
        assert emitted == [(True, True), (False, True)]
        assert ctrl.toggle() is True and ctrl.enabled is True
    finally:
        app.removeEventFilter(ctrl)
        w.close()


def test_that_bai_khi_bat_dat_ok_false_phat_signal_va_chi_log_1_lan():
    app = _app()
    for fake in (FakeUser32(result=0), FakeUser32(raises=OSError("boom"))):
        ctrl = cp.CaptureProtectionController(fake, enabled=False)
        emitted = []
        ctrl.changed.connect(lambda e, ok, em=emitted: em.append((e, ok)))
        w1, w2 = QWidget(), QWidget()
        w1.show()
        w2.show()
        try:
            with patch.object(cp, "get_logger") as lg:
                assert ctrl.set_enabled(True) is False
                assert ctrl.ok is False
                assert emitted[-1] == (True, False)
                assert lg.return_value.warning.call_count == 1
        finally:
            w1.close()
            w2.close()


def test_that_bai_khi_tat_khong_danh_dau_loi():
    app = _app()
    fake = FakeUser32(result=0)
    ctrl = cp.CaptureProtectionController(fake, enabled=True)
    w = QWidget()
    w.show()
    try:
        assert ctrl.set_enabled(False) is True  # tắt: lỗi API không được báo "không ẩn được"
    finally:
        w.close()


def test_luu_lua_chon_loi_khong_chan_viec_doi_trang_thai():
    app = _app()

    def boom(_v):
        raise config_store.ConfigStoreError("disk full")

    ctrl = cp.CaptureProtectionController(FakeUser32(), enabled=False, persist=boom)
    assert ctrl.set_enabled(True) is True
    assert ctrl.enabled is True


# ---------------------------------------------------------------- install()

def test_install_khong_phai_windows_tra_ve_none_va_get_controller_none():
    app = _app()
    cp._reset_for_tests()
    with patch.object(cp, "_get_user32", return_value=None):
        assert cp.install(app) is None
    assert cp.get_controller() is None


def test_install_uu_tien_lua_chon_da_luu_hon_env_va_dang_ky_hotkey_dung():
    app = _app()
    cp._reset_for_tests()
    fake = FakeUser32()
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ, {"APPDATA": tmp, cp.ENV_VAR: "1"}
    ), patch.object(cp, "_get_user32", return_value=fake):
        config_store.save_hide_from_capture(False)  # đã chọn TẮT -> thắng env=1
        ctrl = cp.install(app)
        try:
            assert ctrl is not None and ctrl.enabled is False
            assert cp.get_controller() is ctrl
            reg = [h for h in fake.hotkeys if h[0] == "reg"]
            assert len(reg) == 1
            _, hwnd, _id, mods, vk = reg[0]
            assert hwnd is None
            assert mods == gh.MOD_CONTROL | gh.MOD_ALT | gh.MOD_SHIFT | gh.MOD_NOREPEAT
            assert vk == gh.VK_F9
            # toggle qua controller phải ghi xuống đĩa
            ctrl.set_enabled(True)
            assert config_store.load_hide_from_capture() is True
        finally:
            app.removeEventFilter(ctrl)
            app.removeNativeEventFilter(ctrl._hotkey)
            cp._reset_for_tests()


def test_install_chua_tung_chon_thi_theo_env():
    app = _app()
    cp._reset_for_tests()
    fake = FakeUser32()
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ, {"APPDATA": tmp, cp.ENV_VAR: "1"}
    ), patch.object(cp, "_get_user32", return_value=fake):
        ctrl = cp.install(app)
        try:
            assert ctrl.enabled is True
        finally:
            app.removeEventFilter(ctrl)
            app.removeNativeEventFilter(ctrl._hotkey)
            cp._reset_for_tests()


def test_install_van_chay_khi_hotkey_bi_app_khac_chiem():
    app = _app()
    cp._reset_for_tests()
    fake = FakeUser32(hotkey_ok=0)
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ, {"APPDATA": tmp}
    ), patch.object(cp, "_get_user32", return_value=fake):
        ctrl = cp.install(app)
        try:
            assert ctrl is not None  # checkbox vẫn dùng được
        finally:
            app.removeEventFilter(ctrl)
            cp._reset_for_tests()


# ------------------------------------------------------------- global hotkey

def _fake_msg(message, wparam):
    msg = wintypes.MSG()
    msg.message = message
    msg.wParam = wparam

    class _Ptr:
        def __int__(self_inner):  # noqa: N805
            return ctypes.addressof(msg)

    return msg, _Ptr()


def test_hotkey_native_event_dung_id_thi_goi_callback_va_nuot_event():
    calls = []
    hk = gh.GlobalHotkey(FakeUser32(), lambda: calls.append(1), gh.MOD_CONTROL, gh.VK_F9, hotkey_id=77)
    msg, ptr = _fake_msg(gh.WM_HOTKEY, 77)
    assert hk.nativeEventFilter(b"windows_generic_MSG", ptr) == (True, 0)
    assert calls == [1]


def test_hotkey_bo_qua_event_khong_lien_quan():
    calls = []
    hk = gh.GlobalHotkey(FakeUser32(), lambda: calls.append(1), gh.MOD_CONTROL, gh.VK_F9, hotkey_id=77)
    msg, ptr = _fake_msg(gh.WM_HOTKEY, 99)  # id khác
    assert hk.nativeEventFilter(b"windows_generic_MSG", ptr) == (False, 0)
    msg2, ptr2 = _fake_msg(0x0100, 77)  # không phải WM_HOTKEY
    assert hk.nativeEventFilter(b"windows_generic_MSG", ptr2) == (False, 0)
    assert hk.nativeEventFilter(b"xcb_generic_event_t", ptr) == (False, 0)  # sai nền tảng
    assert calls == []


def test_hotkey_callback_loi_khong_lam_hong_event_loop():
    def boom():
        raise RuntimeError("x")

    hk = gh.GlobalHotkey(FakeUser32(), boom, gh.MOD_CONTROL, gh.VK_F9, hotkey_id=77)
    msg, ptr = _fake_msg(gh.WM_HOTKEY, 77)
    assert hk.nativeEventFilter(b"windows_generic_MSG", ptr) == (False, 0)


def test_hotkey_register_unregister():
    fake = FakeUser32()
    hk = gh.GlobalHotkey(fake, lambda: None, gh.MOD_CONTROL, gh.VK_F9, hotkey_id=77)
    assert hk.register() is True and hk.registered
    hk.unregister()
    assert not hk.registered
    assert [h[0] for h in fake.hotkeys] == ["reg", "unreg"]
    assert gh.GlobalHotkey(FakeUser32(hotkey_ok=0), lambda: None, 0, 0).register() is False


# -------------------------------------------------------------- ui_prefs

def test_ui_prefs_round_trip_mac_dinh_none_va_file_hong():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        assert config_store.load_hide_from_capture(base_dir=base) is None
        config_store.save_hide_from_capture(True, base_dir=base)
        assert config_store.load_hide_from_capture(base_dir=base) is True
        config_store.save_hide_from_capture(False, base_dir=base)
        assert config_store.load_hide_from_capture(base_dir=base) is False
        config_store.get_ui_prefs_path(base).write_text("{hong", encoding="utf-8")
        assert config_store.load_hide_from_capture(base_dir=base) is None
        config_store.get_ui_prefs_path(base).write_text('{"hide_from_capture": "yes"}', encoding="utf-8")
        assert config_store.load_hide_from_capture(base_dir=base) is None


def test_ui_prefs_giu_field_khac_va_khong_bi_save_api_key_xoa():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        path = config_store.get_ui_prefs_path(base)
        path.write_text(json.dumps({"other": 1}), encoding="utf-8")
        config_store.save_hide_from_capture(True, base_dir=base)
        assert json.loads(path.read_text(encoding="utf-8")) == {"other": 1, "hide_from_capture": True}
        # save_api_key/clear_api_key dựng lại config.json từ đầu -- tuỳ chọn ở file RIÊNG nên phải còn nguyên
        config_store.save_api_key("k-123", provider="groq", base_dir=base)
        config_store.set_active_provider("openai", base_dir=base)
        config_store.clear_api_key(provider="groq", base_dir=base)
        assert config_store.load_hide_from_capture(base_dir=base) is True


# -------------------------------------------------------- SettingsDialog

def test_settings_dialog_checkbox_dong_bo_voi_controller():
    from app.ui.settings_dialog import SettingsDialog

    app = _app()
    cp._reset_for_tests()
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"APPDATA": tmp}):
        # 1) không có controller (không phải Windows) -> checkbox bị vô hiệu
        dlg0 = SettingsDialog()
        assert dlg0._capture_checkbox.isEnabled() is False
        dlg0.close()

        # 2) có controller
        fake = FakeUser32()
        ctrl = cp.CaptureProtectionController(fake, enabled=False)
        cp._controller = ctrl
        try:
            dlg = SettingsDialog()
            dlg.show()
            assert dlg._capture_checkbox.isEnabled() and not dlg._capture_checkbox.isChecked()
            assert "HIỆN" in dlg._capture_note.text()

            dlg._capture_checkbox.click()  # tick -> áp NGAY, không cần nút Lưu
            assert ctrl.enabled is True
            assert "🛡" in dlg._capture_note.text()

            ctrl.set_enabled(False)  # như bấm phím tắt -> checkbox tự cập nhật
            assert dlg._capture_checkbox.isChecked() is False

            fake._result = 0  # API thất bại -> KHÔNG được báo "đang ẩn"
            dlg._capture_checkbox.click()
            assert ctrl.ok is False
            assert "⚠" in dlg._capture_note.text() and "🛡" not in dlg._capture_note.text()
            dlg.close()
        finally:
            cp._reset_for_tests()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK")
