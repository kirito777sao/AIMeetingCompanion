"""
Unit test cho app/config_store.py (F14, CONTRACTS.md Mục 12).

🔒 SỬA (05/09/2026, sau khi phát hiện qua verify Backlog #3 trên Windows
thật — xem TASKS.md Backlog): 2 test DPAPI dưới đây (`test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may`,
`test_is_encrypted_storage_available_khop_voi_platform_thuc_te`) trước
đây HARDCODE kỳ vọng `False` (chỉ đúng trên sandbox Linux, dự đoán SAI
khi chạy trên Windows thật — DPAPI có sẵn nên kết quả thật là `True`,
làm test tự động BÁO FAIL dù app hoạt động đúng). Nay tự đọc
`platform.system()` để chọn ĐÚNG kỳ vọng cho MỌI môi trường: Windows
thật -- verify DPAPI THẬT SỰ hoạt động (round-trip OK, `True`); Linux/Mac
(sandbox) -- verify đúng nhánh fallback plaintext (`False`). File
`app/config_store.py` KHÔNG đổi gì -- chỉ sửa TEST để phản ánh đúng thực
tế đa nền tảng.

Sandbox này chạy Linux -- KHÔNG có `ctypes.windll` (DPAPI chỉ tồn tại trên
Windows). Mọi test KHÁC (ngoài 2 test trên) verify nhánh FALLBACK
(plaintext-local) + hành vi an toàn khi đọc file hỏng/thiếu -- các test
đó CỐ Ý không phụ thuộc OS (dùng `base_dir=<thư mục tạm>`, không đụng
DPAPI thật) nên PASS giống nhau trên mọi nền tảng.

Mọi test dùng `base_dir=<thư mục tạm>` để KHÔNG đụng tới
%APPDATA%/AIMeetingCompanion thật trên máy chạy test này.
"""

import json
import os
import platform
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config_store import (  # noqa: E402
    clear_api_key,
    clear_model_overrides,
    get_active_provider,
    get_config_path,
    is_encrypted_storage_available,
    list_configured_providers,
    load_api_key,
    load_model_overrides,
    save_api_key,
    save_model_overrides,
    set_active_provider,
)


def test_load_tra_none_khi_chua_tung_luu():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_api_key(base_dir=Path(tmp)) is None
    print("OK: test_load_tra_none_khi_chua_tung_luu")


def test_save_va_load_roundtrip_dung_key():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_test_abc123", base_dir=base)
        assert load_api_key(base_dir=base) == "gsk_test_abc123"
    print("OK: test_save_va_load_roundtrip_dung_key")


def test_save_tu_dong_don_whitespace_va_quote_thua():
    # Cùng hành vi GroqProvider.__init__() đã làm với .env -- lưu sẵn bản
    # SẠCH để không phải lặp logic dọn này ở nơi đọc lại.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key('  "gsk_test_voi_rac"  \n', base_dir=base)
        assert load_api_key(base_dir=base) == "gsk_test_voi_rac"
    print("OK: test_save_tu_dong_don_whitespace_va_quote_thua")


def test_save_lan_2_ghi_de_lan_1():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("key_cu", base_dir=base)
        save_api_key("key_moi", base_dir=base)
        assert load_api_key(base_dir=base) == "key_moi"
    print("OK: test_save_lan_2_ghi_de_lan_1")


def test_clear_api_key_xoa_duoc_va_load_lai_tra_none():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("key_se_bi_xoa", base_dir=base)
        assert load_api_key(base_dir=base) == "key_se_bi_xoa"
        clear_api_key(base_dir=base)
        assert load_api_key(base_dir=base) is None
    print("OK: test_clear_api_key_xoa_duoc_va_load_lai_tra_none")


def test_clear_api_key_khong_loi_khi_chua_tung_luu():
    with tempfile.TemporaryDirectory() as tmp:
        clear_api_key(base_dir=Path(tmp))  # không raise
    print("OK: test_clear_api_key_khong_loi_khi_chua_tung_luu")


