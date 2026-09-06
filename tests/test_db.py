import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage.db import MeetingStore, StorageError  # noqa: E402


def test_start_va_end_meeting():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            assert isinstance(mid, int) and mid > 0
            meetings = store.list_meetings()
            assert len(meetings) == 1
            assert meetings[0][3] == "vi"
            assert meetings[0][2] is None, "ended_at phải NULL khi mới start"

            store.end_meeting(mid)
            meetings = store.list_meetings()
            assert meetings[0][2] is not None, "ended_at phải có giá trị sau end_meeting()"
    print("OK: test_start_va_end_meeting")


def test_add_segment_va_get_segments_giu_dung_thu_tu():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.add_segment(mid, "Hello", "en", 0.9, "Xin chào", "vi", is_question=False)
            store.add_segment(mid, "How are you?", "en", 0.8, "Bạn khoẻ không?", "vi", is_question=True)

            segs = store.get_segments(mid)
            assert len(segs) == 2
            assert segs[0].original_text == "Hello"
            assert segs[1].is_question is True
            assert segs[0].is_question is False
    print("OK: test_add_segment_va_get_segments_giu_dung_thu_tu")


def test_add_segment_van_luu_duoc_khi_dich_loi():
    # CONTRACTS.md Mục 5: dịch lỗi (translated_text=None) KHÔNG được làm mất original_text.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            seg_id = store.add_segment(mid, "Some text", "en", 0.7, translated_text=None, target_lang=None)
            segs = store.get_segments(mid)
            assert segs[0].original_text == "Some text"
            assert segs[0].translated_text is None

            # update_translation() khi dịch xong muộn hơn
            store.update_translation(seg_id, "Một văn bản", "vi")
            segs = store.get_segments(mid)
            assert segs[0].translated_text == "Một văn bản"
    print("OK: test_add_segment_van_luu_duoc_khi_dich_loi")


def test_segment_voi_meeting_id_khong_ton_tai_raise_error():
    # foreign_keys=ON -> phải raise StorageError, không âm thầm lưu rác.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            try:
                store.add_segment(meeting_id=9999, original_text="x", source_lang="en", confidence=0.5)
                raise AssertionError("Phải raise StorageError khi meeting_id không tồn tại (FK constraint).")
            except StorageError:
                pass
    print("OK: test_segment_voi_meeting_id_khong_ton_tai_raise_error")


def test_khong_luu_audio_tho_chi_luu_text():
    # Đảm bảo schema không có cột nào kiểu BLOB cho audio thô (nguyên tắc riêng tư).
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            cols = [row[1] for row in store._conn.execute("PRAGMA table_info(segments)").fetchall()]
            assert "audio" not in [c.lower() for c in cols]
            assert "raw_audio" not in [c.lower() for c in cols]
    print("OK: test_khong_luu_audio_tho_chi_luu_text")


def test_add_ai_assist_va_get_ai_assists():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.add_ai_assist(
                meeting_id=mid, kind="suggest_answer",
                source_text="What's our churn rate?",
                ai_output="Tỷ lệ rời bỏ hiện tại là [số liệu cụ thể].",
                final_text="Our current churn rate is [specific number].",
                target_lang="en",
            )
            store.add_ai_assist(
                meeting_id=mid, kind="ask_question",
                source_text="Deadline dự án là khi nào?",
                ai_output=None,
                final_text="When is the project deadline?",
                target_lang="en",
            )

            rows = store.get_ai_assists(mid)
            assert len(rows) == 2
            assert rows[0][2] == "suggest_answer"
            assert rows[1][2] == "ask_question"
            assert rows[1][4] is None, "ask_question không có ai_output, phải là NULL."
    print("OK: test_add_ai_assist_va_get_ai_assists")


def test_add_ai_assist_kind_khong_hop_le_raise_error():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            try:
                store.add_ai_assist(
                    meeting_id=mid, kind="invalid_kind", source_text="x",
                    final_text="y", target_lang="en",
                )
                raise AssertionError("Phải raise StorageError khi kind không hợp lệ.")
            except StorageError:
                pass
    print("OK: test_add_ai_assist_kind_khong_hop_le_raise_error")


def test_get_report_tra_none_khi_chua_co_bao_cao():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            assert store.get_report(mid) is None
    print("OK: test_get_report_tra_none_khi_chua_co_bao_cao")


