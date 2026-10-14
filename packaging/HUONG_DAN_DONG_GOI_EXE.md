# Hướng dẫn đóng gói AI Meeting Companion thành file cài đặt .exe

🔒 MỚI (CONTRACTS.md Mục 40). File này hướng dẫn đóng gói app thành 1
file `AIMeetingCompanion_Setup.exe` DUY NHẤT, gửi cho người khác cài trực
tiếp lên máy Windows của họ — mỗi người tự nhập API key riêng của họ qua
màn hình ⚙️ Cài đặt trong app (không cần sửa code, không cần cài Python).

⚠️ **BẮT BUỘC làm TOÀN BỘ các bước dưới đây TRÊN MÁY WINDOWS THẬT** —
PyInstaller (công cụ đóng gói .exe) **không cross-compile được**: chạy
PyInstaller trên Linux/Mac chỉ tạo ra file chạy được trên Linux/Mac, không
tạo ra được .exe Windows. Đây là lý do các file trong thư mục `packaging/`
chỉ có thể được TẠO SẴN (spec file, script cài đặt) chứ không thể tự CHẠY
và cho ra .exe ngay trong môi trường phát triển hiện tại.

## Bước 0 — Chuẩn bị (làm 1 lần)

1. Cài Python 3.11 hoặc 3.12 trên máy Windows (nếu build từ 1 venv sạch
   mới, KHÔNG dùng chung venv đang dev để tránh đóng gói nhầm package
   thừa không cần thiết — làm app nặng hơn).
