"""app/ai/provider_factory.py
-------------------------------
🔒 MỚI (đợt thêm multi-provider — Groq/OpenAI/Gemini, xem CONTRACTS.md Mục
17) — 1 điểm DUY NHẤT quyết định "dùng provider AI nào", thay cho việc
`ui/main_window.py` gọi thẳng `GroqProvider()` ở 6 chỗ khác nhau (audio
worker khởi động phiên ghi, suggest_answer, 2 lần translate, summarize,
v.v — xem lịch sử trước đợt này).

Vì sao cần factory riêng (không để mỗi nơi tự `if provider == "groq": ...`):
1 chỗ sai sót đổi logic chọn provider chỉ cần sửa Ở ĐÂY, không phải lục lại
6 chỗ rải rác trong `main_window.py` mỗi lần thêm provider thứ 4 sau này.

Cách dùng (xem `ui/main_window.py` sau refactor):
    from app.ai.provider_factory import create_provider
    provider = create_provider()   # tự đọc provider "đang dùng" qua config_store

`create_provider()` KHÔNG tự bắt `ProviderError` — để nguyên cho caller xử
lý (mọi nơi gọi `GroqProvider()` cũ trong `main_window.py` đã có sẵn
try/except ProviderError quanh chỗ khởi tạo, xem `AudioWorker.run()`/
`OneShotAIWorker` — hành vi báo lỗi cho người dùng GIỮ NGUYÊN, chỉ đổi
provider nào được tạo ra).
"""

from __future__ import annotations

import os

from app import config_store
from app.ai.base_provider import AIProvider, ProviderError
from app.ai.gemini_provider import GeminiProvider
from app.ai.groq_provider import GroqProvider
from app.ai.openai_provider import OpenAIProvider

_PROVIDER_DISPLAY_NAMES = {
    "groq": "Groq",
    "openai": "OpenAI",
    "gemini": "Gemini",
}

# 🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- CHỈ dùng để hiện placeholder
# cho người dùng biết default HIỆN TẠI là gì trên Settings UI
# (`ui/settings_dialog.py`) -- KHÔNG dùng giá trị này để quyết định hành
# vi thật. Model THẬT SỰ được dùng khi người dùng để trống override luôn
# do CHÍNH constructor của GroqProvider/OpenAIProvider/GeminiProvider
# quyết định (xem `app/ai/*_provider.py`), độc lập hoàn toàn với dict này.
# ⚠️ Dict này PHẢI tự tay cập nhật nếu default thật trong provider đổi --
# không có cơ chế tự đồng bộ (đã cân nhắc dùng `inspect.signature()` đọc
# default thật, nhưng GroqProvider dùng `None` làm default rồi tự resolve
# qua env/hardcode BÊN TRONG `__init__` -- signature không phản ánh đúng
# giá trị hiệu lực thật, nên chọn hardcode dict này, đơn giản hơn và rủi
# ro thấp vì tên model đổi không thường xuyên).
_DEFAULT_MODELS_FOR_DISPLAY: dict[str, dict[str, str]] = {
    "groq": {
        "stt_model": "whisper-large-v3",
        "stt_fallback_model": "whisper-large-v3-turbo",
        "translate_model": "openai/gpt-oss-120b",
        "translate_fallback_model": "openai/gpt-oss-20b",
    },
    "openai": {
        "stt_model": "whisper-1",
        "stt_fallback_model": "(không có -- whisper-1 không có bản rẻ hơn để fallback)",
        "translate_model": "gpt-5-mini",
        "translate_fallback_model": "gpt-5-nano",
    },
    "gemini": {
        "stt_model": "gemini-2.5-flash",
        "stt_fallback_model": "(không có -- Gemini STT không có model dự phòng)",
        "translate_model": "gemini-2.5-flash",
        "translate_fallback_model": "gemini-2.0-flash",
    },
}


def get_default_models_for_display(provider: str) -> dict[str, str]:
    """Trả dict tên model MẶC ĐỊNH của `provider`, CHỈ để hiện placeholder
    gợi ý trên Settings UI -- xem cảnh báo ở docstring `_DEFAULT_MODELS_FOR_DISPLAY`
    phía trên. `provider` lạ trả dict rỗng (KHÔNG raise)."""
    return dict(_DEFAULT_MODELS_FOR_DISPLAY.get(provider.strip().lower(), {}))


