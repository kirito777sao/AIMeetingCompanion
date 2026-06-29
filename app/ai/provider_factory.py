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
            cho người dùng nâng cao muốn ép đổi model mặc định.

    Returns:
        AIProvider: `GroqProvider`/`OpenAIProvider`/`GeminiProvider`.

    Raises:
        ProviderError: provider không được hỗ trợ (lỗi cấu hình, không nên
            xảy ra qua Settings UI vì dropdown chỉ cho chọn 3 giá trị hợp
            lệ — chỉ có thể xảy ra nếu file config.json bị sửa tay sai),
            HOẶC bất kỳ ProviderError nào constructor của provider cụ thể
            tự raise (thiếu key, key mẫu, v.v — xem provider tương ứng).
    """
    resolved = (
        provider
        or os.environ.get("AI_PROVIDER")
        or config_store.get_active_provider()
        or "groq"
    ).strip().lower()

    if resolved == "groq":
        return GroqProvider(api_key=api_key, **kwargs)
    if resolved == "openai":
        return OpenAIProvider(api_key=api_key, **kwargs)
    if resolved == "gemini":
        return GeminiProvider(api_key=api_key, **kwargs)

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
