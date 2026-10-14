# -*- mode: python ; coding: utf-8 -*-
"""
packaging/AIMeetingCompanion.spec
----------------------------------
🔒 MỚI (CONTRACTS.md Mục 40) — spec file PyInstaller, đóng gói kiểu
"onedir" (1 thư mục chứa .exe + toàn bộ DLL/thư viện đi kèm) thay vì
"onefile" (nén hết vào 1 file .exe DUY NHẤT).

Vì sao chọn onedir thay vì onefile: onefile giải nén TOÀN BỘ ra thư mục
tạm MỖI LẦN mở app (chậm hơn ở lần mở đầu mỗi phiên, có thể vài giây với
app PySide6 + nhiều thư viện AI SDK như dự án này), onedir mở NHANH NGAY
(không cần giải nén). Đánh đổi: onedir có NHIỀU file trong 1 thư mục thay
vì 1 file .exe gọn — không sao vì người dùng cuối KHÔNG chạy trực tiếp từ
thư mục `dist/`, mà cài qua `packaging/installer.iss` (Inno Setup) đóng
gói thành 1 `Setup.exe` DUY NHẤT để tải/chạy — người dùng cuối chỉ thấy 1
file cài đặt, không thấy sự khác biệt onedir/onefile.

CHẠY (bắt buộc trên WINDOWS, PyInstaller không cross-compile được từ
Linux/Mac ra .exe Windows — xem packaging/HUONG_DAN_DONG_GOI_EXE.md để
biết đầy đủ các bước trước/sau lệnh này):

    pyinstaller packaging/AIMeetingCompanion.spec --distpath dist --workpath build

Output: `dist/AIMeetingCompanion/AIMeetingCompanion.exe` (+ toàn bộ file
đi kèm trong cùng thư mục `dist/AIMeetingCompanion/`).
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Project root = thư mục CHA của packaging/ (chứa file .spec này) --
# .spec file được PyInstaller exec() với biến sẵn có SPECPATH trỏ đúng
# thư mục chứa .spec, dùng biến đó thay vì __file__ (spec KHÔNG phải
# module Python thường, không có __file__ đáng tin cậy).
_PROJECT_ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH do PyInstaller tự inject lúc exec spec)

datas = [
    # theme.qss -- file resource DUY NHẤT được load qua đường dẫn tương
    # đối tới __file__ trong code (xem app/main.py:_THEME_PATH) -- PHẢI
    # add đúng ĐƯỜNG DẪN TƯƠNG ĐỐI này để lúc chạy .exe, __file__ trong
    # bundle trỏ đúng chỗ tìm thấy file.
    (str(_PROJECT_ROOT / "app" / "ui" / "theme.qss"), "app/ui"),
]
binaries = []

# 🔒 Các package IMPORT LAZY (bên trong hàm, không phải top-level) trong
# app/audio/capture.py (`soundcard`, `pyaudiowpatch`) -- PyInstaller QUÉT
# BYTECODE nên THƯỜNG vẫn tự phát hiện được import kiểu này, nhưng khai
# báo TƯỜNG MINH ở đây để KHÔNG phụ thuộc vào việc quét tự động luôn đúng
# 100% (rủi ro thấp nhưng có thật, đặc biệt với package có import động
# phức tạp bên trong như pyaudiowpatch).
hiddenimports = [
    "soundcard",
    "pyaudiowpatch",
    "webrtcvad",  # package thật cài là webrtcvad-wheels, tên IMPORT vẫn là webrtcvad
    "dotenv",
    "docx",  # package thật cài là python-docx, tên import là docx
    "httpx",
    "groq",
    "openai",
]

# PySide6 cần collect_all() (không chỉ hiddenimports) vì còn có DLL/plugin
# (platforms/, styles/, v.v.) KHÔNG phải file .py thuần -- thiếu bước này
# là nguyên nhân phổ biến nhất khiến app đóng gói xong KHÔNG MỞ ĐƯỢC
# (crash ngay khi tạo QApplication, lỗi kiểu "could not find or load the
# Qt platform plugin windows").
for _pkg in ("PySide6",):
    _pkg_datas, _pkg_binaries, _pkg_hiddenimports = collect_all(_pkg)
    datas += _pkg_datas
    binaries += _pkg_binaries
    hiddenimports += _pkg_hiddenimports

a = Analysis(
    [str(_PROJECT_ROOT / "run_app.py")],
    pathex=[str(_PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AIMeetingCompanion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX (nén exe) đôi khi bị vài phần mềm diệt virus báo NHẦM là mã độc -- tắt để an toàn, đổi True nếu muốn file nhỏ hơn và đã tự test antivirus không báo nhầm
    console=False,  # app GUI, KHÔNG hiện cửa sổ console đen -- lỗi/crash đã có log file riêng (xem app/logging_setup.py, %APPDATA%\AIMeetingCompanion\)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 🔒 TUỲ CHỌN -- đổi thành đường dẫn 1 file .ico (vd "packaging/app_icon.ico") nếu bạn có icon riêng muốn dùng, để trống thì dùng icon mặc định của PyInstaller
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AIMeetingCompanion",
)
