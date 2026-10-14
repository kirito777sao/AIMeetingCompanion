"""
app/ui/capture_protection.py
----------------------------
Ẩn TOÀN BỘ cửa sổ của app khỏi screen share / screen recording / screenshot
(Zoom, Teams, Meet, OBS "Window/Display capture", Snipping Tool...) trong khi
bạn vẫn nhìn thấy bình thường trên màn hình của chính mình. BẬT/TẮT được
LÚC ĐANG CHẠY qua checkbox ở ⚙️ Cài đặt hoặc phím tắt toàn cục
`Ctrl+Alt+Shift+F9` (xem global_hotkey.py).

Cơ chế (Windows): `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`.
Qt/PySide6 KHÔNG có API này -> gọi thẳng qua `ctypes` (stdlib, không thêm
dependency, cùng tinh thần `config_store.py` gọi DPAPI).

QUYẾT ĐỊNH THIẾT KẾ (đọc trước khi sửa):
1. MẶC ĐỊNH TẮT. Trạng thái khởi động = lựa chọn ĐÃ LƯU (ui_prefs.json, do
   checkbox/phím tắt ghi) nếu có, nếu chưa từng chọn thì lấy theo
   `AI_MEETING_HIDE_FROM_CAPTURE=1` trong `.env`. Lý do tắt mặc định: app
   được đóng gói .exe cho người khác dùng -- cửa sổ "tự biến mất khi quay
   màn hình" bật sẵn sẽ gây bất ngờ + khó chụp screenshot báo lỗi.
2. Áp cho MỌI top-level window (kể cả QDialog, QMenu popup, tooltip) qua 1
   event filter ở tầng QApplication, thay vì sửa từng class -- sót 1 dialog
   thì dialog đó sẽ lộ ra trong buổi share. Áp ở cả `WinIdChange` (lúc tạo
   handle) lẫn `Show` để giảm khoảng hở trước khi cửa sổ hiện.
3. KHÔNG fallback sang `WDA_MONITOR` (0x01) khi Windows cũ không hỗ trợ
   0x11: chế độ đó khiến người xem thấy 1 KHỐI ĐEN đúng chỗ cửa sổ -- còn
   lộ hơn là không ẩn. Thà báo lỗi rõ ràng.
4. KHÔNG báo "đang ẩn" nếu API thất bại: `ok=False` + tiêu đề cửa sổ hiện
   ⚠ (xem `window_title_suffix`). Giả vờ an toàn nguy hiểm hơn là cảnh báo.
5. Khi chưa từng bật, controller HOÀN TOÀN không gọi API Windows nào.

GIỚI HẠN THẬT (không nhận vơ):
- Chỉ chặn capture ở tầng hệ điều hành. KHÔNG chặn: quay bằng điện thoại,
  capture card phần cứng, phần mềm giám sát cấp driver/kernel.
- `WDA_EXCLUDEFROMCAPTURE` cần Windows 10 bản 2004 (build 19041) trở lên.
- ⚠️ Tắt bằng phím tắt giữa buổi share = cửa sổ LỘ NGAY LẬP TỨC với mọi
  người đang xem. Tiêu đề cửa sổ (🛡 / ⚠) là chỉ báo trạng thái duy nhất.
- ⚠️ CHƯA verify được trên Windows thật + Zoom/Teams thật trong sandbox
  này (Linux). Đã verify: logic controller, đúng cờ/đúng HWND, nhánh lỗi
  không crash (user32 giả). Cần bạn tự test (checklist ở CHANGELOG.md).
"""

from __future__ import annotations

import ctypes
import os
import platform
from ctypes import wintypes
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from app import config_store
from app.logging_setup import get_logger
from app.ui import global_hotkey

ENV_VAR = "AI_MEETING_HIDE_FROM_CAPTURE"

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004+

# Chọn tổ hợp F-key dài, khó bấm nhầm: bấm nhầm = lộ cửa sổ ra buổi share.
# Tránh Ctrl+Shift+H (theo mình nhớ là "cúp máy" của Teams).
HOTKEY_LABEL = "Ctrl+Alt+Shift+F9"
_HOTKEY_MODIFIERS = global_hotkey.MOD_CONTROL | global_hotkey.MOD_ALT | global_hotkey.MOD_SHIFT
_HOTKEY_VK = global_hotkey.VK_F9

_controller: Optional["CaptureProtectionController"] = None


