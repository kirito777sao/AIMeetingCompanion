# TASKS.md

> Tạo mới lần này (chưa có sẵn trước đó). Chỉ ghi task của lượt làm việc
> hiện tại (tính năng "Hỏi AI") + backlog phát hiện được nhưng CHƯA được
> chốt để làm ngay — không dựng lại lịch sử các Phase 0-3/Vòng 1-9 đã xong
> trước đó (đã có trong CONTRACTS.md).

## Tính năng "Hỏi AI" (chat đa lượt, dùng kiến thức nội tại của model)

- 🔒 T1 (✅ done+verified — xem CHANGELOG.md) — Thêm `chat()` vào `AIProvider`
  (`app/ai/base_provider.py`)
  - Input/Output: xem chữ ký đầy đủ ở CONTRACTS.md Mục 21.
  - Acceptance: abstract method có docstring đầy đủ (cùng chuẩn với
    `suggest_answer()`), không phá vỡ `OpenAICompatProvider` (vẫn phải
    implement cụ thể ở T2 để không còn là ABC "dở dang").
  - Dependency: không.

- 🔒 T2 (✅ done+verified) — Implement `chat()` trong `OpenAICompatProvider`
  (`app/ai/openai_compat_base.py`)
  - Acceptance: dùng lại `_chat_complete()` (fallback 429/404 sẵn có),
    system prompt ép output language theo `user_native_lang`, KHÔNG áp
    lưới an toàn "sai script" (khác `suggest_answer()`, xem lý do Mục 21).
    Test offline (mock client) PASS: trả đúng content, wrap lỗi thành
    `ProviderError`, giữ đúng thứ tự messages gửi lên API.
  - Dependency: T1.

- 🔒 T3 (✅ done+verified) — `ChatDialog` mới (`app/ui/chat_dialog.py`)
  - Acceptance: QDialog không-modal, `QTextEdit` hội thoại readonly + ô
    nhập + nút Gửi, `snapshot_messages()` trả bản sao lịch sử, lượt lỗi
    không được ghi vào lịch sử, cảnh báo "không tra cứu web" hiển thị cố
    định. Không cần unit test riêng (UI thuần, theo đúng convention hiện
    có — các dialog khác trong project cũng không có test riêng ngoài
    `test_ui_smoke.py`).
  - Dependency: không (độc lập với T1/T2 về mặt code, chỉ cần khi wire ở T4).

- 🔒 T4 (✅ done+verified) — Wire `ChatDialog` vào `MainWindow` (`app/ui/main_window.py`)
  - Acceptance: nút "💬 Hỏi AI" luôn bật, 1 instance dialog duy nhất tái sử
    dụng qua các lần bấm, mỗi lượt gửi chạy qua `OneShotAIWorker` mới +
    `_register_worker()` (giữ tham chiếu, tránh garbage-collect giữa
    chừng), `closeEvent()` vẫn đợi được worker đang chạy (không cần sửa gì
    thêm ở đó — `_ai_workers` đã dùng chung).
  - Dependency: T1, T2, T3.

- 🔒 T5 (✅ done+verified) — Test offline cho `chat()` (`tests/test_groq_provider_offline.py`,
  theo đúng convention file test hiện có — không tạo file test riêng, vì
  `chat()` sống trong `openai_compat_base.py`/dùng chung `_chat_complete()`
  đã có sẵn test ở file này)
  - Acceptance: PASS offline, cùng style với các test `suggest_answer()`
    hiện có (fake client, không gọi network thật).
  - Dependency: T1, T2.

## Backlog — phát hiện qua rà soát production-readiness, CHƯA chốt lịch làm

🔒 ~~Retry có backoff cho lỗi mạng tạm thời~~ (Backlog #2, done+verified —
xem Mục 29 dưới đây).

🔒 ~~Observability/log file~~ (Backlog #3, done+verified — xem Mục 30
dưới đây).

🔒 ~~Model chọn qua Settings UI~~ (Backlog #4, 🔒 done+verified trong
sandbox — xem Mục 31 dưới đây, xem CHANGELOG.md).

🔒 ~~Skeleton loading cho các dialog AI~~ (Mục 39, done+verified sandbox
VÀ Windows thật — người dùng đã tự mở app thật xác nhận animation ổn,
không cần chỉnh gì thêm. `SuggestionDrawer` + `AskQuestionDialog`, xem
CONTRACTS.md Mục 39. KHÔNG đụng `ChatDialog` — chủ ý, khác cấu trúc).
Đóng mục — không còn việc gì cần làm thêm.

🔒 ~~2 test DPAPI fail sai trên Windows~~ (dọn dẹp ngoài Backlog #1-3,
done+verified — đổi tên thành `test_save_api_key_encrypted_flag_khop_voi_kha_nang_thuc_te_cua_may`/
`test_is_encrypted_storage_available_khop_voi_platform_thuc_te`, so
`platform.system()` để chọn đúng kỳ vọng theo nền tảng thay vì hardcode
`False`. ✅ Xác nhận PASS trên Windows thật 05/09/2026 — xem CHANGELOG.md).

🔒 ~~`test_config_path_nam_dung_thu_muc_appdata_neu_co` so sánh đường dẫn
sai trên Windows~~ (phát hiện qua log Windows, done+verified — sửa thành
so `Path == Path` thay vì `str() == os.path.join()`. ✅ Xác nhận PASS
trên Windows thật 05/09/2026, cùng lượt log với 2 test DPAPI ở trên —
xem CHANGELOG.md). Toàn bộ 24 test trong `test_config_store.py` PASS
100% trên Windows thật, không còn mục nào treo trong file này.

⚪ Cải tiến khả năng chịu tạp âm NÓI CHUNG của `VadSegmenter`/pipeline
(không chỉ nhạc — tiếng ồn nền, nhiều người nói chồng lấn, v.v.).

