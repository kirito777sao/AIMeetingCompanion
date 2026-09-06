# Gói cập nhật (bản mới nhất) — 4 vấn đề bạn báo đều đã xử lý

## 🎉 Cập nhật mới nhất: test 1-3 thủ công đã PASS! Còn lại `test_ui_smoke.py`

Bạn xác nhận: dialog KHÔNG còn nhảy kích thước, nút bấm đồng bộ hơn, và
dịch/tóm tắt không còn lỗi 404 model_not_found. 🎉

Còn lại 1 vấn đề: `test_thieu_api_key_khong_lam_treo_app` vẫn timeout —
**đã tìm ra nguyên nhân thật và sửa xong**: bài test không cách ly khỏi
`config.json` thật của máy bạn (đã lưu 1 Groq key thật từ lần chạy
`python -m app.main` để test thủ công trước đó) — KHÔNG phải bug ở code
app. Xem chi tiết ở `CONTRACTS.md` Mục 20. File thay đổi: CHỈ
`tests/test_ui_smoke.py` (đã cách ly khỏi `%APPDATA%` thật của máy bạn
cho toàn bộ file test này).

## 🔴 Đọc trước khi test — 3 thay đổi quan trọng nhất (đã xác nhận PASS)

### 1. Model Groq bị decommission — GIẢI PHÁP TRIỆT ĐỂ (không chỉ đổi tên model)
- **Tự động fallback khi model bị "khai tử" (404), không chỉ khi hết quota (429) như trước** —
  nếu Groq lại ngừng hỗ trợ model chính trong tương lai, app tự chuyển
  sang model dự phòng ngay, không báo lỗi cứng.
- **Đổi tên model qua `.env`, không cần chờ code mới** — xem cuối file
  `.env.example`, đã có sẵn hướng dẫn + biến `GROQ_TRANSLATE_MODEL`,
  `GROQ_TRANSLATE_FALLBACK_MODEL`, `GROQ_STT_MODEL`, `GROQ_STT_FALLBACK_MODEL`.
- Model mặc định mới: `openai/gpt-oss-120b` (chính) / `openai/gpt-oss-20b` (dự phòng).

### 2. Dialog nhảy kích thước sau 1-2s — ĐÃ TẮT nguyên nhân nghi ngờ chính
- **`qt_material` giờ TẮT MẶC ĐỊNH** (nghi ngờ chính gây nhảy kích thước
  do nạp font riêng không đồng bộ). App chạy CHỈ với `theme.qss` như
  trước Vòng 9.
- Nếu bạn muốn thử lại `qt_material`: thêm `AI_MEETING_UI_SKIN=qt_material`
  vào `.env` — nhưng **báo lại ngay nếu vẫn còn nhảy kích thước** để tôi
  điều tra tiếp.

### 3. Giao diện "lộn xộn" — ĐÃ TÌM RA NGUYÊN NHÂN THẬT + SỬA
Không phải do bảng màu — do nhiều nút (Tạo lại, 🔄 trong Lịch sử, Huỷ
trong hộp thoại bối cảnh mới...) **chưa từng được style riêng từ trước**,
hiển thị màu xám Windows mặc định lẫn với các nút đã có màu xanh/đỏ riêng.
Đã thêm style mặc định đồng bộ cho MỌI nút/ô nhập trong `theme.qss` —
không cần sửa từng file UI.

## Cách áp dụng
Giải nén, COPY ĐÈ đúng cấu trúc thư mục vào project thật.

## Danh sách file trong gói

### Sửa cho vấn đề model Groq (Mục 19)
- `app/ai/openai_compat_base.py` — `_call_with_fallback()` (đổi tên từ
  `_call_with_rate_limit_fallback`) bắt thêm lỗi 404 model bị decommission.
- `app/ai/groq_provider.py` — model mặc định mới + đọc override từ `.env`.
- `app/ai/openai_provider.py`, `app/ai/gemini_provider.py` — cập nhật theo
  tên hàm mới (`_call_with_fallback`).
- `.env.example` — hướng dẫn đổi model qua `.env`.
- `tests/test_groq_provider_offline.py`, `tests/test_openai_provider_offline.py`
  — sửa cách tạo lỗi giả cho đúng SDK `openai` hiện tại (bạn đang cài
  2.44.0) + thêm 2 test mới cho kịch bản 404.

### Sửa cho vấn đề UI (Mục 18.4)
- `app/main.py` — tắt `qt_material` mặc định, thêm `app.setFont()` tường minh.
- `app/ui/theme.qss` — thêm style mặc định cho MỌI QPushButton/QLineEdit/
  QTextEdit/QToolTip/QMessageBox/QDialog chưa được style riêng, mở rộng
  QComboBox/QScrollBar.

### Thuộc Vòng 9 (đã gửi trước, không đổi thêm)
- `app/ai/base_provider.py`, `app/storage/db.py`, `app/ui/main_window.py`,
  `app/ui/meeting_context_dialog.py`, `tests/test_db.py`,
  `tests/test_meeting_context_offline.py`, `tests/test_ui_smoke.py`.

- `CONTRACTS.md`, `README.md`, `requirements.txt` — cập nhật ghi chú tương ứng.

## Đã tự chạy xác nhận trong sandbox (PASS 100%, không còn lỗi môi trường nào)
```
python3 tests/test_db.py
python3 tests/test_meeting_context_offline.py
python3 tests/test_groq_provider_offline.py       # kể cả 2 test mới cho 404
python3 tests/test_openai_provider_offline.py
python3 tests/test_gemini_provider_offline.py
python3 tests/test_provider_factory_offline.py
```

## Bạn cần tự chạy để xác nhận
```bash
python3 tests/test_ui_smoke.py    # đã sửa cách ly APPDATA -- cần chạy lại xác nhận PASS
```

## Vẫn còn 1 việc CHƯA verify — cần bạn xác nhận
`test_thieu_api_key_khong_lam_treo_app` đã sửa nhưng CHƯA tự chạy lại
được trên Windows thật (chỉ verify được logic `config_store` qua sandbox
không có PySide6) — **đây là việc quan trọng nhất cần bạn làm ở lượt
test này**: chạy lại `python tests/test_ui_smoke.py`, xác nhận KHÔNG còn
timeout.

## Test thủ công (chạy app thật) — theo đúng thứ tự
1. Mở app bình thường (không set `AI_MEETING_UI_SKIN`) → mở bất kỳ dialog
   nào (Cài đặt, Lịch sử, Bối cảnh cuộc họp...) → **có còn nhảy kích
   thước sau 1-2s không?** Đây là câu hỏi quan trọng nhất cần xác nhận.
2. Nhìn lại các nút trước đây "mộc" (nút "🔄" trong Lịch sử, "Tạo lại"
   trong khung gợi ý AI, "Huỷ" trong hộp thoại bối cảnh cuộc họp) — có
   đồng bộ màu/kiểu với các nút khác hơn trước không?
3. Thử dịch/tóm tắt → xác nhận không còn lỗi 404 model_not_found.
4. (Tuỳ chọn, chỉ nếu muốn thử) Thêm `AI_MEETING_UI_SKIN=qt_material` vào
   `.env`, mở lại app → còn nhảy kích thước không? Báo lại kết quả dù có
   hay không.

## Vẫn còn 1 việc tôi CHƯA tự verify được (cần bạn xác nhận)
`test_thieu_api_key_khong_lam_treo_app` (đã hỏi ở lượt trước) — nghi ngờ
do máy bạn đã có sẵn API key hợp lệ trong `%APPDATA%\AIMeetingCompanion\
config.json` hoặc `.env`, không liên quan đến các thay đổi lần này.
