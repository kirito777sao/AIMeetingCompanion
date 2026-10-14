"""
app/ui/global_hotkey.py
-----------------------
Phím tắt TOÀN CỤC (hoạt động cả khi app họp như Zoom/Teams đang giữ focus)
trên Windows, qua `RegisterHotKey` + `QAbstractNativeEventFilter` -- không
thêm dependency (ctypes là stdlib). `QShortcut` của Qt KHÔNG dùng được ở đây
vì chỉ hoạt động khi chính app này đang được focus.

`RegisterHotKey(NULL, ...)` gắn hotkey với THREAD gọi nó -> PHẢI gọi
`register()` từ GUI thread (thread chạy event loop Qt), nơi `WM_HOTKEY` được
đẩy tới. Nếu tổ hợp phím đã bị app khác chiếm, `register()` trả False (không
raise) -- người gọi tự log + vẫn dùng được checkbox trong Settings.

⚠️ CHƯA verify được trên Windows thật trong sandbox Linux: phần PARSE message
(`MSG.from_address`) và logic đăng ký/huỷ đã test bằng user32 giả + struct
MSG thật; việc Windows thực sự đẩy WM_HOTKEY vào native event filter của Qt
cần bạn tự test (xem CHANGELOG.md).
"""

from __future__ import annotations

from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000  # giữ phím không bắn lặp liên tục
VK_F9 = 0x78

_NATIVE_EVENT_TYPE = b"windows_generic_MSG"


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(
        self,
        user32,
        callback: Callable[[], None],
        modifiers: int,
        vk: int,
        hotkey_id: int = 0x4D43,
    ) -> None:
        super().__init__()
        self._user32 = user32
        self._callback = callback
        self._modifiers = modifiers
        self._vk = vk
        self._id = hotkey_id
        self._registered = False

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self) -> bool:
        if self._registered:
            return True
        try:
            ok = bool(
                self._user32.RegisterHotKey(
                    None, self._id, self._modifiers | MOD_NOREPEAT, self._vk
                )
            )
        except Exception:  # noqa: BLE001 - lỗi ctypes lạ không được làm app crash
            ok = False
        self._registered = ok
        return ok

    def unregister(self) -> None:
        if not self._registered:
            return
        try:
            self._user32.UnregisterHotKey(None, self._id)
        except Exception:  # noqa: BLE001
            pass
        self._registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - tên theo Qt convention
        try:
            raw = event_type.data() if hasattr(event_type, "data") else event_type
            if bytes(raw) != _NATIVE_EVENT_TYPE:
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._id:
                self._callback()
                return True, 0
        except Exception:  # noqa: BLE001 - không để lỗi parse làm hỏng event loop Qt
            return False, 0
        return False, 0