**🔒 CẬP NHẬT (sau Mục 38, phản hồi test thật video anime với `language_hint`
đã bật)** — người dùng xác nhận đây là 2 vấn đề KHÁC NHAU, quyết định TẠM
HOÃN cả 2 (không phải huỷ bỏ — ghi vào kế hoạch để phát triển/sửa đổi sau):

1. **Tạp âm/nhạc nền/tiếng đánh nhau KHÔNG có thoại vẫn bị bịa lời** — gốc
   rễ nghi là `webrtcvad` (mặc định `aggressiveness=2`, xem
   `app/audio/vad.py`) phân loại nhầm tạp âm thành "có giọng nói" → đẩy
   xuống Whisper → Whisper không có cơ chế từ chối cứng, vẫn sinh văn bản.
   **Đề xuất chưa làm — T35**: tăng `aggressiveness` 2→3 (nhanh, rẻ,
   nhưng có rủi ro cắt nhầm thoại thật nói nhỏ/nhanh trong cảnh ồn, cần
   audio thật để verify).
2. **Có cả thoại lẫn tạp âm → dịch sai/kém chất lượng** — KHÓ hơn nhiều,
   không có ngưỡng lọc nào sửa được vì Whisper *có* nhận ra thoại, chỉ là
   nhận sai do tín hiệu giọng nói bị che lấp thật trong dữ liệu âm thanh.
   **Đề xuất chưa làm — T36 (quy mô LỚN, cần bàn kiến trúc riêng)**: khử
   nhiễu âm thanh (tách giọng nói khỏi nhạc nền bằng model chuyên dụng)
   TRƯỚC khi đưa vào VAD/Whisper — thêm dependency nặng, thêm độ trễ mỗi
   segment, KHÔNG nên làm vội.

Vẫn cần dữ liệu âm thanh thật (file mẫu hoặc dump chẩn đoán) để tinh chỉnh
mù không đoán được — xem log WARNING mới của T33 (Mục 38,
`_log_if_language_outlier`) làm nguồn dữ liệu tham khảo thêm khi bạn quay
lại vấn đề này. Chỉ quay lại làm T35/T36 khi bạn chủ động yêu cầu + có
audio mẫu thật hoặc mô tả cụ thể hơn.

🔒 ~~Xác nhận chỉ báo "🔊 [Âm thanh]" (Mục 23) hoạt động đúng với audio thật~~
— người dùng đã tự test với audio thật, xác nhận hoạt động đúng. Đóng mục.

🔒 ~~Rủi ro font PDF thiếu glyph Kana/Hangul (Mục 22)~~ — người dùng đã
xác nhận xuất PDF/docx tiếng Hàn/Nhật KHÔNG lỗi định dạng trên máy thật
(xem CHANGELOG.md, cùng lượt log Windows với Mục 25/26). Đóng mục này.


🔒 ~~`test_phase2_nut_nho_ai_tra_loi_mo_drawer_va_nhan_goi_y`~~
(`tests/test_ui_smoke.py`) — ĐÃ SỬA (xem CHANGELOG.md), không còn trong
Backlog.

## Mục 22 — Thêm tiếng Nhật/Hàn (🔒 done+verified, xem CHANGELOG.md)

## Mục 23 — Hiện "🔊 [Âm thanh]" cho nhạc/tạp âm không lời (🔒 done+verified, xem CHANGELOG.md)

## Mục 24 — Xoá vĩnh viễn phiên họp cũ (chọn nhiều, kèm cảnh báo + xác nhận)

- 🔒 T6 (✅ done+verified — xem CHANGELOG.md, đã có log Windows thật PASS) —
  `MeetingStore.delete_meetings()` (`app/storage/db.py`)
  - Acceptance: xoá đúng thứ tự con→cha (meeting_reports, ai_assists,
    segments, meetings), transaction 1 lần, id lạ không raise lỗi, danh
    sách rỗng không làm gì. Test `tests/test_db.py` (4 test mới) PASS.
  - Dependency: không.

- 🔒 T7 (✅ done+verified) — Chọn nhiều + nút xoá + cảnh báo/xác nhận
  (`app/ui/history_dialog.py`)
  - Acceptance: checkbox mỗi dòng, "Chọn tất cả", nút xoá hiện số lượng đã
    chọn, `QMessageBox` cảnh báo khuyến nghị xuất trước khi xoá + cảnh báo
    riêng phiên chưa có báo cáo, mặc định nút "Huỷ" (an toàn), chỉ xoá thật
    khi bấm đúng nút xác nhận. Test `tests/test_ui_smoke.py` (3 test mới)
    PASS trên cả sandbox lẫn Windows thật.
  - Dependency: T6.

- 🔒 T8 (✅ done+verified) — Chặn xoá phiên đang ghi âm
  (`app/ui/history_dialog.py`, `app/ui/main_window.py`)
  - Acceptance: `MainWindow` truyền `current_meeting_id`, dòng tương ứng
    disable checkbox + tooltip, "Chọn tất cả" bỏ qua dòng đó. Đã ghi rõ
    giới hạn (chỉ đúng tại thời điểm mở dialog) vào CHANGELOG.md.
  - Dependency: T7.

## Mục 25 — Cách ly `test_init_thieu_api_key_raise_provider_error` khỏi config.json thật (🔒 done+verified, xem CHANGELOG.md)

