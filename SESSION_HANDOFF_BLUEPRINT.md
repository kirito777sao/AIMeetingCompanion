# 🚀 SESSION HANDOFF BLUEPRINT — AI Meeting Companion

## 1. Project Objective

App desktop Windows (PySide6) ghi âm loopback cuộc họp đa ngôn ngữ, hiển thị transcript song ngữ real-time (STT + dịch), hỗ trợ người dùng trả lời/hỏi chủ động bằng AI, và tổng hợp + xuất biên bản cuộc họp (tóm tắt/quyết định/việc cần làm) sau khi kết thúc, có lịch sử xem lại các phiên cũ. Ưu tiên: chính xác > tự nhiên > miễn phí, riêng tư (không lưu audio thô), không bịa thông tin AI không có trong transcript. Đang chuẩn bị đóng gói `.exe` để phân phối cho người dùng khác — mỗi người tự chọn 1 trong 3 provider AI (Groq/OpenAI/Gemini, MỚI Vòng 8) + tự nhập API key của họ. Nguồn sự thật gốc: `PROJECT_SPEC.md` + `CONTRACTS.md` (hợp đồng kỹ thuật chi tiết, LUÔN đọc trước khi sửa code).

## 2. Established Stack & Architecture

- **Stack**: Python, PySide6 (UI), SDK `openai` (dùng chung cho cả 3 provider qua base_url khác nhau — Groq/OpenAI/Gemini-lớp-tương-thích), `httpx` (MỚI Vòng 8, REST trực tiếp cho Gemini STT — xem dưới), SQLite (`meetings.db`), `python-dotenv`, webrtcvad, `python-docx`+`reportlab` (xuất file).
- **Threading (CONTRACTS.md Mục 3, bất biến)**: mỗi QThread tự tạo `MeetingStore`/`AIProvider` riêng bên trong `run()` (qua `provider_factory.create_provider()`, MỚI Vòng 8 — KHÔNG còn `GroqProvider()` hardcode ở `main_window.py`). UI chỉ nhận data qua Signal. Ngoại lệ CÓ Ý: mọi đọc/ghi SQLite cục bộ KHÔNG-AI/network chạy TRỰC TIẾP trên main thread.
- **`AIProvider` interface** (`app/ai/base_provider.py`) — public method signatures 🔒 KHÔNG đổi qua mọi vòng, kể cả Vòng 8. `TranscriptionResult.no_speech_prob` (Vòng 6) vẫn là tín hiệu lọc hallucination chính, KHÁC `confidence`.
- **🔒 MỚI Vòng 8 — kiến trúc multi-provider** (CONTRACTS.md Mục 17, đọc kỹ trước khi sửa bất kỳ file `app/ai/*`):
  - `app/ai/openai_compat_base.py`: `OpenAICompatProvider` — chứa `translate()`/`suggest_answer()`/`summarize()` DÙNG CHUNG cho Groq/OpenAI/Gemini (cùng đi qua SDK `openai`, chỉ khác `base_url`+tên model). Prompt/logic giữ NGUYÊN 100% so với `groq_provider.py` bản gốc (đã tự verify bằng cách chạy lại 39 test cũ, KHÔNG sửa file test).
  - `app/ai/whisper_utils.py`: parse response Whisper verbose_json (`segments`/`avg_logprob`/`no_speech_prob`) — DÙNG CHUNG Groq + OpenAI (cùng model gốc Whisper, OpenAI `whisper-1` xác nhận qua tài liệu chính thức trả ĐÚNG hình dạng response này).
  - `app/ai/groq_provider.py` (refactor, hành vi KHÔNG đổi), `app/ai/openai_provider.py` (MỚI), `app/ai/gemini_provider.py` (MỚI) — đều kế thừa `OpenAICompatProvider`, chỉ tự viết riêng `transcribe()`.
  - ⚠️ **Gemini KHÔNG có API kiểu Whisper** (lớp tương thích OpenAI của Google chỉ phủ chat, không phủ audio.transcriptions) — `GeminiProvider.transcribe()` viết HOÀN TOÀN riêng, gọi REST `generateContent` qua `httpx`, `confidence` là SỐ CỐ ĐỊNH 0.75 (placeholder, không đo được), `no_speech_prob` là tín hiệu NHỊ PHÂN (0.0/1.0) từ cờ tự-báo-cáo của model — KHÔNG mịn như Whisper thật. CHƯA verify bằng audio Gemini thật (không network trong sandbox).
  - `app/ai/provider_factory.py`: `create_provider()` — 1 điểm DUY NHẤT chọn provider (thứ tự ưu tiên: tham số > biến môi trường `AI_PROVIDER` > `config_store.get_active_provider()` > mặc định "groq").
