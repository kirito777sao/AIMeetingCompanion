"""
storage/db.py
--------------
Lưu transcript theo phiên họp vào SQLite local. Schema xem CONTRACTS.md Mục 5.

Quy ước threading (CONTRACTS.md Mục 3): mỗi worker thread tự mở 1
`MeetingStore` riêng (1 connection riêng), KHÔNG share 1 connection giữa
nhiều thread. Vì vậy class này KHÔNG tự làm singleton/global — main.py chịu
trách nhiệm tạo đúng 1 instance trong worker thread đang xử lý audio.

Không lưu audio thô (đúng nguyên tắc riêng tư PROJECT_SPEC.md mục 2) — chỉ
lưu text.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class StorageError(RuntimeError):
    """Lỗi khi đọc/ghi SQLite (file lỗi, schema sai, v.v.)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SegmentRecord:
    """1 dòng trong bảng `segments`, dùng khi đọc lại transcript (vd cho
    report Phase 3 hoặc lịch sử F13)."""

    id: int
    meeting_id: int
    created_at: str
    original_text: str
    source_lang: str
    confidence: float
    translated_text: Optional[str]
    target_lang: Optional[str]
    is_question: bool


@dataclass
class ActionItemRecord:
    """1 "việc cần làm" trong báo cáo ĐÃ LƯU — khác `SummaryResult.action_items`
    (list[str] thô từ AIProvider, xem base_provider.py), record này có thêm
    `done` để hỗ trợ tick checkbox hoàn thành (PROJECT_SPEC.md Mục 10.4,
    Phase 3 Bước 3/4) — cố tình KHÔNG thêm field này vào `SummaryResult` vì
    đó là contract của TẦNG AI (🔒 đã chốt, CONTRACTS.md Mục 4): model chỉ
    có nhiệm vụ sinh NỘI DUNG action item, không biết/không cần biết gì về
    trạng thái tick UI — tách trạng thái "đã làm hay chưa" ra tầng storage
    để không phá vỡ contract đã chốt của AIProvider."""

    text: str
    done: bool


@dataclass
class ReportRecord:
    """1 báo cáo ĐÃ LƯU cho 1 phiên họp (bảng `meeting_reports`, Phase 3
    Bước 3/4) — MỖI meeting_id chỉ giữ ĐÚNG 1 báo cáo mới nhất (KHÔNG lưu
    lịch sử nhiều lần "Tạo báo cáo mới", xem docstring `save_report()`).
    Tách riêng record này khỏi `SummaryResult` (tầng AI) vì đây là tầng đã
    PERSIST + có thêm trạng thái done của action items mà AIProvider không
    biết tới."""

    meeting_id: int
    generated_at: str
    overview: str
    decisions: list[str]
    action_items: list[ActionItemRecord]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    user_native_lang TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id),
    created_at      TEXT NOT NULL,
    original_text   TEXT NOT NULL,
    source_lang     TEXT NOT NULL,
    confidence      REAL NOT NULL,
    translated_text TEXT,
    target_lang     TEXT,
    is_question     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_segments_meeting_id ON segments(meeting_id);

-- Phase 2 Bước 3/3: lưu lịch sử AI đã hỗ trợ trong phiên họp -- trước đây
-- mọi gợi ý trả lời / câu tự đặt qua "Tôi muốn hỏi" chỉ hiện tạm trong
-- dialog rồi MẤT khi đóng lại, không có cách nào xem lại sau. Cần thiết để
-- Phase 3 (báo cáo cuộc họp) có thể thể hiện cả phần AI đã hỗ trợ, không
-- chỉ transcript thô.
CREATE TABLE IF NOT EXISTS ai_assists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id),
    created_at      TEXT NOT NULL,
    kind            TEXT NOT NULL,      -- 'suggest_answer' | 'ask_question'
    source_text     TEXT NOT NULL,      -- câu hỏi gốc (suggest_answer) hoặc câu user tự nhập (ask_question)
    ai_output       TEXT,               -- gợi ý AI soạn, NGÔN NGỮ MẸ ĐẺ, đã qua sửa tay (suggest_answer); NULL với ask_question (không có bước AI soạn)
    final_text      TEXT,               -- bản dịch cuối cùng đã đọc lên, ngôn ngữ đối phương
    target_lang     TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_assists_meeting_id ON ai_assists(meeting_id);