- 🔒 T9 (✅ done+verified) — Người dùng xác nhận: ĐÚNG, máy dev thật đang
  lưu sẵn 1 Groq API key thật qua ⚙️ Cài đặt (Settings UI) → xác định đúng
  nguyên nhân đã nghi ngờ. Monkeypatch `config_store.load_api_key` trả
  `None` trong lúc test (đúng pattern đã dùng ở
  `tests/test_openai_provider_offline.py::test_init_thieu_key_raise_provider_error_voi_huong_dan_openai`
  và tương đương ở `tests/test_gemini_provider_offline.py`), khôi phục lại
  ở `finally`. KHÔNG đụng code production (`app/ai/groq_provider.py`,
  `app/config_store.py`) — đây thuần là bug thiếu cách ly trong test.
  - Acceptance: test PASS cả khi KHÔNG có key thật lẫn khi CÓ key thật lưu
    sẵn trong config.json (đã tự tái hiện đúng bug cũ bằng cách giả lập
    `APPDATA` trỏ tới thư mục tạm + `save_api_key()` một key giả trước khi
    chạy test — xác nhận: bản CŨ sẽ fail trong tình huống này, bản MỚI
    PASS). Toàn bộ `tests/test_groq_provider_offline.py` (52 test) vẫn
    PASS, không hồi quy. `tests/test_openai_provider_offline.py`,
    `tests/test_gemini_provider_offline.py`, `tests/test_config_store.py`
    verify lại không hồi quy (cùng module `config_store` bị đụng gián
    tiếp qua import).
  - Dependency: không.
  - ⚠️ CHƯA có log chạy trên máy dev Windows thật của bạn cho riêng thay
    đổi này (chỉ verify được trong sandbox Linux) — cần bạn chạy lại
    `python -m pytest tests/test_groq_provider_offline.py` (hoặc file
    tổng) trên máy đó để xác nhận cuối cùng, đúng quy trình mọi lượt
    trước.

## Mục 26 — Audit + sửa toàn bộ test provider offline bị cùng lỗi thiếu cách ly config_store (🔒 done+verified, xem CHANGELOG.md)

- 🔒 T10 (✅ done+verified) — Log Windows thật của bạn (ngay sau Mục 25)
  cho thấy `test_init_voi_placeholder_key_bao_loi_ro_rang_khong_phai_401_kho_hieu`
  fail (traceback, dừng luôn phần còn lại của
  `test_groq_provider_offline.py`) — CÙNG nguyên nhân Mục 25, một chỗ
  khác trong cùng file mà tôi chưa rà hết ở lượt trước. Đã audit lại
  TOÀN BỘ 3 file `test_{groq,openai,gemini}_provider_offline.py`, tìm mọi
  chỗ gọi `Provider()` không truyền `api_key=` mà dựa vào biến môi trường
  — tìm thấy tổng cộng 4 test bị lỗi (2 ở Groq đã báo qua log, thêm 2 ở
  OpenAI/Gemini CHƯA từng được báo lỗi vì chưa ai chạy trên máy có key
  thật lưu sẵn cho 2 provider đó) — sửa cả 4 bằng cùng 1 pattern
  monkeypatch `config_store.load_api_key`.
  - Acceptance: cả 4 test PASS trong tình huống mô phỏng CÓ key thật lưu
    sẵn cho CẢ 3 provider cùng lúc (đã tự kiểm chứng trong sandbox, xem
    CHANGELOG.md) — không chỉ PASS ở điều kiện sạch như trước. Toàn bộ 3
    file test provider offline vẫn PASS 100% ở điều kiện sạch (không hồi
    quy).
  - Dependency: T9 (Mục 25).
  - ✅ Log Windows thật đã xác nhận (bạn gửi ngay sau) — cả 4 test PASS
    trên máy thật (kể cả sau khi bạn thử lưu/xác nhận key OpenAI/Gemini
    qua Settings UI), không hồi quy ở `test_db.py`,
    `test_openai_provider_offline.py`, `test_groq_provider_offline.py`,
    `test_gemini_provider_offline.py`. T10 đóng — 🔒 done+verified.

**Rule mới nên nhớ cho các lượt sau (đã áp dụng, không cần thêm action)**:
mọi test `Provider()`/`Provider(api_key=None)` không truyền `api_key`
tường minh trong `tests/test_*_provider_offline.py` BẮT BUỘC phải
monkeypatch `config_store.load_api_key` trả `None` (trừ khi test đó cố ý
đang kiểm chứng chính hành vi đọc từ `config_store`) — vì thứ tự ưu tiên
đọc key là `api_key tham số > config_store > env var`, nên bất kỳ test nào
dựa vào env var hoặc "không có key" mà thiếu cách ly đều có thể fail giả
(false failure) trên máy đã từng lưu key thật qua Settings UI.

## Mục 27 — Đưa các ngưỡng VAD/no_speech_prob ra `.env` (🔒 done+verified, xem CHANGELOG.md)

**Bối cảnh**: review code theo yêu cầu "tạp âm chung" (không có audio thật)
phát hiện 3 lớp vấn đề riêng biệt (VAD cắt nhầm, STT nghe sai, tạp âm hiện
thành bubble không bị lọc). Người dùng quyết định: (1) làm ngay phần an
toàn — đưa số ra `.env` để tự tinh chỉnh khi gặp tạp âm thật; (2) KHÔNG
thêm lớp lọc thứ 2 dựa confidence (rủi ro lọc nhầm câu ngắn thật, không
chấp nhận đánh đổi); (3) KHÔNG thêm khử nhiễu audio (thư viện mới, phức
tạp hoá dự án, chưa có audio thật để test) — để dành.

- 🔒 T11 (✅ done+verified) — `app/audio/vad.py::create_vad_segmenter_from_env()`
  — hàm mới (KHÔNG sửa `VadSegmenter.__init__`, giữ class thuần/dễ test
  như thiết kế cũ) đọc `VAD_AGGRESSIVENESS`/`VAD_SILENCE_MS`/
  `VAD_MIN_SPEECH_MS`/`VAD_MAX_SEGMENT_MS`/`VAD_PADDING_MS` từ env, fallback
  default cũ nếu không đặt/đặt sai định dạng (không raise). Wire vào
  `ui/main_window.py` thay `VadSegmenter(samplerate=16000)` hardcode.
  - Acceptance: không đặt env → hành vi giống hệt trước (assert khớp từng
    field với `VadSegmenter` default). Đặt env → dùng đúng giá trị đó. Env
    sai định dạng (vd chữ) → fallback default, không crash. 3 test mới
    trong `tests/test_vad.py` PASS.
  - Dependency: không.

