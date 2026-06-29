"""
app/config_store.py
--------------------
🔒 MỚI (F14 — PROJECT_SPEC.md mục 4/10.4, xem CONTRACTS.md Mục 12) — lưu API
key người dùng CUỐI tự nhập qua Settings UI (`ui/settings_dialog.py`), KHÔNG
phải key của người phát triển hardcode trong `.env`.

Vì sao cần module này (bối cảnh — đọc kỹ trước khi sửa):
Lúc đang code/test, `.env` (đọc qua `python-dotenv` ở `app/main.py`) là đủ
dùng vì chỉ có 1 người (bạn) chạy `python -m app.main` từ source. Nhưng khi
đóng gói thành `.exe` (PyInstaller) để đưa người khác dùng, KHÔNG thể đặt
sẵn 1 file `.env` chứa GROQ_API_KEY của BẠN vào trong bản phân phối — mỗi
người dùng phải tự lấy API key CỦA RIÊNG HỌ và tự chịu trách nhiệm về việc
dùng model AI của họ (đúng yêu cầu — xem lịch sử hỏi đáp). Module này lưu
key đó vào 1 file CỤC BỘ trên máy người dùng, đọc lại mỗi lần app khởi
động — không cần sửa code/biên dịch lại app mỗi lần đổi key.

🔒 MỞ RỘNG (đợt thêm multi-provider — Groq/OpenAI/Gemini, xem CONTRACTS.md
Mục 17): trước đây module này CHỈ lưu được 1 key Groq duy nhất (field
"groq_api_key" ở cấp cao nhất của config.json). Giờ lưu được NHIỀU key,
mỗi provider 1 key riêng (người dùng có thể đổi qua lại Groq/OpenAI/Gemini
trong Settings KHÔNG mất key đã nhập của provider khác), + 1 "provider
đang dùng" (`active_provider`). Định dạng file MỚI:

    {
      "active_provider": "groq",
      "providers": {
        "groq":   {"encoding": "dpapi"|"plaintext", "api_key": "..."},
        "openai": {"encoding": "dpapi"|"plaintext", "api_key": "..."},
        "gemini": {"encoding": "dpapi"|"plaintext", "api_key": "..."}
      }
    }

**Tương thích ngược BẮT BUỘC** (người dùng cũ đã lưu key Groq qua Vòng 6
trước khi có multi-provider KHÔNG được mất key khi cập nhật app): mọi hàm
đọc (`load_api_key`) vẫn đọc được file ĐỊNH DẠNG CŨ (flat, không có
"providers") cho đúng `provider="groq"` — coi định dạng cũ là "chỉ có
Groq". File chỉ thật sự chuyển sang định dạng MỚI khi `save_api_key()`
được gọi lần kế tiếp (migrate-on-write, không tự ý sửa file người dùng
chỉ vì đọc). `save_api_key()`/`load_api_key()`/`clear_api_key()` đều có
tham số `provider: str = "groq"` MỚI nhưng đặt SAU `api_key`/đầu tiên
tương ứng — mọi lời gọi CŨ (vị trí/từ khoá `base_dir=`, không truyền
`provider`) tiếp tục hoạt động NGUYÊN VẸN, ngầm định "groq" — KHÔNG cần
sửa `GroqProvider.__init__()` hay `tests/test_config_store.py` ở các test
đã có từ trước.

Vị trí lưu: `%APPDATA%\\AIMeetingCompanion\\config.json` trên Windows (đúng
quy ước Windows cho dữ liệu riêng từng user, KHÔNG nằm trong thư mục cài đặt
chương trình — thư mục đó có thể chỉ-đọc với user thường, vd `Program
Files`). Fallback `~/.ai_meeting_companion/config.json` nếu biến môi trường
APPDATA không tồn tại (vd khi tự chạy thử trên Linux/Mac để dev/test — KHÔNG
phải đường dùng thật cho người dùng cuối, app vẫn chỉ chạy Windows).

⚠️ VỀ "MÃ HOÁ" (PROJECT_SPEC.md mục 5 NFR: "API key mã hoá tại local") — NÓI
THẬT, KHÔNG NHẬN VƠ:
- Trên Windows: dùng DPAPI (`CryptProtectData`/`CryptUnprotectData` của
  Windows, qua `ctypes` — KHÔNG cần cài thêm package nào, có sẵn trong mọi
  Windows). Đây là mã hoá THẬT, gắn với tài khoản Windows đang đăng nhập —
  người khác đăng nhập máy đó (account khác) hoặc copy file qua máy khác sẽ
  KHÔNG giải mã được. Đây chính là API mà Windows Credential Manager/Chrome/
  nhiều app Windows khác dùng để lưu secret cục bộ, không phải tự chế.
- Trên môi trường KHÔNG có DPAPI (Linux/Mac dev/test, hoặc API Windows lỗi
  hi hữu): fallback lưu PLAINTEXT (KHÔNG mã hoá thật) — chỉ đáp ứng được yêu
  cầu "không hardcode/không commit/không nằm trong file .exe phân phối",
  KHÔNG đáp ứng được yêu cầu "mã hoá". `is_encrypted_storage_available()`
  cho biết đang ở nhánh nào — `ui/settings_dialog.py` PHẢI hiện rõ điều này
  cho người dùng biết, không im lặng giả vờ đã mã hoá khi rơi vào fallback.
- ⚠️ **CHƯA verify được DPAPI THẬT chạy đúng trên Windows trong sandbox này**
  (sandbox Linux, không có `ctypes.windll`) — đã verify được: code tự phát
  hiện đúng platform, fallback an toàn (không crash) khi DPAPI không sẵn có,
  và toàn bộ logic save/load/roundtrip ở NHÁNH FALLBACK (test_config_store.py
  chạy được trong sandbox này). Cần bạn tự test trên Windows thật để xác
  nhận nhánh DPAPI hoạt động đúng (lưu key, tắt mở app lại, đọc lại đúng key
  — xem README mục checklist mới) -- mỗi key của mỗi provider mã hoá ĐỘC
  LẬP (1 lần gọi CryptProtectData riêng), không gộp chung.
"""