def test_load_an_toan_khi_file_json_hong():
    # File config bị sửa tay/hỏng -- PHẢI trả None, KHÔNG crash app khởi động.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        config_path = get_config_path(base_dir=base)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{khong phai json hop le", encoding="utf-8")
        assert load_api_key(base_dir=base) is None
    print("OK: test_load_an_toan_khi_file_json_hong")


def test_load_an_toan_khi_encoding_la_dpapi_nhung_dang_chay_khong_phai_windows():
    # Giả lập file config được tạo trên 1 máy Windows khác (encoding=dpapi),
    # giờ đọc lại trên máy/OS hiện tại không giải mã được -- PHẢI trả None
    # (KHÔNG crash), để GroqProvider tự rơi xuống nguồn key tiếp theo
    # (biến môi trường GROQ_API_KEY) thay vì làm app không khởi động được.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        config_path = get_config_path(base_dir=base)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"encoding": "dpapi", "groq_api_key": "khong-the-giai-ma-duoc=="}),
            encoding="utf-8",
        )
        assert load_api_key(base_dir=base) is None
    print("OK: test_load_an_toan_khi_encoding_la_dpapi_nhung_dang_chay_khong_phai_windows")


def test_load_an_toan_khi_thieu_field_key():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        config_path = get_config_path(base_dir=base)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"encoding": "plaintext"}), encoding="utf-8")
        assert load_api_key(base_dir=base) is None
    print("OK: test_load_an_toan_khi_thieu_field_key")


def test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may():
    # 🔒 SỬA (xem docstring đầu file) -- trước đây hardcode kỳ vọng
    # `False`, chỉ đúng trên sandbox Linux. `encrypted` (giá trị trả về
    # của save_api_key) PHẢI phản ánh ĐÚNG thực tế đã lưu mã hoá hay
    # chưa, để Settings UI không hiện sai thông tin -- verify đúng theo
    # từng nền tảng thay vì hardcode 1 giá trị cho mọi máy.
    with tempfile.TemporaryDirectory() as tmp:
        encrypted = save_api_key("gsk_test_xxx", base_dir=Path(tmp))
    if platform.system() == "Windows":
        assert encrypted is True, (
            "Trên Windows THẬT, DPAPI phải dùng được -- nếu False, có vấn "
            "đề THẬT với DPAPI trên máy này (quyền user profile, Windows "
            "bị lỗi...), không phải lỗi của bản thân test này."
        )
    else:
        assert encrypted is False, (
            "Không phải Windows (Linux/Mac) -- không có DPAPI, phải fallback plaintext."
        )
    print("OK: test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may")


def test_is_encrypted_storage_available_khop_voi_platform_thuc_te():
    # 🔒 SỬA (xem docstring đầu file) -- tương tự test trên.
    result = is_encrypted_storage_available()
    if platform.system() == "Windows":
        assert result is True, (
            "Trên Windows THẬT, DPAPI round-trip (encrypt rồi decrypt lại "
            "1 chuỗi test) phải thành công -- False nghĩa là DPAPI THẬT SỰ "
            "có vấn đề trên máy này, cần điều tra riêng, không phải lỗi test."
        )
    else:
        assert result is False, (
            "Không phải Windows -- KHÔNG có DPAPI, phải trả False, không "
            "được lạc quan giả định có."
        )
    print("OK: test_is_encrypted_storage_available_khop_voi_platform_thuc_te")


