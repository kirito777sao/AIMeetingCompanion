# CHANGELOG.md

> File này KHÔNG có trong project trước đây (upload không kèm). Tạo mới lần
> này theo yêu cầu HARNESS protocol — bắt đầu ghi từ đây trở đi, không dựng
> lại lịch sử các đợt sửa trước (đã có sẵn trong CONTRACTS.md/README.md/
> HUONG_DAN_TEST.md, không lặp lại ở đây).

---

## [Chưa code — ghi quyết định trước] Tính năng "Hỏi AI" (chat đa lượt)

**Ngày**: phiên làm việc hiện tại.

**Quyết định** (theo đúng nội dung đã chốt trong cuộc thảo luận trước đó,
xem CONTRACTS.md Mục 21 để biết chi tiết đầy đủ):
- Thêm `chat()` vào interface `AIProvider`, dùng KIẾN THỨC NỘI TẠI của
  model — KHÔNG tích hợp web search (quyết định của người dùng: "từ kiến
  thức của AI là được rồi").
- UI: `ChatDialog` mới, tái dùng pattern `SuggestionDrawer` (QTextEdit +
  QDialog không-modal), KHÔNG thêm thư viện UI nào.
- Nút mở dialog luôn bật (không gate theo phiên họp đang chạy), 1 instance
  dialog duy nhất giữ lịch sử hội thoại suốt phiên làm việc.
- KHÔNG lưu lịch sử chat vào DB (ngoài phạm vi lần này).

**Phạm vi CỐ Ý KHÔNG làm trong lượt này** (đã phát hiện qua rà soát
production-readiness trước đó, nhưng KHÔNG nằm trong nội dung đã chốt cần
giải quyết ngay — xem TASKS.md mục Backlog, cần hỏi lại người dùng trước
khi động vào theo đúng ASK FIRST):
- Timeout tường minh cho HTTP client của Groq/OpenAI/Gemini.
- Retry có backoff cho lỗi mạng tạm thời.
- Observability/log file.
- Model chọn qua Settings UI (hiện chỉ đổi qua `.env`).
- Skeleton loading cho các dialog AI (hiện chỉ có text "Đang...").

**Trade-off/rủi ro CÒN LẠI sau khi làm xong tính năng này**:
- Trả lời chat dựa hoàn toàn vào kiến thức train-time của model — có thể
  cũ/sai với tin tức, số liệu, sự kiện xảy ra SAU thời điểm model được
  huấn luyện. Đã hiện cảnh báo cố định trong `ChatDialog` để người dùng
  biết giới hạn này.
- `chat()` implement chung ở `OpenAICompatProvider` nên áp dụng được ngay
  cho cả Groq/OpenAI/Gemini — NHƯNG chỉ verify được bằng test offline
  (mock client) trong sandbox này, CHƯA chạy được với API key thật trên
  Windows (không có mạng ra ngoài + không có PySide6 cài sẵn để dựng UI
  thật trong sandbox này). Cần bạn tự chạy lại xác nhận trên máy thật.

---

## [Đã code + verify offline] Tính năng "Hỏi AI" (chat đa lượt)

**File thay đổi**:
- `app/ai/base_provider.py` — thêm abstract method `chat()` vào `AIProvider`.
- `app/ai/openai_compat_base.py` — implement `chat()` trong
  `OpenAICompatProvider` (dùng chung `_chat_complete()`, tự động áp dụng
  cho cả `GroqProvider`/`OpenAIProvider`/`GeminiProvider` qua kế thừa,
  KHÔNG sửa 3 file provider cụ thể).
- `app/ui/chat_dialog.py` — MỚI, `ChatDialog` (QDialog không-modal,
  QTextEdit hội thoại + ô nhập + nút Gửi, giữ lịch sử `self._history`).
- `app/ui/main_window.py` — thêm nút "💬 Hỏi AI" (luôn bật), 1 instance
  `self._chat_dialog` duy nhất, `_on_chat_message_sent()` chạy qua
  `OneShotAIWorker` (đúng quy ước threading Mục 6).
- `tests/test_groq_provider_offline.py` — thêm 5 test offline cho `chat()`
  (đúng content, đúng thứ tự messages + system prompt, cảnh báo không bịa
  tin tức trong prompt, wrap lỗi ProviderError, fallback 429).
- `CONTRACTS.md` — thêm Mục 21 (chốt đầy đủ interface + UI + threading).

**Verify đã làm** (Phase 3, trong sandbox Linux — KHÔNG có Windows thật):
- ✅ `python -m py_compile` toàn bộ file đã sửa/tạo — không lỗi cú pháp.
- ✅ `tests/test_groq_provider_offline.py` — 47/47 test PASS (bao gồm 5
  test mới cho `chat()`).
- ✅ `tests/test_openai_provider_offline.py`,
  `tests/test_gemini_provider_offline.py`,
  `tests/test_provider_factory_offline.py` — PASS 100%, không hồi quy
  (xác nhận `chat()` kế thừa đúng, không phá vỡ 3 provider cụ thể).
- ✅ Smoke test thủ công `ChatDialog` với `QApplication` thật (offscreen
  Qt platform): gửi tin nhắn → lịch sử cập nhật đúng; `set_answer()` →
  lịch sử + hội thoại hiển thị đúng; `set_error()` → lịch sử KHÔNG bị
  thêm lượt lỗi giả (đúng thiết kế).
- ✅ Smoke test thủ công `MainWindow`: nút "💬 Hỏi AI" luôn `enabled=True`
  ngay từ đầu (không cần bắt đầu phiên họp); bấm 2 lần → vẫn CÙNG 1
  instance `ChatDialog` (không tạo trùng).
- ⚠️ `tests/test_ui_smoke.py` — chạy đủ, có 1 lỗi ở
  `test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y` (dòng 197,
  `SuggestionDrawer` không kịp nhận gợi ý). **ĐÃ XÁC NHẬN lỗi này tồn tại
  SẴN TRÊN BẢN GỐC CHƯA SỬA** (chạy lại y hệt trên bản zip gốc, cùng lỗi,
  cùng dòng) — là giới hạn timing xử lý signal QThread trong môi trường
  Linux offscreen của sandbox này, KHÔNG phải do thay đổi lần này gây ra.
  Không thuộc phạm vi sửa của lượt này (không đụng vào `SuggestionDrawer`/
  `suggest_answer` flow) — chỉ ghi nhận lại, không tự ý sửa.
- ❌ CHƯA verify được với API key Groq/OpenAI/Gemini THẬT trên Windows —
  cần bạn tự chạy `python -m app.main`, mở "💬 Hỏi AI", thử hỏi vài câu
  (kể cả câu cần tin tức mới, để xác nhận model tự nói "không chắc/không
  có thông tin mới" thay vì bịa) rồi xác nhận lại.

---

## [Đã code + verify] Sửa `test_ui_smoke.py` — `test_co_api_key_nhung_khong_phai_windows_van_dung_phien_hop` treo thật trên Windows

**Ngày**: cùng phiên làm việc, sau khi bạn báo lỗi thật khi tự chạy trên Windows.

**Vấn đề**: log lỗi thật bạn gửi — test timeout 5s trên Windows thật (`AssertionError: Worker phải kết thúc (window._worker = None) trong vòng 5s`, kèm `QThread: Destroyed while thread '' is still running`). Rà lại code: bản fix "monkeypatch `platform.system()`" mô tả trong CONTRACTS.md Mục 20 (nội dung cuộc thảo luận trước) **KHÔNG thực sự có trong code của zip bạn gửi** — test chỉ "ăn may" pass trong sandbox Linux của tôi vì máy đó thật sự không phải Windows, không hề patch gì cả. Chạy trên Windows thật: `_assert_windows()` (app/audio/capture.py) không raise vì ĐÚNG LÀ Windows → `AudioWorker` cố ghi âm loopback thật thay vì lỗi ngay → timeout 5s giả. Đây là bug ở TEST (thiếu cách ly OS), không phải bug app — đúng bản chất vấn đề đã mô tả trước đó, chỉ là bản fix chưa từng thực sự được áp dụng vào code.

**Giải pháp**: `tests/test_ui_smoke.py` — bọc `window._start_recording(...)` + toàn bộ vòng đợi worker trong `unittest.mock.patch("app.audio.capture.platform.system", return_value="Linux")`. Patch tại đúng điểm `_assert_windows()` đọc `platform.system()` — có hiệu lực cho cả main thread lẫn `QThread` của `AudioWorker` (cùng 1 module Python dùng chung). Giữ patch xuyên suốt toàn bộ vòng đợi (không chỉ lúc gọi `_start_recording()`) vì `AudioWorker` chạy bất đồng bộ trên `QThread` riêng.

**Verify**: chạy lại `tests/test_ui_smoke.py` trong sandbox này (Linux, offscreen) — test 3 PASS với message `'Đã kết thúc phiên họp #22 — CÓ LỖI xảy ra trong lúc ghi: ... Hệ điều hành hiện tại: Linux.'` (đúng vì patch ép branch "Linux" tường minh, không còn phụ thuộc OS thật của máy chạy test nữa). Test 4 (`test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y`) vẫn lỗi — **đã xác nhận từ trước là lỗi có sẵn, không liên quan** (xem entry phía trên). **Cần bạn tự chạy lại `python tests/test_ui_smoke.py` trên Windows thật để xác nhận test 3 giờ pass.**

**✅ XÁC NHẬN TỪ NGƯỜI DÙNG (Windows thật)**: chạy lại 2 lần
`python tests/test_ui_smoke.py` trên Windows — cả 2 lần test 3
(`test_co_api_key_nhung_khong_phai_windows_van_dung_phien_hop`) đều PASS.
Test 4 (`test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y`) vẫn lỗi
Y HỆT trên Windows thật (không chỉ sandbox Linux) — vẫn CHƯA thuộc phạm vi
đã chốt để sửa lần này, xem TASKS.md mục Backlog (mục mới thêm).

---

## [Đã code + verify] Sửa `test_ui_smoke.py` — `test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y` (và 1 test khác cùng lỗi) báo sai "không nhận được gợi ý"

**Nguyên nhân thật** (SAU KHI ĐIỀU TRA, không phải suy đoán race condition
ban đầu): 2 fake provider trong `tests/test_ui_smoke.py`
(`_FakeProviderForSuggest`, xuất hiện ở
`test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y` VÀ
`test_phase2_buoc3_luu_ai_assist_vao_db_sau_khi_dich_xong`) định nghĩa
`suggest_answer(question_text, context_text, user_native_lang)` — THIẾU
tham số `meeting_context=""` mà interface thật (`AIProvider.suggest_answer`)
đã có sẵn từ trước. `_start_suggest_worker()` trong `main_window.py` LUÔN
gọi `provider.suggest_answer(..., meeting_context=meeting_context)` (kể cả
`meeting_context=""` khi không có ngữ cảnh) → gọi vào fake provider thiếu
tham số này → `TypeError` bên trong `OneShotAIWorker.run()` → bị
`except Exception` bắt và emit `failed` (KHÔNG PHẢI `succeeded`) →
`drawer.set_error()` chạy thay vì `drawer.set_answer()` → `_answer_edit`
rỗng đúng như log lỗi cho thấy. Xác nhận bằng cách chạy lại thủ công có
trace `drawer.set_answer` (không bao giờ được gọi) trong sandbox này.

**Không phải bug ở app** (`SuggestionDrawer`/`OneShotAIWorker`/threading
đều đúng) — bug hoàn toàn nằm ở 2 fake provider trong TEST bị lạc hậu so
với interface thật sau khi `meeting_context` được thêm vào
`suggest_answer()` ở 1 đợt sửa trước đó.

**Giải pháp**: thêm `meeting_context=""` vào chữ ký cả 2
`_FakeProviderForSuggest.suggest_answer()` trong `tests/test_ui_smoke.py`.

**Verify**: chạy lại TOÀN BỘ `tests/test_ui_smoke.py` (20 test, không dừng
giữa chừng nữa) — **PASS 100% (20/20)** trong sandbox này (Linux,
offscreen). **Cần bạn tự chạy lại trên Windows để xác nhận cuối cùng.**

---

## [Đã code + verify offline] Mục 22 — Thêm tiếng Nhật/Hàn vào "Ngôn ngữ mẹ đẻ của bạn"

**File thay đổi**:
- `app/ui/main_window.py` — `_NATIVE_LANG_OPTIONS` thêm `ja`/`ko`.
- `app/ai/openai_compat_base.py` — `_LANGUAGE_NAMES` thêm `ja`/`ko`;
  `_looks_like_wrong_script()` thêm 2 nhánh xử lý đúng đặc trưng script
  của ja/ko (xem CONTRACTS.md Mục 22 để biết chi tiết đầy đủ).
- `tests/test_groq_provider_offline.py` — thêm
  `test_looks_like_wrong_script_ho_tro_ja_ko`.

**Verify**:
- ✅ `python -m py_compile` — không lỗi cú pháp.
- ✅ `tests/test_groq_provider_offline.py` — 49/49 PASS (gồm 1 test mới).
- ✅ `tests/test_ui_smoke.py` — 20/20 PASS (không hồi quy).
- ✅ Smoke test thủ công: dropdown hiện đúng 5 mục
  `[('Tiếng Việt','vi'), ('English','en'), ('中文','zh'), ('日本語','ja'),
  ('한국어','ko')]`.
- ⚠️ **Rủi ro THẬT phát hiện qua đọc code** (chưa sửa, chưa thuộc yêu cầu
  gốc): xuất báo cáo PDF dùng cố định font Segoe UI — khả năng cao KHÔNG
  có glyph Kana/Hangul, PDF tiếng Nhật/Hàn (và cả tiếng Trung vốn đã tồn
  tại từ trước) có thể hiện ô vuông trống. Xem CONTRACTS.md Mục 22 mục
  "CHƯA VERIFY" để biết chi tiết + cần bạn xác nhận.
- ❌ Chưa test STT (Whisper) nhận diện GIỌNG NÓI tiếng Nhật/Hàn thật —
  Whisper tự nhận diện ngôn ngữ nói, không phụ thuộc code đã sửa, nhưng
  chưa có bằng chứng thực tế chất lượng nhận diện tiếng Nhật/Hàn ra sao.

**Plan-alignment self-check**:
- Chỉ sửa 1 file (`tests/test_ui_smoke.py`), 1 test — không đụng
  `app/audio/capture.py`/`_assert_windows()` (không cần sửa app, chỉ test
  thiếu cách ly).
- Không phá vỡ 2 test còn lại trong cùng file (`test_main_window_...`,
  `test_thieu_api_key_...`) — verify lại cả 2 vẫn PASS cùng lượt chạy.

---

## [Đã code + verify offline] Mục 23 — Hiện "🔊 [Âm thanh]" thay vì im lặng khi phát hiện nhạc/tạp âm không có giọng nói

**Yêu cầu người dùng**: nhạc CÓ lời vẫn dịch đúng (đã đúng từ trước — xem
giải thích cơ chế bên dưới), nhưng nhạc/tạp âm KHÔNG lời hiện đang bị bỏ
qua hoàn toàn (không hiện gì) — muốn thấy 1 chỉ báo "âm thanh" thay vì im
lặng, để biết pipeline vẫn đang hoạt động.

**Cơ chế đã có sẵn (KHÔNG cần xây mới)**: Whisper trả `no_speech_prob` cho
mỗi đoạn — `pipeline.py` đã có ngưỡng `NO_SPEECH_PROB_DROP_THRESHOLD=0.6`
để lọc hallucination (CONTRACTS.md Mục 11). Nhạc CÓ lời → Whisper "nghe"
được nội dung như giọng nói thật → `no_speech_prob` THẤP → tự động đi qua
bình thường, dịch đúng như bạn đã quan sát. Nhạc KHÔNG lời/tạp âm →
`no_speech_prob` CAO → trước đây bị bỏ qua hoàn toàn, giờ hiện chỉ báo.

**File thay đổi**:
- `app/pipeline.py` — thêm field `is_audio_only: bool = False` vào
  `TranscriptEvent`; 2 nhánh "STT trả text rỗng" và "no_speech_prob cao"
  giờ set `is_audio_only=True` thay vì chỉ trả event rỗng bị UI bỏ qua
  hoàn toàn. VẪN `segment_id=None` (không lưu DB), VẪN không set `error`
  — đúng tinh thần quyết định gốc (đây là tình huống bình thường, không
  phải lỗi).
- `app/ui/audio_only_bubble.py` (MỚI) — `AudioOnlyBubble`: widget RIÊNG,
  gọn hơn `TranscriptBubble` nhiều (chỉ timestamp + chip "🔊 [Âm thanh]" +
  tooltip), KHÔNG tái dùng/nhánh rẽ vào `TranscriptBubble` (bản chất khác
  hẳn — không có text/ngôn ngữ/nút hành động nào để hiện).
- `app/ui/theme.qss` — thêm `#AudioOnlyChip` (cùng tông màu trung tính với
  `#LanguageChip`, KHÔNG dùng màu cảnh báo — đây không phải lỗi).
- `app/ui/main_window.py` — `_on_new_event()` thêm nhánh `is_audio_only`
  RIÊNG, chèn `AudioOnlyBubble` thay vì `TranscriptBubble`, KHÔNG cập nhật
  `_recent_originals`/`_recent_source_langs` (không phải câu nói thật,
  không được lẫn vào ngữ cảnh cho `suggest_answer()`/`translate()` sau
  này).
- `tests/test_pipeline.py` — cập nhật
  `test_pipeline_bo_qua_segment_hallucination_no_speech_prob_cao` (thêm
  assertion `is_audio_only=True` + `segment_id is None`). **Phát hiện +
  sửa 1 regression THẬT của tôi ở lượt trước**: `FakeProvider(AIProvider)`
  trong file này CHƯA implement `chat()` (thêm ở Mục 21) → toàn bộ
  `tests/test_pipeline.py` (9 test) CRASH ngay từ đầu (`TypeError: Can't
  instantiate abstract class`) — đã thêm `chat()` stub.

**Verify**:
- ✅ `python -m py_compile` toàn bộ file liên quan — không lỗi cú pháp.
- ✅ `tests/test_pipeline.py` — 9/9 PASS (đã tự phát hiện + sửa regression
  `chat()` trước khi verify, xem trên).
- ✅ `tests/test_ui_smoke.py` — 20/20 PASS, không hồi quy.
- ✅ Smoke test thủ công: gửi 1 `TranscriptEvent(is_audio_only=True)` qua
  `_on_new_event()` — đúng 1 `AudioOnlyBubble` được chèn, `_recent_originals`
  KHÔNG bị thêm gì (đúng thiết kế).
- ✅ Verify Windows thật (bổ sung sau, xem Mục 39 tương tự cách làm):
  người dùng đã tự nghe/quan sát với audio thật, xác nhận chỉ báo "🔊
  [Âm thanh]" hoạt động đúng — ngưỡng `0.6` không cần chỉnh. Đóng mục,
  không còn cảnh báo "CHƯA verify" nào cho tính năng này.
- **KHÔNG thuộc phạm vi lần này** (bài toán tinh chỉnh VAD/nhận diện cho
  MỌI loại tạp âm nói chung — không chỉ nhạc — cần dữ liệu âm thanh thật
  để tinh chỉnh `aggressiveness`/`silence_ms` của `VadSegmenter`, không
  thể làm mù trong sandbox này, xem TASKS.md mục Backlog).

---

## [Đã code + verify] Mục 24 — Xoá vĩnh viễn phiên họp cũ (chọn nhiều, kèm cảnh báo + xác nhận)

**Ngày**: cùng phiên làm việc, sau Mục 22/23 (Vòng 10).

**Yêu cầu người dùng đã chốt**: màn hình "Lịch sử phiên họp"
(`ui/history_dialog.py`, F13/Mục 13) cho phép chọn 1 HOẶC NHIỀU phiên họp
để xoá, tránh DB/lịch sử phình to theo thời gian. TRƯỚC khi xoá PHẢI cảnh
báo + khuyến nghị người dùng xuất báo cáo (.docx/.pdf) ra máy cá nhân, và
người dùng phải XÁC NHẬN rõ ràng đã kiểm tra/xuất xong mới cho xoá. Xoá là
xoá CỨNG — KHÔNG có thùng rác/cờ xoá mềm/khôi phục lại được.

**File thay đổi**:
- `app/storage/db.py` — thêm `MeetingStore.delete_meetings(meeting_ids:
  list[int]) -> int`. Xoá theo đúng thứ tự CON trước CHA (`meeting_reports`
  → `ai_assists` → `segments` → `meetings`) để không vi phạm `PRAGMA
  foreign_keys = ON`. Chạy trong 1 transaction (rollback nếu lỗi giữa
  chừng). `meeting_ids` rỗng → trả 0, không làm gì. Id không tồn tại sẵn
  → không tính vào số trả về, không raise lỗi.
- `app/ui/history_dialog.py`:
  - `_MeetingRow` — thêm `QCheckBox` chọn dòng (`selection_changed(int,
    bool)`), thêm `is_protected` (True khi đây là phiên đang ghi âm hiện
    tại) để tự disable checkbox + tooltip giải thích. Thêm property
    `meeting_id`, `is_selectable`, `has_report`, method `set_selected()`.
  - `MeetingHistoryDialog` — thêm tham số `current_meeting_id` (constructor,
    mặc định `None` — không phá tương thích ngược), toolbar "Chọn tất cả" +
    nút "🗑️ Xoá đã chọn (N)" (object name `DangerButton`, tái dùng style đỏ
    sẵn có của nút "⏹ Dừng ghi"). `_on_delete_clicked()` dựng `QMessageBox`
    cảnh báo (liệt kê số lượng, khuyến nghị xuất trước, CẢNH BÁO RIÊNG các
    phiên chưa có báo cáo), 2 nút "Huỷ" (mặc định, an toàn)/"Tôi đã kiểm
    tra/xuất xong — XOÁ VĨNH VIỄN" — chỉ gọi `delete_meetings()` khi bấm
    đúng nút xác nhận. `_reload()` reset lựa chọn về rỗng sau mỗi lần tải
    lại (kể cả sau khi xoá xong).
- `app/ui/main_window.py` — `_on_history_clicked()` truyền thêm
  `current_meeting_id=self._current_meeting_id` khi tạo
  `MeetingHistoryDialog`, để dialog tự bảo vệ đúng phiên đang ghi.
- `tests/test_db.py` — thêm 4 test cho `delete_meetings()`: xoá đúng
  meeting + dữ liệu liên quan (không đụng meeting khác), xoá nhiều id cùng
  lúc, id lạ không raise lỗi, danh sách rỗng không làm gì.
- `tests/test_ui_smoke.py` — thêm 3 test UI thật (`QApplication` offscreen):
  checkbox phiên đang ghi bị disable + "Chọn tất cả" không đụng tới nó,
  luồng chọn nhiều → xác nhận → xoá thật khỏi DB + reset lựa chọn, bấm
  "Huỷ" → không xoá gì.

**Trade-off/giới hạn đã biết**:
- `current_meeting_id` chỉ đúng tại THỜI ĐIỂM mở dialog — dialog
  không-modal, không tự cập nhật nếu người dùng dừng ghi/bắt đầu phiên mới
  trong lúc dialog vẫn đang mở. Chấp nhận cho V1 (cùng tinh thần đơn giản
  hoá đã áp dụng nhiều chỗ khác trong CONTRACTS.md). Lớp phòng vệ thứ 2:
  `pipeline.py` đã bọc `try/except StorageError` quanh `add_segment()` từ
  trước — dù rơi vào ca hiếm này cũng không crash app, chỉ mất dữ liệu
  segment đang ghi một cách âm thầm.
- Không theo dõi trạng thái "đã thực sự xuất file ra máy chưa" — cảnh báo
  chỉ dựa vào `has_report` (đã tạo báo cáo trong app hay chưa) + xác nhận
  bằng lời của người dùng, KHÔNG có cách nào ép buộc/kiểm chứng người dùng
  đã thực sự bấm nút xuất file trước khi xoá.

**Verify** (✅ đã có xác nhận từ người dùng chạy trên Windows thật):
- ✅ `tests/test_db.py` — 27/27 PASS (gồm 4 test `delete_meetings()` mới),
  cả trong sandbox Linux lẫn Windows thật (log người dùng gửi).
- ✅ `tests/test_ui_smoke.py` — PASS toàn bộ (gồm 3 test lịch sử mới), trên
  Windows thật.
- ✅ `tests/test_pipeline.py`, `tests/test_groq_provider_offline.py` —
  không hồi quy (log Windows thật của người dùng xác nhận).
- ❌ Ghi nhận (KHÔNG thuộc phạm vi lượt này, lỗi CÓ SẴN TỪ TRƯỚC — xuất
  hiện y hệt ở cả log lần đầu người dùng gửi trước khi có thay đổi này):
  `test_init_thieu_api_key_raise_provider_error`
  (`tests/test_groq_provider_offline.py`) fail trên MÁY DEV THẬT của người
  dùng — cùng nguyên nhân đã ghi nhận ở entry "Sửa test_ui_smoke.py..." phía
  trên (test không cách ly khỏi `config.json`/API key thật đã lưu sẵn trên
  máy qua Settings UI, không phải bug logic `GroqProvider`). Đã thêm vào
  TASKS.md mục Backlog, CẦN người dùng xác nhận trước khi sửa (ASK FIRST).

**Plan-alignment self-check**:
- Tái dùng ĐÚNG pattern query-DB-trực-tiếp-trên-main-thread đã có sẵn ở
  `history_dialog.py`/`_on_action_item_toggled()` (Mục 10.4) — xoá cũng là
  thao tác SQLite cục bộ nhẹ, không cần `OneShotAIWorker` riêng.
- Tái dùng object name `DangerButton` có sẵn trong `theme.qss` thay vì tạo
  rule QSS mới trùng lặp.
- Không đụng vào `list_meetings()`/`search_meetings()`/`MeetingSummary` cũ
  — chỉ thêm method mới, không sửa hành vi các chỗ gọi cũ.

## [Đã code + verify] Mục 25 — Cách ly `test_init_thieu_api_key_raise_provider_error` khỏi `config.json` thật trên máy dev

**Ngày**: cùng phiên làm việc, sau Mục 24.

**Bối cảnh**: entry Mục 24 ghi nhận `test_init_thieu_api_key_raise_provider_error`
(`tests/test_groq_provider_offline.py`) fail trên máy dev thật của người
dùng, nghi ngờ máy đó đã lưu sẵn 1 Groq API key thật qua ⚙️ Cài đặt
(Settings UI) khiến `GroqProvider(api_key=None)` đọc được key thật từ
`config.json` thay vì raise `ProviderError` như test kỳ vọng — đây là bug
THIẾU CÁCH LY của test, KHÔNG phải bug logic `GroqProvider`. Đã hỏi lại
người dùng theo đúng nguyên tắc ASK FIRST trước khi sửa; người dùng xác
nhận: **đúng, máy dev đó đang lưu sẵn 1 API key thật qua Settings UI.**

**File thay đổi**:
- `tests/test_groq_provider_offline.py`:
  - Thêm `from app import config_store`.
  - `test_init_thieu_api_key_raise_provider_error()` — monkeypatch
    `config_store.load_api_key = lambda provider="groq", base_dir=None:
    None` trong lúc test, khôi phục `original_load` ở `finally`. Đúng
    pattern ĐÃ CÓ SẴN trong codebase ở
    `tests/test_openai_provider_offline.py::test_init_thieu_key_raise_provider_error_voi_huong_dan_openai`
    và tương đương ở `tests/test_gemini_provider_offline.py` — không phát
    minh cách làm mới, chỉ áp dụng lại cho file Groq đang thiếu.

**Trade-off/giới hạn đã biết**:
- Không sửa `GroqProvider.__init__`/`config_store` — đúng phạm vi (chỉ
  test thiếu cách ly, code production đã đúng hành vi theo thiết kế 3 tầng
  ưu tiên đọc key ở CONTRACTS.md Mục 12/17).
- Chỉ verify được trong sandbox Linux (tự giả lập `APPDATA` + key thật để
  tái hiện đúng bug cũ, xác nhận bản cũ fail/bản mới pass) — CHƯA có log
  chạy lại trên máy dev Windows thật của người dùng cho riêng thay đổi
  này, xem TASKS.md Mục 25/T9.

**Verify**:
- ✅ Tái hiện ĐÚNG bug cũ trong sandbox: giả lập `APPDATA` trỏ thư mục tạm,
  `config_store.save_api_key("gsk_fake_real_key_saved_via_settings_ui",
  provider="groq")`, gọi `load_api_key(provider="groq")` xác nhận đọc được
  key giả — xác nhận đúng cơ chế gây fail trên máy dev thật.
- ✅ Chạy `test_init_thieu_api_key_raise_provider_error()` sau khi sửa,
  NGAY TRONG tình huống có key thật đã lưu ở trên → PASS (trước đây sẽ
  fail).
- ✅ `tests/test_groq_provider_offline.py` — 52/52 PASS (toàn bộ file,
  không chỉ test đã sửa).
- ✅ `tests/test_openai_provider_offline.py`, `tests/test_gemini_provider_offline.py`,
  `tests/test_config_store.py` — PASS, không hồi quy (cùng module
  `config_store` bị đụng gián tiếp).
- ⚠️ CHƯA VERIFY: log Windows thật cho riêng thay đổi này (sandbox không
  đại diện 100% cho môi trường Windows thật, dù cơ chế bug là thuần
  Python/logic, không phụ thuộc OS).

**Ghi nhận thêm từ người dùng (không thuộc phạm vi sửa lượt này)**: xuất
file (PDF/docx) tiếng Hàn/Nhật đã xuất đúng, KHÔNG lỗi định dạng trên máy
dev thật — hạ mức rủi ro "font PDF thiếu glyph Kana/Hangul" (Mục 22) trong
TASKS.md Backlog từ "chưa verify" xuống "đã verify OK trên máy thật".

**Plan-alignment self-check**:
- Tái dùng ĐÚNG pattern monkeypatch `config_store.load_api_key` đã có sẵn
  ở 2 file test provider khác — không tạo cách cách ly mới/không nhất
  quán.
- Không mở rộng phạm vi: không sửa code production, không đụng các test
  khác ngoài 1 hàm bị lỗi.

## [Đã code + verify] Mục 26 — Audit + sửa toàn bộ test provider offline bị cùng lỗi thiếu cách ly `config_store` (phát hiện ngay sau Mục 25)

**Ngày**: cùng phiên làm việc, sau Mục 25 — bạn gửi log Windows thật chạy
lại `test_groq_provider_offline.py` để xác nhận T9.

**Bối cảnh**: log Windows thật cho thấy `test_init_thieu_api_key_raise_provider_error`
(fix Mục 25) đã PASS đúng như kỳ vọng — nhưng NGAY SAU đó,
`test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu`
raise `AssertionError` chưa từng thấy trước đây, làm dừng luôn phần còn
lại của file (mọi test phía sau nó trong `__main__` không chạy được nữa).
Kiểm tra: CÙNG nguyên nhân hệt Mục 25 — test này set
`os.environ["GROQ_API_KEY"] = "your_groq_api_key_here"` (placeholder) rồi
gọi `GroqProvider()` không truyền `api_key=`, kỳ vọng raise `ProviderError`
vì key vẫn là giá trị mẫu. Nhưng do thứ tự ưu tiên đọc key là `api_key
tham số > config_store.load_api_key() > env var`
(`app/ai/groq_provider.py::__init__`), key THẬT đã lưu qua Settings UI
trên máy bạn được đọc TRƯỚC, che mất giá trị placeholder ở env var —
resolved_key là key thật (không phải chuỗi mẫu) → không raise, assert
fail.

**Tự phê bình rõ ràng**: ở Mục 25, tôi chỉ sửa ĐÚNG 1 test được báo lỗi,
KHÔNG chủ động rà soát xem còn chỗ nào khác trong CÙNG file (hoặc 2 file
test provider khác) bị đúng lỗi cùng loại — đây là lỗi rà soát chưa đủ
của tôi ở lượt trước, không phải bug mới phát sinh do thay đổi nào khác.
Lượt này sửa dứt điểm bằng cách audit toàn bộ, không chờ báo lỗi tiếp.

**File thay đổi**:
- `tests/test_groq_provider_offline.py`:
  - `test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu`
    — thêm monkeypatch `config_store.load_api_key` → `None`.
  - `test_init_tu_dong_strip_quote_va_whitespace_thua` — audit phát hiện
    CÙNG lỗ hổng (set env var, gọi `GroqProvider()` không `api_key=`,
    assert `._client.api_key` đúng giá trị từ env) dù CHƯA từng fail
    trên máy bạn (may mắn máy bạn cùng lúc test này chạy chưa gặp đúng
    tình huống) — sửa phòng ngừa trước khi thành bug thật.
- `tests/test_openai_provider_offline.py` —
  `test_init_doc_key_tu_bien_moi_truong_openai_api_key`: audit phát hiện
  CÙNG lỗ hổng, sửa tương tự.
- `tests/test_gemini_provider_offline.py` —
  `test_init_doc_key_tu_bien_moi_truong_gemini_api_key`: audit phát hiện
  CÙNG lỗ hổng, sửa tương tự.

**Verify**:
- ✅ Mô phỏng máy có key THẬT lưu sẵn cho CẢ 3 provider (groq/openai/
  gemini) cùng lúc trong sandbox (giả `APPDATA`, `save_api_key()` cho cả
  3) — chạy cả 4 test vừa sửa (2 Groq + 1 OpenAI + 1 Gemini, kèm 2 test
  "thiếu key" liên quan để chắc chắn không hồi quy chéo) → TẤT CẢ PASS,
  kể cả trong tình huống trước đây sẽ fail.
- ✅ Chạy sạch (không giả lập key) cả 3 file
  `test_{groq,openai,gemini}_provider_offline.py` + `test_config_store.py`
  → PASS 100%, không hồi quy.
- ⚠️ CHƯA VERIFY: log Windows thật riêng cho 2 test OpenAI/Gemini (chưa
  từng fail trên máy bạn — máy đó có thể chưa lưu key thật cho 2 provider
  này). Nếu sau này bạn lưu thêm key OpenAI/Gemini qua Settings UI, nên
  chạy lại 1 lần để xác nhận cuối, xem TASKS.md Mục 26/T10.

**Fix cho harness (theo đúng quy trình đã thống nhất — "sửa quy trình,
không chỉ sửa output")**: đã ghi 1 rule mới vào TASKS.md Mục 26 — mọi test
gọi `Provider()`/`Provider(api_key=None)` không truyền `api_key` tường
minh trong `tests/test_*_provider_offline.py` bắt buộc phải cách ly
`config_store.load_api_key`, trừ khi chính test đó đang kiểm chứng hành vi
đọc từ `config_store`. Mục đích: lần sau viết test provider mới (nếu có
provider thứ 4) không lặp lại đúng lớp lỗi này.

**Plan-alignment self-check**:
- Cùng 1 pattern monkeypatch duy nhất, áp dụng nhất quán ở cả 3 file —
  không phát minh cách cách ly khác nhau giữa các provider.
- Phạm vi mở rộng (từ 1 test lên 4 test, 3 file) là audit CÙNG MỘT lớp
  bug vừa xác nhận ở Mục 25, không phải "tiện tay sửa luôn" việc không
  liên quan — đúng tinh thần "fix the harness" của quy trình, không phải
  mở rộng phạm vi tuỳ tiện.

## [Verified] Mục 26 — T10 xác nhận trên Windows thật

Log Windows thật (bạn gửi) xác nhận cả 4 test đã sửa PASS:
`test_init_thieu_api_key_raise_provider_error`,
`test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu`,
`test_init_tu_dong_strip_quote_va_whitespace_thua` (Groq),
`test_init_doc_key_tu_bien_moi_truong_openai_api_key` (OpenAI),
`test_init_doc_key_tu_bien_moi_truong_gemini_api_key` (Gemini) — không
hồi quy ở `test_db.py`, và 3 file provider offline PASS 100%. Mục 25 +
Mục 26 đóng hẳn.

**Ghi nhận cần theo dõi (CHƯA kết luận, KHÔNG thuộc phạm vi Mục 25/26) — ĐÃ
GIẢI QUYẾT**: log lần đó của `test_ui_smoke.py` thiếu dòng `OK:
test_history_dialog_khong_cho_chon_phien_dang_ghi` (có ở log Mục 24 trước
đó) dù test này KHÔNG bị đụng vào ở Mục 25/26. Log Windows thật mới nhất
(kèm theo xác nhận Mục 27 bên dưới) đã có lại đúng dòng `OK:
test_history_dialog_khong_cho_chon_phien_dang_ghi` — kết luận: lần trước
chỉ là thiếu sót copy log, KHÔNG phải lỗi thật. Đóng hẳn, không cần task
sửa.

## [Đã code + verify] Mục 27 — Đưa ngưỡng VAD/no_speech_prob ra `.env` (phản hồi thảo luận xử lý tạp âm)

**Ngày**: cùng phiên làm việc, sau Mục 26.

**Bối cảnh**: người dùng nêu vấn đề chịu tạp âm chung (không chỉ nhạc, đã
xử lý ở Mục 23). Không có audio thật để tái hiện lỗi cụ thể, nên trước khi
sửa mù, đã đọc lại `app/audio/vad.py`, `app/ai/whisper_utils.py`,
`app/pipeline.py` để báo cáo đúng hiện trạng, tách thành 3 vấn đề riêng:
(1) VAD (`webrtcvad`) là bộ phân loại năng lượng/phổ đơn giản, tạp âm to
dễ bị hiểu nhầm "có nói"; (2) STT (Whisper qua Groq) tự nó nghe sai khi
audio không được khử nhiễu trước — code app không có bước tiền xử lý nào;
(3) `pipeline.py` chỉ lọc dựa `no_speech_prob >= 0.6`, tạp âm được Whisper
"nghe nhầm" thành chữ với `no_speech_prob` THẤP thì lọt qua, hiện thành
bubble. Đã hỏi lại người dùng quyết định hướng xử lý cho từng phần (xem
TASKS.md Mục 27 + Backlog để biết đầy đủ 3 quyết định).

**Quyết định người dùng (ghi lại để không hỏi lại)**:
1. Đưa các số đang hardcode ra `.env` để tự tinh chỉnh — LÀM (mục này).
2. Thêm lớp lọc thứ 2 dựa `confidence` cho case #3 — KHÔNG LÀM (không
   chấp nhận đánh đổi rủi ro lọc nhầm câu ngắn thật).
3. Khử nhiễu audio thật (thư viện mới) cho case #1/#2 — KHÔNG LÀM, để
   dành (phức tạp hoá dự án, chưa có audio thật để test hiệu quả).

**File thay đổi**:
- `app/audio/vad.py` — thêm `create_vad_segmenter_from_env(samplerate)`,
  hàm ĐỘC LẬP đặt NGOÀI class `VadSegmenter` (không sửa `__init__` của
  class, giữ đúng nguyên tắc "state machine thuần, không biết gì về môi
  trường ngoài" đã ghi sẵn trong docstring đầu file) — đọc
  `VAD_AGGRESSIVENESS`/`VAD_SILENCE_MS`/`VAD_MIN_SPEECH_MS`/
  `VAD_MAX_SEGMENT_MS`/`VAD_PADDING_MS`, fallback default cũ khi không đặt
  hoặc parse lỗi (không raise, không làm app crash vì gõ nhầm `.env`).
- `app/pipeline.py` — `MeetingPipeline.__init__` thêm tham số
  `no_speech_prob_drop_threshold: float | None = None`; khi `None`, tự
  đọc `NO_SPEECH_PROB_DROP_THRESHOLD` từ env (fallback hardcode `0.6` cũ
  nếu không đặt/parse lỗi) — đúng 3 tầng ưu tiên (tham số > env >
  hardcode) như `GroqProvider.__init__` đã dùng. Chỗ dùng threshold để so
  sánh (`_process_segment`) đổi từ đọc hằng số module sang đọc
  `self._no_speech_prob_drop_threshold`.
- `app/ui/main_window.py` — đổi `VadSegmenter(samplerate=16000)` thành
  `create_vad_segmenter_from_env(samplerate=16000)`, đổi import tương ứng.
- `.env.example` — thêm block giải thích + 6 biến mới (comment sẵn, giữ
  default hiện tại, không tự bật gì).
- `tests/test_vad.py` — 3 test mới: không có env → giữ default cũ; có env
  → dùng đúng giá trị; env sai định dạng → fallback default, không crash.
- `tests/test_pipeline.py` — 3 test mới: không truyền tham số + có env →
  dùng env; tham số trực tiếp ưu tiên hơn env; env sai định dạng →
  fallback đúng `0.6`.

**Trade-off/giới hạn đã biết**:
- Đây CHỈ giúp người dùng tự tinh chỉnh số dễ hơn, KHÔNG tự giải quyết
  được cả 3 vấn đề tạp âm đã nêu — 2 phần còn lại (lớp lọc thứ 2, khử
  nhiễu) đã bị từ chối có chủ đích, không phải thiếu sót.
- `create_vad_segmenter_from_env()` chỉ validate parse số (int) — validate
  logic (vd `aggressiveness` ngoài 0-3) vẫn do `VadSegmenter.__init__` tự
  raise như cũ, không lặp lại logic đó ở hàm mới.

**Verify**:
- ✅ `tests/test_vad.py` — 12/12 PASS (9 cũ + 3 mới).
- ✅ `tests/test_pipeline.py` — 12/12 PASS (9 cũ + 3 mới, gồm 2 test
  hallucination/câu ngắn liên quan trực tiếp threshold — xác nhận không
  hồi quy).
- ✅ `tests/test_db.py`, `tests/test_groq_provider_offline.py`,
  `tests/test_openai_provider_offline.py`,
  `tests/test_gemini_provider_offline.py`, `tests/test_config_store.py` —
  PASS, không hồi quy (đổi import ở `main_window.py` không ảnh hưởng).
- ✅ [Verified] Log Windows thật (bạn gửi, chạy cả 7 file test cùng lúc:
  `test_vad.py` 12/12, `test_pipeline.py` 12/12, `test_db.py` 27/27,
  `test_groq_provider_offline.py` 52/52, `test_openai_provider_offline.py`
  8/8, `test_gemini_provider_offline.py` 7/7, `test_ui_smoke.py` toàn bộ —
  gồm đủ dòng `test_history_dialog_khong_cho_chon_phien_dang_ghi`, giải
  quyết luôn ghi nhận treo ở Mục 26) — TẤT CẢ PASS, không hồi quy. Xác
  nhận `main_window.py` đổi import `VadSegmenter` →
  `create_vad_segmenter_from_env` không lỗi khi chạy UI thật. Mục 27
  đóng hẳn — 🔒 done+verified, không còn cảnh báo nào treo.

**Plan-alignment self-check**:
- Không sửa `VadSegmenter.__init__` — giữ đúng nguyên tắc kiến trúc đã có
  sẵn trong docstring gốc của file (pure state machine).
- Tái dùng ĐÚNG pattern 3 tầng ưu tiên (tham số > env > hardcode) đã thiết
  lập ở `GroqProvider.__init__` — nhất quán cách đọc cấu hình trong toàn
  bộ dự án, không phát minh cách mới.
- Không tự ý làm 2 phần người dùng đã từ chối (lớp lọc confidence, khử
  nhiễu) dù có thể "tiện tay làm luôn" — đúng ASK FIRST, tôn trọng quyết
  định đã chốt.

## [🔒 Done + verified — có log Windows thật] Mục 28 — Timeout tường minh cho client Groq/OpenAI/Gemini (Backlog #1)

**Ngày**: cùng phiên làm việc, ngay sau khi người dùng chốt thứ tự làm
Backlog (Timeout → Retry backoff → Log file → Model Settings UI →
Skeleton loading), bắt đầu với mục 1.

**Vấn đề**: SDK `openai` không tự set timeout tường minh khi khởi tạo
`openai.OpenAI(...)` — đo trực tiếp trong sandbox (`openai==3.8.0`) xác
nhận default rơi xuống `httpx.Timeout(connect=5.0, read=600, write=600,
pool=600)`, tức gần 10 phút cho 1 lần gọi nếu mạng "treo" giữa chừng.
Pipeline đồng bộ/tuần tự (CONTRACTS.md Mục 3) khiến 1 lần treo như vậy
chặn luôn segment audio tiếp theo — trải nghiệm là app "đứng hình" không
rõ lý do.

**Giải pháp**: `app/ai/openai_compat_base.py` thêm
`_resolve_client_timeout_seconds(explicit, env_var_name, default=30.0)` —
3 tầng ưu tiên (tham số > env > hardcode), cùng pattern đã dùng cho tên
model (Mục 19) và ngưỡng VAD (Mục 27). Cả 3 provider
(`groq_provider.py`/`openai_provider.py`/`gemini_provider.py`) thêm tham
số constructor `client_timeout_seconds: float | None = None` (optional,
không phá lời gọi cũ) + biến môi trường riêng
(`GROQ_CLIENT_TIMEOUT_SECONDS`/`OPENAI_CLIENT_TIMEOUT_SECONDS`/
`GEMINI_CLIENT_TIMEOUT_SECONDS`), truyền `timeout=` vào `OpenAI(...)`.
Gemini: CHỈ áp dụng cho `self._client` (phần chat — translate/
suggest_answer/summarize/chat) — `http_timeout_seconds` (client `httpx`
riêng của `transcribe()`, đã có default 60.0s từ Mục 17.3) KHÔNG đổi, 2
tham số hoàn toàn độc lập.

**File thay đổi**:
- `app/ai/openai_compat_base.py` — thêm `import os`,
  `_DEFAULT_CLIENT_TIMEOUT_SECONDS = 30.0`, hàm
  `_resolve_client_timeout_seconds()`.
- `app/ai/groq_provider.py` — import thêm `_DEFAULT_CLIENT_TIMEOUT_SECONDS`/
  `_resolve_client_timeout_seconds` (re-export), thêm tham số
  `client_timeout_seconds`, wire vào `OpenAI(...)`.
- `app/ai/openai_provider.py` — tương tự Groq.
- `app/ai/gemini_provider.py` — tương tự, nhưng CHỈ áp dụng cho
  `self._client` (không đụng `http_timeout_seconds`).
- `.env.example` — thêm block giải thích + 3 biến mới (comment sẵn,
  default hiện tại, không tự bật gì).
- `tests/test_groq_provider_offline.py` — 5 test mới (default không phải
  600s, tham số trực tiếp, env, tham số thắng env, env sai định dạng/≤0
  fallback default).
- `tests/test_openai_provider_offline.py` — 2 test mới (default, tham số
  + env + ưu tiên + fallback gộp vào 1 test).
- `tests/test_gemini_provider_offline.py` — 2 test mới (đối chứng quan
  trọng nhất: `client_timeout_seconds` KHÔNG lẫn với `http_timeout_seconds`
  có sẵn; tham số + env + ưu tiên + fallback).

**Trade-off/giới hạn đã biết**:
- Default 30.0s là con số hợp lý dựa trên số liệu thật đã ghi nhận (độ
  trễ ~1.5-4s/lệnh gọi bình thường, VAD cắt segment tối đa 8000ms) —
  KHÔNG phải số đã verify bằng cách mô phỏng mạng chậm thật (sandbox
  không network thật ra ngoài để test kịch bản "mạng chậm nhưng vẫn
  chạy được trong 30s" so với "mạng treo hẳn, phải timeout ở 30s").
- Đây CHỈ giải quyết "treo vô thời hạn" (Backlog #1) — KHÔNG tự thêm
  retry/backoff cho lỗi mạng tạm thời (Backlog #2, việc tiếp theo theo
  đúng thứ tự người dùng đã chốt) — 1 lần timeout ở 30s vẫn là lỗi CỨNG
  ngay, chưa tự thử lại.

**Verify**:
- ✅ `tests/test_groq_provider_offline.py`, `tests/test_openai_provider_offline.py`,
  `tests/test_gemini_provider_offline.py` — PASS 100% (gồm 9 test mới),
  chạy riêng từng file theo đúng quy ước README (KHÔNG gộp `pytest tests/`
  — xem HUONG_DAN_TEST.md/README.md mục Kiểm thử để biết lý do).
- ✅ Không hồi quy: `tests/test_config_store.py`,
  `tests/test_provider_factory_offline.py` PASS (đổi import ở
  `openai_compat_base.py` không ảnh hưởng).
- ✅ Đã tự đo trực tiếp giá trị default THẬT của SDK `openai` trong
  sandbox này (`Timeout(connect=5.0, read=600, write=600, pool=600)`) để
  xác nhận đúng con số "~10 phút" nêu trong vấn đề, không phải suy đoán.
- ⚠️ **CHƯA có log Windows thật** cho riêng thay đổi này — cần bạn tự
  chạy lại 3 file test provider offline trên máy Windows để xác nhận
  cuối cùng, đúng quy trình mọi lượt trước.

**Cập nhật 05/09/2026 — log Windows thật đã có**: chạy trên
`D:\Code_All\ai-meeting-companion-vong8-multi-provider\project` (PowerShell,
`.venv` activated) — cả 3 file (`test_groq_provider_offline.py`,
`test_openai_provider_offline.py`, `test_gemini_provider_offline.py`) PASS
100%, thứ tự và số lượng test khớp Y HỆT log sandbox, không có test nào
fail hay bị skip khác biệt. Mục 28 đóng hẳn — 🔒 done+verified.

**Plan-alignment self-check**:
- Tái dùng ĐÚNG pattern 3 tầng ưu tiên (tham số > env > hardcode) đã
  thiết lập ở `GroqProvider.__init__` (Mục 19) và
  `create_vad_segmenter_from_env()` (Mục 27) — không phát minh cách mới.
- Đặt hàm dùng chung ở `openai_compat_base.py` (nơi đã gom mọi logic
  chung cho 3 provider, xem Mục 17) thay vì viết lặp lại 3 lần ở từng
  file provider — nhất quán với lý do `OpenAICompatProvider` tồn tại.
  Không đụng vào `http_timeout_seconds` sẵn có của Gemini (đúng phạm vi
  task, tránh mở rộng ngoài yêu cầu).
- Không tự ý làm thêm Backlog #2 (retry/backoff) dù "tiện tay làm luôn"
  — đúng ASK FIRST/thứ tự người dùng đã chốt, dừng đúng ở Backlog #1.

## [🔒 Done + verified — có log Windows thật] Mục 29 — Retry có backoff cho lỗi kết nối mạng tạm thời (Backlog #2)

**Ngày**: cùng phiên làm việc, ngay sau Mục 28 (Backlog #1), theo đúng
thứ tự người dùng đã chốt.

**Vấn đề**: mọi lỗi qua client Groq/OpenAI/Gemini (kể cả lỗi kết nối
mạng TẠM THỜI — wifi chớp tắt, timeout đúng lúc mạng chập chờn) đều
raise `ProviderError` cứng ngay, không tự thử lại — dù loại lỗi này
thường tự khỏi nếu thử lại sau vài giây.

**Giải pháp**: `app/ai/openai_compat_base.py` thêm `_retry_with_backoff()`
(hàm tổng quát, nhận `is_retryable(exc)` tuỳ caller định nghĩa) +
`_call_with_retry()` (chuyên biệt cho SDK `openai`, retry khi
`openai.APIConnectionError`). `_call_with_fallback()` (Mục 19) được sửa
để mỗi lần gọi model (primary lẫn fallback) đều đi qua
`_call_with_retry()` trước — retry GIỮ NGUYÊN model (khác fallback, ĐỔI
model). `GeminiProvider._post_generate_content()` (đi qua `httpx` riêng,
không qua SDK `openai`) dùng trực tiếp `_retry_with_backoff()` với
`httpx.RequestError`. Backoff: 1s → 2s (nhân đôi), tối đa 2 lần thử lại
(tổng 3 lần gọi/model) — hardcode, chưa expose qua `.env` (quyết định có
chủ ý, xem CONTRACTS.md Mục 29.2).

**File thay đổi**:
- `app/ai/openai_compat_base.py` — thêm `import time`,
  `_TRANSIENT_NETWORK_MAX_RETRIES=2`,
  `_TRANSIENT_NETWORK_BACKOFF_BASE_SECONDS=1.0`, `_sleep_backoff()`,
  `_retry_with_backoff()`, `_call_with_retry()`; sửa `_call_with_fallback()`
  gọi qua `_call_with_retry()`; sửa `_chat_complete()` thêm nhánh
  `except openai.APIConnectionError` riêng (message rõ ràng hơn).
- `app/ai/groq_provider.py` — import thêm 3 tên mới (re-export), sửa
  `transcribe()` thêm nhánh `except openai.APIConnectionError`.
- `app/ai/openai_provider.py` — tương tự Groq.
- `app/ai/gemini_provider.py` — import `_retry_with_backoff`,
  `_TRANSIENT_NETWORK_MAX_RETRIES`; sửa `_post_generate_content()` bọc
  `client.post()` qua `_retry_with_backoff()`, thêm message lỗi rõ ràng
  hơn khi hết lượt retry.
- `.env.example` — thêm ghi chú giải thích (số lần retry/backoff hiện
  hardcode, không phải biến `.env`).
- `tests/test_groq_provider_offline.py` — thêm `_make_fake_connection_error()`
  + 4 test mới (retry thành công, hết lượt retry raise rõ ràng, transcribe()
  cũng retry, đối chứng 429 vẫn fallback model như cũ).
- `tests/test_openai_provider_offline.py` — thêm `_FakeSequencedAudioTranscriptions`
  + 1 test đại diện (transcribe() retry).
- `tests/test_gemini_provider_offline.py` — thêm 2 test (retry qua httpx
  thành công sau 2 lần lỗi, hết lượt retry raise rõ ràng).

**Trade-off/giới hạn đã biết**:
- Số lần retry (2) và backoff base (1.0s) HARDCODE, không cấu hình qua
  `.env` — quyết định có chủ ý để giữ phạm vi task gọn; nếu cần chỉnh
  sau này, thêm 3 tầng ưu tiên (tham số/env/default) giống Mục 28 vào
  đúng 2 hằng số `_TRANSIENT_NETWORK_MAX_RETRIES`/
  `_TRANSIENT_NETWORK_BACKOFF_BASE_SECONDS` là đủ.
- Retry CHỈ áp dụng cho lỗi kết nối (APIConnectionError/httpx.RequestError)
  — KHÔNG retry cho 429 (đã có fallback model riêng, retry cùng model khi
  hết quota không ích gì) hay 401/400 (lỗi cấu hình, thử lại vô nghĩa).
- Tổng thời gian chờ tối đa khi mạng lỗi liên tục: timeout (30s, Mục 28)
  × tối đa 3 lần gọi + 1s + 2s backoff ≈ có thể lên tới ~93s trong kịch
  bản XẤU NHẤT (mạng treo đủ 30s ở CẢ 3 lần thử) trước khi báo lỗi cuối
  cùng — CHẤP NHẬN ĐƯỢC so với ~10 phút trước Mục 28, nhưng đáng lưu ý
  nếu sau này người dùng thấy UI "treo" lâu hơn mong đợi khi mạng THẬT SỰ
  mất hẳn (không phải chỉ chập chờn tạm thời).

**Verify**:
- ✅ `tests/test_groq_provider_offline.py` (4 test mới),
  `tests/test_openai_provider_offline.py` (1 test mới),
  `tests/test_gemini_provider_offline.py` (2 test mới) — PASS 100%, chạy
  riêng từng file đúng quy ước README.
- ✅ Không hồi quy: `test_config_store.py`, `test_provider_factory_offline.py`,
  `test_vad.py`, `test_pipeline.py`, `test_db.py` PASS.
- ✅ Test retry chạy NHANH (không delay thật) nhờ monkeypatch
  `openai_compat_base._sleep_backoff` — đã tự kiểm tra PHẢI patch đúng
  module định nghĩa hàm (`app.ai.openai_compat_base`), KHÔNG phải tên
  re-export ở `groq_provider.py`/`openai_provider.py` (patch nhầm chỗ sẽ
  vẫn sleep thật, làm test chậm mà không báo lỗi rõ ràng).
- ⚠️ **CHƯA có log Windows thật**, và **CHƯA verify bằng mạng gián đoạn
  thật** (sandbox không có cách mô phỏng rớt mạng thật trong vài giây) —
  chỉ verify đúng logic qua mock exception, đã tự đo đúng exception
  hierarchy thật của SDK `openai` (`APIConnectionError` là base,
  `APITimeoutError` kế thừa từ đó) để chọn đúng loại lỗi bắt, không phải
  đoán mò.

**Cập nhật 05/09/2026 — log Windows thật đã có**: cùng lượt chạy với Mục
28 ở trên (`D:\Code_All\ai-meeting-companion-vong8-multi-provider\project`)
— cả 3 file test PASS 100%, khớp y hệt log sandbox (bao gồm đủ 7 test
retry mới). Mục 29 đóng hẳn — 🔒 done+verified. Vẫn CHƯA tự mô phỏng
mạng gián đoạn thật (rút cáp/tắt wifi) — không bắt buộc, chỉ là gợi ý
kiểm tra thêm nếu người dùng muốn tự tay xác nhận hành vi thực tế.

Backlog #1 (Mục 28) và Backlog #2 (Mục 29) đều đã đóng theo đúng thứ tự
đã chốt (Timeout → Retry backoff → Log file → Model Settings UI →
Skeleton loading). Tiếp theo: Backlog #3 — Log ra file (Observability).

**Plan-alignment self-check**:
- Tái dùng ĐÚNG cấu trúc `_call_with_fallback()` đã có (Mục 19) thay vì
  viết 1 luồng retry riêng biệt chồng lên — chỉ chèn `_call_with_retry()`
  vào đúng điểm gọi `call_fn(model)`, không đổi API/chữ ký của
  `_call_with_fallback()`.
- `_retry_with_backoff()` viết TỔNG QUÁT ngay từ đầu (nhận `is_retryable`)
  để dùng chung được cho cả SDK `openai` LẪN `httpx` trực tiếp (Gemini) —
  tránh phải viết 2 lần logic backoff giống hệt nhau cho 2 cơ chế lỗi
  khác nhau, đúng tinh thần "gom code chung" đã lập ở Mục 17.
- Không tự ý làm thêm Backlog #3 (log file) dù đã "quen tay" — dừng đúng
  ở Backlog #2, đúng thứ tự người dùng đã chốt.

## [🔒 Done + verified — có log Windows thật] Mục 30 — Log ra file để debug từ xa (Backlog #3)

**Ngày**: cùng phiên làm việc, ngay sau Mục 29 (Backlog #2), theo đúng
thứ tự người dùng đã chốt. Đã có log Windows thật ngay trong lượt đầu
tiên báo cáo (05/09/2026).

**Vấn đề**: lỗi chỉ hiện trên UI hoặc `print()` ra console — bản `.exe`
đóng gói (windowed, không terminal) khiến `print()` vô nghĩa, không có
cách nào tự chẩn đoán lỗi khi người dùng cuối report từ xa.

**Giải pháp**: `app/logging_setup.py` (MỚI) cấu hình `logging` chuẩn ghi
ra `%APPDATA%\AIMeetingCompanion\app.log` (dùng chung thư mục
config.json), `RotatingFileHandler` 2MB×3 backup, idempotent, fallback
`NullHandler` nếu không ghi được file. Wire `get_logger()` vào MỌI điểm
bắt lỗi có sẵn ở `pipeline.py`/`ai_worker.py`/`main_window.py`/`main.py`
(chi tiết đầy đủ ở CONTRACTS.md Mục 30.2) — không viết logic bắt lỗi
mới, chỉ thêm log ngay tại các except block đã tồn tại. `main.py` thêm
`sys.excepthook` để bắt cả crash không lường trước.

**File thay đổi**:
- `app/logging_setup.py` — MỚI: `setup_logging()`, `get_logger()`,
  `get_log_path()`.
- `app/main.py` — gọi `setup_logging()` sớm nhất + `sys.excepthook` +
  log start/stop app + đổi 3 chỗ `print()` cảnh báo theme sang log thêm
  (vẫn giữ `print()` để dev chạy trực tiếp vẫn thấy).
- `app/pipeline.py` — log transcribe (ERROR)/translate (WARNING)/DB
  (ERROR) kèm `meeting_id`.
- `app/ui/ai_worker.py` — log lỗi `OneShotAIWorker`.
- `app/ui/main_window.py` — log init provider/tạo phiên họp/audio
  capture/flush lỗi + mốc bắt đầu/kết thúc phiên họp (INFO).
- `tests/test_logging_setup.py` — MỚI, 5 test.
- `tests/test_pipeline.py` — thêm `_CaptureLogHandler` + 2 test.

**Trade-off/giới hạn đã biết**:
- Chưa có UI xem log trong app (vd nút "Mở thư mục log") — người dùng
  cuối phải tự vào `%APPDATA%\AIMeetingCompanion\` bằng tay. Không nằm
  trong phạm vi Backlog #3 đã chốt (chỉ "ghi log", chưa phải "xem log
  trong app") — có thể thêm sau nếu cần.
- Số lượng/kích thước rotate (2MB×3) hardcode, không cấu hình qua
  `.env` — quyết định có chủ ý, giữ phạm vi gọn giống Mục 29.

**Verify**:
- ✅ `tests/test_logging_setup.py` (5 test), `tests/test_pipeline.py`
  (2 test mới + 11 test cũ) — PASS 100% trong sandbox VÀ trên Windows
  thật (`D:\Code_All\ai-meeting-companion-vong8-multi-provider\project`),
  log khớp y hệt.
- ✅ Không hồi quy: `test_config_store.py` (trừ 2 test DPAPI, xem dưới),
  `test_provider_factory_offline.py`, `test_vad.py`, `test_db.py`, 3 file
  test provider offline — PASS trên cả 2 môi trường.
- ⚠️ **Phát hiện khi verify trên Windows** (KHÔNG phải do Mục 30 gây
  ra): `test_config_store.py` có 2 test
  (`test_save_tra_ve_false_tren_linux_vi_khong_co_dpapi`,
  `test_is_encrypted_storage_available_false_tren_linux`) CHỦ Ý chỉ
  đúng trên Linux/sandbox (tên hàm nói rõ) — trên Windows thật DPAPI CÓ
  sẵn nên 2 assertion "phải là False" FAIL đúng như dự kiến (app hoạt
  động ĐÚNG hơn — mã hoá được bằng DPAPI thật, an toàn hơn plaintext
  của sandbox). Đã ghi vào TASKS.md Backlog (mục mới, ASK FIRST) để xử
  lý riêng — không tự ý sửa vì ngoài phạm vi Backlog #3.
- ⚠️ Chưa tự verify thủ công trên UI thật (mở `app.log` xem nội dung lúc
  chạy app/tạo phiên họp thật) — chỉ verify qua test tự động, không bắt
  buộc.

**Plan-alignment self-check**:
- Dùng module `logging` CHUẨN của Python (RotatingFileHandler), không tự
  viết cơ chế ghi file/rotate riêng — đúng nguyên tắc "không phát minh
  lại bánh xe" khi thư viện chuẩn đã đủ tốt.
- Log đặt CÙNG thư mục `config.json` (`get_config_dir()` đã có từ Mục
  1x) — không tạo khái niệm "chỗ lưu" thứ 2, tái dùng hàm đã có thay vì
  viết logic tìm thư mục riêng.
- Chỉ THÊM log vào các except block ĐÃ TỒN TẠI — không viết logic xử lý
  lỗi mới, không đổi hành vi UI hiện tại (message hiện ra cho người dùng
  giữ nguyên y hệt, chỉ thêm 1 dòng ghi log song song).
- Phát hiện 2 test DPAPI fail trên Windows — KHÔNG tự ý sửa (ngoài phạm
  vi Backlog #3), ghi vào Backlog đúng quy trình ASK FIRST thay vì âm
  thầm "tiện tay" sửa luôn.
- Không tự ý làm thêm Backlog #4 (Model Settings UI) dù đã "quen tay" —
  dừng đúng ở Backlog #3, đúng thứ tự người dùng đã chốt, chờ xác nhận
  tiếp tục.

## [Đã code + verify sandbox, cần Windows xác nhận] Sửa 2 test DPAPI fail sai trên Windows (dọn dẹp, ngoài phạm vi Backlog #1-3)

**Ngày**: cùng phiên làm việc, ngay sau khi đóng Backlog #3, theo yêu cầu
"giải quyết triệt để" trước khi sang Backlog #4.

**Vấn đề**: `tests/test_config_store.py` có 2 test viết CHỦ Ý chỉ đúng
trên sandbox Linux (`test_save_tra_ve_false_tren_linux_vi_khong_co_dpapi`,
`test_is_encrypted_storage_available_false_tren_linux`) — hardcode kỳ
vọng `False`. Trên Windows thật, DPAPI có sẵn nên kết quả thật là `True`
→ 2 assertion FAIL (đã thấy trong log Windows gửi kèm Backlog #3) — KHÔNG
phải bug của `app/config_store.py` (app hoạt động đúng, mã hoá được bằng
DPAPI thật), chỉ là test giả định sai môi trường.

**Giải pháp**: sửa 2 test tự đọc `platform.system()` để chọn ĐÚNG kỳ
vọng theo từng nền tảng — Windows thật: mong đợi `True` (verify DPAPI
THẬT SỰ hoạt động, round-trip encrypt/decrypt OK); Linux/Mac: mong đợi
`False` (verify đúng nhánh fallback). Đổi tên 2 hàm cho đúng ý nghĩa mới
(không còn "trên Linux" trong tên vì giờ đúng trên mọi nền tảng):
- `test_save_tra_ve_false_tren_linux_vi_khong_co_dpapi` →
  `test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may`
- `test_is_encrypted_storage_available_false_tren_linux` →
  `test_is_encrypted_storage_available_khop_voi_platform_thuc_te`

**File thay đổi**:
- `tests/test_config_store.py` — sửa docstring đầu file + 2 test trên +
  runner cuối file. `app/config_store.py` KHÔNG đổi gì (bug nằm ở test,
  không phải code).

**Verify**:
- ✅ Sandbox (Linux): cả 2 test PASS (mong đợi `False`, đúng như trước).
- ⚠️ **CHƯA có log Windows thật cho riêng lần sửa này** — cần bạn tự
  chạy lại `python tests/test_config_store.py` trên Windows để xác nhận
  cả 2 test giờ PASS đúng nghĩa (verify DPAPI thật hoạt động) thay vì
  fail như log trước đó gửi kèm Backlog #3.
- ✅ Không hồi quy: toàn bộ 11 test còn lại trong `test_config_store.py`
  + 8 file test khác (logging_setup, pipeline, 3 provider offline,
  provider_factory, vad, db) vẫn PASS 100% trong sandbox.

**Plan-alignment self-check**:
- Chỉ sửa TEST, không đụng `app/config_store.py` — đúng bản chất vấn đề
  (bug ở giả định test, không phải ở code).
- Đổi tên hàm test phản ánh đúng ý nghĩa mới, tránh tên cũ ("trên_linux")
  gây hiểu lầm sau khi test đã tổng quát hoá cho mọi OS.

## [Đã code + verify — có log Windows xác nhận lỗi, đã sửa] Sửa test so sánh đường dẫn sai trên Windows (`test_config_path_nam_dung_thu_muc_appdata_neu_co`)

**Ngày**: cùng phiên làm việc, phát hiện qua log Windows thật người dùng
gửi SAU lần sửa DPAPI ở trên (log cho thấy vẫn còn 1 test khác fail,
KHÁC 2 test DPAPI đã sửa).

**Vấn đề**: `tests/test_config_store.py::test_config_path_nam_dung_thu_muc_appdata_neu_co`
so sánh `str(get_config_path())` (dựng từ `pathlib.Path`, TỰ CHUẨN HOÁ
mọi dấu `/` thành `\` trên Windows) với `os.path.join("/fake/appdata/path",
"AIMeetingCompanion", "config.json")` (KHÔNG chuẩn hoá phần đầu đã có
sẵn — `os.path.join` trên Windows chỉ thêm `\` cho các phần NỐI VÀO,
giữ nguyên `/` đã có trong tham số đầu). Kết quả: 2 CHUỖI KHÁC NHAU dù
cùng trỏ đúng 1 đường dẫn —
`os.path.join(...)` → `/fake/appdata/path\AIMeetingCompanion\config.json`
(lẫn cả `/` lẫn `\`), còn `str(Path(...))` →
`\fake\appdata\path\AIMeetingCompanion\config.json` (toàn `\`) — assertion
FAIL dù `app/config_store.py` hoạt động HOÀN TOÀN đúng. Đã tự mô phỏng
lại bằng `ntpath`/`PureWindowsPath` (không cần máy Windows thật) để xác
nhận chính xác nguyên nhân trước khi sửa.

**Giải pháp**: so sánh 2 `Path` OBJECT trực tiếp (`path == expected`,
pathlib tự so sánh đúng ý nghĩa đường dẫn, không quan tâm chuỗi biểu
diễn/loại dấu phân cách) thay vì so `str()` với `os.path.join()`.

**File thay đổi**:
- `tests/test_config_store.py` — sửa
  `test_config_path_nam_dung_thu_muc_appdata_neu_co()`. `app/config_store.py`
  KHÔNG đổi gì (bug nằm ở cách viết test, không phải logic
  `get_config_path()`/`get_config_dir()`).

**Verify**:
- ✅ Sandbox (Linux): PASS.
- ✅ Tự mô phỏng logic Windows bằng `ntpath.join()` +
  `pathlib.PureWindowsPath` (không cần máy Windows thật) — xác nhận
  ĐÚNG nguyên nhân lỗi (2 cách nối đường dẫn cho ra 2 chuỗi khác nhau
  trên Windows dù cùng ý nghĩa) VÀ xác nhận cách sửa (so `Path == Path`)
  giải quyết triệt để.
- ✅ Không hồi quy: toàn bộ `test_config_store.py` (17 test) + 8 file
  test khác (logging_setup, pipeline, 3 provider offline,
  provider_factory, vad, db) + `test_ui_smoke.py` (23 test, chạy được
  trong sandbox từ nay vì đã cài `PySide6`+`pytest-qt`+`QT_QPA_PLATFORM=offscreen`
  — xem ghi chú capability mới ở cuối file) — PASS 100% trong sandbox.
- ⚠️ **CHƯA có log Windows thật cho riêng lần sửa này** — cần bạn tự
  chạy lại `python tests/test_config_store.py` để xác nhận PASS hết,
  không còn lỗi nào.

**Plan-alignment self-check**:
- Tự mô phỏng được môi trường Windows (qua `ntpath`/`PureWindowsPath`)
  để xác nhận nguyên nhân + cách sửa TRƯỚC khi giao cho người dùng test
  lại lần nữa — tránh vòng lặp "sửa mò, gửi lại, fail tiếp" nếu đoán sai.
- Chỉ sửa đúng 1 test bị lỗi, không "tiện tay" sửa thêm các test khác
  đang PASS — đúng nguyên tắc không mở rộng phạm vi ngoài lỗi đang xử lý.

🔒 **Ghi chú năng lực mới của môi trường sandbox** (05/09/2026): đã cài
được `PySide6` + `pytest-qt` + chạy `QT_QPA_PLATFORM=offscreen` thành
công trong sandbox này — từ nay có thể tự chạy `tests/test_ui_smoke.py`
(và mọi test UI mới) để verify TRỰC TIẾP, không chỉ compile-check cú
pháp như trước (áp dụng từ Backlog #4 trở đi).

## [Xác nhận Windows thật] Cả 2 lần sửa test_config_store.py (DPAPI + đường dẫn) PASS trên Windows

**Ngày**: 05/09/2026, log Windows do người dùng gửi
(`D:\Code_All\ai-meeting-companion-vong8-multi-provider\project`).

**Nội dung log**: `python tests/test_config_store.py` — toàn bộ 24 test
PASS, gồm cả 3 test trước đó đang chờ xác nhận Windows:
- `test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may`
  (trước: `test_save_tra_ve_false_tren_linux_vi_khong_co_dpapi`)
- `test_is_encrypted_storage_available_khop_voi_platform_thuc_te`
  (trước: `test_is_encrypted_storage_available_false_tren_linux`)
- `test_config_path_nam_dung_thu_muc_appdata_neu_co`

Kết luận: cả 2 lần sửa test ở trên (đổi kỳ vọng DPAPI theo platform +
so `Path == Path` thay vì `str()`) đều ĐÚNG, không còn test nào giả định
sai môi trường trong `test_config_store.py`. `app/config_store.py` KHÔNG
đổi gì trong suốt quá trình — xác nhận cuối cùng: bug luôn nằm ở test,
chưa bao giờ ở code production.

**Verify**: ✅ 24/24 test PASS trên Windows thật, khớp kỳ vọng sandbox.
File `test_config_store.py` đóng hẳn, không còn mục nào treo.

**Plan-alignment self-check**:
- Không có code nào bị đổi ở lượt này — chỉ ghi nhận kết quả xác nhận,
  đúng nguyên tắc không tự ý mở rộng phạm vi khi không có gì cần sửa.
- Đã cập nhật TASKS.md gạch 2 mục Backlog liên quan sang done+verified.

## [Đã code + verify sandbox, chờ Windows thật] Mục 31 — Model Settings UI (Backlog #4)

**Ngày**: cùng phiên làm việc, ngay sau khi xác nhận Windows cho
`test_config_store.py` (xem entry ngay trên).

**Phát hiện quan trọng trước khi làm**: phần backend cho tính năng này
(`app/config_store.py::save_model_overrides()/load_model_overrides()/
clear_model_overrides()`, merge trong `app/ai/provider_factory.py::create_provider()`)
đã tồn tại SẴN trong code, comment ghi rõ "Backlog #4, CONTRACTS.md Mục
31" — nhưng KHÔNG có Mục 31 nào trong `CONTRACTS.md`, KHÔNG có test nào
cho 3 hàm này (dù `test_config_store.py` có `import` chúng), và
`TASKS.md`/`CHANGELOG.md` không ghi nhận việc này. Đã báo lại cho người
dùng TRƯỚC khi viết thêm code (đúng nguyên tắc "document decisions before
writing code") — người dùng xác nhận tiếp tục, giữ nguyên thiết kế backend
đã có.

**Nội dung làm ở lượt này (T17-T21, xem TASKS.md Mục 31)**:
- `CONTRACTS.md` — viết Mục 31 mô tả đúng thiết kế backend đã có (schema
  `model_overrides`, 4 field, 4 tầng ưu tiên).
- `tests/test_config_store.py` — 8 test mới cho save/load/clear model
  overrides.
- `tests/test_provider_factory_offline.py` — 3 test mới cho việc merge
  override vào `create_provider()` (monkeypatch, không đụng %APPDATA% thật).
- `app/ui/settings_dialog.py` — 4 ô nhập model (stt_model/
  stt_fallback_model/translate_model/translate_fallback_model) + nút
  "Khôi phục mặc định", đổi theo dropdown provider giống pattern ô API
  key, lưu chung 1 nút "Lưu" hiện có.

**Trade-off/quyết định có chủ ý**:
- KHÔNG dropdown chọn model có sẵn — 4 ô text đơn giản (người dùng xác
  nhận đủ dùng cho lượt này).
- KHÔNG thêm nút "Lưu" riêng cho model — dùng chung nút "Lưu" API key đã
  có, tránh 2 nút Lưu gây nhầm lẫn.
- KHÔNG mở rộng biến môi trường override cho OpenAI/Gemini (Mục 19 vẫn
  chỉ áp dụng cho Groq) — Mục 31 chỉ thêm đường Settings UI, không đổi
  phạm vi Mục 19.

**File thay đổi**:
- `CONTRACTS.md` (+Mục 31, MỚI).
- `tests/test_config_store.py` (+8 test).
- `tests/test_provider_factory_offline.py` (+3 test).
- `app/ui/settings_dialog.py` (sửa — thêm UI, KHÔNG đổi hành vi API key
  đã có).
- `app/config_store.py`, `app/ai/provider_factory.py` — KHÔNG đổi (giữ
  nguyên code backend đã có sẵn).

**Verify**:
- ✅ `tests/test_config_store.py` — 32/32 PASS trong sandbox.
- ✅ `tests/test_provider_factory_offline.py` — 13/13 PASS trong sandbox.
- ✅ Không hồi quy: `test_groq_provider_offline.py`,
  `test_openai_provider_offline.py`, `test_gemini_provider_offline.py`,
  `test_logging_setup.py`, `test_db.py`, `test_vad.py`, `test_pipeline.py`
  — PASS 100% trong sandbox (đã cài thêm `httpx`, `PySide6`, `pytest-qt`
  vào sandbox — thiếu sẵn trước lượt này).
- ✅ `tests/test_ui_smoke.py` (23 test, chạy đúng bằng
  `python3 tests/test_ui_smoke.py`, KHÔNG phải `pytest` — file này không
  có `conftest.py`, fixture `app` chỉ định nghĩa trong khối
  `if __name__ == "__main__":`) — PASS 100%, không hồi quy.
- ✅ Smoke-test thủ công `SettingsDialog` trong sandbox
  (`QT_QPA_PLATFORM=offscreen`): khởi tạo thành công, 4 ô model hiện
  đúng placeholder = default hiện tại của Groq
  (`whisper-large-v3`/`whisper-large-v3-turbo`/`openai/gpt-oss-120b`/
  `openai/gpt-oss-20b`), `_on_restore_defaults_clicked()` chạy đúng,
  không lỗi. Đã xoá sạch file config tạm sinh ra trong sandbox sau khi
  test xong.
- ⚠️ **CHƯA verify trên Windows thật** — cần bạn tự mở app, vào ⚙️ Cài
  đặt, xác nhận giao diện hiển thị đúng (4 ô model + nút "Khôi phục mặc
  định"), thử điền 1 model override thật (vd đổi `translate_model` sang
  giá trị khác), bấm Lưu, đóng app, mở lại, xác nhận giá trị vẫn còn.
- ⚠️ **CHƯA test với model KHÔNG hợp lệ thật** (gõ nhầm tên model) — lỗi
  sẽ xảy ra lúc GỌI model (giống hệt cách `.env` hoạt động từ Mục 19),
  không phải lúc lưu — đúng ý định, nhưng chưa tự verify bằng key thật
  (sandbox không có mạng ra ngoài).

**Plan-alignment self-check**:
- KHÔNG viết lại `app/config_store.py`/`app/ai/provider_factory.py` dù
  phát hiện thiếu tài liệu/test — đọc kỹ, xác nhận thiết kế đúng convention
  dự án (3→4 tầng ưu tiên, semantics rỗng, không đụng provider khác) rồi
  MỚI bổ sung phần thiếu, đúng nguyên tắc "không viết lại khi không cần".
- Đã báo cáo minh bạch cho người dùng về code có sẵn không rõ nguồn gốc
  TRƯỚC khi tiếp tục, thay vì âm thầm coi như bình thường hoặc âm thầm
  viết lại — đúng tinh thần "chỉ ra điểm mù" thay vì che giấu.
- UI tái dùng ĐÚNG pattern `_refresh_provider_fields()`/nút "Lưu" đã có,
  không tạo khái niệm/luồng lưu thứ 2 song song.

---

## Mục 32-34 — Bàn phím cho nút chính + chặn mở trùng dialog + reset số thứ tự khi xoá hết lịch sử

**Ngày**: phiên làm việc hiện tại (sau khi người dùng xác nhận Mục 31 pass
trên Windows thật, kèm log test + ảnh chụp UI Settings).

**Yêu cầu người dùng** (3 đề xuất bổ sung vào kế hoạch tối ưu trải nghiệm):
1. Cho phép thao tác các nút cơ bản bằng bàn phím (không chỉ chuột).
2. Popup/hộp thoại bị mở trùng nhiều lần khi nhấn đúp/nhấn nhiều lần vào 1 nút.
3. Xoá lịch sử: xoá 1/nhiều phiên không được đổi số thứ tự các phiên còn
   lại; xoá TOÀN BỘ thì số thứ tự phải reset lại từ đầu.

**Đã làm**:
- Mục 32: thêm mnemonic Alt+B/K/T/X/L/A/C cho 7 nút chính `ui/main_window.py`
  + tooltip ghi chú phím tắt. Chi tiết: CONTRACTS.md Mục 32.
- Mục 33: `MeetingStore.delete_meetings()` (`app/storage/db.py`) — xoá 1
  phần giữ nguyên id (đã đúng sẵn, không cần sửa); THÊM: xoá xong bảng
  `meetings` trống hoàn toàn → tự reset `sqlite_sequence`, phiên mới tiếp
  theo bắt đầu lại từ `id=1`. Chi tiết: CONTRACTS.md Mục 33.
- Mục 34: áp dụng pattern singleton (đã có sẵn cho Chat, Mục 21) cho
  Settings/History/AskQuestion (`ui/main_window.py` + `showEvent()` ở
  `settings_dialog.py` + `refresh()` ở `history_dialog.py` +
  `set_default_target_lang()` ở `ask_question_dialog.py`); Report dùng
  `dict[meeting_id, ReportDialog]` riêng vì có trạng thái theo từng phiên.
  Chi tiết: CONTRACTS.md Mục 34.

**Verify**:
- ✅ `tests/test_db.py` — 32/32 PASS (28 cũ + 4 mới cho Mục 33), không hồi
  quy trên 28 test cũ.
- ✅ `tests/test_ui_smoke.py` — 28/28 PASS (23 cũ + 5 mới cho Mục 32/34),
  không hồi quy trên 23 test cũ (đã kiểm tra kỹ trước khi sửa: không test
  nào so `.text()` bằng chuỗi chính xác cho 7 nút chính bị đổi text thêm
  `&`).
- ✅ Không hồi quy 7 file test còn lại (`test_config_store.py` 32,
  `test_provider_factory_offline.py` 13, `test_groq_provider_offline.py`
  60, `test_openai_provider_offline.py` 11, `test_gemini_provider_offline.py`
  11, `test_logging_setup.py` 5, `test_pipeline.py` 14) — tất cả PASS
  100% trong sandbox, cùng môi trường (`httpx`/`PySide6`/`openai` SDK cài
  tạm) đã dùng để verify Mục 31.
- Tổng: 9/9 file test PASS, 206 dòng `OK:` (tăng từ 181, đúng +25 test
  mới thêm cho Mục 32-34).
- ⚠️ **CHƯA verify trên Windows thật** cho cả 3 mục — cần bạn tự làm, xem
  checklist chi tiết ở cuối CONTRACTS.md (ngay sau Mục 34).

**Phạm vi CỐ Ý KHÔNG làm trong lượt này** (chưa ai yêu cầu, tự đề xuất
nhưng KHÔNG tự làm để tránh mở rộng phạm vi ngoài ý định gốc — ASK FIRST
nếu muốn làm sau này):
- `QShortcut` toàn cục không cần giữ Alt (vd F5 = Bắt đầu ghi) — mnemonic
  hiện tại đã đáp ứng đúng yêu cầu gốc, thêm phím tắt không-Alt có rủi ro
  đụng phím hệ thống/IME gõ tiếng Việt nếu chọn nhầm phím.
- Reset bộ đếm cho `segments`/`ai_assists`/`meeting_reports` — các bảng
  này không có "số thứ tự" hiển thị cho người dùng, không nằm trong yêu
  cầu gốc.

**Plan-alignment self-check**:
- Mục 34 tái dùng NGUYÊN pattern singleton đã có sẵn của `_chat_dialog`
  (Mục 21) thay vì phát minh cơ chế mới — nhất quán kiến trúc, dễ bảo trì.
- Mục 33 nằm gọn trong transaction đã có sẵn của `delete_meetings()`
  (Mục 24.2), không mở thêm transaction/kết nối DB riêng.
- Không đụng tới bất kỳ contract công khai nào đã chốt (`AIProvider`
  interface, DB schema, threading model) — cả 3 mục đều là bổ sung ở tầng
  UI/DB nội bộ, không phá vỡ tương thích ngược.

## Mục 35 — Bugfix: Lịch sử khoá nhầm phiên đã kết thúc (T27)

- Sửa `_on_history_clicked()` (`app/ui/main_window.py`): dùng
  `self._worker is not None` thay vì `self._current_meeting_id is not None`
  để xác định phiên nào đang "được bảo vệ, không cho chọn/xoá" trong
  dialog Lịch sử. Lý do: `_current_meeting_id` cố ý không reset sau khi
  kết thúc phiên (phục vụ nút "Xem báo cáo") nên trước đây phiên vừa kết
  thúc bị coi nhầm là "đang ghi" mãi mãi, khiến "Chọn tất cả" bỏ sót +
  không xoá hết + số thứ tự không reset (Mục 33).
- Thêm 1 test mới (`test_ui_smoke.py`), verify bằng cách mô phỏng đúng
  trạng thái sau khi kết thúc ghi (`_worker=None`, `_current_meeting_id`
  vẫn còn giá trị cũ).
- ✅ **Khác biệt so với các lượt trước**: lần này tự `pip install PySide6`
  thành công trong sandbox (trước đây luôn thiếu, phải ghi "CHƯA verify
  Windows thật") — đã tự chạy `tests/test_ui_smoke.py` thật, 29/29 test
  PASS (28 cũ + 1 mới), không hồi quy. Cũng chạy lại `test_config_store.py`
  và `test_db.py`, PASS. **CHƯA verify**: hành vi thật trên Windows với
  audio loopback thật + UI thật (sandbox vẫn là Linux offscreen).
- KHÔNG đụng: nút "Xem báo cáo" (vẫn dựa `_current_meeting_id`, không
  đổi), DB schema, `AIProvider` interface, threading model.

## Mục 36-37 — Lớp lọc confidence opt-in (T28) + Dialog Trợ giúp (T29)

- **T28**: `MeetingPipeline` thêm `confidence_drop_threshold` (mặc định
  `None`=TẮT, opt-in qua `.env` biến `CONFIDENCE_DROP_THRESHOLD`) — xét lại
  quyết định cũ Mục 27 theo yêu cầu người dùng, sau khi báo tạp âm/nhạc
  nền bị bịa chữ + dịch loạn tệ hơn bản trước. Trade-off RÕ RÀNG: có thể
  lọc nhầm câu ngắn-nhưng-thật, người dùng tự chọn bật + tự tinh chỉnh số.
  6 test mới, không hồi quy 14 test cũ.
- **T29**: Thêm `app/ui/help_dialog.py` (`HelpDialog`) + nút "❓ Trợ &Giúp"
  (Alt+G) ở màn hình chính — liệt kê 7 phím tắt Alt+... đã có + quy trình
  dùng cơ bản, gom về 1 chỗ thay vì rải rác tooltip. Singleton, không cần
  refresh (nội dung tĩnh). Không hồi quy 29 test `test_ui_smoke.py` cũ.
- ✅ **Verify**: LẦN ĐẦU tự cài `PySide6` + `webrtcvad` qua `pip` trong
  sandbox (khác mọi lượt trước — luôn thiếu 2 gói này) → chạy THẬT toàn bộ
  9/9 file test, PASS 100%, không hồi quy bất kỳ test nào.
- **CHƯA verify**: hiệu quả thật của lớp lọc confidence trên audio thật có
  vấn đề (anime/tạp âm) — cần bạn tự bật + tinh chỉnh trên Windows; nghi
  vấn RIÊNG về nguyên nhân gốc (fallback sang model turbo do rate-limit)
  cũng CHƯA xác nhận được, cần xem log file thật.
- KHÔNG đụng: DB schema, `AIProvider` interface, threading model, hành vi
  mặc định của bất kỳ ai chưa chỉnh `.env` (cả 2 mục đều opt-in/thêm mới,
  không đổi default).

## Mục 38 — Hint ngôn ngữ nguồn (T31) + log outlier ngôn ngữ (T33)

- **Bối cảnh**: người dùng bật `CONFIDENCE_DROP_THRESHOLD` (Mục 36) như đề
  xuất, xác nhận "đỡ hơn 1 chút" nhưng vẫn bị nhảy ngôn ngữ EN/JA trên
  video anime tiếng Nhật có tạp âm chiến đấu/nhạc nền — đúng dự đoán rằng
  2 lớp lọc output cũ (Mục 11/36) không sửa được gốc rễ là Whisper tự đoán
  SAI ngôn ngữ ở bước nhận diện.
- **T31**: Thêm `language_hint: str = ""` xuyên suốt `AIProvider.transcribe()`
  → `GroqProvider`/`OpenAIProvider` (truyền `language=` cho Whisper API) /
  `GeminiProvider` (nhét vào prompt) → `MeetingPipeline` → `AudioWorker` →
  UI mới: dropdown "Ngôn ngữ nguồn dự kiến của audio" trong
  `MeetingContextDialog`, mặc định "🌐 Tự động" (không đổi hành vi cũ).
  Trade-off đã thống nhất với người dùng: có thể "Nhật hoá" ngữ âm vài từ
  tiếng Anh thật xen giữa khi ép hint — chấp nhận vì tạp âm là vấn đề lớn
  hơn trong bối cảnh test.
- **T33**: `_log_if_language_outlier()` mới trong `pipeline.py` — CHỈ ghi
  log WARNING khi ngôn ngữ lệch khỏi hint/đa số gần đây, KHÔNG tự lọc/ẩn
  gì (tránh lặp rủi ro Mục 27/36). Thuần chẩn đoán qua file log (Mục 30).
- 9 test mới (2 Groq, 1 OpenAI, 2 Gemini, 2 pipeline, 2 UI), toàn bộ PASS.
  1 regression phát hiện+sửa: `FakeProvider.transcribe()` trong
  `tests/test_pipeline.py` thiếu tham số `language_hint` mới (bài học lặp
  lại từ Mục 23 — thêm tham số vào `AIProvider` phải grep hết implementer).
- ✅ **Verify**: toàn bộ 9 file test (kể cả `test_ui_smoke.py`, 32/32) PASS
  trong sandbox sau khi thêm test mới, không hồi quy test nào.
- **CHƯA verify**: hiệu quả thật trên Windows + video anime đã gặp vấn đề
  (xem CONTRACTS.md Mục 38 — cần người dùng tự chọn "Ngôn ngữ nguồn dự
  kiến" = Nhật, so sánh tần suất nhảy ngôn ngữ trước/sau).
- KHÔNG đụng: DB schema, chữ ký `translate()`/`suggest_answer()`, threading
  model, hành vi mặc định của bất kỳ ai chưa đổi dropdown mới (mặc định
  "Tự động" = y hệt trước Mục 38).

## Sau Mục 38 — Quyết định TẠM HOÃN xử lý tạp âm/thoại lẫn tạp âm + dọn TASKS.md

- Người dùng xác nhận: `language_hint` (T31) chạy đúng kỹ thuật trên
  Windows thật (10/10 file test PASS, dropdown hoạt động), nhưng KHÔNG
  giải quyết được 2 vấn đề khác: (1) tạp âm/nhạc nền/tiếng đánh nhau
  KHÔNG có thoại vẫn bị bịa lời, (2) có cả thoại lẫn tạp âm thì dịch kém
  chất lượng. Phân tích: đây là 2 vấn đề KHÁC gốc rễ với Mục 38 (vốn chỉ
  sửa việc đoán SAI ngôn ngữ) — (1) nghi do `webrtcvad` (mặc định
  `aggressiveness=2`) phân loại nhầm tạp âm thành giọng nói; (2) là hạn
  chế cố hữu của Whisper khi audio thật sự bị nhiễu, không có ngưỡng lọc
  nào sửa được.
- Theo đúng nguyên tắc circuit breaker (đã tinh chỉnh cùng 1 tầng lọc
  output 3 lần liên tiếp — Mục 27/36/38 — mà chưa giải quyết được gốc),
  KHÔNG tiếp tục đoán mò tinh chỉnh lần 4. Đề xuất 2 hướng mới (T35: tăng
  `aggressiveness` VAD; T36: khử nhiễu âm thanh, quy mô lớn) nhưng người
  dùng quyết định **TẠM HOÃN cả 2**, ghi vào kế hoạch dài hạn (TASKS.md
  Backlog) để phát triển/sửa đổi sau, KHÔNG code trong lượt này.
- Dọn dẹp `TASKS.md`: xoá 1 section "## Backlog" trùng lặp/lỗi thời (liệt
  kê nhầm các việc ĐÃ xong ở Mục 28/30/31 như thể còn chưa làm — sót lại
  từ trước khi các Mục đó hoàn thành), gộp thông tin còn giá trị vào đúng
  1 mục backlog duy nhất về tạp âm. Đóng luôn mục "font PDF thiếu glyph"
  (đã verify OK từ trước nhưng chưa cập nhật trạng thái) và sửa 1 marker
  ⚪ lẽ ra phải là 🔒 (task đã xong nhưng ghi sai ký hiệu).
- KHÔNG đụng code (`app/`) trong lượt này — thuần cập nhật tài liệu theo
  đúng quyết định của người dùng.

## Mục 39 — Skeleton loading cho SuggestionDrawer + AskQuestionDialog

- Module mới `app/ui/skeleton_loader.py` (`SkeletonBar`,
  `SkeletonLoadingWidget`) — không thêm thư viện ngoài PySide6 sẵn có.
- Thay placeholder text tĩnh bằng skeleton animate mờ-đậm so le, tại
  `SuggestionDrawer` (ô "Đang soạn gợi ý...") và `AskQuestionDialog` (vùng
  readback "Đang dịch..."). CỐ TÌNH không đụng `ChatDialog` — khác cấu
  trúc (log nối tiếp, không phải vùng nội dung độc lập), xem CONTRACTS.md
  Mục 39 để biết lý do đầy đủ.
- 2 test mới (`test_suggestion_drawer_skeleton_hien_luc_dang_tai_an_khi_co_ket_qua`,
  `test_ask_question_dialog_skeleton_hien_luc_dang_dich_an_khi_co_readback`),
  test trực tiếp trên widget (không qua thread) để tránh timing-sensitive.
- **Bài học ghi nhớ** (đã tự phát hiện+sửa ngay trong lượt code): viết
  test `isVisible()` mà QUÊN gọi `dialog.show()` trước sẽ luôn fail dù
  code đúng — Qt chỉ báo đúng visibility khi cây widget cha đã hiện. Cũng
  tự phát hiện+sửa 1 lỗi thao tác chèn code làm mất nhầm 1 dòng `def` khi
  chèn function mới vào giữa file test — bài học: LUÔN đọc lại đoạn vừa
  sửa (không chỉ chạy test) khi chèn code vào giữa file dài.
- ✅ Verify: 34/34 test UI smoke (tăng từ 32) + 9 file test khác PASS.
- KHÔNG đụng: `ChatDialog`, DB schema, provider, pipeline.

## Mục 39 — Verify Windows thật (bổ sung)

- Người dùng đã tự mở app thật (có API key), test kỹ "Nhờ AI trả lời"/"Tôi
  muốn hỏi", xác nhận skeleton animation hiển thị ổn — không cần chỉnh
  màu/tốc độ. Đóng hoàn toàn Mục 39, không còn cảnh báo "CHƯA verify" nào.

## Mục 40 — Ẩn cửa sổ khỏi screen share (T37–T39)

**Quyết định** (ghi trước khi code): thêm vào app PySide6 hiện có (KHÔNG
làm app mới, KHÔNG Electron). Dùng `SetWindowDisplayAffinity(0x11)` qua
`ctypes`; MẶC ĐỊNH TẮT, bật bằng `AI_MEETING_HIDE_FROM_CAPTURE=1`; không
fallback `WDA_MONITOR` (hiện khối đen -> lộ); áp cho mọi top-level window
qua event filter ở QApplication. Chat trực tiếp với AI đã có sẵn ("💬 Hỏi
AI", Mục 21) -- không làm lại.

**File thay đổi**: `app/ui/capture_protection.py` (MỚI), `app/main.py`
(+2 dòng import/cài filter), `.env.example` (+1 biến), `tests/test_capture_protection.py`
(MỚI, 5 test).

**Trade-off**: không có nút bật/tắt lúc đang chạy (cần restart app khi đổi
`.env`) -- chưa làm vì sẽ đụng `main_window.py`/Settings (ASK FIRST).

**CHƯA verify (cần bạn tự test trên Windows thật)**:
1. Đặt `AI_MEETING_HIDE_FROM_CAPTURE=1`, chạy app, share màn hình/cửa sổ
   trong Zoom/Teams/Meet tới 1 máy/tài khoản khác -> cửa sổ chính, "Hỏi AI",
   drawer gợi ý, Settings, menu chuột phải đều KHÔNG hiện bên người xem.
2. Thử quay bằng OBS (Display Capture + Window Capture) và Win+Shift+S.
3. Nếu máy Windows < 10 bản 2004: xem log có cảnh báo `capture_protection`.

## Mục 41 — Bật/tắt ẩn khỏi screen share lúc đang chạy (T40, T42–T44)

**Quyết định** (theo yêu cầu người dùng: làm CẢ checkbox lẫn phím tắt):
- `capture_protection.py` đổi từ "filter bật 1 lần" thành
  `CaptureProtectionController` (bật/tắt lúc chạy, signal `changed(enabled, ok)`).
- Checkbox trong ⚙️ Cài đặt áp NGAY khi tick (không qua nút Lưu).
- Phím tắt toàn cục `Ctrl+Alt+Shift+F9` (module mới `global_hotkey.py`,
  `RegisterHotKey` + native event filter). Chọn tổ hợp dài, khó bấm nhầm
  vì bấm nhầm = lộ cửa sổ; tránh `Ctrl+Shift+H` (theo mình nhớ là "cúp máy" Teams).
- Tiêu đề cửa sổ chính là chỉ báo trạng thái: `🛡` đang ẩn, `⚠` bật nhưng
  API thất bại (KHÔNG giả vờ an toàn). Không dùng beep/âm thanh -- có thể lọt
  vào audio cuộc họp.
- Trạng thái khởi động = lựa chọn đã lưu; chưa từng chọn thì theo `.env`.

**PHÁT HIỆN QUAN TRỌNG** (bài học ghi nhớ): `save_api_key()`,
`clear_api_key()`, `set_active_provider()` dựng lại TOÀN BỘ payload
config.json và chỉ giữ `providers`/`active_provider`/`model_overrides` --
thêm field mới vào config.json sẽ bị XOÁ mỗi lần lưu API key. Vì vậy lựa
chọn được lưu ở FILE RIÊNG `ui_prefs.json` (cùng thư mục), có test chứng
minh sống sót qua save_api_key/set_active_provider/clear_api_key. KHÔNG
sửa các hàm cũ.

**File thay đổi**: `app/ui/capture_protection.py` (viết lại),
`app/ui/global_hotkey.py` (MỚI), `app/config_store.py` (chỉ NỐI THÊM 3 hàm
`*_hide_from_capture`/`get_ui_prefs_path`), `app/ui/settings_dialog.py`
(+checkbox), `app/ui/main_window.py` (+tiêu đề trạng thái), `app/main.py`,
`.env.example`, `tests/test_capture_protection.py` (5 -> 19 test).

**Trade-off / rủi ro còn lại**:
- Tắt bằng phím tắt giữa buổi share = cửa sổ lộ NGAY với người xem.
- Phím tắt cố định, chưa cho đổi trong Settings. Nếu bị app khác chiếm,
  app chỉ log cảnh báo và checkbox vẫn dùng được.
- `HelpDialog` chưa nhắc phím tắt (không đụng trong lượt này).
- Cửa sổ tạo SAU khi bật được áp ở `WinIdChange`/`Show` -- chưa đo được
  có khoảng hở 1 frame hay không trên máy thật.

**CHƯA verify (cần bạn tự test trên Windows thật)**:
1. Bỏ `QT_QPA_PLATFORM` (nếu còn từ lần trước), chạy `python -m app.main`,
   tick checkbox trong ⚙️ -> tiêu đề đổi sang `🛡`; xem `app.log` KHÔNG có
   cảnh báo `SetWindowDisplayAffinity`.
2. Bấm `Ctrl+Alt+Shift+F9` khi Zoom/Teams đang giữ focus -> tiêu đề app đổi
   🛡 <-> không; mở lại Settings thấy checkbox khớp.
3. Share màn hình tới tài khoản khác: lúc 🛡 người xem KHÔNG thấy app (cả
   Settings, menu chuột phải); tắt đi thì thấy.
4. Đóng app, mở lại: trạng thái được giữ đúng như lần chọn cuối.