from __future__ import annotations

import base64
import json
import os
import platform
from pathlib import Path
from typing import Optional

_APP_DIR_NAME = "AIMeetingCompanion"
_CONFIG_FILE_NAME = "config.json"
_KEY_FIELD = "groq_api_key"            # tên field LEGACY (định dạng cũ, chỉ Groq)
_ENCODING_FIELD = "encoding"  # "dpapi" | "plaintext"
_PROVIDERS_FIELD = "providers"          # 🔒 MỚI -- định dạng multi-provider
_ACTIVE_PROVIDER_FIELD = "active_provider"
_DEFAULT_PROVIDER = "groq"
_KNOWN_PROVIDERS = ("groq", "openai", "gemini")


class ConfigStoreError(RuntimeError):
    """Lỗi khi đọc/ghi file config cục bộ (quyền ghi, đĩa đầy, v.v.)."""


def get_config_dir(base_dir: Optional[Path] = None) -> Path:
    """Trả về thư mục chứa config.

    `base_dir`: CHỈ dùng để test (`tests/test_config_store.py`) trỏ vào 1
    thư mục tạm, KHÔNG dùng ở code thật — production luôn gọi
    `get_config_dir()` không truyền gì, tự suy đúng vị trí theo OS.
    """
    if base_dir is not None:
        return Path(base_dir)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / _APP_DIR_NAME
    # Fallback KHÔNG dùng cho người dùng cuối thật (app chỉ chạy Windows,
    # luôn có APPDATA) -- chỉ để dev/test trên Linux/Mac không crash.
    return Path.home() / ".ai_meeting_companion"


def get_config_path(base_dir: Optional[Path] = None) -> Path:
    return get_config_dir(base_dir) / _CONFIG_FILE_NAME


# ---------------------------------------------------------------------------
# DPAPI (Windows only) — pure ctypes, KHÔNG cần thêm package (pywin32, ...)
# ---------------------------------------------------------------------------


def is_encrypted_storage_available() -> bool:
    """True nếu đang chạy Windows VÀ gọi thử DPAPI thành công (round-trip 1
    chuỗi test ngắn) — dùng để `ui/settings_dialog.py` hiện đúng trạng thái
    cho người dùng, KHÔNG đoán mò chỉ dựa vào `platform.system()`."""
    if platform.system() != "Windows":
        return False
    try:
        sample = _dpapi_encrypt(b"healthcheck")
        return _dpapi_decrypt(sample) == b"healthcheck"
    except Exception:  # noqa: BLE001 - bất kỳ lỗi DPAPI nào -> coi như không sẵn có
        return False