def test_config_path_nam_dung_thu_muc_appdata_neu_co():
    # Xác nhận logic chọn đường dẫn ĐÚNG quy ước Windows khi APPDATA tồn tại
    # (mô phỏng bằng biến môi trường, không cần chạy Windows thật để verify
    # phần LOGIC chọn đường dẫn -- chỉ phần DPAPI thật mới cần Windows).
    #
    # 🔒 SỬA (05/09/2026, phát hiện qua log Windows thật gửi kèm) -- trước
    # đây so sánh `str(path)` (từ `pathlib.Path`, TỰ CHUẨN HOÁ mọi dấu "/"
    # thành "\\" trên Windows) với `os.path.join(...)` (KHÔNG chuẩn hoá
    # phần đầu đã có sẵn, chỉ nối thêm phần sau bằng "\\") -- 2 cách tính
    # ra 2 CHUỖI KHÁC NHAU trên Windows (`os.path.join` giữ nguyên "/" ở
    # phần gốc, pathlib đổi hết thành "\\") dù cùng trỏ 1 đường dẫn, khiến
    # assertion FAIL dù logic app hoàn toàn đúng. Sửa: so sánh 2 `Path`
    # object trực tiếp (`==`, pathlib tự so sánh đúng ý nghĩa, không quan
    # tâm chuỗi biểu diễn) thay vì so `str()` với `os.path.join()`.
    original = os.environ.get("APPDATA")
    os.environ["APPDATA"] = "/fake/appdata/path"
    try:
        path = get_config_path()
        expected = Path("/fake/appdata/path") / "AIMeetingCompanion" / "config.json"
        assert path == expected, f"Mong đợi {expected!r}, nhận {path!r}"
    finally:
        if original is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = original
    print("OK: test_config_path_nam_dung_thu_muc_appdata_neu_co")


# ---------------------------------------------------------------------------
# 🔒 MỚI -- multi-provider (CONTRACTS.md Mục 17). Mọi test PHÍA TRÊN giữ
# NGUYÊN, không sửa gì -- chứng minh tương thích ngược 100% với hành vi
# trước khi có multi-provider (gọi không truyền `provider=` luôn ngầm định
# "groq", đọc/ghi đúng như Vòng 6).
# ---------------------------------------------------------------------------


def test_save_load_3_provider_doc_lap_khong_de_lan():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        save_api_key("sk_openai_key", provider="openai", base_dir=base)
        save_api_key("gemini_key_abc", provider="gemini", base_dir=base)

        assert load_api_key(provider="groq", base_dir=base) == "gsk_groq_key"
        assert load_api_key(provider="openai", base_dir=base) == "sk_openai_key"
        assert load_api_key(provider="gemini", base_dir=base) == "gemini_key_abc"
    print("OK: test_save_load_3_provider_doc_lap_khong_de_lan")


def test_save_provider_khac_khong_lam_mat_key_provider_cu():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        save_api_key("sk_openai_key", provider="openai", base_dir=base)
        # Lưu lại key Groq lần 2 (đổi key) -- KHÔNG được ảnh hưởng key OpenAI.
        save_api_key("gsk_groq_key_v2", provider="groq", base_dir=base)
        assert load_api_key(provider="groq", base_dir=base) == "gsk_groq_key_v2"
        assert load_api_key(provider="openai", base_dir=base) == "sk_openai_key", (
            "Đổi key Groq KHÔNG được làm mất key OpenAI đã lưu trước đó."
        )
    print("OK: test_save_provider_khac_khong_lam_mat_key_provider_cu")


def test_load_provider_chua_tung_luu_tra_none_khong_anh_huong_provider_khac():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        assert load_api_key(provider="gemini", base_dir=base) is None
        assert load_api_key(provider="groq", base_dir=base) == "gsk_groq_key"
    print("OK: test_load_provider_chua_tung_luu_tra_none_khong_anh_huong_provider_khac")


def test_save_tu_dong_dat_active_provider():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        assert get_active_provider(base_dir=base) == "groq"
        save_api_key("sk_openai_key", provider="openai", base_dir=base)
        assert get_active_provider(base_dir=base) == "openai", (
            "Lưu key cho provider MỚI phải tự đặt provider đó thành đang dùng."
        )
    print("OK: test_save_tu_dong_dat_active_provider")


