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
    print("\n=== TẤT CẢ TEST DB PASS ===")