def _dpapi_encrypt(data: bytes) -> bytes:
    """Mã hoá `data` bằng Windows DPAPI (CryptProtectData), gắn với user
    Windows hiện tại — chỉ chính user/máy đó giải mã lại được.

    Raises:
        RuntimeError: không phải Windows, hoặc Win32 API trả lỗi.
    """
    import ctypes
    import ctypes.wintypes as wintypes  # type: ignore[import-not-found]

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _to_blob(raw: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    in_blob = _to_blob(data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise RuntimeError("CryptProtectData thất bại (DPAPI).")
    try:
        result = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return result


def _dpapi_decrypt(data: bytes) -> bytes:
    """Giải mã ngược lại `_dpapi_encrypt()`. Raises RuntimeError nếu data
    không phải blob DPAPI hợp lệ cho đúng user/máy hiện tại (vd file config
    bị copy sang máy khác, hoặc user Windows khác) — caller (`load_api_key`)
    PHẢI bắt lỗi này và trả `None` thay vì để crash app khởi động."""
    import ctypes
    import ctypes.wintypes as wintypes  # type: ignore[import-not-found]

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _to_blob(raw: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    in_blob = _to_blob(data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise RuntimeError("CryptUnprotectData thất bại (DPAPI) — file config có thể không "
                            "hợp lệ cho user/máy hiện tại.")
    try:
        result = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return result


# ---------------------------------------------------------------------------
# API công khai — dùng ở ui/settings_dialog.py và app/ai/provider_factory.py
# ---------------------------------------------------------------------------


def _normalize_provider(provider: str) -> str:
    return (provider or _DEFAULT_PROVIDER).strip().lower()


def _read_raw_payload(base_dir: Optional[Path] = None) -> dict:
    """Đọc + parse file config thô. Trả `{}` (KHÔNG raise) nếu file chưa
    tồn tại hoặc JSON hỏng — mọi caller tự coi `{}` là "chưa có gì lưu"."""
    config_path = get_config_path(base_dir)
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _decode_entry(entry: Optional[dict]) -> Optional[str]:
    """Giải mã 1 entry `{"encoding": ..., "api_key": ...}` của ĐỊNH DẠNG
    MỚI hoặc của 1 entry Groq legacy đã được chuẩn hoá về hình dạng này.
    Trả None (KHÔNG raise) nếu entry hỏng/giải mã lỗi -- xem lý do ở
    docstring `load_api_key()`."""
    if not isinstance(entry, dict):
        return None
    encoding = entry.get("encoding")
    raw_value = entry.get("api_key")
    if not raw_value:
        return None
    if encoding == "plaintext":
        return str(raw_value)
    if encoding == "dpapi":
        try:
            cipher = base64.b64decode(raw_value)
            return _dpapi_decrypt(cipher).decode("utf-8")
        except Exception:  # noqa: BLE001 - giải mã lỗi -> coi như không có key
            return None
    return None  # encoding lạ (file bị sửa tay sai format) -> an toàn, không đoán mò


def save_api_key(
    api_key: str, provider: str = _DEFAULT_PROVIDER, base_dir: Optional[Path] = None,
) -> bool:
    """Lưu `api_key` của `provider` vào file config cục bộ, mã hoá bằng
    DPAPI nếu có thể. KHÔNG đụng tới key đã lưu của CÁC provider KHÁC
    (mỗi provider 1 entry riêng trong "providers", xem docstring đầu file)
    — đổi qua Settings xem Gemini rồi đổi lại Groq không làm mất key Groq
    đã nhập trước đó.

    Lưu xong cũng tự đặt `provider` này thành "đang dùng"
    (`get_active_provider()` sẽ trả về `provider` này ở lần đọc kế tiếp) —
    hợp lý vì người dùng vừa chủ động lưu key cho provider đó, nhiều khả
    năng họ muốn dùng NGAY provider đó.

    Tự dọn whitespace/quote thừa hay gặp khi copy-paste key (cùng cách
    `GroqProvider.__init__()` đã làm với .env trước đây) -- KHÔNG lặp logic
    này lần thứ 2 lúc đọc lại, lưu sẵn bản đã sạch.

    Returns:
        bool: True nếu đã lưu ở dạng MÃ HOÁ (DPAPI), False nếu chỉ lưu được
        plaintext (fallback) — `ui/settings_dialog.py` dùng giá trị này để
        hiện đúng trạng thái cho người dùng, KHÔNG tự suy đoán.

    Raises:
        ConfigStoreError: không ghi được file (quyền/đĩa).
    """
    provider = _normalize_provider(provider)
    cleaned = api_key.strip().strip('"').strip("'")
    config_dir = get_config_dir(base_dir)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigStoreError(f"Không tạo được thư mục config tại {config_dir}: {exc}") from exc

    encrypted = False
    if platform.system() == "Windows":
        try:
            cipher = _dpapi_encrypt(cleaned.encode("utf-8"))
            entry = {_ENCODING_FIELD: "dpapi", "api_key": base64.b64encode(cipher).decode("ascii")}
            encrypted = True
        except Exception:  # noqa: BLE001 - DPAPI lỗi hi hữu -> fallback plaintext, KHÔNG crash
            entry = {_ENCODING_FIELD: "plaintext", "api_key": cleaned}
    else:
        entry = {_ENCODING_FIELD: "plaintext", "api_key": cleaned}

    # Đọc payload hiện có + chuẩn hoá (migrate-on-write) về định dạng MỚI,
    # giữ lại key của các provider KHÁC đã lưu trước đó.
    existing = _read_raw_payload(base_dir)
    providers: dict = {}
    if _PROVIDERS_FIELD in existing and isinstance(existing[_PROVIDERS_FIELD], dict):
        providers = dict(existing[_PROVIDERS_FIELD])
    elif _KEY_FIELD in existing:
        # Định dạng CŨ (flat, chỉ Groq) -- migrate entry Groq cũ sang
        # định dạng mới TRƯỚC khi ghi đè, không làm mất key Groq đã lưu.
        legacy_groq = {
            _ENCODING_FIELD: existing.get(_ENCODING_FIELD),
            "api_key": existing.get(_KEY_FIELD),
        }
        if legacy_groq["api_key"]:
            providers["groq"] = legacy_groq

    providers[provider] = entry

    payload = {
        _ACTIVE_PROVIDER_FIELD: provider,
        _PROVIDERS_FIELD: providers,
    }

    config_path = get_config_path(base_dir)
    try:
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        # Best-effort siết quyền chỉ-user-hiện-tại đọc được (KHÔNG bảo mật
        # tuyệt đối -- vẫn nên ưu tiên DPAPI ở trên -- nhưng còn hơn không
        # với nhánh fallback plaintext). Bỏ qua nếu hệ điều hành không hỗ
        # trợ chmod kiểu POSIX (Windows os.chmod gần như no-op, không lỗi).
        try:
            os.chmod(config_path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        raise ConfigStoreError(f"Không ghi được file config tại {config_path}: {exc}") from exc

    return encrypted


def load_api_key(provider: str = _DEFAULT_PROVIDER, base_dir: Optional[Path] = None) -> Optional[str]:
    """Đọc lại API key đã lưu của `provider`, tự giải mã nếu cần.

    Đọc được CẢ 2 định dạng file: ĐỊNH DẠNG MỚI (có "providers", mọi
    provider) VÀ ĐỊNH DẠNG CŨ trước multi-provider (flat, chỉ áp dụng cho
    `provider="groq"` — vì trước đây module này chỉ từng lưu được Groq;
    gọi với `provider` khác "groq" trên 1 file định dạng cũ luôn trả None,
    KHÔNG đoán mò suy ra key của provider khác từ dữ liệu không liên quan).

    Trả `None` (KHÔNG raise) nếu: chưa từng lưu, file hỏng/không parse
    được, provider này chưa từng lưu key, hoặc blob DPAPI không giải mã
    được cho đúng user/máy hiện tại (vd file config bị copy sang máy
    khác) — mọi trường hợp này đều nên được caller
    (`GroqProvider.__init__`/`OpenAIProvider.__init__`/`GeminiProvider.__init__`)
    coi như "chưa có key từ nguồn này", tự rơi xuống nguồn tiếp theo (biến
    môi trường), KHÔNG làm crash app khởi động chỉ vì 1 file config cục
    bộ có vấn đề.
    """
    provider = _normalize_provider(provider)
    payload = _read_raw_payload(base_dir)
    if not payload:
        return None

    if _PROVIDERS_FIELD in payload and isinstance(payload[_PROVIDERS_FIELD], dict):
        entry = payload[_PROVIDERS_FIELD].get(provider)
        return _decode_entry(entry) if entry else None

    # Định dạng CŨ (flat) -- chỉ từng có Groq.
    if provider != "groq":
        return None
    encoding = payload.get(_ENCODING_FIELD)
    raw_value = payload.get(_KEY_FIELD)
    if not raw_value:
        return None
    return _decode_entry({_ENCODING_FIELD: encoding, "api_key": raw_value})


def clear_api_key(provider: str = _DEFAULT_PROVIDER, base_dir: Optional[Path] = None) -> None:
    """Xoá key đã lưu CỦA RIÊNG `provider` (nút 'Xoá' trên Settings, hoặc
    đổi ý không lưu local nữa) -- KHÔNG đụng key của provider khác. Không
    lỗi nếu chưa từng lưu provider này (hoặc chưa từng lưu gì cả).

    Nếu xoá xong KHÔNG còn provider nào có key -> xoá luôn cả file (dọn
    sạch, đúng hành vi cũ trước multi-provider). Nếu `provider` đang là
    "active_provider" và đã bị xoá, đặt lại active_provider về provider
    CÒN LẠI bất kỳ (ưu tiên "groq" nếu còn) để `get_active_provider()`
    không trả về 1 provider rỗng key.
    """
    provider = _normalize_provider(provider)
    payload = _read_raw_payload(base_dir)
    if not payload:
        return

    if _PROVIDERS_FIELD in payload and isinstance(payload[_PROVIDERS_FIELD], dict):
        providers = dict(payload[_PROVIDERS_FIELD])
    elif _KEY_FIELD in payload:
        providers = {"groq": {_ENCODING_FIELD: payload.get(_ENCODING_FIELD), "api_key": payload.get(_KEY_FIELD)}}
    else:
        providers = {}

    providers.pop(provider, None)

    config_path = get_config_path(base_dir)
    if not providers:
        try:
            config_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ConfigStoreError(f"Không xoá được file config tại {config_path}: {exc}") from exc
        return

    active = payload.get(_ACTIVE_PROVIDER_FIELD, _DEFAULT_PROVIDER)
    if active == provider or active not in providers:
        active = "groq" if "groq" in providers else next(iter(providers))

    new_payload = {_ACTIVE_PROVIDER_FIELD: active, _PROVIDERS_FIELD: providers}
    try:
        config_path.write_text(json.dumps(new_payload), encoding="utf-8")
    except OSError as exc:
        raise ConfigStoreError(f"Không xoá được file config tại {config_path}: {exc}") from exc


def get_active_provider(base_dir: Optional[Path] = None) -> str:
    """Trả provider người dùng đang dùng (lưu lần gần nhất `save_api_key()`
    được gọi) -- mặc định "groq" nếu chưa từng lưu gì (đúng hành vi trước
    khi có multi-provider, KHÔNG phá vỡ người dùng cũ chỉ có 1 key Groq)."""
    payload = _read_raw_payload(base_dir)
    active = payload.get(_ACTIVE_PROVIDER_FIELD)
    if active and isinstance(active, str):
        return active
    # File định dạng CŨ (flat, chỉ Groq, chưa từng có active_provider) HOẶC
    # chưa từng lưu gì -- mặc định "groq" cho tương thích ngược.
    return _DEFAULT_PROVIDER


def set_active_provider(provider: str, base_dir: Optional[Path] = None) -> None:
    """Đổi "provider đang dùng" KHÔNG cần lưu lại key (vd người dùng đổi
    qua provider đã lưu key từ trước trong dropdown Settings, không nhập
    lại key) -- KHÔNG xoá/tạo entry key nào."""
    provider = _normalize_provider(provider)
    payload = _read_raw_payload(base_dir)

    if _PROVIDERS_FIELD in payload and isinstance(payload[_PROVIDERS_FIELD], dict):
        providers = payload[_PROVIDERS_FIELD]
    elif _KEY_FIELD in payload:
        providers = {"groq": {_ENCODING_FIELD: payload.get(_ENCODING_FIELD), "api_key": payload.get(_KEY_FIELD)}}
    else:
        providers = {}

    new_payload = {_ACTIVE_PROVIDER_FIELD: provider, _PROVIDERS_FIELD: providers}
    config_dir = get_config_dir(base_dir)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        get_config_path(base_dir).write_text(json.dumps(new_payload), encoding="utf-8")
    except OSError as exc:
        raise ConfigStoreError(f"Không lưu được provider đang dùng: {exc}") from exc


def list_configured_providers(base_dir: Optional[Path] = None) -> list[str]:
    """Trả danh sách provider ĐÃ có key lưu cục bộ (để Settings UI biết
    provider nào đã nhập key trước đó mà không cần gọi load_api_key() lần
    lượt cho từng provider)."""
    payload = _read_raw_payload(base_dir)
    if _PROVIDERS_FIELD in payload and isinstance(payload[_PROVIDERS_FIELD], dict):
        return [p for p, entry in payload[_PROVIDERS_FIELD].items() if entry and entry.get("api_key")]
    if _KEY_FIELD in payload and payload.get(_KEY_FIELD):
        return ["groq"]
    return []