- 🔒 T12 (✅ done+verified) — `app/pipeline.py::MeetingPipeline` — thêm
  tham số `no_speech_prob_drop_threshold: float | None = None`, đọc
  `NO_SPEECH_PROB_DROP_THRESHOLD` từ env khi không truyền, fallback hardcode
  `0.6` khi env không đặt/sai định dạng. Đúng 3 tầng ưu tiên (tham số > env
  > hardcode) như `GroqProvider.__init__`.
  - Acceptance: 3 test mới trong `tests/test_pipeline.py` — không truyền
    tham số + có env → dùng env; truyền tham số trực tiếp + có env → tham
    số thắng; env sai định dạng → fallback đúng `0.6`. Toàn bộ test
    pipeline cũ (bao gồm 2 test hallucination/câu ngắn) vẫn PASS không
    hồi quy.
  - Dependency: không.

- `.env.example` — thêm block giải thích + ví dụ (comment sẵn, không bật
  mặc định) cho cả 6 biến mới.

**Verify**: `tests/test_vad.py` (12/12 PASS, gồm 3 test mới),
`tests/test_pipeline.py` (12/12 PASS, gồm 3 test mới), không hồi quy ở
`test_db.py`/`test_groq_provider_offline.py`/`test_openai_provider_offline.py`/
`test_gemini_provider_offline.py`/`test_config_store.py`. ✅ Log Windows
thật đã xác nhận (bạn gửi log chạy `test_vad.py` + `test_pipeline.py` +
`test_db.py` + 3 file provider offline + `test_ui_smoke.py` cùng lúc, tất
cả PASS — `main_window.py` đổi import `create_vad_segmenter_from_env`
không lỗi khi chạy UI thật). Mục 27 đóng hẳn — 🔒 done+verified, không còn
mục nào treo.

## Mục 28 — Timeout tường minh cho client Groq/OpenAI/Gemini (Backlog #1, 🔒 done+verified, xem CHANGELOG.md)

**Bối cảnh**: người dùng chốt làm Backlog #1 trước, theo đúng thứ tự đã
liệt kê (Timeout → Retry backoff → Log file → Model Settings UI →
Skeleton loading).

- 🔒 T13 (✅ done+verified) — `_resolve_client_timeout_seconds()` mới
  (`app/ai/openai_compat_base.py`) + wire `timeout=` vào `openai.OpenAI(...)`
  ở cả 3 provider (`groq_provider.py`, `openai_provider.py`,
  `gemini_provider.py`).
  - Acceptance: default 30.0s (KHÔNG phải ~600s mặc định của SDK), tham số
    constructor `client_timeout_seconds` > biến môi trường
    (`GROQ_CLIENT_TIMEOUT_SECONDS`/`OPENAI_CLIENT_TIMEOUT_SECONDS`/
    `GEMINI_CLIENT_TIMEOUT_SECONDS`) > default, env sai định dạng hoặc
    `<= 0` fallback default không raise. Gemini: CHỈ áp dụng cho
    `self._client` (phần chat) — `http_timeout_seconds` (transcribe REST
    riêng) KHÔNG đổi. 9 test mới (5 Groq + 2 OpenAI + 2 Gemini) PASS
    trong sandbox, không hồi quy 3 file test provider offline +
    `test_config_store.py` + `test_provider_factory_offline.py`.
  - Dependency: không.
  - ✅ Đã verify bằng log Windows thật (`D:\Code_All\ai-meeting-companion-
    vong8-multi-provider\project`) — 3 file test PASS 100%, khớp y hệt
    sandbox. Mục 28 đóng hẳn — 🔒 done+verified, không còn treo.

## Mục 29 — Retry có backoff cho lỗi kết nối mạng tạm thời (Backlog #2, 🔒 done+verified, xem CHANGELOG.md)

- 🔒 T14 (✅ done+verified) — `_retry_with_backoff()` + `_call_with_retry()`
  mới (`app/ai/openai_compat_base.py`); `_call_with_fallback()` (Mục 19)
  wire mỗi lần gọi model qua `_call_with_retry()`; Gemini
  `_post_generate_content()` wire qua `_retry_with_backoff()` trực tiếp
  (đi qua `httpx`, không qua SDK `openai`).
  - Acceptance: retry GIỮ NGUYÊN model khi `openai.APIConnectionError`
    (Groq/OpenAI) hoặc `httpx.RequestError` (Gemini), backoff tăng dần
    1s→2s, tối đa 2 lần thử lại (tổng 3 lần gọi/model). Lỗi 429/404 VẪN
    fallback model như cũ (Mục 19), không bị đổi hành vi. Hết lượt retry
    → `ProviderError` nêu rõ "lỗi kết nối mạng (đã tự động thử lại N
    lần)". 7 test mới (4 Groq + 1 OpenAI + 2 Gemini) PASS trong sandbox,
    không hồi quy 3 file test provider offline + `test_config_store.py`
    + `test_provider_factory_offline.py` + `test_vad.py` +
    `test_pipeline.py` + `test_db.py`.
  - Dependency: Mục 19 (`_call_with_fallback`), Mục 28 (đi chung 1 mạch
    "độ tin cậy mạng" — timeout trước, retry sau).
  - ✅ Đã verify bằng log Windows thật (cùng lượt chạy với Mục 28) — PASS
    100%, khớp y hệt sandbox. Mục 29 đóng hẳn — 🔒 done+verified. Backlog
    #1 + #2 đều đã xong theo đúng thứ tự người dùng chốt, chuyển sang
    Backlog #3 (log ra file).

