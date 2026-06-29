"""
app/report.py
--------------
Helper DÙNG CHUNG cho mọi nơi cần build transcript_text để gọi
`AIProvider.summarize()` — tách riêng ra khỏi `scripts/test_summarize.py`
khi thêm `ui/report_view.py` (Phase 3 Bước 2), để KHÔNG có 2 bản copy lệch
nhau của cùng 1 logic ghép transcript (CONTRACTS.md Mục 4 quy định rõ
ràng buộc "dùng original_text, KHÔNG dùng bản đã dịch" — quy tắc này nên
chỉ tồn tại ở ĐÚNG 1 chỗ).
"""

from __future__ import annotations

from app.storage.db import MeetingStore


def build_transcript_text(store: MeetingStore, meeting_id: int) -> str:
    """Ghép `original_text` của mọi segment theo thứ tự thời gian — ĐÚNG
    NHƯ contract đã chốt ở AIProvider.summarize() (dùng original_text,
    KHÔNG dùng bản đã dịch, tránh cộng dồn lỗi dịch vào bản tóm tắt).

    Trả về "" nếu phiên họp không có segment nào (transcript rỗng) — caller
    tự quyết định xử lý ra sao (CLI script thoát sớm với message; UI hiện
    lỗi thân thiện trong dialog), function này không tự `raise`/`exit` để
    dùng được ở cả 2 ngữ cảnh.
    """
    segments = store.get_segments(meeting_id)
    if not segments:
        return ""
    return "\n".join(seg.original_text for seg in segments)