def create_provider(provider: str | None = None, api_key: str | None = None, **kwargs) -> AIProvider:
    """Tạo 1 instance `AIProvider` ĐÚNG loại người dùng đang chọn.

    Args:
        provider: "groq" | "openai" | "gemini". Nếu None, đọc theo thứ tự:
            (1) biến môi trường `AI_PROVIDER` (dev/test từ source code,
            xem .env.example); (2) `config_store.get_active_provider()` —
            provider người dùng lưu lần gần nhất qua Settings (mặc định
            "groq" nếu chưa từng cài đặt gì, tương thích ngược với người
            dùng cũ chỉ biết Groq).
        api_key: truyền thẳng xuống constructor của provider cụ thể — để
            trống (None) trong mọi trường hợp dùng thật (mỗi provider tự
            đọc key đã lưu của CHÍNH NÓ qua `config_store.load_api_key()`)
            — tham số này chỉ hữu ích cho test/script dev muốn ép 1 key cụ
            thể không qua Settings UI.
        **kwargs: truyền thẳng xuống constructor (vd `translate_model=`)
            cho người dùng nâng cao muốn ép đổi model mặc định. 🔒 MỚI
            (Backlog #4) -- field NÀO caller ĐÃ truyền tường minh ở đây sẽ
            THẮNG model override đã lưu qua Settings UI (xem bên dưới) --
            caller gọi trực tiếp trong code (vd test, script dev) luôn có
            quyền ưu tiên cao nhất, override qua UI chỉ là lớp mặc định kế
            tiếp cho người dùng thường không sửa code.

    Returns:
        AIProvider: `GroqProvider`/`OpenAIProvider`/`GeminiProvider`.

    Raises:
        ProviderError: provider không được hỗ trợ (lỗi cấu hình, không nên
            xảy ra qua Settings UI vì dropdown chỉ cho chọn 3 giá trị hợp
            lệ — chỉ có thể xảy ra nếu file config.json bị sửa tay sai),
            HOẶC bất kỳ ProviderError nào constructor của provider cụ thể
            tự raise (thiếu key, key mẫu, model override sai tên, v.v —
            xem provider tương ứng).
    """
    resolved = (
        provider
        or os.environ.get("AI_PROVIDER")
        or config_store.get_active_provider()
        or "groq"
    ).strip().lower()

    # 🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- merge model override đã
    # lưu qua Settings UI (`config_store.load_model_overrides()`) làm nền,
    # NHƯNG field nào `kwargs` (caller truyền trực tiếp) ĐÃ có thì GIỮ
    # NGUYÊN của caller -- {**overrides, **kwargs} đúng thứ tự ưu tiên đó
    # (dict sau đè dict trước ở Python).
    merged_kwargs = {**config_store.load_model_overrides(resolved), **kwargs}

    if resolved == "groq":
        return GroqProvider(api_key=api_key, **merged_kwargs)
    if resolved == "openai":
        return OpenAIProvider(api_key=api_key, **merged_kwargs)
    if resolved == "gemini":
        return GeminiProvider(api_key=api_key, **merged_kwargs)

    raise ProviderError(
        f"Provider AI '{resolved}' không được hỗ trợ (chỉ hỗ trợ: "
        f"{', '.join(_PROVIDER_DISPLAY_NAMES)}). Vào ⚙️ Cài đặt, chọn lại "
        "provider hợp lệ — nếu lỗi này lặp lại, file config cục bộ có thể "
        "đã bị sửa tay sai định dạng, thử bấm 'Xoá key đã lưu' rồi nhập lại."
    )


def display_name(provider: str) -> str:
    """Tên hiển thị đẹp cho UI (Settings dropdown, thông báo lỗi) — fallback
    về chính `provider` (capitalize) nếu lạ, KHÔNG raise."""
    return _PROVIDER_DISPLAY_NAMES.get(provider.strip().lower(), provider.strip().capitalize())