## Mục 30 — Log ra file để debug từ xa (Backlog #3, 🔒 done+verified, xem CHANGELOG.md)

- 🔒 T15 (✅ done+verified) — `app/logging_setup.py` MỚI
  (`setup_logging()`/`get_logger()`/`get_log_path()`, ghi ra
  `%APPDATA%\AIMeetingCompanion\app.log`, `RotatingFileHandler` 2MB×3
  backup, idempotent, fallback `NullHandler` nếu không tạo được thư mục).
  - Acceptance: 5 test mới (`tests/test_logging_setup.py`) PASS — tạo
    file đúng nội dung/định dạng, gọi 2 lần không nhân đôi handler, fail
    tạo thư mục không raise.
  - Dependency: `app.config_store.get_config_dir()` (Mục 1x — dùng
    CHUNG thư mục config.json).
- 🔒 T16 (✅ done+verified) — wire `get_logger()` vào MỌI điểm bắt lỗi
  hiện có: `app/main.py` (setup sớm nhất + `sys.excepthook` bắt crash +
  log start/stop app), `app/pipeline.py` (transcribe ERROR/translate
  WARNING/DB ERROR kèm `meeting_id`), `app/ui/ai_worker.py`
  (`OneShotAIWorker` — mọi lỗi suggest_answer/translate/summarize 1-lần),
  `app/ui/main_window.py` (`AudioWorker` — init provider, tạo phiên họp,
  audio capture, flush, mốc bắt đầu/kết thúc phiên).
  - Acceptance: 2 test mới trong `tests/test_pipeline.py`
    (`test_pipeline_log_loi_transcribe_ra_logger`,
    `test_pipeline_log_loi_translate_ra_logger`) xác nhận log THẬT SỰ
    được ghi (không chỉ `TranscriptEvent.error`), dùng
    `_CaptureLogHandler` tạm, không phụ thuộc file thật.
  - Dependency: T15.
  - ✅ Đã verify bằng log Windows thật (`D:\Code_All\ai-meeting-companion-
    vong8-multi-provider\project`) — cả 2 file test PASS 100%, khớp y hệt
    sandbox. `test_config_store.py`/`test_provider_factory_offline.py`/
    `test_vad.py`/`test_db.py` cũng chạy lại — PASS hết TRỪ 2 test DPAPI
    fail "đúng như dự kiến" trên Windows (KHÔNG phải hồi quy, xem mục
    Backlog mới ở trên: "tách test DPAPI theo OS"). Mục 30 đóng hẳn — 🔒
    done+verified. Backlog #1+#2+#3 đều đã xong theo đúng thứ tự đã
    chốt, chuyển sang Backlog #4 (Model Settings UI) khi người dùng sẵn
    sàng — nhớ ASK FIRST trước khi bắt đầu, đúng quy tắc Backlog.
  - ⚠️ CHƯA tự verify thủ công trên UI thật (mở `%APPDATA%\
    AIMeetingCompanion\app.log`, xem nội dung log lúc chạy app/tạo phiên
    họp thật) — chỉ verify qua test tự động. Không bắt buộc, chỉ là gợi
    ý kiểm tra thêm nếu người dùng muốn tự tay xác nhận.

## Mục 31 — Model Settings UI: đổi model qua ⚙️ Cài đặt, không cần `.env` (Backlog #4, 🔒 done — chờ xác nhận Windows thật)

**Bối cảnh quan trọng**: phần backend (`config_store.py::save/load/
clear_model_overrides()`, merge trong `provider_factory.py::create_provider()`)
đã được viết ở 1 lượt làm việc TRƯỚC lượt này — nhưng KHÔNG được ghi vào
TASKS.md/CHANGELOG.md, KHÔNG có test, đã báo lại cho người dùng trước khi
làm tiếp (xem CHANGELOG.md). T17-T21 dưới đây là phần HOÀN THIỆN (viết
tài liệu + test + UI) cho code backend đã có sẵn đó, không phải viết lại.

- 🔒 T17 (✅ done) — Viết `CONTRACTS.md` Mục 31 mô tả đúng thiết kế backend
  đã có (schema `model_overrides`, 4 field, 4 tầng ưu tiên: tham số >
  override Settings UI > env (chỉ Groq) > hardcode default).
  - Dependency: không.
- 🔒 T18 (✅ done+verified) — 8 test mới cho `save/load/clear_model_overrides()`
  (`tests/test_config_store.py`): roundtrip, chưa từng lưu trả dict rỗng,
  field rỗng không được lưu, field lạ bị bỏ qua, không đụng provider
  khác, `clear_model_overrides()` xoá đúng/không lỗi khi chưa từng lưu,
  không ảnh hưởng API key/active_provider đã lưu.
  - Acceptance: 32/32 test `test_config_store.py` PASS trong sandbox.
  - Dependency: không (code backend đã có sẵn).
- 🔒 T19 (✅ done+verified) — 3 test mới cho merge override trong
  `create_provider()` (`tests/test_provider_factory_offline.py`,
  monkeypatch `config_store.load_model_overrides` — KHÔNG dùng base_dir
  thật, cùng lý do cách ly Mục 25/T9): override đã lưu được dùng khi
  không truyền kwargs; kwargs truyền trực tiếp thắng override; chưa từng
  override → dùng default hardcode của provider (không đổi hành vi cũ).
  - Acceptance: 13/13 test `test_provider_factory_offline.py` PASS.
  - Dependency: không.