def test_save_report_va_get_report_action_items_mac_dinh_chua_tick():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            saved = store.save_report(
                mid, overview="Tóm tắt test.",
                decisions=["Quyết định 1"],
                action_items=["Việc A", "Việc B"],
            )
            assert saved.action_items[0].done is False, "Action item MỚI lưu phải mặc định chưa tick."

            report = store.get_report(mid)
            assert report is not None
            assert report.overview == "Tóm tắt test."
            assert report.decisions == ["Quyết định 1"]
            assert [i.text for i in report.action_items] == ["Việc A", "Việc B"]
            assert all(i.done is False for i in report.action_items)
    print("OK: test_save_report_va_get_report_action_items_mac_dinh_chua_tick")


def test_set_action_item_done_chi_doi_dung_item_duoc_chon():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.save_report(mid, overview="x", decisions=[], action_items=["Việc A", "Việc B"])

            store.set_action_item_done(mid, index=1, done=True)
            report = store.get_report(mid)
            assert report.action_items[0].done is False, "Item 0 KHÔNG được đổi theo."
            assert report.action_items[1].done is True

            store.set_action_item_done(mid, index=1, done=False)  # bỏ tick lại
            report = store.get_report(mid)
            assert report.action_items[1].done is False
    print("OK: test_set_action_item_done_chi_doi_dung_item_duoc_chon")


def test_set_action_item_done_index_ngoai_pham_vi_raise_error():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.save_report(mid, overview="x", decisions=[], action_items=["Việc A"])
            try:
                store.set_action_item_done(mid, index=5, done=True)
                raise AssertionError("Phải raise StorageError khi index ngoài phạm vi.")
            except StorageError:
                pass
    print("OK: test_set_action_item_done_index_ngoai_pham_vi_raise_error")


def test_set_action_item_done_chua_co_bao_cao_raise_error():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            try:
                store.set_action_item_done(mid, index=0, done=True)
                raise AssertionError("Phải raise StorageError khi chưa có báo cáo nào lưu.")
            except StorageError:
                pass
    print("OK: test_set_action_item_done_chua_co_bao_cao_raise_error")


def test_save_report_lan_2_ghi_de_va_reset_done():
    # Mỗi meeting chỉ giữ 1 báo cáo mới nhất -- "Tạo báo cáo mới" ghi đè,
    # action_items reset done=False (xem docstring save_report()).
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.save_report(mid, overview="Bản 1", decisions=[], action_items=["Việc A"])
            store.set_action_item_done(mid, index=0, done=True)

            store.save_report(mid, overview="Bản 2", decisions=[], action_items=["Việc khác hẳn"])
            report = store.get_report(mid)
            assert report.overview == "Bản 2"
            assert [i.text for i in report.action_items] == ["Việc khác hẳn"]
            assert report.action_items[0].done is False, "Báo cáo MỚI phải reset done, không giữ tick cũ."
    print("OK: test_save_report_lan_2_ghi_de_va_reset_done")


def test_list_meetings_with_counts_dem_dung_segment_va_has_report():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m1, original_text="A", source_lang="en", confidence=0.9)
            store.add_segment(m1, original_text="B", source_lang="en", confidence=0.9)
            store.save_report(m1, overview="OK", decisions=[], action_items=[])

            m2 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m2, original_text="C", source_lang="en", confidence=0.9)
            # m2 KHÔNG có báo cáo -- để test has_report=False đúng.

            results = store.list_meetings_with_counts()
            by_id = {r.id: r for r in results}

            assert by_id[m1].segment_count == 2
            assert by_id[m1].has_report is True
            assert by_id[m2].segment_count == 1
            assert by_id[m2].has_report is False
            # Mới nhất trước (m2 tạo sau m1).
            assert [r.id for r in results][:2] == [m2, m1]
    print("OK: test_list_meetings_with_counts_dem_dung_segment_va_has_report")


def test_list_meetings_with_counts_meeting_chua_co_segment_van_xuat_hien():
    # 🔒 Bug thật đã gặp: phiên họp dừng ngay (KHÔNG nói gì) trước đây
    # KHÔNG xem được báo cáo/lịch sử -- LEFT JOIN phải vẫn trả về phiên họp
    # này với segment_count=0, KHÔNG bị INNER JOIN làm biến mất khỏi danh sách.
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            mid = store.start_meeting(user_native_lang="vi")
            results = store.list_meetings_with_counts()
            assert len(results) == 1
            assert results[0].id == mid
            assert results[0].segment_count == 0
            assert results[0].has_report is False
    print("OK: test_list_meetings_with_counts_meeting_chua_co_segment_van_xuat_hien")


def test_search_meetings_query_rong_tra_ve_nhu_list_with_counts():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            store.start_meeting(user_native_lang="vi")
            assert len(store.search_meetings("")) == len(store.list_meetings_with_counts())
            assert len(store.search_meetings("   ")) == len(store.list_meetings_with_counts())
    print("OK: test_search_meetings_query_rong_tra_ve_nhu_list_with_counts")


