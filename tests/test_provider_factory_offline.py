"""
Unit test cho app/ai/provider_factory.py — KHÔNG gọi network thật.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config_store  # noqa: E402
from app.ai.base_provider import ProviderError  # noqa: E402
from app.ai.gemini_provider import GeminiProvider  # noqa: E402
from app.ai.groq_provider import GroqProvider  # noqa: E402
from app.ai.openai_provider import OpenAIProvider  # noqa: E402
from app.ai.provider_factory import create_provider, display_name  # noqa: E402


def test_create_provider_explicit_groq():
    provider = create_provider(provider="groq", api_key="gsk_fake")
    assert isinstance(provider, GroqProvider)
    print("OK: test_create_provider_explicit_groq")


def test_create_provider_explicit_openai():
    provider = create_provider(provider="openai", api_key="sk-fake")
    assert isinstance(provider, OpenAIProvider)
    print("OK: test_create_provider_explicit_openai")


def test_create_provider_explicit_gemini():
    provider = create_provider(provider="gemini", api_key="fake")
    assert isinstance(provider, GeminiProvider)
    print("OK: test_create_provider_explicit_gemini")


def test_create_provider_case_insensitive():
    provider = create_provider(provider="OpenAI", api_key="sk-fake")
    assert isinstance(provider, OpenAIProvider), "Phải không phân biệt hoa/thường."
    print("OK: test_create_provider_case_insensitive")


def test_create_provider_provider_none_doc_active_provider_tu_config_store():
    # Mô phỏng việc create_provider(provider=None) đọc
    # config_store.get_active_provider() -- monkeypatch hàm này để KHÔNG
    # đụng tới %APPDATA% thật của máy chạy test.
    original_get_active = config_store.get_active_provider
    config_store.get_active_provider = lambda base_dir=None: "gemini"
    try:
        provider = create_provider(provider=None, api_key="fake")
        assert isinstance(provider, GeminiProvider)
    finally:
        config_store.get_active_provider = original_get_active
    print("OK: test_create_provider_provider_none_doc_active_provider_tu_config_store")


def test_create_provider_default_la_groq_khi_chua_tung_cai_dat_gi():
    original_get_active = config_store.get_active_provider
    config_store.get_active_provider = lambda base_dir=None: "groq"
    try:
        provider = create_provider(provider=None, api_key="gsk_fake")
        assert isinstance(provider, GroqProvider), (
            "Người dùng cũ (Vòng 6, chỉ biết Groq) chưa từng cài đặt gì -- "
            "PHẢI mặc định về Groq, không được tự đổi sang provider khác."
        )
    finally:
        config_store.get_active_provider = original_get_active
    print("OK: test_create_provider_default_la_groq_khi_chua_tung_cai_dat_gi")


def test_create_provider_ten_khong_hop_le_raise_provider_error():
    try:
        create_provider(provider="claude", api_key="x")
        raise AssertionError("Phải raise ProviderError với provider không hỗ trợ.")
    except ProviderError as exc:
        assert "claude" in str(exc)
    print("OK: test_create_provider_ten_khong_hop_le_raise_provider_error")


def test_create_provider_truyen_kwargs_xuong_constructor():
    provider = create_provider(provider="groq", api_key="gsk_fake", translate_model="llama-3.1-8b-instant")
    assert provider._translate_model == "llama-3.1-8b-instant"
    print("OK: test_create_provider_truyen_kwargs_xuong_constructor")


# ---------------------------------------------------------------------------
# 🔒 MỚI (T19, CONTRACTS.md Mục 31, Backlog #4) -- test cho việc merge
# model override đã lưu qua Settings UI vào create_provider(). Monkeypatch
# `config_store.load_model_overrides` (KHÔNG dùng base_dir thật) -- cùng lý
# do cách ly test khỏi %APPDATA% thật đã áp dụng ở TASKS.md Mục 25 (T9)
# cho `load_api_key`: `create_provider()` gọi `load_model_overrides()`
# KHÔNG truyền base_dir, nên phải monkeypatch thẳng hàm thay vì dùng
# tempfile, nếu không test sẽ đọc/ghi nhầm vào config.json thật của máy
# chạy test.
# ---------------------------------------------------------------------------


def test_create_provider_dung_model_override_da_luu_qua_settings():
    original_load = config_store.load_model_overrides
    config_store.load_model_overrides = lambda provider, base_dir=None: {
        "translate_model": "model-tu-settings-ui",
    }
    try:
        provider = create_provider(provider="groq", api_key="gsk_fake")
        assert provider._translate_model == "model-tu-settings-ui", (
            "create_provider() PHẢI dùng model override đã lưu qua Settings "
            "UI khi caller KHÔNG tự truyền kwargs."
        )
    finally:
        config_store.load_model_overrides = original_load
    print("OK: test_create_provider_dung_model_override_da_luu_qua_settings")


def test_create_provider_kwargs_thang_model_override_da_luu():
    original_load = config_store.load_model_overrides
    config_store.load_model_overrides = lambda provider, base_dir=None: {
        "translate_model": "model-tu-settings-ui",
    }
    try:
        provider = create_provider(
            provider="groq", api_key="gsk_fake", translate_model="model-truyen-truc-tiep",
        )
        assert provider._translate_model == "model-truyen-truc-tiep", (
            "kwargs caller truyền TRỰC TIẾP phải THẮNG override đã lưu qua "
            "Settings UI (đúng thứ tự ưu tiên CONTRACTS.md Mục 31)."
        )
    finally:
        config_store.load_model_overrides = original_load
    print("OK: test_create_provider_kwargs_thang_model_override_da_luu")


def test_create_provider_khong_co_override_dung_default_provider():
    original_load = config_store.load_model_overrides
    config_store.load_model_overrides = lambda provider, base_dir=None: {}
    try:
        provider = create_provider(provider="groq", api_key="gsk_fake")
        assert provider._translate_model == "openai/gpt-oss-120b", (
            "Chưa từng override qua Settings UI -- PHẢI dùng default hardcode "
            "của GroqProvider như trước Mục 31, không bị đổi hành vi."
        )
    finally:
        config_store.load_model_overrides = original_load
    print("OK: test_create_provider_khong_co_override_dung_default_provider")


def test_display_name():
    assert display_name("groq") == "Groq"
    assert display_name("openai") == "OpenAI"
    assert display_name("gemini") == "Gemini"
    assert display_name("OPENAI") == "OpenAI", "Phải không phân biệt hoa/thường."
    assert display_name("mystery") == "Mystery", "Provider lạ -- fallback capitalize(), không raise."
    print("OK: test_display_name")


def test_create_provider_doc_bien_moi_truong_ai_provider_khi_khong_truyen_gi():
    os.environ.pop("AI_PROVIDER", None)
    original_get_active = config_store.get_active_provider
    config_store.get_active_provider = lambda base_dir=None: "groq"
    try:
        os.environ["AI_PROVIDER"] = "openai"
        provider = create_provider(provider=None, api_key="sk-fake")
        assert isinstance(provider, OpenAIProvider), (
            "AI_PROVIDER env var phải được ưu tiên HƠN config_store khi dev "
            "từ source code (xem .env.example)."
        )
    finally:
        os.environ.pop("AI_PROVIDER", None)
        config_store.get_active_provider = original_get_active
    print("OK: test_create_provider_doc_bien_moi_truong_ai_provider_khi_khong_truyen_gi")


if __name__ == "__main__":
    test_create_provider_explicit_groq()
    test_create_provider_explicit_openai()
    test_create_provider_explicit_gemini()
    test_create_provider_case_insensitive()
    test_create_provider_provider_none_doc_active_provider_tu_config_store()
    test_create_provider_default_la_groq_khi_chua_tung_cai_dat_gi()
    test_create_provider_ten_khong_hop_le_raise_provider_error()
    test_create_provider_truyen_kwargs_xuong_constructor()
    test_create_provider_doc_bien_moi_truong_ai_provider_khi_khong_truyen_gi()
    test_create_provider_dung_model_override_da_luu_qua_settings()
    test_create_provider_kwargs_thang_model_override_da_luu()
    test_create_provider_khong_co_override_dung_default_provider()
    test_display_name()
    print("\n=== TẤT CẢ TEST PROVIDER_FACTORY (OFFLINE/MOCK) PASS ===")