- 🔒 T20 (✅ done — verify sandbox, CHƯA verify Windows thật) — 4 ô nhập
  model + nút "Khôi phục mặc định" trong `ui/settings_dialog.py`
  (placeholder = default hiện tại qua `get_default_models_for_display()`,
  đổi theo dropdown provider giống pattern ô API key, lưu cùng 1 nút "Lưu"
  hiện có — KHÔNG thêm nút Lưu riêng cho model).
  - Acceptance: import/khởi tạo `SettingsDialog` thành công qua smoke-test
    thủ công trong sandbox (`QT_QPA_PLATFORM=offscreen`) — placeholder
    đúng default Groq, restore-defaults hoạt động đúng. `tests/test_ui_smoke.py`
    (23 test, KHÔNG có test riêng cho `SettingsDialog` — đúng convention
    dự án, UI thuần không cần unit test riêng, xem T3) chạy lại PASS
    100%, không hồi quy. Toàn bộ 9 file test khác (config_store,
    provider_factory, 3 provider offline, logging_setup, db, vad,
    pipeline) PASS 100% trong sandbox.
  - ⚠️ **CHƯA verify thủ công trên Windows thật** (mở app, vào ⚙️ Cài đặt,
    nhìn giao diện thật, thử điền/xoá 1 model override thật) — cần bạn
    tự làm.
  - Dependency: T17.
- 🔒 T21 (✅ done) — Ghi `CHANGELOG.md`, cập nhật `TASKS.md` (mục này).
  - Dependency: T17-T20.

**Verify tổng**: 9/9 file test PASS 100% trong sandbox (bao gồm cài mới
`httpx`/`PySide6`/`pytest-qt` — thiếu trong sandbox trước khi bắt đầu Mục
31, đã cài để tự verify được UI). Sandbox này chạy `test_ui_smoke.py` bằng
`python3 tests/test_ui_smoke.py` (script thuần, KHÔNG phải `pytest` — file
không có `conftest.py`, fixture `app` chỉ tồn tại trong khối
`if __name__ == "__main__":`, gọi qua `pytest` trực tiếp sẽ báo lỗi
"fixture 'app' not found", KHÔNG phải regression thật).

**CHƯA làm/CHƯA verify**:
1. Chưa test Windows thật (xem T20).
2. Chưa test với model KHÔNG hợp lệ thật (vd gõ nhầm tên model vào ô Settings
   → lỗi từ API xảy ra ở lúc GỌI model, không phải lúc lưu — hành vi ĐÚNG Ý
   ĐỊNH giống hệt cách `.env` hoạt động trước đây, không phải bug, nhưng
   CHƯA tự verify bằng key thật trong sandbox này — không có mạng ra ngoài).
3. `.env.example` KHÔNG cần sửa gì (Mục 31 không thêm biến môi trường mới,
   chỉ thêm đường Settings UI song song).

## Mục 32-34 (MỚI — theo yêu cầu người dùng sau khi xác nhận Mục 31 pass)

- 🔒 T22 (✅ done — verify sandbox, CHƯA verify Windows thật) — Mnemonic
  bàn phím (Alt+B/K/T/X/L/A/C) cho 7 nút chính `ui/main_window.py`
  (CONTRACTS.md Mục 32).
  - Acceptance: `test_nut_chinh_co_mnemonic_rieng_biet_khong_trung` PASS
    (7 nút đều có đúng 1 mnemonic, không trùng chữ cái). Toàn bộ
    `test_ui_smoke.py` cũ PASS không sửa assert nào (đã xác nhận không
    test nào so `.text()` bằng chuỗi chính xác cho các nút này).
  - Dependency: không.
- 🔒 T23 (✅ done+verified sandbox) — `MeetingStore.delete_meetings()`
  reset `sqlite_sequence` của bảng `meetings` khi xoá xong bảng TRỐNG
  HOÀN TOÀN; giữ nguyên id khi xoá 1 phần (CONTRACTS.md Mục 33).
  - Acceptance: 4 test mới trong `tests/test_db.py` PASS (xoá 1 phần
    không đổi id + bộ đếm vẫn tăng tiếp bình thường; xoá hết 1 lệnh reset
    về 1; xoá hết qua nhiều lệnh riêng lẻ vẫn reset đúng lúc; DB rỗng chưa
    từng ghi gì không lỗi "no such table sqlite_sequence"). 4 test cũ của
    `delete_meetings()` PASS không sửa.
  - Dependency: không.
- 🔒 T24 (✅ done — verify sandbox, CHƯA verify Windows thật) — Singleton
  reuse cho `SettingsDialog`/`MeetingHistoryDialog`/`AskQuestionDialog`
  (theo đúng pattern `_chat_dialog` có sẵn) + `showEvent()`/`refresh()`/
  `set_default_target_lang()` để tự làm mới dữ liệu khi tái dùng
  (CONTRACTS.md Mục 34.2).
  - Acceptance: 3 test mới trong `test_ui_smoke.py` PASS (bấm nút 2-3 lần
    liên tiếp chỉ tạo ĐÚNG 1 instance + tự refresh đúng dữ liệu mới nhất
    mỗi lần mở lại).
  - Dependency: không.
- 🔒 T25 (✅ done — verify sandbox, CHƯA verify Windows thật) —
  `_report_dialogs: dict[meeting_id, ReportDialog]` ở `main_window.py`:
  bấm lại đúng 1 phiên đang mở không gọi lại AI/tạo cửa sổ mới; phiên
  khác vẫn mở cửa sổ riêng; tự dọn dict khi dialog đóng qua `finished`
  signal (CONTRACTS.md Mục 34.3).
  - Acceptance: `test_xem_bao_cao_cung_1_phien_khong_mo_trung_khac_phien_thi_mo_rieng`
    PASS (đếm `summarize()` chỉ gọi đúng 2 lần cho 2 phiên khác nhau, lần
    bấm lại thứ 3 không tăng thêm).
  - Dependency: không.