def test_search_meetings_tim_dung_theo_original_text():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m1, original_text="Let's talk about the quarterly report",
                              source_lang="en", confidence=0.9)
            m2 = store.start_meeting(user_native_lang="vi")
            store.add_segment(m2, original_text="Good morning everyone",
                              source_lang="en", confidence=0.9)

            results = store.search_meetings("quarterly")
            assert [r.id for r in results] == [m1], (
                f"Chỉ m1 chứa 'quarterly', nhận {[r.id for r in results]}."
            )
            assert "quarterly" in results[0].snippet
    print("OK: test_search_meetings_tim_dung_theo_original_text")


def test_search_meetings_tim_dung_theo_translated_text():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.add_segment(mid, original_text="Quarterly report", source_lang="en",
                              confidence=0.9, translated_text="Báo cáo quý",
                              target_lang="vi")
            results = store.search_meetings("Báo cáo")
            assert [r.id for r in results] == [mid]
    print("OK: test_search_meetings_tim_dung_theo_translated_text")


def test_search_meetings_khong_khop_tra_ve_rong():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            mid = store.start_meeting(user_native_lang="vi")
            store.add_segment(mid, original_text="Hello", source_lang="en", confidence=0.9)
            assert store.search_meetings("khong-co-trong-transcript") == []
    print("OK: test_search_meetings_khong_khop_tra_ve_rong")


def test_search_meetings_snippet_bi_cat_ngan_dung_do_dai():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            mid = store.start_meeting(user_native_lang="vi")
            long_text = "từ khoá " + ("x" * 200)
            store.add_segment(mid, original_text=long_text, source_lang="en", confidence=0.9)
            results = store.search_meetings("từ khoá", snippet_max_len=20)
            assert len(results[0].snippet) <= 20
    print("OK: test_search_meetings_snippet_bi_cat_ngan_dung_do_dai")


def test_start_meeting_luu_va_doc_lai_duoc_meeting_context():
    """🔒 MỚI (Vòng 9, CONTRACTS.md Mục 18)."""
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            mid = store.start_meeting(
                user_native_lang="vi",
                meeting_context="Phỏng vấn xin việc vị trí Backend Developer.",
            )
            assert store.get_meeting_context(mid) == "Phỏng vấn xin việc vị trí Backend Developer."
    print("OK: test_start_meeting_luu_va_doc_lai_duoc_meeting_context")


def test_start_meeting_khong_truyen_meeting_context_van_hoat_dong_nhu_cu():
    """Backward-compat: lời gọi CŨ chỉ truyền user_native_lang (như mọi
    test khác trong file này) phải vẫn chạy được, và get_meeting_context()
    trả về "" (không phải None/lỗi) khi không có gì."""
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            mid = store.start_meeting(user_native_lang="vi")
            assert store.get_meeting_context(mid) == ""
    print("OK: test_start_meeting_khong_truyen_meeting_context_van_hoat_dong_nhu_cu")


def test_get_meeting_context_meeting_id_khong_ton_tai_tra_rong():
    with tempfile.TemporaryDirectory() as tmp:
        with MeetingStore(os.path.join(tmp, "test.db")) as store:
            assert store.get_meeting_context(9999) == ""
    print("OK: test_get_meeting_context_meeting_id_khong_ton_tai_tra_rong")


def test_migrate_them_cot_meeting_context_cho_db_cu_khong_mat_du_lieu():
    """🔒 MỚI (Vòng 9) — mô phỏng DB được tạo TỪ TRƯỚC Vòng 9 (bảng
    `meetings` chưa có cột `meeting_context`), xác nhận mở lại bằng
    MeetingStore hiện tại tự ALTER TABLE thêm cột mà KHÔNG mất dữ liệu cũ,
    và vẫn dùng được start_meeting()/get_meeting_context() bình thường sau
    đó."""
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "legacy.db")
        legacy_conn = sqlite3.connect(db_path)
        legacy_conn.execute(
            """CREATE TABLE meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                user_native_lang TEXT NOT NULL
            )"""
        )
        legacy_conn.execute(
            "INSERT INTO meetings (started_at, ended_at, user_native_lang) VALUES (?, NULL, ?)",
            ("2024-01-01T00:00:00Z", "vi"),
        )
        legacy_conn.commit()
        legacy_conn.close()

        with MeetingStore(db_path) as store:
            old_meetings = store.list_meetings()
            assert len(old_meetings) == 1, "dữ liệu phiên họp CŨ không được mất sau migrate"
            assert store.get_meeting_context(old_meetings[0][0]) == ""

            new_mid = store.start_meeting(user_native_lang="vi", meeting_context="Bối cảnh mới sau migrate.")
            assert store.get_meeting_context(new_mid) == "Bối cảnh mới sau migrate."
    print("OK: test_migrate_them_cot_meeting_context_cho_db_cu_khong_mat_du_lieu")