-- Phase 3 Bước 3/4: lưu báo cáo (tổng hợp biên bản) đã tạo cho 1 phiên họp,
-- để (a) mở lại dialog "Xem báo cáo" KHÔNG phải gọi lại summarize() mỗi lần
-- (tốn quota free-tier + chậm vô ích nếu nội dung không đổi), (b) giữ trạng
-- thái tick checkbox "việc cần làm đã xong" (PROJECT_SPEC.md Mục 10.4) qua
-- lần mở lại app, kể cả sau khi tắt máy. `meeting_id` làm PRIMARY KEY trực
-- tiếp (không AUTOINCREMENT riêng) vì mỗi phiên họp CHỦ Ý chỉ giữ ĐÚNG 1
-- báo cáo mới nhất -- nút "Tạo báo cáo mới" ghi ĐÈ (REPLACE) báo cáo cũ,
-- không tích lại nhiều bản (xem report.py/save_report()). `decisions`/
-- `action_items` lưu dạng TEXT chứa JSON (không tách bảng riêng từng dòng)
-- vì số lượng nhỏ, không cần query/lọc riêng từng item -- JSON đơn giản hơn
-- nhiều cho 1 danh sách ngắn chỉ đọc/viết nguyên cục mỗi lần.
CREATE TABLE IF NOT EXISTS meeting_reports (
    meeting_id      INTEGER PRIMARY KEY REFERENCES meetings(id),
    generated_at    TEXT NOT NULL,
    overview        TEXT NOT NULL,
    decisions       TEXT NOT NULL,      -- JSON array of strings
    action_items    TEXT NOT NULL       -- JSON array of {"text": str, "done": bool}
);
"""


@dataclass
class MeetingSummary:
    """1 dòng cho màn hình "Lịch sử phiên họp" (F13, 🔒 MỚI -- xem
    CONTRACTS.md Mục 13). Tách riêng khỏi tuple thô của `list_meetings()`
    (vẫn giữ nguyên, KHÔNG đổi, có thể nơi khác đang dùng) vì màn hình lịch
    sử cần thêm 2 thông tin tổng hợp (segment_count, has_report) mà
    `list_meetings()` không có và không nên thêm vào (đổi kiểu trả về của
    method đã tồn tại có thể phá vỡ chỗ gọi cũ -- thêm method MỚI an toàn
    hơn sửa method cũ)."""

    id: int
    started_at: str
    ended_at: Optional[str]
    user_native_lang: str
    segment_count: int
    has_report: bool
    snippet: Optional[str] = None  # chỉ có giá trị khi trả về từ search_meetings()


class MeetingStore:
    """Wrapper SQLite cho 1 worker thread. Mở 1 connection riêng, đóng bằng
    close() hoặc dùng như context manager (`with MeetingStore(...) as store:`).
    """

    def __init__(self, db_path: str | Path = "meetings.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            # check_same_thread=True (mặc định) là ĐÚNG Ý: instance này chỉ
            # dùng trong 1 thread duy nhất theo quy ước CONTRACTS.md Mục 3 —
            # để mặc định True giúp tự bắt lỗi sớm nếu code sau này lỡ share
            # connection này sang thread khác.
            self._conn = sqlite3.connect(str(db_path))
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể mở/khởi tạo database tại {db_path}: {exc}") from exc

    def __enter__(self) -> "MeetingStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # -- meetings ------------------------------------------------------

    def start_meeting(self, user_native_lang: str) -> int:
        """Tạo 1 phiên họp mới, trả về meeting_id để dùng cho add_segment()."""
        try:
            cur = self._conn.execute(
                "INSERT INTO meetings (started_at, ended_at, user_native_lang) "
                "VALUES (?, NULL, ?)",
                (_utcnow_iso(), user_native_lang),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể tạo phiên họp mới: {exc}") from exc

    def end_meeting(self, meeting_id: int) -> None:
        """Đánh dấu phiên họp đã kết thúc (set ended_at). Gọi khi người dùng
        nhấn 'Kết thúc họp' — KHÔNG xoá segment nào, chỉ đóng phiên."""
        try:
            self._conn.execute(
                "UPDATE meetings SET ended_at = ? WHERE id = ?",
                (_utcnow_iso(), meeting_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể kết thúc phiên họp id={meeting_id}: {exc}") from exc

    # -- segments --------------------------------------------------------

    def add_segment(
        self,
        meeting_id: int,
        original_text: str,
        source_lang: str,
        confidence: float,
        translated_text: Optional[str] = None,
        target_lang: Optional[str] = None,
        is_question: bool = False,
    ) -> int:
        """Lưu 1 segment NGAY KHI có (CONTRACTS.md Mục 5: ghi cả khi dịch lỗi,
        translated_text=None — không vì bước dịch lỗi mà mất original_text).

        Trả về id của segment vừa tạo (dùng để sau này update nếu dịch xong
        muộn hơn transcribe, qua update_translation()).
        """
        try:
            cur = self._conn.execute(
                "INSERT INTO segments "
                "(meeting_id, created_at, original_text, source_lang, confidence, "
                " translated_text, target_lang, is_question) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    meeting_id,
                    _utcnow_iso(),
                    original_text,
                    source_lang,
                    confidence,
                    translated_text,
                    target_lang,
                    1 if is_question else 0,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể lưu segment cho meeting_id={meeting_id}: {exc}") from exc

    def update_translation(self, segment_id: int, translated_text: str, target_lang: str) -> None:
        """Cập nhật bản dịch cho 1 segment đã lưu trước đó (trường hợp
        transcribe() xong trước, translate() xong sau — vẫn ghi original_text
        ngay, update bản dịch khi có)."""
        try:
            self._conn.execute(
                "UPDATE segments SET translated_text = ?, target_lang = ? WHERE id = ?",
                (translated_text, target_lang, segment_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể cập nhật bản dịch cho segment id={segment_id}: {exc}") from exc

    def get_segments(self, meeting_id: int) -> list[SegmentRecord]:
        """Lấy toàn bộ segment của 1 phiên họp, theo thứ tự thời gian — dùng
        cho report Phase 3 và lịch sử F13."""
        try:
            rows = self._conn.execute(
                "SELECT id, meeting_id, created_at, original_text, source_lang, "
                "confidence, translated_text, target_lang, is_question "
                "FROM segments WHERE meeting_id = ? ORDER BY id ASC",
                (meeting_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể đọc segments của meeting_id={meeting_id}: {exc}") from exc

        return [
            SegmentRecord(
                id=r[0], meeting_id=r[1], created_at=r[2], original_text=r[3],
                source_lang=r[4], confidence=r[5], translated_text=r[6],
                target_lang=r[7], is_question=bool(r[8]),
            )
            for r in rows
        ]

    def list_meetings(self) -> list[tuple[int, str, Optional[str], str]]:
        """Trả về (id, started_at, ended_at, user_native_lang) của mọi phiên
        họp, mới nhất trước — dùng cho màn hình lịch sử (F13)."""
        try:
            return self._conn.execute(
                "SELECT id, started_at, ended_at, user_native_lang "
                "FROM meetings ORDER BY id DESC"
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể đọc danh sách phiên họp: {exc}") from exc

    def list_meetings_with_counts(self) -> list[MeetingSummary]:
        """🔒 MỚI (F13, CONTRACTS.md Mục 13) — như `list_meetings()` nhưng
        kèm số lượng segment đã ghi + đã có báo cáo chưa, để màn hình lịch
        sử (`ui/history_dialog.py`) hiển thị đủ thông tin mà KHÔNG phải mở
        từng phiên họp ra mới biết. 1 query duy nhất (LEFT JOIN + GROUP BY),
        KHÔNG N+1 query cho từng meeting — tránh chậm khi danh sách dài.
        """
        try:
            rows = self._conn.execute(
                "SELECT m.id, m.started_at, m.ended_at, m.user_native_lang, "
                "COUNT(s.id) AS segment_count, "
                "CASE WHEN r.meeting_id IS NULL THEN 0 ELSE 1 END AS has_report "
                "FROM meetings m "
                "LEFT JOIN segments s ON s.meeting_id = m.id "
                "LEFT JOIN meeting_reports r ON r.meeting_id = m.id "
                "GROUP BY m.id "
                "ORDER BY m.id DESC"
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể đọc danh sách phiên họp (kèm thống kê): {exc}") from exc

        return [
            MeetingSummary(
                id=r[0], started_at=r[1], ended_at=r[2], user_native_lang=r[3],
                segment_count=r[4], has_report=bool(r[5]),
            )
            for r in rows
        ]

    def search_meetings(self, query: str, snippet_max_len: int = 80) -> list[MeetingSummary]:
        """🔒 MỚI (F13, CONTRACTS.md Mục 13) — tìm các phiên họp có transcript
        (original_text HOẶC translated_text) chứa `query` (LIKE, không phân
        biệt hoa thường nhờ SQLite mặc định COLLATE NOCASE cho LIKE với ASCII
        — ⚠️ với chữ có dấu tiếng Việt, LIKE của SQLite KHÔNG tự nhận biết
        hoa/thường giống ASCII, nên tìm "việc" sẽ KHÔNG khớp "VIỆC" — hạn chế
        đã biết của SQLite thuần, CHƯA dùng extension FTS5/unicode61 vì PROJECT_SPEC
        ưu tiên đơn giản cho V1, lượng dữ liệu cá nhân nhỏ thì gõ đúng hoa/
        thường gốc là chấp nhận được).

        Mỗi phiên họp trong kết quả chỉ xuất hiện 1 lần (dù khớp nhiều
        segment), kèm 1 `snippet` đại diện (segment khớp đầu tiên, cắt ngắn
        tới `snippet_max_len` ký tự) để hiện preview trên UI.

        Args:
            query: chuỗi tìm kiếm. Rỗng/chỉ whitespace -> trả về NHƯ
                `list_meetings_with_counts()` (không lọc gì, snippet=None) —
                để `ui/history_dialog.py` có thể dùng method DUY NHẤT này
                cho cả 2 trường hợp "xoá ô tìm kiếm" và "đang tìm".
        """
        query = query.strip()
        if not query:
            return self.list_meetings_with_counts()

        like_pattern = f"%{query}%"
        try:
            rows = self._conn.execute(
                "SELECT m.id, m.started_at, m.ended_at, m.user_native_lang, "
                "(SELECT COUNT(*) FROM segments WHERE meeting_id = m.id) AS segment_count, "
                "CASE WHEN r.meeting_id IS NULL THEN 0 ELSE 1 END AS has_report, "
                "(SELECT s2.original_text FROM segments s2 "
                " WHERE s2.meeting_id = m.id "
                " AND (s2.original_text LIKE ? OR s2.translated_text LIKE ?) "
                " ORDER BY s2.id LIMIT 1) AS snippet "
                "FROM meetings m "
                "LEFT JOIN meeting_reports r ON r.meeting_id = m.id "
                "WHERE EXISTS ("
                "  SELECT 1 FROM segments s3 WHERE s3.meeting_id = m.id "
                "  AND (s3.original_text LIKE ? OR s3.translated_text LIKE ?)"
                ") "
                "ORDER BY m.id DESC",
                (like_pattern, like_pattern, like_pattern, like_pattern),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể tìm kiếm phiên họp: {exc}") from exc

        results = []
        for r in rows:
            snippet = r[6]
            if snippet and len(snippet) > snippet_max_len:
                snippet = snippet[: snippet_max_len - 1].rstrip() + "…"
            results.append(
                MeetingSummary(
                    id=r[0], started_at=r[1], ended_at=r[2], user_native_lang=r[3],
                    segment_count=r[4], has_report=bool(r[5]), snippet=snippet,
                )
            )
        return results

    # -- ai_assists (Phase 2 Bước 3/3) ------------------------------------

    def add_ai_assist(
        self,
        meeting_id: int,
        kind: str,
        source_text: str,
        final_text: Optional[str],
        target_lang: Optional[str],
        ai_output: Optional[str] = None,
    ) -> int:
        """Lưu 1 lần AI hỗ trợ (gợi ý trả lời hoặc câu tự đặt qua "Tôi muốn
        hỏi"). `kind` phải là "suggest_answer" hoặc "ask_question".

        Gọi đúng 1 lần SAU KHI người dùng đã hoàn tất bước dịch ngược (bấm
        "Dịch & Sẵn sàng nói"/"Dịch & Sẵn sàng hỏi") — `final_text` là bản
        ĐÃ DÙNG THẬT, không lưu các lần "Tạo lại" bị bỏ giữa đường.
        """
        if kind not in ("suggest_answer", "ask_question"):
            raise StorageError(f"kind không hợp lệ: {kind!r} (phải là suggest_answer/ask_question).")
        try:
            cur = self._conn.execute(
                "INSERT INTO ai_assists "
                "(meeting_id, created_at, kind, source_text, ai_output, final_text, target_lang) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (meeting_id, _utcnow_iso(), kind, source_text, ai_output, final_text, target_lang),
            )
            self._conn.commit()
            return int(cur.lastrowid)
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể lưu ai_assist cho meeting_id={meeting_id}: {exc}") from exc

    def get_ai_assists(self, meeting_id: int) -> list[tuple[int, str, str, str, Optional[str], Optional[str], Optional[str]]]:
        """Lấy toàn bộ lịch sử AI hỗ trợ của 1 phiên họp, theo thứ tự thời
        gian — dùng cho report Phase 3."""
        try:
            return self._conn.execute(
                "SELECT id, created_at, kind, source_text, ai_output, final_text, target_lang "
                "FROM ai_assists WHERE meeting_id = ? ORDER BY id ASC",
                (meeting_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể đọc ai_assists của meeting_id={meeting_id}: {exc}") from exc

    # -- meeting_reports (Phase 3 Bước 3/4) -------------------------------

    def save_report(
        self, meeting_id: int, overview: str, decisions: list[str], action_items: list[str],
    ) -> ReportRecord:
        """Lưu báo cáo MỚI cho `meeting_id`, GHI ĐÈ báo cáo cũ nếu có (1
        meeting chỉ giữ đúng 1 báo cáo mới nhất — xem comment ở `_SCHEMA`).

        `action_items` nhận `list[str]` THÔ đúng như `SummaryResult.action_items`
        (xem base_provider.py) — mọi item LUÔN khởi tạo `done=False` ở đây,
        KHÔNG cố gắng "đoán lại" trạng thái tick từ báo cáo cũ: lần gọi
        `summarize()` mới có thể trả về nội dung/thứ tự action item HOÀN
        TOÀN khác lần trước (model không deterministic), nên không có cách
        nào map đúng "item cũ đã tick" sang "item mới" một cách an toàn —
        thà reset rõ ràng còn hơn map sai khiến người dùng tưởng đã làm
        xong 1 việc mà thực ra là việc khác.

        Trả về `ReportRecord` vừa lưu (tiện cho caller không phải gọi
        `get_report()` lại ngay sau đó)."""
        generated_at = _utcnow_iso()
        decisions_json = json.dumps(decisions, ensure_ascii=False)
        action_items_json = json.dumps(
            [{"text": text, "done": False} for text in action_items], ensure_ascii=False
        )
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO meeting_reports "
                "(meeting_id, generated_at, overview, decisions, action_items) "
                "VALUES (?, ?, ?, ?, ?)",
                (meeting_id, generated_at, overview, decisions_json, action_items_json),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể lưu báo cáo cho meeting_id={meeting_id}: {exc}") from exc

        return ReportRecord(
            meeting_id=meeting_id, generated_at=generated_at, overview=overview,
            decisions=list(decisions),
            action_items=[ActionItemRecord(text=text, done=False) for text in action_items],
        )

    def get_report(self, meeting_id: int) -> Optional[ReportRecord]:
        """Lấy báo cáo ĐÃ LƯU của 1 phiên họp, hoặc `None` nếu chưa từng
        tạo báo cáo nào (caller — `ui/main_window.py` — tự quyết định gọi
        `summarize()` mới khi gặp `None`, hàm này không tự gọi AI)."""
        try:
            row = self._conn.execute(
                "SELECT meeting_id, generated_at, overview, decisions, action_items "
                "FROM meeting_reports WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"Không thể đọc báo cáo của meeting_id={meeting_id}: {exc}") from exc

        if row is None:
            return None

        decisions = json.loads(row[3])
        raw_items = json.loads(row[4])
        action_items = [
            ActionItemRecord(text=str(item["text"]), done=bool(item.get("done", False)))
            for item in raw_items
        ]
        return ReportRecord(
            meeting_id=row[0], generated_at=row[1], overview=row[2],
            decisions=decisions, action_items=action_items,
        )

    def set_action_item_done(self, meeting_id: int, index: int, done: bool) -> None:
        """Tick/bỏ tick 1 action item theo vị trí `index` (0-based, theo
        đúng thứ tự hiện trong `ReportRecord.action_items`).

        ⚠️ Ngoại lệ CÓ Ý so với CONTRACTS.md Mục 3 ("ghi SQLite nên gọi từ
        worker thread"): quy ước đó nhằm tránh BLOCK UI thread khi chờ
        AIProvider (network, 1-4s). Hành động này KHÔNG gọi AI/network —
        chỉ 1 UPDATE cực nhỏ (1 cột) trên file SQLite local, độ trễ thực tế
        ở mức micro-giây — nên `ui/main_window.py` được phép gọi method này
        TRỰC TIẾP từ main thread khi người dùng click checkbox, đổi lại UX
        tick ngay lập tức không cần đợi thread mới khởi tạo. Đọc rồi viết
        lại NGUYÊN bảng `action_items` (không UPDATE 1 phần tử JSON qua SQL
        function) vì SQLite chuẩn không có hàm sửa JSON path sẵn (cần
        extension `json1` với cú pháp riêng) — với danh sách action item
        luôn NGẮN (vài item), đọc/viết lại nguyên list rẻ hơn nhiều so với
        rủi ro phụ thuộc thêm 1 SQLite extension.

        Raises:
            StorageError: chưa có báo cáo nào lưu cho `meeting_id`, hoặc
                `index` ngoài phạm vi danh sách action_items hiện có (vd
                UI đang hiện báo cáo CŨ trong khi báo cáo đã bị "Tạo báo
                cáo mới" ghi đè ở 1 cửa sổ khác — hiếm nhưng phải raise rõ,
                không âm thầm ghi sai item).
        """
        report = self.get_report(meeting_id)
        if report is None:
            raise StorageError(
                f"Chưa có báo cáo nào lưu cho meeting_id={meeting_id} — "
                "không thể cập nhật trạng thái action item."
            )
        if not (0 <= index < len(report.action_items)):
            raise StorageError(
                f"Action item index={index} không hợp lệ (báo cáo hiện có "
                f"{len(report.action_items)} action item, meeting_id={meeting_id})."
            )

        updated_items = list(report.action_items)
        updated_items[index] = ActionItemRecord(text=updated_items[index].text, done=done)
        action_items_json = json.dumps(
            [{"text": item.text, "done": item.done} for item in updated_items], ensure_ascii=False
        )
        try:
            self._conn.execute(
                "UPDATE meeting_reports SET action_items = ? WHERE meeting_id = ?",
                (action_items_json, meeting_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(
                f"Không thể cập nhật action item cho meeting_id={meeting_id}: {exc}"
            ) from exc
