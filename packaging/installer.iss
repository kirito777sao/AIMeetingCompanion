; packaging/installer.iss
; -------------------------
; 🔒 MỚI (CONTRACTS.md Mục 40) — Inno Setup script, gộp toàn bộ thư mục
; `dist/AIMeetingCompanion/` (output của PyInstaller) thành 1 file
; `AIMeetingCompanion_Setup.exe` DUY NHẤT để gửi cho người dùng khác cài
; trực tiếp.
;
; CÔNG CỤ CẦN CÀI TRƯỚC (chỉ trên máy BẠN dùng để build, KHÔNG cần trên
; máy người dùng cuối): Inno Setup — tải miễn phí tại
; https://jrsoftware.org/isdl.php (bản Unicode, hỗ trợ sẵn tiếng Việt
; trong tên file/đường dẫn).
;
; CHẠY (SAU KHI đã chạy xong PyInstaller, xem
; packaging/HUONG_DAN_DONG_GOI_EXE.md để biết đúng thứ tự các bước):
;
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
;
; Output: packaging\installer_output\AIMeetingCompanion_Setup.exe

#define MyAppName "AI Meeting Companion"
#define MyAppVersion "1.0.0"
#define MyAppExeName "AIMeetingCompanion.exe"
#define MyAppPublisher "Ban tu dien ten nha phat trien o day"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; 🔒 QUAN TRỌNG NHẤT của file này -- {autopf} kết hợp PrivilegesRequired=lowest
; nghĩa là: nếu người dùng cài KHÔNG có quyền Admin (rất phổ biến ở máy
; công ty/tổ chức), Inno Setup TỰ ĐỘNG cài vào
; %LocalAppData%\Programs\AI Meeting Companion\ (luôn ghi được, không cần
; hỏi mật khẩu Admin); nếu người dùng CÓ quyền Admin và chọn "Run as
; Administrator" lúc cài, tự động cài vào Program Files như bình thường.
; Không cần 2 bản cài riêng cho 2 trường hợp.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=AIMeetingCompanion_Setup
Compression=lzma2
SolidCompression=yes
; Icon cho chính trình cài đặt (KHÔNG bắt buộc) -- bỏ dòng dưới nếu chưa
; có file .ico, hoặc trỏ đúng đường dẫn nếu đã tạo (xem ghi chú icon
; trong AIMeetingCompanion.spec).
; SetupIconFile=app_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Lấy TOÀN BỘ nội dung thư mục dist/AIMeetingCompanion/ (output PyInstaller)
; -- đường dẫn TƯƠNG ĐỐI tính từ vị trí file .iss này (packaging/), nên
; ".." trỏ về project root, rồi xuống dist/AIMeetingCompanion/.
Source: "..\dist\AIMeetingCompanion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Gỡ cài đặt {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo shortcut ngoài Desktop"; GroupDescription: "Icon bổ sung:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Khởi chạy {#MyAppName} ngay"; Flags: nowait postinstall skipifsilent

; 🔒 LƯU Ý (không cần code gì thêm ở đây) -- KHÔNG cần [UninstallDelete]
; xoá config/DB/log của người dùng, vì tất cả đều nằm ở
; %APPDATA%\AIMeetingCompanion\ (NGOÀI thư mục cài đặt {app}, xem
; app/config_store.py + Mục 40) -- gỡ cài đặt app KHÔNG tự xoá dữ liệu
; của người dùng (transcript cũ, API key đã lưu), đúng hành vi mong đợi
; (người dùng có thể cài lại mà không mất dữ liệu). Nếu sau này muốn cho
; phép "gỡ cài đặt kèm xoá sạch dữ liệu", cần thêm 1 tuỳ chọn RIÊNG, có
; hỏi xác nhận rõ ràng -- không tự động xoá âm thầm.