2. Cài [Inno Setup](https://jrsoftware.org/isdl.php) (bản Unicode) — dùng
   để gộp thành 1 file cài đặt duy nhất ở Bước 3.
3. Mở PowerShell/CMD tại thư mục `project/` (project root, nơi có file
   `run_app.py` vừa tạo và thư mục `app/`).

## Bước 1 — Cài dependency (kể cả PyInstaller)

```powershell
python -m venv .venv-build
.venv-build\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

⚠️ Nhớ `pip install pyinstaller` — package này **KHÔNG** có trong
`requirements.txt` (đúng — đó là dependency lúc DEV/BUILD, không phải lúc
CHẠY app, không nên lẫn vào requirements.txt của app).

## Bước 2 — Chạy PyInstaller

```powershell
pyinstaller packaging\AIMeetingCompanion.spec --distpath dist --workpath build
```

Kết quả: thư mục `dist\AIMeetingCompanion\` chứa `AIMeetingCompanion.exe`
+ toàn bộ file đi kèm. **Tự test ngay tại đây trước khi sang Bước 3**:

```powershell
dist\AIMeetingCompanion\AIMeetingCompanion.exe
```

App phải mở lên bình thường (màn hình chính, nút "Bắt đầu ghi", v.v.). Vì
chưa có API key nào cấu hình trên máy build (bình thường), bấm "Bắt đầu
ghi" sẽ báo lỗi "Thiếu Groq API key" — **đây là hành vi ĐÚNG**, không phải
lỗi đóng gói. Vào ⚙️ Cài đặt, nhập thử 1 API key thật, xác nhận lưu được
và app hoạt động bình thường (ghi âm, dịch, v.v.) trước khi đóng gói tiếp.

**Nếu app KHÔNG mở lên được** (đóng ngay, hoặc lỗi "could not find or
load the Qt platform plugin"): mở lại `packaging/AIMeetingCompanion.spec`,
đổi tạm `console=False` thành `console=True`, chạy lại Bước 2, mở lại
`.exe` — lần này sẽ hiện cửa sổ console kèm traceback lỗi thật, cho biết
chính xác thiếu gì (thường là thiếu 1 hidden import) để báo lại.

## Bước 3 — Đóng gói thành 1 file cài đặt (Inno Setup)

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

(Đường dẫn `ISCC.exe` có thể khác tuỳ nơi bạn cài Inno Setup — kiểm tra
lại nếu lệnh báo "không tìm thấy".)

Kết quả: `packaging\installer_output\AIMeetingCompanion_Setup.exe` — **đây
là file DUY NHẤT bạn gửi cho người khác.**

## Bước 4 — Test file cài đặt trên 1 máy KHÁC (hoặc máy ảo sạch)

Quan trọng: test trên máy **CHƯA từng cài Python/dependency** của dự án,
để chắc chắn PyInstaller đã đóng gói đủ, không có gì "chạy được nhờ máy
bạn tình cờ đã có sẵn thứ gì đó".

1. Copy `AIMeetingCompanion_Setup.exe` sang máy test.
2. Chạy file — cài đặt (không cần quyền Admin, xem ghi chú trong
   `installer.iss`).
3. Mở app từ Start Menu/Desktop shortcut.
4. Vào ⚙️ Cài đặt, nhập API key CỦA NGƯỜI DÙNG ĐÓ (mỗi người 1 key riêng
   — đã lưu mã hoá qua Windows DPAPI, gắn với tài khoản Windows của họ,
   xem `app/config_store.py`).
5. Thử ghi âm 1 cuộc gọi/video ngắn, xác nhận dịch + lưu lịch sử hoạt
   động bình thường.
6. Gỡ cài đặt thử (Control Panel → Uninstall, hoặc shortcut "Gỡ cài đặt"
   trong Start Menu) — xác nhận gỡ sạch, không để lại file rác trong thư
   mục cài đặt (dữ liệu người dùng ở `%APPDATA%\AIMeetingCompanion\` vẫn
   còn nguyên sau khi gỡ — CHỦ Ý, xem ghi chú trong `installer.iss`).

## Phân phối cho nhiều người dùng

Mỗi người nhận `AIMeetingCompanion_Setup.exe`, tự cài, tự nhập API key
riêng của họ (Groq/OpenAI/Gemini — xem `.env.example` để biết cách lấy
key từng nơi) qua ⚙️ Cài đặt — **không cần sửa file, không cần biết lập
trình, không cần quyền Admin**. Dữ liệu (lịch sử họp, config, log) của
mỗi người tách biệt hoàn toàn (gắn với tài khoản Windows đăng nhập của
họ), không ai thấy được dữ liệu của người khác dù dùng chung 1 máy.

## Cập nhật phiên bản sau này

Mỗi lần sửa code xong, muốn ra bản .exe mới:
1. Đổi `MyAppVersion` trong `packaging/installer.iss` (vd "1.0.0" →
   "1.1.0") để người dùng cũ phân biệt được bản mới.
2. Lặp lại Bước 2 → Bước 3 ở trên.
3. Gửi lại file `AIMeetingCompanion_Setup.exe` mới — người dùng chạy đè
   lên bản cũ, dữ liệu của họ (ở `%APPDATA%\AIMeetingCompanion\`) không
   bị mất vì nằm ngoài thư mục cài đặt.

## Những gì CHƯA làm (nếu cần sau này)

- ⚪ Icon riêng cho app (`.ico`) — hiện dùng icon mặc định của PyInstaller.
  Có icon riêng: tạo file `packaging/app_icon.ico`, bỏ comment dòng
  `icon=` trong `.spec` và `SetupIconFile=` trong `.iss`.
- ⚪ Ký số (code signing) file .exe — KHÔNG có, nghĩa là Windows
  SmartScreen/1 số phần mềm diệt virus CÓ THỂ cảnh báo "nhà phát hành
  không xác định" lúc cài lần đầu (bình thường với app tự đóng gói không
  trả phí ký số ~100-300 USD/năm) — người dùng cần bấm "More info" → "Run
  anyway" khi gặp cảnh báo này, KHÔNG phải app có mã độc.
- ⚪ Tự động cập nhật (auto-update) — hiện phải gửi lại file .exe mới thủ
  công mỗi lần có bản cập nhật, không có cơ chế app tự kiểm tra/tải bản
  mới.