def test_set_active_provider_khong_xoa_key_da_luu():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        save_api_key("sk_openai_key", provider="openai", base_dir=base)
        set_active_provider("groq", base_dir=base)
        assert get_active_provider(base_dir=base) == "groq"
        # Key OpenAI vẫn còn nguyên, KHÔNG bị xoá chỉ vì đổi active_provider.
        assert load_api_key(provider="openai", base_dir=base) == "sk_openai_key"
    print("OK: test_set_active_provider_khong_xoa_key_da_luu")


def test_get_active_provider_mac_dinh_groq_khi_chua_tung_luu_gi():
    with tempfile.TemporaryDirectory() as tmp:
        assert get_active_provider(base_dir=Path(tmp)) == "groq", (
            "Người dùng cũ/mới hoàn toàn chưa cài đặt gì -- mặc định groq."
        )
    print("OK: test_get_active_provider_mac_dinh_groq_khi_chua_tung_luu_gi")


def test_clear_1_provider_khong_dung_provider_khac():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        save_api_key("sk_openai_key", provider="openai", base_dir=base)
        clear_api_key(provider="openai", base_dir=base)
        assert load_api_key(provider="openai", base_dir=base) is None
        assert load_api_key(provider="groq", base_dir=base) == "gsk_groq_key", (
            "Xoá key OpenAI KHÔNG được đụng tới key Groq."
        )
    print("OK: test_clear_1_provider_khong_dung_provider_khac")


def test_clear_provider_dang_active_tu_chuyen_active_sang_provider_con_lai():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("sk_openai_key", provider="openai", base_dir=base)  # active="openai"
        save_api_key("gemini_key", provider="gemini", base_dir=base)     # active="gemini"
        clear_api_key(provider="gemini", base_dir=base)
        # "gemini" vừa bị xoá VÀ đang là active -- phải tự chuyển sang
        # provider còn lại ("openai"), không được trả về "gemini" rỗng key.
        assert get_active_provider(base_dir=base) == "openai"
    print("OK: test_clear_provider_dang_active_tu_chuyen_active_sang_provider_con_lai")


def test_clear_provider_cuoi_cung_xoa_luon_ca_file():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        clear_api_key(provider="groq", base_dir=base)
        assert not get_config_path(base_dir=base).exists(), (
            "Xoá provider DUY NHẤT còn lại -- phải dọn sạch cả file (đúng "
            "hành vi cũ trước multi-provider)."
        )
    print("OK: test_clear_provider_cuoi_cung_xoa_luon_ca_file")


def test_list_configured_providers():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        assert list_configured_providers(base_dir=base) == []
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        save_api_key("sk_openai_key", provider="openai", base_dir=base)
        configured = set(list_configured_providers(base_dir=base))
        assert configured == {"groq", "openai"}
    print("OK: test_list_configured_providers")


def test_load_doc_duoc_file_dinh_dang_cu_chi_groq_truoc_multi_provider():
    # 🔒 Test TƯƠNG THÍCH NGƯỢC quan trọng nhất: người dùng đã cài app từ
    # Vòng 6 (TRƯỚC khi có multi-provider), file config.json của họ là
    # ĐỊNH DẠNG CŨ (flat, field "groq_api_key" -- xem
    # test_load_an_toan_khi_encoding_la_dpapi_nhung_dang_chay_khong_phai_windows
    # ở trên, viết file THỦ CÔNG đúng định dạng cũ, KHÔNG qua save_api_key
    # mới). Cập nhật app KHÔNG được làm mất key Groq họ đã nhập.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        config_path = get_config_path(base_dir=base)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"encoding": "plaintext", "groq_api_key": "gsk_da_luu_truoc_khi_co_multi_provider"}),
            encoding="utf-8",
        )
        assert load_api_key(provider="groq", base_dir=base) == "gsk_da_luu_truoc_khi_co_multi_provider"
        # Provider KHÁC trên file định dạng cũ -- chưa từng tồn tại, phải None.
        assert load_api_key(provider="openai", base_dir=base) is None
        assert get_active_provider(base_dir=base) == "groq", (
            "File định dạng cũ chưa từng có active_provider -- mặc định groq."
        )
    print("OK: test_load_doc_duoc_file_dinh_dang_cu_chi_groq_truoc_multi_provider")