- 🔒 T26 (✅ done) — Ghi `CONTRACTS.md` Mục 32/33/34, cập nhật `TASKS.md`
  (mục này), `CHANGELOG.md`.
  - Dependency: T22-T25.

**Verify tổng**: 9/9 file test PASS 100% trong sandbox, KHÔNG hồi quy —
tổng 206 dòng `OK:` (tăng từ 181 trước Mục 32-34, đúng 25 test mới thêm:
4 ở `test_db.py`, 21 ở `test_ui_smoke.py` gồm 5 test mới + 16 assert phụ
trong các test đó — xem log chạy đầy đủ).

**CHƯA làm/CHƯA verify**:
1. Chưa test Windows thật cho cả 3 mục (xem cảnh báo cuối CONTRACTS.md
   Mục 32-34): Alt+phím tắt có hoạt động đúng trên Windows thật (mnemonic
   hiển thị gạch chân là hành vi Windows-specific); xoá lịch sử thật qua
   UI (không phải gọi thẳng `delete_meetings()` trong test) có thấy đúng
   id `#1` sau khi xoá hết; nhấn đúp CHUỘT THẬT (không phải gọi hàm trực
   tiếp) vào từng nút có chỉ mở đúng 1 cửa sổ.
2. Cân nhắc thêm (KHÔNG làm trong lượt này, chưa ai yêu cầu): `QShortcut`
   toàn cục không cần Alt (vd F5 = Bắt đầu ghi) — mnemonic hiện tại đã đủ
   cho yêu cầu gốc "thao tác được bằng bàn phím", thêm phím tắt không-Alt
   rủi ro xung đột với phím hệ thống/IME gõ tiếng Việt nếu chọn sai phím.

## Mục 35 (MỚI — bugfix theo phản hồi test thật của người dùng)

- 🔒 T27 (✅ done+verified, CHẠY THẬT được trong sandbox lần này nhờ tự
  cài PySide6) — Sửa `MainWindow._on_history_clicked()`: không còn khoá
  nhầm phiên ĐÃ kết thúc là "đang ghi âm" khi mở dialog Lịch sử
  (CONTRACTS.md Mục 35).
  - Acceptance: test mới `test_lich_su_khong_khoa_phien_da_ket_thuc_du_current_meeting_id_con_luu`
    PASS; 28 test cũ trong `test_ui_smoke.py` PASS không sửa assert nào.
  - Dependency: không.

**CHƯA làm/đang chờ quyết định của bạn (xem phần chat)**:
1. Trợ giúp/hướng dẫn trong UI cho người mới (phím tắt Alt+..., quy trình
   dùng cơ bản) — CHƯA có task cụ thể, đang chờ bạn chốt phạm vi.
2. Tạp âm không lời thoại bị bịa chữ + dịch loạn — TASKS.md mục cũ (trước
   Mục 32) đã ghi nhận đây là quyết định CỐ Ý KHÔNG làm thêm lớp lọc/khử
   nhiễu; bạn báo bản này TỆ HƠN bản trước — cần bạn xác nhận có muốn xét
   lại quyết định đó không (xem phần chat, chưa tự ý làm gì thêm ở đây).

## Mục 36-37 (MỚI — theo lựa chọn của người dùng sau khi hỏi lại ở Mục 35)

- 🔒 T28 (✅ done+verified sandbox) — Lớp lọc confidence thứ 2 (opt-in qua
  `.env`, xét lại quyết định cũ Mục 27) trong `app/pipeline.py`
  (CONTRACTS.md Mục 36).
  - Acceptance: 6 test mới `tests/test_pipeline.py` PASS, 14 test cũ PASS
    không sửa.
  - Dependency: không.
  - ⚠️ CHƯA verify bằng audio thật (anime/tạp âm thật) — người dùng cần tự
    bật + tinh chỉnh `CONFIDENCE_DROP_THRESHOLD` trên Windows.
- 🔒 T29 (✅ done+verified sandbox) — Dialog "❓ Trợ giúp" (Alt+G) liệt kê
  phím tắt + quy trình dùng cơ bản (CONTRACTS.md Mục 37).
  - Acceptance: `test_nut_chinh_co_mnemonic_rieng_biet_khong_trung` PASS
    với 8 nút; test mới singleton PASS; 29 test cũ còn lại PASS.
  - Dependency: không.
  - ⚠️ CHƯA verify Windows thật (Alt+G, font/encoding tiếng Việt).
- 🔒 T30 (✅ done) — Ghi CONTRACTS.md Mục 36/37, TASKS.md (mục này),
  CHANGELOG.md.
  - Dependency: T28, T29.

**Verify tổng lượt này**: 9/9 file test PASS 100% trong sandbox — LẦN ĐẦU
TIÊN tự cài được `PySide6`/`webrtcvad` qua pip và chạy THẬT `test_ui_smoke.py`
+ `test_pipeline.py` (các lượt trước luôn thiếu, phải ghi "CHƯA verify").
30 dòng `OK:` ở `test_ui_smoke.py` (tăng từ 28, +2: T27 + T29), 20 dòng
`OK:` ở `test_pipeline.py` (tăng từ 14, +6: T28).

**CHƯA làm/CHƯA verify (cần bạn tự làm trên Windows thật)**:
1. Bật `CONFIDENCE_DROP_THRESHOLD` trong `.env`, thử lại đúng audio đã gặp
   vấn đề (anime/tạp âm), quan sát 2 chiều (tạp âm còn lọt không / có mất
   câu ngắn thật không) rồi tinh chỉnh số — CHƯA có số "đúng" sẵn.
2. Kiểm tra file log (Mục 30) xem lần test anime có thật sự bị fallback
   `whisper-large-v3` → `whisper-large-v3-turbo` do rate-limit không —
   nếu đúng, đây mới là nguyên nhân GỐC (T28 chỉ giảm triệu chứng ở tầng
   sau, không sửa nguyên nhân đó).