def test_delete_meetings_xoa_dung_meeting_va_du_lieu_lien_quan():
    # Vòng 10 (CONTRACTS.md Mục 24) -- xoá 1 meeting phải kéo theo xoá
    # segments/ai_assists/meeting_reports của CHÍNH meeting đó, KHÔNG đụng
    # tới meeting khác.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid_to_delete = store.start_meeting(user_native_lang="vi")
            store.add_segment(mid_to_delete, "Hello", "en", 0.9, "Xin chào", "vi", is_question=False)
            store.add_ai_assist(
                mid_to_delete, kind="ask_question", source_text="Q?",
                ai_output=None, final_text="A.", target_lang="en",
            )
            store.save_report(mid_to_delete, overview="Tổng quan", decisions=[], action_items=["Việc 1"])

            mid_to_keep = store.start_meeting(user_native_lang="en")
            store.add_segment(mid_to_keep, "Keep me", "en", 0.9, "Giữ lại", "vi", is_question=False)

            deleted_count = store.delete_meetings([mid_to_delete])
            assert deleted_count == 1

            remaining = store.list_meetings()
            assert len(remaining) == 1
            assert remaining[0][0] == mid_to_keep

            assert store.get_segments(mid_to_keep)[0].original_text == "Keep me"
            assert store.get_report(mid_to_delete) is None
    print("OK: test_delete_meetings_xoa_dung_meeting_va_du_lieu_lien_quan")


def test_delete_meetings_nhieu_id_cung_luc():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            m2 = store.start_meeting(user_native_lang="vi")
            m3 = store.start_meeting(user_native_lang="vi")

            deleted_count = store.delete_meetings([m1, m3])
            assert deleted_count == 2

            remaining_ids = [row[0] for row in store.list_meetings()]
            assert remaining_ids == [m2]
    print("OK: test_delete_meetings_nhieu_id_cung_luc")


def test_delete_meetings_id_khong_ton_tai_khong_raise_loi():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            deleted_count = store.delete_meetings([mid, 9999])
            assert deleted_count == 1, "chỉ đếm id THỰC SỰ tồn tại, id lạ không tính, không raise lỗi"
            assert store.list_meetings() == []
    print("OK: test_delete_meetings_id_khong_ton_tai_khong_raise_loi")


def test_delete_meetings_danh_sach_rong_tra_ve_0_khong_lam_gi():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            mid = store.start_meeting(user_native_lang="vi")
            deleted_count = store.delete_meetings([])
            assert deleted_count == 0
            assert len(store.list_meetings()) == 1, "danh sách rỗng không được xoá nhầm gì cả"
    print("OK: test_delete_meetings_danh_sach_rong_tra_ve_0_khong_lam_gi")


def test_delete_meetings_1_phan_khong_doi_id_cac_phien_con_lai():
    # 🔒 MỚI (Mục 33) -- xoá 1 PHẦN (không phải hết) không được đổi số thứ
    # tự (= id) của các phiên còn lại, và phiên MỚI tạo sau đó vẫn phải
    # tiếp tục tăng bình thường (KHÔNG reset bộ đếm khi bảng chưa trống).
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            m2 = store.start_meeting(user_native_lang="vi")
            m3 = store.start_meeting(user_native_lang="vi")

            store.delete_meetings([m1])

            remaining_ids = [row[0] for row in store.list_meetings()]
            assert remaining_ids == [m3, m2], "id các phiên còn lại phải giữ nguyên, không dồn lại"

            m4 = store.start_meeting(user_native_lang="vi")
            assert m4 == m3 + 1, "bộ đếm phải tiếp tục tăng bình thường, KHÔNG reset khi bảng chưa trống"
    print("OK: test_delete_meetings_1_phan_khong_doi_id_cac_phien_con_lai")


