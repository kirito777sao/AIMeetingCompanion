# Tổng hợp đầy đủ — đóng gói, khác biệt khi dùng, vị trí file

## 1. Lệnh cần chạy (tóm tắt — chi tiết đầy đủ ở `packaging/HUONG_DAN_DONG_GOI_EXE.md`)

**⚠️ Bắt buộc chạy TRÊN WINDOWS THẬT** (không chạy được từ máy Linux/Mac, kể cả sandbox tôi đang dùng — PyInstaller không cross-compile).

```powershell
# Bước 0: mở PowerShell tại thư mục project/ (nơi có run_app.py)

# Bước 1: môi trường build sạch + cài PyInstaller
python -m venv .venv-build
.venv-build\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller

# Bước 2: đóng gói thành thư mục chạy được
pyinstaller packaging\AIMeetingCompanion.spec --distpath dist --workpath build

# --> Test ngay tại đây trước khi sang bước 3:
dist\AIMeetingCompanion\AIMeetingCompanion.exe

# Bước 3: gộp thành 1 file cài đặt duy nhất (cần cài Inno Setup trước, miễn phí)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss

# --> Kết quả: packaging\installer_output\AIMeetingCompanion_Setup.exe
#     Đây là file DUY NHẤT bạn gửi cho người khác.
```

Test lại lần nữa trên **1 máy khác/máy ảo sạch chưa từng cài Python** trước khi phát cho nhiều người — để chắc chắn không có gì "chạy nhờ máy bạn tình cờ có sẵn".

---

## 2. Khác biệt/bất tiện khi người dùng khác chạy .exe (so với môi trường bạn đang dev/test)

| Khía cạnh | Lúc dev (máy bạn, `python -m app.main`) | Lúc chạy .exe (máy người khác) |
|---|---|---|
| **Python** | Cần cài sẵn | Không cần — mọi thứ đã đóng gói kèm |
| **API key** | Đọc từ `.env` (nếu có) hoặc Settings UI | **Chỉ** qua Settings UI (⚙️ Cài đặt trong app) — mỗi người tự nhập key riêng, không có `.env` nào đi kèm bản .exe |
| **Lỗi/crash** | Thấy ngay trên terminal | **Không** có cửa sổ console (chủ ý, app GUI) — lỗi chỉ nằm trong file log, xem mục 3 bên dưới |
| **Cảnh báo Windows SmartScreen** | Không gặp (chạy source) | **CÓ THỂ** gặp "Windows protected your PC" lúc cài lần đầu, vì .exe chưa được ký số (code signing tốn phí ~100-300 USD/năm) — người dùng bấm "More info" → "Run anyway". Cần báo trước cho người nhận, kẻo họ tưởng file có mã độc |
| **Phần mềm diệt virus** | Không liên quan | Một số AV **có thể** báo nhầm (false positive) với file PyInstaller đóng gói lạ — hiếm nhưng có thể xảy ra, không phải mã độc thật |
| **Quyền Admin lúc cài** | Không liên quan | **Không cần** — đã cấu hình cài vào `%LocalAppData%\Programs\...` nếu máy không có quyền Admin |
| **Hệ điều hành** | Bạn test trên Windows | Vẫn **chỉ chạy được trên Windows** (WASAPI loopback là giới hạn gốc của tính năng ghi âm hệ thống, không đổi gì) |
| **Cập nhật phiên bản mới** | `git pull` + chạy lại | **Thủ công** — bạn phải gửi lại file `Setup.exe` mới mỗi lần sửa code, không có cơ chế tự động kiểm tra bản mới |
| **Font hiển thị PDF** | Máy bạn có sẵn Segoe UI | Cần máy người dùng có font Segoe UI (mặc định **mọi Windows 7 trở lên**, gần như chắc chắn có sẵn — không phải lo) |

**Không có gì khác về mặt hành vi/logic app** — code chạy y hệt, mọi tính năng (dịch, VAD, lưu lịch sử, xuất báo cáo, skeleton loading, v.v.) hoạt động giống hệt bản dev, đã verify bằng 35 test UI smoke + 9 file test khác PASS.

---

## 3. File sau khi cài đặt lưu ở đâu — xem/gỡ/xoá thế nào

Có **2 vị trí tách biệt hoàn toàn** — đây là điểm quan trọng nhất cần hiểu:

### A. Thư mục CÀI ĐẶT (chương trình, .exe + DLL)
```
%LocalAppData%\Programs\AI Meeting Companion\    (nếu cài không quyền Admin — mặc định)
```
hoặc
```
C:\Program Files\AI Meeting Companion\           (nếu cài với quyền Admin)
```
→ **Gỡ cài đặt** (Control Panel → Apps, hoặc shortcut "Gỡ cài đặt" trong Start Menu) sẽ **xoá SẠCH** toàn bộ thư mục này.

### B. Thư mục DỮ LIỆU (config, API key, lịch sử họp, log) — hoàn toàn KHÁC chỗ trên
```
%APPDATA%\AIMeetingCompanion\
```
Cách xem nhanh: mở File Explorer, gõ `%APPDATA%\AIMeetingCompanion\` vào thanh địa chỉ, Enter. Bên trong có:
- `config.json` — API key đã mã hoá (DPAPI, gắn với tài khoản Windows đăng nhập, người khác dùng chung máy KHÔNG đọc được key của nhau) + model đã chọn.
- `meetings.db` — toàn bộ lịch sử cuộc họp/transcript (SQLite).
- File log (`.log`) — để debug nếu app báo lỗi, gửi file này cho tôi/bạn xem nếu người dùng báo sự cố.

⚠️ **Gỡ cài đặt app KHÔNG xoá thư mục này** — chủ ý, để nếu cài lại thì không mất lịch sử cũ. Nếu người dùng muốn **xoá sạch hoàn toàn** (kể cả API key + lịch sử), họ phải tự vào `%APPDATA%\AIMeetingCompanion\` và xoá tay thư mục đó — hiện **chưa có** tuỳ chọn "gỡ kèm xoá dữ liệu" tự động trong trình cài đặt (có thể làm thêm nếu bạn muốn, là 1 task riêng).

### C. File xuất báo cáo (.docx/.pdf)
**Không có thư mục cố định** — mỗi lần bấm "💾 Xuất .docx/.pdf", app hiện hộp thoại "Lưu file" chuẩn của Windows, người dùng tự chọn nơi lưu (Desktop, Documents, USB, v.v.) như mọi phần mềm khác — không tự động lưu vào 1 chỗ định sẵn.