3. Alt+G có hoạt động đúng trên Windows thật không (cùng nhóm câu hỏi
   "CHƯA verify Windows thật" với Mục 32/33/34 — xem CONTRACTS.md).

## Mục 38 (MỚI — theo phản hồi test thật video anime sau khi bật T28)

- 🔒 T31 (✅ done+verified sandbox) — `language_hint` xuyên suốt
  `AIProvider.transcribe()` → 3 provider → `MeetingPipeline` → UI dropdown
  "Ngôn ngữ nguồn dự kiến" ở `MeetingContextDialog` (CONTRACTS.md Mục 38).
  - Acceptance: 2 test Groq + 1 OpenAI + 2 Gemini + 2 pipeline + 2 UI, tất
    cả PASS; toàn bộ test cũ PASS (1 regression phát hiện+sửa ngay:
    `FakeProvider` thiếu tham số mới).
  - Dependency: không.
  - ⚠️ CHƯA verify bằng audio thật — người dùng cần tự chọn "Ngôn ngữ
    nguồn dự kiến" = Nhật khi ghi lại video anime đã gặp vấn đề.
- 🔒 T33 (✅ done+verified sandbox) — `_log_if_language_outlier()` trong
  `app/pipeline.py`, log WARNING (không lọc) khi ngôn ngữ lệch hint/đa số
  gần đây (CONTRACTS.md Mục 38).
  - Acceptance: không đổi hành vi UI nào, không có test riêng (thuần
    logging nội bộ) — verify gián tiếp qua toàn bộ test pipeline vẫn PASS.
  - Dependency: không.
- 🔒 T34 (✅ done) — Ghi CONTRACTS.md Mục 38, TASKS.md (mục này),
  CHANGELOG.md.
  - Dependency: T31, T33.
- ⚪ T32 (CHỜ quyết định — phụ thuộc kết quả test T31 trên Windows) — đưa
  `meeting_context` làm `prompt` gửi kèm Whisper API, giảm thêm
  hallucination bối cảnh. Tạm HOÃN: ưu tiên để người dùng test hiệu quả
  T31 trước, tránh đổi 2 biến cùng lúc khiến khó đánh giá cái nào thật sự
  có tác dụng.

**Verify tổng lượt này**: toàn bộ 9 file test PASS 100% trong sandbox, kể
cả `test_ui_smoke.py` (32/32, tăng từ 30, +2: T31) và `test_pipeline.py`
(22/22, tăng từ 20, +2: T31).

**CHƯA làm/CHƯA verify (cần bạn tự làm trên Windows thật)**:
1. Chọn "Ngôn ngữ nguồn dự kiến" = tiếng Nhật khi ghi lại đúng video anime
   đã gặp vấn đề, so sánh tần suất "nhảy" sang EN/Norwegian/RU trước/sau —
   quyết định T31 có đủ hay cần làm tiếp T32.
2. (Kế thừa từ Mục 36, VẪN CHƯA xác nhận) Kiểm tra file log (Mục 30) xem
   có bị fallback `whisper-large-v3` → `whisper-large-v3-turbo` do
   rate-limit trong lúc test anime không.
3. Xem log WARNING mới của T33 (`_log_if_language_outlier`) trong lúc test
   để có con số cụ thể "nhảy ngôn ngữ bao nhiêu lần" thay vì chỉ cảm nhận
   qua mắt.

## Mục 40 (MỚI — theo yêu cầu người dùng: đóng gói .exe phân phối nhiều máy)

- 🔒 T-DB-PATH (✅ done+verified sandbox) — sửa `_DEFAULT_DB_PATH` dùng
  `get_config_dir()` thay vì chuỗi tương đối "meetings.db" (CONTRACTS.md
  Mục 40). Bug thật tự phát hiện khi soi code, không phải người dùng báo.
  - Acceptance: `test_default_db_path_dung_thu_muc_appdata_khong_phai_duong_dan_tuong_doi`
    PASS. Toàn bộ 35/35 test UI smoke + 9 file test khác PASS.
  - Dependency: không.
- 🔒 T-PACKAGING (✅ file đã viết xong, ⚠️ CHƯA verify build thật) —
  `run_app.py`, `packaging/AIMeetingCompanion.spec`,
  `packaging/installer.iss`, `packaging/HUONG_DAN_DONG_GOI_EXE.md`
  (CONTRACTS.md Mục 40).
  - Acceptance: `run_app.py` import + chạy thử trong sandbox không lỗi
    (đã verify). Build .exe thật + Inno Setup + cài trên máy khác — CHƯA
    verify (PyInstaller không cross-compile từ sandbox Linux).
  - Dependency: T-DB-PATH (phải sửa bug DB TRƯỚC khi đóng gói, nếu không
    bug sẽ lộ ra ngay trên máy người dùng khác).

**CHƯA làm/CHƯA verify (cần bạn tự làm trên Windows thật)**:
1. Chạy toàn bộ `packaging/HUONG_DAN_DONG_GOI_EXE.md` từ Bước 0 đến Bước
   4 trên máy Windows thật, báo lại nếu PyInstaller báo lỗi hidden import
   thiếu (dùng `console=True` tạm thời để xem traceback thật, xem hướng
   dẫn "Nếu app KHÔNG mở lên được").
2. Test file `AIMeetingCompanion_Setup.exe` trên 1 máy KHÁC (hoặc máy ảo
   sạch chưa từng cài Python) — xác nhận cài không cần quyền Admin, nhập
   API key mới, ghi âm thử, gỡ cài đặt sạch.
3. Nếu ổn, gửi file cài đặt cho người dùng thật đầu tiên, thu thập phản
   hồi trước khi phân phối rộng hơn.