def test_delete_meetings_xoa_het_reset_bo_dem_ve_1():
    # 🔒 MỚI (Mục 33 -- yêu cầu người dùng) -- xoá HẾT (bảng meetings trống
    # hoàn toàn sau khi xoá) phải reset bộ đếm AUTOINCREMENT, để phiên họp
    # MỚI tiếp theo bắt đầu lại từ id=1 thay vì tiếp tục tăng vô hạn.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            m2 = store.start_meeting(user_native_lang="vi")
            assert m2 == m1 + 1

            deleted_count = store.delete_meetings([m1, m2])
            assert deleted_count == 2
            assert store.list_meetings() == []

            m3 = store.start_meeting(user_native_lang="vi")
            assert m3 == 1, "xoá hết sạch lịch sử thì phiên tiếp theo phải bắt đầu lại từ id=1"
    print("OK: test_delete_meetings_xoa_het_reset_bo_dem_ve_1")


def test_delete_meetings_xoa_het_qua_nhieu_lan_rieng_le_van_reset():
    # Xoá hết KHÔNG NHẤT THIẾT qua 1 lệnh gọi duy nhất -- 2 lệnh xoá riêng
    # biệt mà kết quả cuối cùng làm bảng trống cũng phải reset bộ đếm ở
    # đúng lệnh xoá làm bảng trống (không cần biết trước đó có bao nhiêu
    # lượt xoá riêng lẻ).
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            m1 = store.start_meeting(user_native_lang="vi")
            m2 = store.start_meeting(user_native_lang="vi")

            store.delete_meetings([m1])  # còn lại m2, chưa trống -- KHÔNG reset
            store.delete_meetings([m2])  # giờ mới trống hẳn -- reset

            m3 = store.start_meeting(user_native_lang="vi")
            assert m3 == 1
    print("OK: test_delete_meetings_xoa_het_qua_nhieu_lan_rieng_le_van_reset")


def test_delete_meetings_db_chua_tung_co_gi_khong_loi_sqlite_sequence():
    # Phòng vệ: DB mới toanh chưa từng insert gì -> bảng `sqlite_sequence`
    # chưa tồn tại -- gọi delete_meetings với id lạ (kết quả vẫn trống 0
    # dòng) KHÔNG được raise lỗi "no such table: sqlite_sequence".
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with MeetingStore(db_path) as store:
            deleted_count = store.delete_meetings([9999])
            assert deleted_count == 0
    print("OK: test_delete_meetings_db_chua_tung_co_gi_khong_loi_sqlite_sequence")


if __name__ == "__main__":
    test_start_va_end_meeting()
    test_add_segment_va_get_segments_giu_dung_thu_tu()
    test_add_segment_van_luu_duoc_khi_dich_loi()
    test_segment_voi_meeting_id_khong_ton_tai_raise_error()
    test_khong_luu_audio_tho_chi_luu_text()
    test_add_ai_assist_va_get_ai_assists()
    test_add_ai_assist_kind_khong_hop_le_raise_error()
    test_get_report_tra_none_khi_chua_co_bao_cao()
    test_save_report_va_get_report_action_items_mac_dinh_chua_tick()
    test_set_action_item_done_chi_doi_dung_item_duoc_chon()
    test_set_action_item_done_index_ngoai_pham_vi_raise_error()
    test_set_action_item_done_chua_co_bao_cao_raise_error()
    test_save_report_lan_2_ghi_de_va_reset_done()
    test_list_meetings_with_counts_dem_dung_segment_va_has_report()
    test_list_meetings_with_counts_meeting_chua_co_segment_van_xuat_hien()
    test_search_meetings_query_rong_tra_ve_nhu_list_with_counts()
    test_search_meetings_tim_dung_theo_original_text()
    test_search_meetings_tim_dung_theo_translated_text()
    test_search_meetings_khong_khop_tra_ve_rong()
    test_search_meetings_snippet_bi_cat_ngan_dung_do_dai()
    test_start_meeting_luu_va_doc_lai_duoc_meeting_context()
    test_start_meeting_khong_truyen_meeting_context_van_hoat_dong_nhu_cu()
    test_get_meeting_context_meeting_id_khong_ton_tai_tra_rong()
    test_migrate_them_cot_meeting_context_cho_db_cu_khong_mat_du_lieu()
    test_delete_meetings_xoa_dung_meeting_va_du_lieu_lien_quan()
    test_delete_meetings_nhieu_id_cung_luc()
    test_delete_meetings_id_khong_ton_tai_khong_raise_loi()
    test_delete_meetings_danh_sach_rong_tra_ve_0_khong_lam_gi()
    test_delete_meetings_1_phan_khong_doi_id_cac_phien_con_lai()
    test_delete_meetings_xoa_het_reset_bo_dem_ve_1()
    test_delete_meetings_xoa_het_qua_nhieu_lan_rieng_le_van_reset()
    test_delete_meetings_db_chua_tung_co_gi_khong_loi_sqlite_sequence()
    print("\n=== TẤT CẢ TEST DB PASS ===")