- **`app/config_store.py` MỞ RỘNG (Vòng 8)**: từ chỗ chỉ lưu 1 key Groq (flat) → lưu NHIỀU key, 1 mỗi provider, độc lập (đổi qua lại không mất key cũ) + `active_provider`. **Tương thích ngược 100%**: đọc được file định dạng CŨ của người dùng Vòng 6, migrate-on-write sang định dạng mới khi `save_api_key()` được gọi lần kế. 12 test CŨ pass không sửa, +12 test multi-provider MỚI.
- **DB schema** (`app/storage/db.py`): `meetings`, `segments`, `ai_assists`, `meeting_reports` — KHÔNG đổi từ Vòng 6.
- **`app/pipeline.py`** — `NO_SPEECH_PROB_DROP_THRESHOLD = 0.6` (Vòng 6, không đổi) — vẫn hoạt động đúng với tín hiệu nhị phân 0.0/1.0 của Gemini (Vòng 8) vì cả 2 giá trị đều nằm rõ về 1 phía ngưỡng.
- **UI**: `ui/settings_dialog.py` MỞ RỘNG Vòng 8 — thêm dropdown chọn provider (Groq/OpenAI/Gemini), mỗi provider có link lấy key/placeholder/ghi chú giá-free-tier riêng. `ui/main_window.py`: 5 chỗ `GroqProvider()` → `create_provider()`.
- **Test convention**: `tests/test_*_offline.py`/`test_db.py`/`test_report_export.py`/`test_config_store.py`/`test_capture.py` chạy `python3 file.py` thuần. `test_vad.py`/`test_pipeline.py` cần `webrtcvad` (không có trong sandbox phiên Vòng 8). `test_ui_smoke.py` cần PySide6 thật (không có trong sandbox) — **đã sửa 27 chỗ monkeypatch `mw_module.GroqProvider`→`mw_module.create_provider`** theo refactor Vòng 8 nhưng **CHƯA tự chạy lại được để xác nhận** (rủi ro còn sót, xem mục 4 dưới). Dùng shim nội bộ KHÔNG đóng gói (`/home/claude/shims` — `openai`/`httpx` giả) để tự verify logic provider Vòng 8 trước khi giao.

## 3. Latest Working Deliverables

Zip mới nhất: `ai-meeting-companion-phase3-vong8-multi-provider.zip`.

**Vòng 8 (phiên này, theo yêu cầu MỚI của user — làm TRƯỚC khi trả lời câu hỏi Phase 4)**: thêm hỗ trợ Groq/OpenAI/Gemini — dán key của BẤT KỲ provider nào vào ⚙️ Cài đặt là dùng được. Chi tiết đầy đủ: CONTRACTS.md Mục 17, README.md mục "Vòng 8". 25 test MỚI (offline/mock) + 12 test config_store MỚI, TẤT CẢ pass; 39 test `test_groq_provider_offline.py` CŨ pass KHÔNG sửa 1 dòng (xác nhận refactor không đổi hành vi). Đã tự phát hiện + sửa 1 lỗi trong lúc làm: lúc viết `translate()` ở module chung, ban đầu paraphrase nhầm thay vì copy verbatim prompt gốc — bị test cũ bắt ngay, đã sửa đúng. Đã tự phát hiện + sửa 1 regression: `test_ui_smoke.py` monkeypatch tên `GroqProvider` không còn tồn tại sau refactor — đã sed lại 27 chỗ, NHƯNG chưa tự chạy lại được (thiếu PySide6 trong sandbox).

