"""
run_app.py
----------
🔒 MỚI (chuẩn bị đóng gói .exe, xem CONTRACTS.md Mục 40 + packaging/HUONG_DAN_DONG_GOI_EXE.md).

Entry point RIÊNG cho PyInstaller — KHÔNG dùng trực tiếp `app/main.py` làm
entry point khi đóng gói, vì:

Chạy từ source dùng `python -m app.main` — cờ `-m` tự thêm PROJECT ROOT
(thư mục chứa `app/`) vào `sys.path`, nhờ vậy `from app.logging_setup
import ...` bên trong `app/main.py` mới import được (`app` được coi là 1
package nằm TRONG project root).

PyInstaller khi được trỏ thẳng vào `app/main.py` lại mặc định thêm thư mục
CHỨA file đó (tức `app/`) vào `sys.path` — SAI cấp, khiến `from app.xxx
import yyy` bên trong chính `app/main.py` lỗi `ModuleNotFoundError: No
module named 'app'` ngay khi mở app đã đóng gói (KHÔNG lỗi lúc chạy từ
source vì `-m` che mất vấn đề này — đây là lý do bug loại này thường CHỈ
lộ ra sau khi đóng gói, không lộ lúc dev bình thường).

File NÀY nằm ở PROJECT ROOT (cùng cấp với thư mục `app/`) — PyInstaller
trỏ vào ĐÂY thay vì `app/main.py`, tự thêm ĐÚNG project root vào
`sys.path` trước khi import `app.main`, y hệt hiệu ứng `-m` lúc chạy từ
source.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Đảm bảo project root nằm trong sys.path -- an toàn kể cả khi PyInstaller
# hoặc cách gọi khác không tự thêm đúng (belt-and-suspenders, không hại gì
# nếu đã có sẵn -- Python bỏ qua path trùng).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import main  # noqa: E402 (phải đặt sau dòng sys.path.insert ở trên)

if __name__ == "__main__":
    sys.exit(main())