def test_save_migrate_dinh_dang_cu_sang_moi_khong_mat_key_groq():
    # Người dùng cũ mở Settings, đổi qua thử Gemini -- save_api_key() PHẢI
    # tự "migrate-on-write" file định dạng cũ sang định dạng mới, GIỮ
    # NGUYÊN key Groq cũ thay vì ghi đè mất.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        config_path = get_config_path(base_dir=base)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"encoding": "plaintext", "groq_api_key": "gsk_key_cu_truoc_migrate"}),
            encoding="utf-8",
        )
        save_api_key("gemini_key_moi", provider="gemini", base_dir=base)

        assert load_api_key(provider="groq", base_dir=base) == "gsk_key_cu_truoc_migrate", (
            "Migrate-on-write PHẢI giữ nguyên key Groq cũ, không làm mất."
        )
        assert load_api_key(provider="gemini", base_dir=base) == "gemini_key_moi"
    print("OK: test_save_migrate_dinh_dang_cu_sang_moi_khong_mat_key_groq")


# ---------------------------------------------------------------------------
# 🔒 MỚI (T18, CONTRACTS.md Mục 31, Backlog #4) -- test cho
# save/load/clear_model_overrides(). Cùng convention `base_dir=<thư mục
# tạm>` như mọi test trên -- KHÔNG đụng %APPDATA% thật.
# ---------------------------------------------------------------------------


def test_model_overrides_roundtrip_dung_field():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_model_overrides(
            "groq",
            {"translate_model": "openai/gpt-oss-120b", "stt_model": "whisper-large-v3"},
            base_dir=base,
        )
        result = load_model_overrides("groq", base_dir=base)
        assert result == {
            "translate_model": "openai/gpt-oss-120b",
            "stt_model": "whisper-large-v3",
        }
    print("OK: test_model_overrides_roundtrip_dung_field")


def test_model_overrides_chua_tung_luu_tra_dict_rong():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        assert load_model_overrides("groq", base_dir=base) == {}
    print("OK: test_model_overrides_chua_tung_luu_tra_dict_rong")


def test_model_overrides_field_rong_khong_duoc_luu():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_model_overrides(
            "openai",
            {"translate_model": "gpt-5-mini", "stt_model": "   "},
            base_dir=base,
        )
        result = load_model_overrides("openai", base_dir=base)
        assert result == {"translate_model": "gpt-5-mini"}, (
            "Field rỗng/toàn khoảng trắng KHÔNG được lưu như 1 override thật."
        )
    print("OK: test_model_overrides_field_rong_khong_duoc_luu")


def test_model_overrides_field_la_bi_bo_qua():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_model_overrides(
            "gemini",
            {"translate_model": "gemini-2.5-flash", "field_khong_ton_tai": "abc"},
            base_dir=base,
        )
        result = load_model_overrides("gemini", base_dir=base)
        assert result == {"translate_model": "gemini-2.5-flash"}, (
            "Field không nằm trong _MODEL_OVERRIDE_FIELDS phải bị bỏ qua lặng lẽ."
        )
    print("OK: test_model_overrides_field_la_bi_bo_qua")


def test_model_overrides_provider_khac_khong_bi_dung():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_model_overrides("groq", {"translate_model": "openai/gpt-oss-120b"}, base_dir=base)
        save_model_overrides("openai", {"translate_model": "gpt-5-mini"}, base_dir=base)

        assert load_model_overrides("groq", base_dir=base) == {
            "translate_model": "openai/gpt-oss-120b",
        }
        assert load_model_overrides("openai", base_dir=base) == {
            "translate_model": "gpt-5-mini",
        }
    print("OK: test_model_overrides_provider_khac_khong_bi_dung")