**⚠️ Trạng thái Vòng 7 (TRƯỚC Vòng 8) — QUAN TRỌNG, dễ bị hiểu lầm đã xong**: Vòng 7 (sửa suggest_answer() sai ngôn ngữ với hội thoại CJK + giảm `max_segment_ms` 15s→8s) **CHƯA được user retest/xác nhận pass** trên Windows thật — chỉ verify được ĐÚNG LOGIC trong sandbox. User yêu cầu làm Vòng 8 (multi-provider) TRƯỚC khi quay lại retest Vòng 7 — đây là quyết định CÓ Ý của user (đọc kỹ message gốc), KHÔNG phải bị bỏ quên, nhưng người tiếp tục phiên sau PHẢI biết Vòng 7 vẫn đang ở trạng thái "đã sửa, chưa retest" khi đọc README.

**Việc lớn CHƯA làm trong phạm vi Vòng 8 (do user yêu cầu RIÊNG, xem mục 4)**: trả lời câu hỏi "có cần làm Phase 4 không + thứ tự nào hợp lý" + đóng gói `.exe` chuyên nghiệp — 2 việc này được trả lời/đề xuất trong PHẦN CHAT trực tiếp với user (không phải code), README.md có bản tóm tắt ngắn ở mục cuối "Đề xuất thứ tự Phase 4".

## 4. Immediate Pending Tasks

1. **User tự test Vòng 8 với key OpenAI + key Gemini THẬT** trên Windows — theo checklist trong README.md mục "Vòng 8" (đổi provider trong Settings, ghi thử mỗi provider, đối chiếu transcript/dịch/gợi ý). CHƯA verify được trong sandbox (không network).
2. **User tự chạy lại `tests/test_ui_smoke.py` thật** (có PySide6) để xác nhận 27 chỗ sed `mw_module.GroqProvider`→`mw_module.create_provider` không có lỗi sót — CHƯA tự chạy lại được trong sandbox Vòng 8 (thiếu PySide6).
3. **Vòng 7 vẫn đang chờ retest** (xem mục 3 cảnh báo trên) — đừng nhầm là đã xong chỉ vì Vòng 8 đã xong.
4. Sau khi mục 1-3 xác nhận pass → quyết định CHÍNH THỨC có làm Phase 4 (diarization F12, `faster-whisper` local fallback) hay không + thứ tự — đã có đề xuất sơ bộ ở README.md mục cuối + trong phần chat trực tiếp với user phiên này, NHƯNG đây là Ý KIẾN, user cần tự quyết định dựa trên use-case thật.
5. Đóng gói `.exe` (PyInstaller) CHUYÊN NGHIỆP — CHƯA làm trong phiên Vòng 8 này (đã thảo luận hướng làm trong phần chat trực tiếp với user, nhưng chưa viết spec file `.spec`/script build cụ thể) — nên làm sớm (xem đề xuất thứ tự ở README) vì sẽ lộ ra bug đóng gói riêng (DPAPI, font, antivirus) không lường được khi chỉ chạy từ source.
6. Quy tắc làm việc CỐ ĐỊNH (nhắc lại từ phiên trước): làm từng bước nhỏ, dừng chờ user duyệt trước khi làm bước tiếp theo, trừ khi user tự yêu cầu gộp nhiều bước rõ ràng như phiên Vòng 8 này.

🚀 Session archived. Copy the blueprint above, open a New Chat, and paste it to continue with a 100% clean memory buffer.
