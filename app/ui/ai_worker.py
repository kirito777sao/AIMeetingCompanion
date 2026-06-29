"""
ui/ai_worker.py
----------------
Phase 2: chạy 1 lệnh AIProvider bất kỳ (suggest_answer()/translate()) trên
1 thread riêng, kích hoạt bởi hành động người dùng (bấm nút) trên main thread.

⚠️ Quyết định kiến trúc quan trọng: KHÔNG tái dùng `AudioWorker` (đang chạy
vòng lặp audio liên tục, xem main_window.py) để gọi suggest_answer()/
translate() khi người dùng bấm nút. Lý do:

1. `AudioWorker.run()` là 1 vòng lặp imperative (`for chunk in
   stream_loopback_chunks(): ...`), KHÔNG gọi `self.exec()` -> thread đó
   KHÔNG có event loop Qt đang chạy để nhận signal/slot qua queued
   connection. Một slot gắn vào AudioWorker sẽ KHÔNG được gọi cho tới khi
   vòng lặp audio tự nhường lại quyền điều khiển (không bao giờ xảy ra
   trong lúc đang ghi) -- nối signal vào AudioWorker sẽ bị "treo" vô thời
   hạn, không phải lỗi dễ thấy ngay (signal vẫn "emit" được, chỉ là handler
   không bao giờ chạy).
2. Dù có giải được vấn đề (1) bằng cách chèn logic check-queue vào giữa
   vòng lặp audio, suggest_answer()/translate() mất 1-3s — chèn vào giữa
   vòng lặp đang đọc audio realtime có rủi ro làm trễ/rớt audio buffer của
   hệ thống (audio loopback không "đợi" app xử lý xong).

-> Mỗi lần người dùng bấm "Nhờ AI trả lời" / "Dịch & Sẵn sàng nói" sẽ tạo
1 `OneShotAIWorker` MỚI, độc lập, tự tạo 1 `AIProvider` riêng (qua
`provider_factory.create_provider()` — Groq/OpenAI/Gemini tuỳ người dùng
chọn ở Settings, xem CONTRACTS.md Mục 17; provider không giữ tài nguyên
ràng buộc thread như SQLite connection -- xem CONTRACTS.md Mục 3, an toàn
để tạo nhiều instance) — không đụng gì tới AudioWorker đang chạy.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QThread, Signal

from app.ai.base_provider import ProviderError


class OneShotAIWorker(QThread):
    """Chạy đúng 1 lần `action_fn()` (không tham số, tự đóng gói qua closure)
    trên thread riêng, emit kết quả hoặc lỗi qua signal. Dùng 1 instance cho
    1 hành động — không tái sử dụng lại sau khi đã `start()`.

    ⚠️ **`succeeded` đổi từ `Signal(str)` sang `Signal(object)` ở Phase 3**:
    Phase 2 chỉ cần mang `str` (gợi ý trả lời/bản dịch), nhưng Phase 3
    (`summarize()`) trả về `SummaryResult` (object có cấu trúc, không phải
    str) — đúng tinh thần docstring gốc của class này ("chạy 1 lệnh
    AIProvider BẤT KỲ"), không phải method riêng cho Phase 2. `Signal(object)`
    của PySide6/Qt vẫn marshal an toàn qua queued connection giữa thread
    (cơ chế chuẩn để truyền Python object qua signal cross-thread), và
    `str` vẫn là 1 `object` hợp lệ — KHÔNG cần sửa gì ở các chỗ gọi Phase 2
    hiện có (`drawer.set_answer`, `dialog.show_readback`, ...)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action_fn: Callable[[], object], parent=None) -> None:
        super().__init__(parent)
        self._action_fn = action_fn

    def run(self) -> None:
        try:
            result = self._action_fn()
        except ProviderError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - không để lỗi lạ làm app crash
            self.failed.emit(f"Lỗi không xác định: {exc}")
            return
        self.succeeded.emit(result)