def test_clear_model_overrides_xoa_dung_provider_khong_dung_provider_khac():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_model_overrides("groq", {"translate_model": "openai/gpt-oss-120b"}, base_dir=base)
        save_model_overrides("openai", {"translate_model": "gpt-5-mini"}, base_dir=base)

        clear_model_overrides("groq", base_dir=base)

        assert load_model_overrides("groq", base_dir=base) == {}
        assert load_model_overrides("openai", base_dir=base) == {"translate_model": "gpt-5-mini"}
    print("OK: test_clear_model_overrides_xoa_dung_provider_khong_dung_provider_khac")


def test_clear_model_overrides_khong_loi_khi_chua_tung_luu():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        clear_model_overrides("groq", base_dir=base)  # KHÔNG raise
        assert load_model_overrides("groq", base_dir=base) == {}
    print("OK: test_clear_model_overrides_khong_loi_khi_chua_tung_luu")


def test_model_overrides_khong_anh_huong_api_key_va_active_provider():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_api_key("gsk_groq_key", provider="groq", base_dir=base)
        set_active_provider("groq", base_dir=base)

        save_model_overrides("groq", {"translate_model": "openai/gpt-oss-120b"}, base_dir=base)

        assert load_api_key(provider="groq", base_dir=base) == "gsk_groq_key", (
            "Lưu model override KHÔNG được làm mất API key đã lưu."
        )
        assert get_active_provider(base_dir=base) == "groq", (
            "Lưu model override KHÔNG được đổi active_provider."
        )
    print("OK: test_model_overrides_khong_anh_huong_api_key_va_active_provider")


if __name__ == "__main__":
    test_load_tra_none_khi_chua_tung_luu()
    test_save_va_load_roundtrip_dung_key()
    test_save_tu_dong_don_whitespace_va_quote_thua()
    test_save_lan_2_ghi_de_lan_1()
    test_clear_api_key_xoa_duoc_va_load_lai_tra_none()
    test_clear_api_key_khong_loi_khi_chua_tung_luu()
    test_load_an_toan_khi_file_json_hong()
    test_load_an_toan_khi_encoding_la_dpapi_nhung_dang_chay_khong_phai_windows()
    test_load_an_toan_khi_thieu_field_key()
    test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may()
    test_is_encrypted_storage_available_khop_voi_platform_thuc_te()
    test_config_path_nam_dung_thu_muc_appdata_neu_co()
    test_save_load_3_provider_doc_lap_khong_de_lan()
    test_save_provider_khac_khong_lam_mat_key_provider_cu()
    test_load_provider_chua_tung_luu_tra_none_khong_anh_huong_provider_khac()
    test_save_tu_dong_dat_active_provider()
    test_set_active_provider_khong_xoa_key_da_luu()
    test_get_active_provider_mac_dinh_groq_khi_chua_tung_luu_gi()
    test_clear_1_provider_khong_dung_provider_khac()
    test_clear_provider_dang_active_tu_chuyen_active_sang_provider_con_lai()
    test_clear_provider_cuoi_cung_xoa_luon_ca_file()
    test_list_configured_providers()
    test_load_doc_duoc_file_dinh_dang_cu_chi_groq_truoc_multi_provider()
    test_save_migrate_dinh_dang_cu_sang_moi_khong_mat_key_groq()
    test_model_overrides_roundtrip_dung_field()
    test_model_overrides_chua_tung_luu_tra_dict_rong()
    test_model_overrides_field_rong_khong_duoc_luu()
    test_model_overrides_field_la_bi_bo_qua()
    test_model_overrides_provider_khac_khong_bi_dung()
    test_clear_model_overrides_xoa_dung_provider_khong_dung_provider_khac()
    test_clear_model_overrides_khong_loi_khi_chua_tung_luu()
    test_model_overrides_khong_anh_huong_api_key_va_active_provider()
    print("\n=== TẤT CẢ TEST CONFIG_STORE PASS ===")