def is_enabled_from_env() -> bool:
    """True nếu `.env`/biến môi trường bật tính năng (1/true/yes/on)."""
    return os.environ.get(ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def window_title_suffix(enabled: bool, ok: bool) -> str:
    """Hậu tố tiêu đề cửa sổ chính -- chỉ báo trạng thái cục bộ (người xem
    không thấy khi đang ẩn)."""
    if not enabled:
        return ""
    return " 🛡 (ẩn khỏi share)" if ok else " ⚠ (KHÔNG ẩn được khỏi share)"


def get_controller() -> Optional["CaptureProtectionController"]:
    """Controller đã cài (singleton), hoặc None (không phải Windows / chưa
    cài). UI dùng để hiện checkbox -- None => checkbox bị vô hiệu."""
    return _controller


def _get_user32():
    """Trả về `user32` đã khai báo kiểu tham số, hoặc None nếu không phải
    Windows. Tách riêng để test thay bằng đối tượng giả."""
    if platform.system() != "Windows":
        return None
    user32 = ctypes.windll.user32
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    return user32


class CaptureProtectionController(QObject):
    """Giữ trạng thái bật/tắt + áp affinity cho mọi top-level window.

    Signal `changed(enabled, ok)`: `ok=False` nghĩa là đang BẬT nhưng ít nhất
    1 cửa sổ KHÔNG áp được affinity (vẫn hiện trong screen share)."""

    changed = Signal(bool, bool)

    def __init__(
        self,
        user32,
        enabled: bool = False,
        persist: Optional[Callable[[bool], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._user32 = user32
        self._enabled = bool(enabled)
        self._persist = persist
        self._ok = True
        # Chỉ gọi WDA_NONE khi đã TỪNG bật -- chưa bật bao giờ thì không đụng API.
        self._touched = self._enabled
        self._warned = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def ok(self) -> bool:
        return self._ok

    def toggle(self) -> bool:
        return self.set_enabled(not self._enabled)

    def set_enabled(self, enabled: bool, persist: bool = True) -> bool:
        """Đổi trạng thái, áp NGAY cho mọi cửa sổ đang hiện (cửa sổ đang ẩn
        sẽ được áp ở lần Show kế tiếp). Trả về `ok`."""
        self._enabled = bool(enabled)
        if self._enabled:
            self._touched = True
        self._ok = True
        self.apply_to_visible_windows()
        if persist and self._persist is not None:
            try:
                self._persist(self._enabled)
            except Exception as exc:  # noqa: BLE001 - lỗi lưu không được chặn việc đổi trạng thái
                get_logger().warning("capture_protection: không lưu được lựa chọn (%s)", exc)
        get_logger().info(
            "capture_protection: %s (ok=%s)", "BẬT" if self._enabled else "TẮT", self._ok
        )
        self.changed.emit(self._enabled, self._ok)
        return self._ok

    def apply_to_visible_windows(self) -> None:
        for w in QApplication.topLevelWidgets():
            if w.isVisible():
                self._apply(w)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - tên theo Qt convention
        if (
            event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange)
            and isinstance(obj, QWidget)
            and obj.isWindow()
        ):
            was_ok = self._ok
            self._apply(obj)
            if was_ok != self._ok:
                self.changed.emit(self._enabled, self._ok)
        return False

    def _apply(self, widget: QWidget) -> bool:
        """Đặt affinity theo trạng thái hiện tại. Không raise -- lỗi chỉ log
        (1 lần) và đặt `ok=False` nếu đang BẬT."""
        if not self._enabled and not self._touched:
            return True
        affinity = WDA_EXCLUDEFROMCAPTURE if self._enabled else WDA_NONE
        try:
            hwnd = int(widget.winId())
            if hwnd == 0:  # WinIdChange lúc handle đang bị huỷ
                return True
            ok = bool(self._user32.SetWindowDisplayAffinity(hwnd, affinity))
        except Exception as exc:  # noqa: BLE001 - lỗi ctypes/Qt lạ không được làm app crash
            self._fail(f"lỗi khi gọi SetWindowDisplayAffinity: {exc}")
            return False
        if not ok:
            self._fail(
                "SetWindowDisplayAffinity trả về thất bại (Windows < 10 bản "
                "2004 không hỗ trợ WDA_EXCLUDEFROMCAPTURE?) -- cửa sổ này "
                "VẪN HIỆN trong screen share."
            )
        return ok

    def _fail(self, msg: str) -> None:
        if self._enabled:
            self._ok = False
        if not self._warned:
            self._warned = True
            get_logger().warning("capture_protection: %s", msg)


def install(app: QApplication) -> Optional[CaptureProtectionController]:
    """Gọi 1 lần ở `main()` SAU khi tạo QApplication, TRƯỚC `window.show()`.
    Trả về controller (người gọi nên giữ tham chiếu) hoặc None nếu không
    phải Windows. Luôn cài (kể cả đang tắt) để bật được lúc đang chạy."""
    global _controller
    user32 = _get_user32()
    if user32 is None:
        if is_enabled_from_env():
            get_logger().warning(
                "capture_protection: %s=1 nhưng không phải Windows -- bỏ qua.", ENV_VAR
            )
        return None

    saved = config_store.load_hide_from_capture()
    initial = saved if saved is not None else is_enabled_from_env()

    ctrl = CaptureProtectionController(
        user32, enabled=initial, persist=config_store.save_hide_from_capture, parent=app
    )
    app.installEventFilter(ctrl)
    if initial:
        ctrl.apply_to_visible_windows()
        get_logger().info("capture_protection: BẬT lúc khởi động.")

    hotkey = global_hotkey.GlobalHotkey(user32, ctrl.toggle, _HOTKEY_MODIFIERS, _HOTKEY_VK)
    if hotkey.register():
        app.installNativeEventFilter(hotkey)
        app.aboutToQuit.connect(hotkey.unregister)
        ctrl._hotkey = hotkey  # giữ tham chiếu, tránh bị GC
        get_logger().info("capture_protection: phím tắt toàn cục %s sẵn sàng.", HOTKEY_LABEL)
    else:
        get_logger().warning(
            "capture_protection: không đăng ký được phím tắt %s (đã bị app khác "
            "chiếm?) -- vẫn bật/tắt được bằng checkbox trong ⚙️ Cài đặt.",
            HOTKEY_LABEL,
        )

    _controller = ctrl
    return ctrl


def _reset_for_tests() -> None:
    global _controller
    _controller = None
