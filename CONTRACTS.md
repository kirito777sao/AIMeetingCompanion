# CONTRACTS.md — Các hợp đồng kỹ thuật đã chốt giữa các module

> **Lưu ý quan trọng**: file này KHÔNG có trong các file bạn upload, nhưng
> code hiện tại (capture.py, vad.py, base_provider.py, groq_provider.py)
> tham chiếu tới "CONTRACTS.md Mục 2/3/4/5" rất nhiều lần như một nguồn sự
> thật đã có sẵn. Có 2 khả năng: (a) file này đã được tạo ở một phiên làm
> việc khác và bị quên upload, hoặc (b) file này chưa từng được tạo thật,
> các comment chỉ là "lời hứa" của agent trước. Tôi đã **dựng lại** nội
> dung Mục 2-4 bằng cách suy ngược từ chính hành vi code hiện tại (đã chạy
> test xác nhận khớp), và **chốt mới** Mục 5 (schema DB) vì đây là phần
> tiếp theo cần làm (storage/db.py) mà chưa có ai quyết định trước.
>
> ⚠️ Nếu bạn có bản CONTRACTS.md gốc khác ở nơi nào đó — gửi lại để tôi đối
> chiếu, tránh 2 bản lệch nhau về sau.

---

## Mục 1 — Mục đích

File này là nguồn sự thật duy nhất cho các "hợp đồng" giữa module: kiểu dữ
liệu trao đổi, đơn vị, ai chịu trách nhiệm làm gì. Khi 1 module thay đổi
hành vi đã chốt ở đây, phải sửa luôn các module phụ thuộc + sửa lại mục
tương ứng trong file này, không để lệch.

---

## Mục 2 — Hợp đồng dữ liệu audio (capture.py → vad.py → ai/*)

- `stream_loopback_chunks()` luôn yield chunk kiểu **`numpy.float32`**, giá
  trị trong khoảng **`[-1.0, 1.0]`**.
- `mono=True` (mặc định): shape `(n_frames,)`. `mono=False`: shape
  `(n_frames, n_channels)`.
- Đã **resample về `target_samplerate`** (mặc định **16000 Hz**) ngay tại
  lớp audio — `vad.py` và `ai/*` KHÔNG tự resample lại.
- `VadSegmenter.feed()`/`flush()` trả về segment cùng dtype/range như trên,
  **cùng samplerate đầu vào** (vad.py không đổi samplerate).
- `AIProvider.transcribe(audio, samplerate)` luôn nhận `samplerate` rõ ràng
  qua tham số — KHÔNG hardcode 16000, vì `record_system_audio()` (đường
  Phase 0, dùng cho file .wav test) mặc định 48000Hz, khác với đường
  streaming Phase 1 (16000Hz).
- ⚠️ **Giới hạn quan trọng đã xác nhận bằng test thật**: loopback audio thu
  được là **1 dòng mono/stereo DUY NHẤT đã được app họp (Zoom/Teams/Meet)
  TRỘN SẴN mọi người nói ở đầu kia** trước khi phát ra loa — `capture.py`
  không có và không thể tự tách lại "ai nói" chỉ từ tín hiệu loopback. Đây
  KHÔNG phải hạn chế riêng của việc test bằng video có sẵn — họp thật với
  nhiều người ở đầu kia cũng bị gộp y như vậy, vì app họp đã mix tất cả
  audio người tham gia thành 1 stream output duy nhất trước khi tới
  loopback. Muốn phân biệt người nói phải qua diarization riêng (F12,
  pyannote.audio) phân tích đặc trưng giọng nói (pitch/timbre) trên CHÍNH
  dòng audio đã trộn này — không có nguồn dữ liệu nào khác "sạch hơn" để
  lấy. Xem PROJECT_SPEC.md mục 11 (rủi ro) — mức độ ưu tiên of diarization
  cần xem lại sau phản hồi thật từ người dùng (ban đầu xếp Phase 4, nhưng
  ảnh hưởng UX nhiều hơn dự kiến với họp nhiều người).

## Mục 3 — Mô hình threading

- Audio capture (`stream_loopback_chunks`) + VAD (`VadSegmenter.feed`) chạy
  trên **1 worker thread riêng**, KHÔNG chạy trên Qt main thread — vì đây
  là vòng lặp audio gần như vô hạn, sẽ block UI nếu chạy trên main thread.
- `VadSegmenter` dùng pattern **feed()/flush()** (không phải generator) vì
  lý do trên: caller (worker thread) gọi `feed(chunk)` mỗi khi có chunk
  mới, nhận về list segment vừa chốt (nếu có) rồi tự đẩy qua Qt bằng
  **Signal** (`QThread`/`QObject.Signal`) để cập nhật UI an toàn — không
  bao giờ gọi trực tiếp API thay đổi UI từ worker thread.
- `AIProvider.transcribe()` / `translate()` là **đồng bộ (blocking)** theo
  thiết kế (xem docstring `base_provider.py`) — bắt buộc gọi từ worker
  thread, không gọi trực tiếp từ Qt main thread (slot xử lý signal), nếu
  không UI sẽ đứng trong lúc chờ network.
- Ghi SQLite (`storage/db.py`) cũng nên gọi từ worker thread (cùng thread
  với AIProvider) để main thread chỉ làm việc duy nhất là vẽ UI — SQLite
  connection không thread-safe nếu share giữa nhiều thread mà không cấu
  hình `check_same_thread=False`; ở Phase 1 ta dùng 1 connection riêng cho
  worker thread, không share với main thread.

## Mục 4 — Interface `AIProvider` (`ai/base_provider.py`)

| Method | Trạng thái | Chữ ký |
|---|---|---|
| `transcribe(audio, samplerate)` | 🔒 Đã chốt, đã chạy thật trên Windows | `(np.ndarray mono float32 [-1,1], int) -> TranscriptionResult` |
| `translate(text, source_lang, target_lang, context_text="")` | 🔒 Đã chốt — thêm `context_text` (optional) sau phản hồi test thật lần 3 | `(str, str, str, str) -> str` |
| `suggest_answer(question_text, context_text, user_native_lang)` | 🔒 Đã chốt (Phase 2, F5-F7), đã implement + unit test (mock) — **CHƯA chạy thật**, cần bạn tự test bằng `scripts/test_suggest_answer.py` | `(str, str, str) -> str` |
| `summarize(transcript_text, user_native_lang)` | 🔒 Đã chốt (Phase 3, F10-F11), `decisions`/`action_items` là `list[str]` (đổi từ `str` sau lỗi JSON thật — xem ghi chú dưới) | `(str, str) -> SummaryResult` |

- `TranscriptionResult(text: str, language: str, confidence: float[0,1])`.
- Mọi lỗi (network/auth/rate-limit/parse) từ provider cụ thể phải được bọc
  thành `ProviderError`, không để leak exception thô của SDK ra ngoài.
- Mã ngôn ngữ dùng xuyên suốt dự án: **ISO 639-1** (`en`, `vi`, `zh`).
- `suggest_answer()` trả lời LUÔN bằng `user_native_lang` (để người dùng
  đọc/sửa dễ) — việc dịch ngược sang ngôn ngữ người hỏi (F7 "Dịch & Sẵn
  sàng nói") **dùng lại `translate()`** đã chốt ở Phase 1, KHÔNG cần thêm
  method mới. Prompt cố tình chặn model bịa số liệu/sự kiện cụ thể (rủi ro
  PROJECT_SPEC.md mục 2 #2) — chỗ cần số liệu thật, model phải trả
  placeholder dạng ngoặc vuông viết bằng chính `user_native_lang`.
- ⚠️ **Đã viết lại prompt sau phản hồi test thật** (câu trả lời ban đầu lan
  man, mở đầu kiểu "I appreciate this question..." rồi mới vào ý, né tránh
  cả với kiến thức chung model thừa biết): prompt mới CẤM rõ kiểu mở đầu
  câu giờ, bắt trả lời TRỰC TIẾP với kiến thức chung/kỹ thuật, giới hạn
  1-3 câu ngắn tự nhiên. Đồng thời tổng quát hoá: `question_text` không
  còn bắt buộc là câu hỏi "sạch" — xem ghi chú dưới về nút "Nhờ AI trả lời".
- ⚠️ **`is_question` KHÔNG còn gate việc hiện nút "Nhờ AI trả lời" nữa**
  (quyết định sau phản hồi test thật): heuristic dấu "?" miss nhiều câu hỏi
  thật trong hội thoại nói nhanh/liền mạch không có khoảng nghỉ rõ, VAD có
  thể cắt câu hỏi vắt qua 2 segment. Nút giờ hiện ở MỌI bubble
  (`transcript_bubble.py`), không tốn thêm API call cho pipeline chính
  (suggest_answer() vẫn chỉ gọi khi bấm nút). `is_question` vẫn giữ làm
  chip hiển thị MIỄN PHÍ, không liên quan gì tới việc hiện/ẩn nút nữa.
- ⚠️ **`translate()` cũng đã viết lại prompt** (bản dịch ban đầu bị phản
  hồi là "máy móc, không tự nhiên, đôi khi gây hiểu sai"): đổi khung từ
  "professional translator" (dễ ra văn dịch sát từng từ) sang "đang phiên
  dịch hội thoại nói trực tiếp" + yêu cầu tự nhiên như người bản ngữ nói
  ra miệng — không đổi signature/contract.
- ⚠️ **Thêm `context_text` (optional, mặc định "") vào `translate()`** sau
  phản hồi test thật lần 3: dịch từng câu riêng lẻ không biết mạch chuyện
  trước/sau khiến văn dịch "thô, máy móc" dù đã đúng nghĩa/đúng ngôi. Vài
  câu nói TRƯỚC đưa vào USER message (không phải system), kèm chỉ dẫn rõ
  "chỉ để hiểu bối cảnh, KHÔNG dịch phần này". `pipeline.py` tự track rolling
  buffer (`_TRANSLATE_CONTEXT_SIZE=5`) cho luồng transcript chính;
  `main_window.py` tái dùng `context_text`/`_recent_originals` đã có sẵn
  cho luồng Suggestion Drawer/Ask Question — không cần thêm state mới.
- ⚠️ **Bug lỗi ký tự (mất dấu tiếng Việt) đã xác nhận KHÔNG phải lỗi dữ
  liệu** — đọc trực tiếp `ai_output` trong `meetings.db` thật cho thấy dữ
  liệu lưu ĐÚNG 100% dấu. Lỗi chỉ xảy ra lúc hiển thị trong `QTextEdit`
  (font "Be Vietnam Pro"/"Inter" trong theme.qss không có sẵn trên Windows
  trừ khi tự cài, QSS cascade vào QTextEdit không đáng tin cậy ở nhiều
  phiên bản Qt). Đã sửa: đổi `theme.qss` ưu tiên "Segoe UI" lên đầu (chắc
  chắn có sẵn trên Windows) + set font TRỰC TIẾP bằng code lên đúng các
  QTextEdit (`suggestion_drawer.py`, `ask_question_dialog.py`), không qua
  QSS nữa. **CHƯA verify được trên Windows thật** — cần người dùng xác nhận lại.
- 🔒 **`summarize(transcript_text, user_native_lang) -> SummaryResult`** —
  chốt khi bắt đầu Phase 3 Bước 1. `SummaryResult(overview, decisions,
  action_items)` — 3 field riêng (không phải 1 string lớn) để Phase 3 Bước
  2 (UI report) render được từng mục có heading riêng, không cần parse lại.
  `transcript_text` do CALLER tự ghép từ `MeetingStore.get_segments()` —
  dùng `original_text` (ngôn ngữ gốc), KHÔNG dùng bản đã dịch (tránh cộng
  dồn lỗi dịch vào bản tóm tắt). Dùng `response_format={"type":
  "json_object"}` của Groq để bắt cấu trúc JSON chặt hơn, vẫn tự validate
  đủ 3 field (không tin tưởng tuyệt đối model nhỏ free-tier luôn đúng format).
- ⚠️ **Đã verify bằng dữ liệu thật (chạy Windows + GROQ_API_KEY thật)**:
  Groq Whisper (`response.language` của verbose_json) trả về **tên ngôn
  ngữ đầy đủ** (ví dụ `"English"`), KHÔNG phải mã ISO như chốt ở trên. Đã
  sửa: `GroqProvider.transcribe()` tự chuẩn hoá qua
  `_normalize_language_to_iso()` (bảng tra ~70 ngôn ngữ theo chuẩn Whisper)
  TRƯỚC khi trả `TranscriptionResult` — mọi module khác (pipeline.py,
  translate(), UI) tiếp tục nhận đúng mã ISO, không cần biết chi tiết lệch
  này của API. Nếu sau này đổi sang provider khác (Gemini, local Whisper),
  phải tự kiểm tra lại provider đó có cùng vấn đề không.
- ⚠️ Cũng đã verify: công thức `_estimate_confidence()` cho range hợp lý
  trên dữ liệu thật (0.46–0.93 trên 1 đoạn podcast tiếng Anh rõ ràng), giá
  trị thấp nhất rơi đúng vào 1 từ đơn lẻ bị VAD cắt lẻ — khớp trực giác.
- ⚠️ **`SummaryResult.decisions`/`action_items` đổi từ `str` sang
  `list[str]`** sau lỗi THẬT phát hiện qua `scripts/test_summarize.py`
  (chạy trên Windows, GROQ_API_KEY thật — log lỗi 400 "Failed to generate
  JSON" + dashboard Groq cũng ghi nhận 3 request `json_validate_failed`
  cùng thời điểm): schema cũ yêu cầu 1 string lớn chứa nhiều dòng + tự
  thêm "- " khiến model lệch cú pháp JSON khi nhúng cấu trúc đó vào 1 field
  string (có lần quên cả dấu ngoặc kép mở đầu giá trị "overview"). Schema
  MỚI: mỗi field là JSON ARRAY of strings, mỗi phần tử 1 ý ngắn — dễ encode
  đúng JSON hơn nhiều. `[]` (list rỗng) = model xác nhận THẬT không có
  quyết định/action item, khác hẳn lỗi/thiếu dữ liệu. Parse vẫn CHẤP NHẬN
  CẢ string kiểu cũ (tương thích ngược, xem `_coerce_to_string_list()`
  trong `groq_provider.py`) — chỉ raise `ProviderError` nếu kiểu dữ liệu
  hoàn toàn không đoán được (số, bool, dict...).
- ⚠️ **`translate()` viết lại prompt lần 4** sau phản hồi test thật: vẫn
  còn cảm giác "đúng nghĩa nhưng máy móc" dù đã có `context_text` (lần 3).
  Thêm 4 quy tắc CỤ THỂ thay vì chỉ nói chung "tự nhiên": (1) được reflow/
  gộp/tách câu tự do miễn giữ đủ nghĩa, (2) dịch idiom/filler sang biểu đạt
  tự nhiên tương đương của ngôn ngữ đích (không dịch nguyên cụm), (3) giữ
  đúng register/tone (thân mật giữ thân mật, formal giữ formal), (4) ưu
  tiên cách nói người bản ngữ thật dùng hơn nghĩa từ-điển-chính-xác-nhất.
  Quy tắc giữ đúng ngôi xưng hô (chốt từ lần 2) vẫn là rule KHÔNG bị 4 quy
  tắc mới này ghi đè. **CHƯA verify được chất lượng thật trong sandbox này
  (không có network)** — cần nghe lại bằng tai trên dữ liệu thật.
- ⚠️ **Thêm fallback model tự động theo rate limit (429)** ở
  `GroqProvider` — KHÔNG đổi signature `AIProvider.transcribe()/translate()/
  suggest_answer()/summarize()`, chỉ thêm tham số constructor mới (có giá
  trị mặc định, không phá lời gọi cũ): `stt_fallback_model` (mặc định
  `"whisper-large-v3-turbo"`) và `translate_fallback_model` (mặc định
  `"llama-3.1-8b-instant"`). Model
  CHÍNH đổi ưu tiên độ chính xác: `stt_model` mặc định đổi từ
  `"whisper-large-v3-turbo"` sang **`"whisper-large-v3"`** (đầy đủ — đúng
  phản hồi test "nghe sai/sót từ"). Khi Groq trả 429 ở model chính, tự
  động thử lại NGAY 1 lần với model phụ — README không còn yêu cầu người
  dùng tự sửa code mỗi lần gặp 429 nữa. Đánh đổi (model đầy đủ có thể chậm
  hơn turbo 1 chút) **CHƯA verify được trong sandbox này** — nếu độ trễ
  trên Windows thật tệ rõ rệt, truyền `stt_model="whisper-large-v3-turbo"`
  lúc khởi tạo `GroqProvider` để quay lại model nhanh làm mặc định.

## Mục 5 — Schema SQLite (`storage/db.py`) — 🔒 Chốt mới trong phiên này

Cần thiết để: (a) Phase 1 lưu transcript ngay khi nhận từng segment
(không mất dữ liệu nếu app crash), (b) làm nền cho `summarize()` Phase 3
và lịch sử phiên họp (F13).

```sql
CREATE TABLE IF NOT EXISTS meetings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,      -- ISO 8601, UTC
    ended_at        TEXT,               -- NULL khi đang diễn ra
    user_native_lang TEXT NOT NULL      -- ISO 639-1, ví dụ "vi"
);

CREATE TABLE IF NOT EXISTS segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id),
    created_at      TEXT NOT NULL,      -- ISO 8601, UTC
    original_text   TEXT NOT NULL,
    source_lang     TEXT NOT NULL,      -- ISO 639-1, có thể rỗng nếu provider không xác định
    confidence      REAL NOT NULL,      -- [0.0, 1.0]
    translated_text TEXT,               -- NULL nếu dịch lỗi/chưa dịch
    target_lang     TEXT,
    is_question     INTEGER NOT NULL DEFAULT 0   -- 0/1, dùng cho nút "Nhờ AI trả lời" Phase 2
);

CREATE INDEX IF NOT EXISTS idx_segments_meeting_id ON segments(meeting_id);
```

- **Không lưu audio thô** vào DB (đúng nguyên tắc riêng tư ở PROJECT_SPEC.md
  mục 2) — chỉ lưu text.
- `is_question` tính bằng heuristic đơn giản ở Phase 1 (kết thúc bằng "?"),
  để sẵn cột cho Phase 2 dùng, không cần đổi schema khi làm Phase 2.
- Một phiên họp = 1 dòng `meetings`; mỗi segment transcript = 1 dòng
  `segments`, ghi ngay sau khi có kết quả dịch (hoặc ghi cả khi dịch lỗi —
  `translated_text=NULL` — không được làm mất `original_text` chỉ vì bước
  dịch lỗi).
- 🔒 **Chốt thêm ở Phase 2 Bước 3/3**: bảng `ai_assists` lưu lịch sử AI hỗ
  trợ (gợi ý trả lời + câu tự đặt qua "Tôi muốn hỏi") — xem Mục 9.

## Mục 6 — Worker riêng cho hành động do người dùng kích hoạt (Phase 2)

`suggest_answer()`/`translate()` gọi khi người dùng bấm nút (KHÔNG phải
luồng audio liên tục) chạy qua `OneShotAIWorker` (`app/ui/ai_worker.py`) —
1 `QThread` MỚI cho MỖI lần bấm, tự tạo `GroqProvider` riêng, KHÔNG tái
dùng/gửi việc vào `AudioWorker` đang chạy. Lý do bắt buộc: `AudioWorker.run()`
là vòng lặp imperative không gọi `self.exec()` nên không có Qt event loop
để nhận queued signal/slot — nối thêm việc vào đó sẽ bị "treo" tới khi vòng
lặp audio tự kết thúc (không xảy ra trong lúc đang ghi). Xem chi tiết đầy đủ
ở docstring đầu file `app/ui/ai_worker.py`.

`MainWindow` phải giữ tham chiếu Python tới mọi `OneShotAIWorker` đang chạy
(`self._ai_workers: list`) — Qt sẽ garbage-collect QThread nếu không còn
tham chiếu Python nào giữ nó, kể cả khi thread vẫn đang chạy ngầm, gây crash
ngầm khó debug.

Ngữ cảnh (`context_text`) cho `suggest_answer()` được snapshot NGAY LÚC TẠO
bubble (vài dòng transcript TRƯỚC segment đó), gắn cố định vào
`TranscriptBubble`, KHÔNG tính lại lúc bấm nút — đảm bảo đúng ngữ cảnh dù
người dùng bấm nút muộn sau khi transcript đã trôi xa thêm.

## Mục 7 — Tính năng "Tôi muốn hỏi" (mở rộng sau phản hồi test thật)

Họp không phải 1 chiều — người dùng cũng cần CHỦ ĐỘNG hỏi/đặt vấn đề ngược
lại, không chỉ ngồi đợi bị hỏi. `AskQuestionDialog` (`app/ui/ask_question_dialog.py`)
là chiều NGƯỢC của `SuggestionDrawer`: người dùng tự nhập câu hỏi bằng tiếng
mẹ đẻ (KHÔNG cần AI soạn nội dung — họ đã biết mình muốn hỏi gì), chỉ cần
**tái dùng `translate()`** đã chốt từ Phase 1 để dịch sang ngôn ngữ đối
phương, không cần method mới.

Ngôn ngữ đích mặc định = ngôn ngữ KHÁC tiếng mẹ đẻ người dùng được phát hiện
gần đây nhất trong transcript (`MainWindow._guess_other_party_lang()`,
tracking qua `self._recent_source_langs`), fallback `"en"` nếu chưa có dữ
liệu — người dùng có thể tự đổi qua dropdown nếu đoán sai.

Nút "❓ Tôi muốn hỏi" chỉ bật khi đang có phiên họp (`meeting_started` →
`_on_worker_finished`), cùng quy ước với nút "Kết thúc họp".

## Mục 8 — Bug auto-scroll đã sửa (phát hiện qua test thật)

`QScrollArea.verticalScrollBar().setValue(maximum())` gọi NGAY sau khi
insert widget mới KHÔNG hoạt động đúng khi vùng transcript đã đầy — Qt
chưa kịp tính lại layout/scrollbar range tại đúng thời điểm đó.

⚠️ **Lần sửa đầu (`QTimer.singleShot(0, ...)`) KHÔNG đủ** — người dùng xác
nhận qua test thật vẫn còn bug sau lần sửa đó. 1 timer 0ms vẫn có thể được
xử lý TRƯỚC khi Qt thực sự polish/relayout xong, tuỳ thứ tự hàng đợi event
nội bộ — không có gì đảm bảo "0ms sau" nghĩa là "sau khi layout đã settle".

✅ **Đã sửa đúng bằng cách lắng nghe trực tiếp `QScrollBar.rangeChanged(min, max)`**
— signal CHỈ bắn ra đúng lúc Qt đã tính xong range mới, cấp sẵn `max` mới
làm tham số, không cần đoán/đợi. Kết nối 1 LẦN trong `__init__`
(`_on_scrollbar_range_changed`), set cờ `_pending_autoscroll` ở
`_on_new_event()` (tính TRƯỚC khi insert widget, theo state hiện tại —
"smart-follow": không kéo người dùng xuống nếu họ đang chủ động cuộn lên
đọc lại lịch sử), cờ được tiêu thụ trong handler `rangeChanged` (set lại
False sau khi cuộn). Đã verify chịu được cả trường hợp nhiều bubble đến dồn
cục liên tiếp (test `test_auto_scroll_dung_khi_nhieu_bubble_den_lien_tiep_nhanh`).

## Mục 9 — Bảng `ai_assists` (Phase 2 Bước 3/3) — 🔒 Chốt mới

Lưu lịch sử AI hỗ trợ trong phiên họp — trước đây gợi ý trả lời/câu tự đặt
qua "Tôi muốn hỏi" chỉ hiện tạm trong dialog rồi MẤT khi đóng lại.

```sql
CREATE TABLE IF NOT EXISTS ai_assists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id),
    created_at      TEXT NOT NULL,
    kind            TEXT NOT NULL,      -- 'suggest_answer' | 'ask_question'
    source_text     TEXT NOT NULL,
    ai_output       TEXT,               -- NULL với ask_question (không có bước AI soạn)
    final_text      TEXT,               -- bản dịch CUỐI CÙNG đã đọc lên (không lưu các lần "Tạo lại" bỏ giữa đường)
    target_lang     TEXT
);
```

Ghi vào bảng này xảy ra TRONG action() của `OneShotAIWorker` (cùng thread
gọi `translate()`/`suggest_answer()`) — tự mở 1 `MeetingStore` riêng qua
context manager, tự đóng ngay sau khi ghi (khác `AudioWorker` giữ connection
suốt phiên họp). Lỗi ghi DB (`StorageError`) KHÔNG được làm mất kết quả
dịch đã có cho người dùng — chỉ bỏ qua việc lưu lịch sử, không raise lên UI.

## Mục 10 — Bảng `meeting_reports` + xuất .docx/.pdf (Phase 3 Bước 3/4, F11) — 🔒 Chốt mới

### 10.1 Schema

```sql
CREATE TABLE IF NOT EXISTS meeting_reports (
    meeting_id      INTEGER PRIMARY KEY REFERENCES meetings(id),
    generated_at    TEXT NOT NULL,
    overview        TEXT NOT NULL,
    decisions       TEXT NOT NULL,      -- JSON array of strings
    action_items    TEXT NOT NULL       -- JSON array of {"text": str, "done": bool}
);
```

`meeting_id` làm PRIMARY KEY trực tiếp (không AUTOINCREMENT riêng) — CHỦ Ý
mỗi phiên họp chỉ giữ **đúng 1 báo cáo mới nhất**, không tích lịch sử nhiều
lần "Tạo báo cáo mới" (khác `ai_assists` — Mục 9 — vốn lưu MỌI lần). `decisions`/
`action_items` lưu nguyên JSON (không tách bảng riêng) vì danh sách luôn
ngắn, chỉ đọc/viết nguyên cục, không cần query lọc từng dòng.

### 10.2 Tách contract AI (`SummaryResult`) khỏi tầng lưu trữ (`ReportRecord`)

`AIProvider.summarize()` (Mục 4, 🔒 đã chốt) **KHÔNG đổi** — vẫn trả
`SummaryResult.action_items: list[str]` thô, không biết gì về trạng thái
tick UI. PROJECT_SPEC.md Mục 10.4 yêu cầu action item tick-được — trạng
thái `done` này được thêm ở **TẦNG STORAGE MỚI**
(`storage/db.py`: `ActionItemRecord`, `ReportRecord`), KHÔNG đẩy ngược lên
tầng AI. `ui/report_view.py.set_result()` nhận `ReportRecord`, không còn
nhận `SummaryResult` trực tiếp như Bước 2/4 — `main_window.py` chịu trách
nhiệm gọi `summarize()` rồi `store.save_report()` để có `ReportRecord`
trước khi đưa cho dialog.

### 10.3 Cache báo cáo — tránh gọi lại `summarize()` thừa

`ui/main_window.py._start_report_worker(force_regenerate: bool)`:
- `force_regenerate=False` (mở dialog lần đầu/"Thử lại"): đọc
  `store.get_report()` trước — CHỈ gọi `summarize()` khi chưa có cache.
- `force_regenerate=True` (bấm "🔄 Tạo báo cáo mới"): luôn gọi `summarize()`
  mới, ghi đè (`save_report()` REPLACE), **reset toàn bộ `done=False`** —
  KHÔNG cố map tick cũ sang action item mới (model không deterministic,
  nội dung/thứ tự item lần sau có thể hoàn toàn khác lần trước, map sai sẽ
  khiến người dùng tưởng đã hoàn thành nhầm việc).

### 10.4 Ngoại lệ CÓ Ý về threading khi tick checkbox

`MainWindow._on_action_item_toggled()` gọi `MeetingStore.set_action_item_done()`
**TRỰC TIẾP trên main thread**, KHÔNG qua `OneShotAIWorker` — khác hẳn quy
ước chung ở Mục 3/6 (mọi lệnh AIProvider phải chạy thread riêng vì network
1-4s). Lý do: đây không phải lệnh AI/network, chỉ 1 UPDATE SQLite cực nhỏ
(đọc+viết lại nguyên JSON action_items, không có hàm sửa JSON path sẵn
trong SQLite chuẩn không có extension `json1`), độ trễ thực tế ở mức
micro-giây — tạo thêm 1 QThread cho mỗi lần tick checkbox là chi phí không
cần thiết so với lợi ích.

### 10.5 Xuất .docx/.pdf (`app/report_export.py`)

Module hoàn toàn độc lập Qt/network — xuất TRỰC TIẾP từ `ReportRecord` đã
lưu (đúng kiến trúc PROJECT_SPEC.md Mục 6: L "LLM tổng hợp" → M "Export"),
KHÔNG tự đọc transcript/gọi AI.

- **.docx** (`python-docx`): an toàn về font — Word/LibreOffice tự fallback
  font hệ thống khi render, dấu tiếng Việt không cần xử lý đặc biệt. Vẫn
  set style mặc định "Segoe UI" cho đồng bộ hình ảnh với UI, không bắt
  buộc kỹ thuật.
- **.pdf** (`reportlab`): **PHẢI** tự register font Unicode trước khi vẽ —
  core font tích hợp của reportlab (Helvetica...) không có glyph dấu tiếng
  Việt, sẽ ra PDF lỗi câm (thiếu/sai ký tự, không báo lỗi gì) nếu dùng font
  mặc định. Dùng đúng `C:\Windows\Fonts\segoeui.ttf` — CHÍNH font đã được
  xác nhận đúng dấu tiếng Việt thật trong dự án này (theme.qss/Mục 4), nhất
  quán hơn đóng gói thêm 1 font Unicode khác. App chỉ chạy Windows (yêu cầu
  hệ thống đã chốt từ Phase 0) nên đường dẫn tuyệt đối tới font hệ thống
  Windows AN TOÀN. Nếu không tìm thấy font này → raise `ReportExportError`
  RÕ RÀNG ngay, không lặng lẽ xuất PDF lỗi câm.
- `Paragraph` của reportlab hiểu 1 tập con tag kiểu XML trong text — PHẢI
  escape `&`/`<`/`>` (`html.escape`) trước khi đưa nội dung AI/transcript
  vào, tránh lệch cú pháp markup nội bộ khi nội dung gốc chứa đúng các ký
  tự này.

⚠️ **CHƯA verify được trên Windows thật** (sandbox không có font hệ thống
Windows, không network ra ngoài) — `tests/test_report_export.py` verify
được logic build nội dung + hành vi raise lỗi khi thiếu font (THẬT, đúng
điều kiện sandbox này), và verify pipeline register-font/build PDF chạy
được về kỹ thuật bằng cách tạm trỏ sang font khác (DejaVu Sans) có sẵn
trong sandbox — KHÔNG verify được đúng "Segoe UI" thật trên Windows có hiển
thị đúng dấu hay không, cần tự mở file .docx/.pdf xuất ra THẬT bằng Word/
Acrobat trên Windows để xác nhận lại bằng mắt.

## Mục 11 — Lọc hallucination của Whisper trên im lặng/nhạc nền — 🔒 Chốt mới (phản hồi test thật)

### 11.1 Bối cảnh phát hiện

Test thật trên Windows (Phase 3 Bước 3/4) cho kết quả: bản dịch ban đầu ổn,
nhưng khi audio im lặng/chỉ có nhạc nền, app vẫn hiện ra các câu KHÔNG liên
quan, LẶP LẠI giống nhau ở nhiều mốc thời gian khác nhau trong cùng video
(vd "Hãy subscribe cho kênh Ghiền Mì Gõ...", "Soul Tech Care of the Garden",
"Me and you" → "bạn"), kèm `confidence` thấp (7%–48%) VÀ ngôn ngữ nhận diện
sai be bét (EN bị nhận thành VI, hiện cả JA/KO/JV dù không nói các ngôn ngữ
này). Đây là hành vi **hallucination nổi tiếng của Whisper**: model KHÔNG
có cách trả "rỗng" đúng nghĩa khi audio không có giọng nói thật — vẫn sinh
text + ngôn ngữ nghe tự nhiên (nhưng bịa).

### 11.2 Vì sao KHÔNG dùng `confidence` để lọc (đã cân nhắc và loại)

Công thức `confidence` hiện có (`_estimate_confidence()`, Mục 4) NHÂN
`(1 - no_speech_prob)` vào `exp(avg_logprob)` — gộp 2 nguyên nhân rất khác
nhau: (a) model không chắc TỪ NÀO đúng (có thể CHÍNH ĐÁNG — câu/từ ngắn bị
VAD cắt lẻ, vẫn là giọng nói THẬT, vd "Human." confidence 0.46 — xem comment
gốc ở `groq_provider.py`), và (b) model nghĩ ĐOẠN NÀY không có ai nói. Dùng
1 ngưỡng confidence để lọc sẽ vô tình lọc mất cả câu nói ngắn nhưng thật của
người dùng — KHÔNG chấp nhận được cho 1 app trợ lý cuộc họp (mất đúng lúc
người dùng nói gì đó ngắn, quan trọng).

### 11.3 Giải pháp đã chọn: tách `no_speech_prob` thành tín hiệu riêng

- `app/ai/base_provider.py`: `TranscriptionResult` thêm field
  `no_speech_prob: float = 0.0` (mặc định AN TOÀN — KHÔNG breaking change
  cho provider khác chưa trả được giá trị này).
- `app/ai/groq_provider.py`: hàm MỚI `_estimate_no_speech_prob(segments)` —
  trung bình THÔ `no_speech_prob` (KHÔNG nhân `avg_logprob`), độc lập với
  `_estimate_confidence()`.
- `app/pipeline.py`: hằng số `NO_SPEECH_PROB_DROP_THRESHOLD = 0.6` (ngưỡng
  phổ biến cộng đồng dùng để lọc hallucination Whisper, vd faster-whisper/
  whisper.cpp). Trong `_process_segment()`: nếu `text` không rỗng NHƯNG
  `no_speech_prob >= 0.6` → xử lý GIỐNG nhánh "STT trả text rỗng" đã có sẵn
  (không lưu DB, không hiện bubble, KHÔNG set error — đây là tình huống xảy
  ra BÌNH THƯỜNG mỗi khi có khoảng lặng, không phải lỗi cần cảnh báo).
- **CỐ TÌNH KHÔNG sửa `audio/vad.py`** (đã cân nhắc 1 lớp gate RMS-energy ở
  tầng VAD trước khi gửi sang Whisper, rồi LOẠI BỎ): giá trị tăng thêm nhỏ
  so với việc lọc bằng `no_speech_prob` (vốn đã bắt được đúng tâm case này
  — Whisper tự đánh giá trên audio gốc, đáng tin hơn 1 ngưỡng biên độ thô),
  trong khi tăng thêm rủi ro/độ phức tạp — không đáng đánh đổi cho ích lợi
  biên nhỏ.

### 11.4 Test đã verify (offline, sandbox không gọi network thật được)

`tests/test_groq_provider_offline.py`:
`test_estimate_no_speech_prob_*`, `test_no_speech_prob_la_tin_hieu_chat_hon_confidence_cho_cau_ngan_nhung_thuc`
(case minh hoạ trực tiếp Mục 11.2 — confidence thấp NHƯNG no_speech_prob
thấp → KHÔNG được lọc), `test_transcribe_wire_dung_no_speech_prob_cao_tu_segments`.

`tests/test_pipeline.py`:
`test_pipeline_bo_qua_segment_hallucination_no_speech_prob_cao` (mô phỏng
ĐÚNG case thật đã gặp — text "Hãy subscribe..." + no_speech_prob=0.85 → bị
lọc, không lưu DB, không gọi `translate()`),
`test_pipeline_giu_lai_cau_ngan_du_confidence_thap_neu_no_speech_prob_thap`
(đối chứng — "Human." confidence=0.46 NHƯNG no_speech_prob=0.02 → PHẢI giữ).

⚠️ **CHƯA verify bằng số liệu Groq thật** (sandbox không gọi network được)
— ngưỡng 0.6 là khởi điểm hợp lý theo khuyến nghị phổ biến, CẦN bạn quan
sát lại trên Windows (nếu vẫn lọt rác hoặc ngược lại mất câu thật, chỉnh
`NO_SPEECH_PROB_DROP_THRESHOLD` ở `pipeline.py`, không cần sửa nơi khác).
KHÔNG khẳng định đã sửa hết mọi sai sót nhận diện ngôn ngữ — chỉ sửa đúng
case "ngôn ngữ sai VÌ audio gốc là im lặng/nhạc nền/hallucination"; sai
ngôn ngữ trên audio CÓ giọng nói thật rõ ràng (vd accent nặng, code-switch
giữa câu) vẫn là hạn chế đã biết, chấp nhận ở V1 (PROJECT_SPEC.md Mục 2).

## Mục 12 — Settings UI cho API key (F14) — 🔒 Chốt mới

### 12.1 Vì sao cần (đóng gói .exe phân phối)

`.env` + `GROQ_API_KEY` chỉ phù hợp lúc dev (1 người, chạy từ source). Khi
đóng gói `.exe` cho người khác dùng, KHÔNG thể kèm sẵn key của người phát
triển — mỗi người dùng CUỐI phải tự lấy API key CỦA HỌ
(console.groq.com/keys) và tự chịu trách nhiệm dùng model AI của mình.

### 12.2 `app/config_store.py` — lưu trữ cục bộ

- Vị trí: `%APPDATA%\AIMeetingCompanion\config.json` (đúng quy ước Windows
  cho dữ liệu riêng user, KHÔNG nằm trong thư mục cài đặt — thư mục đó có
  thể chỉ-đọc với user thường).
- Mã hoá: Windows DPAPI (`CryptProtectData`/`CryptUnprotectData` qua
  `ctypes` — KHÔNG cần thêm package, có sẵn trong Windows) khi
  `platform.system() == "Windows"`. **Fallback PLAINTEXT** (nói thật, KHÔNG
  nhận vơ là "đã mã hoá") khi DPAPI không sẵn có — vẫn đáp ứng yêu cầu
  "không hardcode/không kèm .exe phân phối", KHÔNG đáp ứng yêu cầu "mã hoá
  thật". `is_encrypted_storage_available()` cho UI biết đang ở nhánh nào để
  hiển thị ĐÚNG trạng thái cho người dùng (`ui/settings_dialog.py`).
- Đọc lỗi (file hỏng, blob DPAPI không giải mã được cho đúng user/máy hiện
  tại — vd file bị copy sang máy khác) → trả `None`, KHÔNG raise — để
  `GroqProvider.__init__()` tự rơi xuống nguồn key tiếp theo, không làm
  crash app khởi động.

⚠️ **CHƯA verify được DPAPI THẬT trên Windows** (sandbox Linux, không có
`ctypes.windll`) — đã verify (`tests/test_config_store.py`, chạy thật, KHÔNG
cần shim): toàn bộ logic save/load/clear/roundtrip ở NHÁNH FALLBACK, tự
phát hiện đúng platform, không crash khi DPAPI không sẵn có. Cần bạn tự
test trên Windows: lưu key qua Settings → tắt mở app lại → đọc lại đúng key
→ xác nhận `is_encrypted_storage_available()` trả `True` và ghi chú trên
UI hiện đúng "đã mã hoá" (xem README.md mục checklist mới).

### 12.3 Thứ tự ưu tiên đọc key (`GroqProvider.__init__`)

`api_key` tham số (test/code gọi trực tiếp) → `config_store.load_api_key()`
(Settings UI, đường BẮT BUỘC cho .exe phân phối) → biến môi trường
`GROQ_API_KEY` (`.env`, đường DEV hiện tại — VẪN hoạt động bình thường,
KHÔNG bị thay thế). Đây là phần resolution NỘI BỘ trong `__init__`, KHÔNG
đụng tới chữ ký public `transcribe()`/`translate()`/`summarize()` đã 🔒 chốt
ở Mục 4.

### 12.4 `ui/settings_dialog.py`

QLineEdit ẨN (echo mode Password) + nút 👁 bật/tắt hiện rõ (đúng mô tả
PROJECT_SPEC.md Mục 10.4), nút mở `console.groq.com/keys`, nút Lưu/Xoá,
ghi chú rõ trạng thái mã hoá thật/fallback (Mục 12.2). Không gọi AI/network
— mọi action đều local (file I/O cực nhỏ) nên KHÔNG cần `OneShotAIWorker`
(cùng tiền lệ Mục 10.4).

## Mục 13 — Lịch sử phiên họp (F13, Phase 3 Bước 4/4) — 🔒 Chốt mới

### 13.1 Bối cảnh — đây CHÍNH LÀ bug thật đã báo

Trước khi sửa: nút "📄 Xem báo cáo" CHỈ hoạt động với `_current_meeting_id`
của session HIỆN TẠI — đóng app/mở lại, hoặc bắt đầu phiên ghi MỚI, MẤT HẲN
khả năng xem báo cáo/checkbox việc-cần-làm của các phiên CŨ, dù dữ liệu vẫn
còn nguyên trong `meetings.db`. Đây không phải bug riêng — đây CHÍNH LÀ F13
("lịch sử phiên họp") chưa có UI, dữ liệu/method DB (`list_meetings()`) đã
có từ Phase 1.

### 13.2 `storage/db.py` — method mới

- `MeetingSummary` (dataclass MỚI, KHÔNG đổi `list_meetings()` cũ — method
  cũ giữ nguyên tránh phá chỗ gọi cũ nếu có): `id, started_at, ended_at,
  user_native_lang, segment_count, has_report, snippet`.
- `list_meetings_with_counts()`: 1 query LEFT JOIN + GROUP BY (KHÔNG N+1
  query/meeting) — phiên họp CHƯA có segment nào (dừng ngay không nói gì)
  vẫn PHẢI xuất hiện (LEFT JOIN, không INNER JOIN — bug thật đã cố tình
  test riêng: `test_list_meetings_with_counts_meeting_chua_co_segment_van_xuat_hien`).
- `search_meetings(query, snippet_max_len=80)`: LIKE trên `original_text`
  HOẶC `translated_text`, query rỗng → trả y như `list_meetings_with_counts()`
  (để UI dùng 1 method DUY NHẤT cho cả 2 trường hợp). ⚠️ LIKE của SQLite
  KHÔNG tự nhận biết hoa/thường cho ký tự có dấu tiếng Việt (chỉ ASCII) —
  hạn chế đã biết, chấp nhận cho V1 (PROJECT_SPEC.md ưu tiên đơn giản, chưa
  dùng FTS5/unicode61).

### 13.3 `ui/history_dialog.py` (MeetingHistoryDialog, MỚI)

Không-modal (cùng pattern AskQuestionDialog/ReportDialog/SuggestionDrawer).
Ô tìm kiếm + danh sách (mỗi dòng: trạng thái, số đoạn, badge "✅ Đã có báo
cáo" nếu có, snippet khi đang tìm, nút "📄 Xem báo cáo"). Bấm "Xem báo cáo"
emit `report_requested(meeting_id, user_native_lang)` — `MainWindow` tái
dùng NGUYÊN luồng đã có (`_open_report_for_meeting`, xem 13.4), KHÔNG viết
lại logic gọi AI/cache lần 2.

Threading: query DB TRỰC TIẾP trên main thread — ĐÚNG tiền lệ Mục 10.4
(đọc/tìm SQLite cục bộ, không AI/network, không đáng 1 worker riêng).

### 13.4 `ui/main_window.py` — refactor `_on_report_clicked`

Tách thành `_open_report_for_meeting(meeting_id, native_lang)` dùng CHUNG
cho 2 nguồn: (a) phiên ĐANG chạy (`native_lang = self._current_native_lang`)
và (b) phiên CŨ từ Lịch sử (`native_lang` = CHÍNH `user_native_lang` đã lưu
của phiên đó, lấy từ `MeetingSummary` — KHÔNG dùng combo box hiện tại, 2 giá
trị có thể KHÁC nhau). `_start_report_worker()` nay nhận `native_lang` rõ
ràng qua tham số (trước đây đọc qua closure `self._current_native_lang` —
SAI khi mở báo cáo phiên cũ khác ngôn ngữ). `_on_export_requested()` đọc
`dialog._native_lang_for_export` (gắn vào dialog lúc tạo ở
`_open_report_for_meeting`) thay vì `self._current_native_lang`, cùng lý do.

Nút "🕓 Lịch sử" CỐ TÌNH luôn bật (KHÔNG gate theo `_current_meeting_id`
như nút "📄 Xem báo cáo") — đây chính là điểm sửa bug.

## Mục 14 — Tự phục hồi khi đổi default playback device giữa lúc ghi — 🔒 Chốt mới

### 14.1 Bối cảnh + PHẠM VI CHÍNH XÁC (đọc kỹ trước khi coi đây là "đã fix")

Phản hồi test thật: "đổi sang ứng dụng khác/trình duyệt khác để mở thì
không nhận diện được". ⚠️ WASAPI loopback gắn với 1 DEVICE đầu ra, KHÔNG
gắn với 1 app/tab nguồn phát — nếu chỉ đổi tab/app nhưng default playback
device của Windows KHÔNG đổi, fix ở Mục này KHÔNG áp dụng (nguyên nhân thật
sẽ KHÁC, vd âm lượng app mới quá nhỏ). Fix này nhằm ĐÚNG kịch bản: Windows
tự đổi default output device giữa lúc ghi (cắm/rút tai nghe Bluetooth,
chuyển loa, app khác chiếm exclusive mode).

### 14.2 `audio/capture.py`

- `AudioDeviceChangedError(AudioCaptureError)` (exception MỚI) — raise khi
  `_stream_with_soundcard()`/`_stream_with_pyaudiowpatch()` phát hiện
  default output device đã đổi so với lúc mở stream (kiểm tra ĐỊNH KỲ
  ~1 lần/giây, KHÔNG mỗi chunk — tránh overhead gọi OS quá dày).
- `stream_loopback_chunks()`: bắt RIÊNG `AudioDeviceChangedError` và
  `raise` THẲNG lên caller — KHÔNG rơi vào nhánh `except Exception` chung
  (vốn dùng để "thử lib kế tiếp" khi lỗi SETUP). ⚠️ Phát hiện PHỤ trong lúc
  sửa: code GỐC (trước phiên này) có chỗ KHÔNG khớp với docstring của
  riêng nó ("lỗi mid-stream sẽ raise lên caller, không tự đổi lib") — thực
  ra `except Exception` generic bọc CẢ `yield from`, nên 1 lỗi xảy ra GIỮA
  STREAM (không chỉ lúc setup) vẫn bị nuốt và CHUYỂN SANG lib khác âm thầm.
  **CỐ TÌNH KHÔNG sửa phần này** trong phiên này — không phải bug được báo,
  sửa thêm sẽ tăng rủi ro ngoài phạm vi đã verify; chỉ đảm bảo
  `AudioDeviceChangedError` (lỗi MỚI) không bị cuốn vào hành vi đó.

### 14.3 `ui/main_window.py` (`AudioWorker.run()`)

Vòng `while` ngoài bắt riêng `AudioDeviceChangedError`: mở lại
`stream_loopback_chunks()` (tự resolve đúng device mới), KHÔNG kết thúc
phiên họp, KHÔNG emit `error_occurred` (đã tự phục hồi, không nên đánh dấu
phiên "kết thúc có lỗi"). Có giới hạn an toàn
`_MAX_CONSECUTIVE_DEVICE_RETRIES = 5` (đếm số lần gặp LIÊN TIẾP mà KHÔNG
nhận được chunk thật nào ở giữa) — vượt quá thì dừng hẳn, tránh treo thread
vô hạn nếu rơi vào case bệnh lý (lỗi nhận diện sai liên tục).

### 14.4 Test đã verify (mock `soundcard`, KHÔNG cần hardware)

`tests/test_capture.py` (file MỚI): verify ĐÚNG LOGIC phát hiện đổi device
(không đổi → không raise qua nhiều chunk; đổi → raise đúng loại lỗi, đúng
message nêu rõ tên device cũ/mới) và verify `stream_loopback_chunks()`
KHÔNG nuốt `AudioDeviceChangedError` để đổi lib. **CHƯA test** nhánh
`_stream_with_pyaudiowpatch` (mock phức tạp hơn nhiều — callback+queue+dict
device) — chấp nhận rủi ro chưa test nhánh đó.

⚠️ **CHƯA verify được trên Windows thật với audio hardware** (sandbox
không có) — mọi test ở đây mock hoàn toàn `soundcard`, verify được ĐÚNG
LOGIC Python, KHÔNG verify được hành vi WASAPI thật (vd format `speaker.id`
Windows trả về thật có đúng giả định không, có quirk nào khi thật sự
cắm/rút thiết bị không). Cần bạn tự test CHÍNH XÁC theo 2 kịch bản tách
biệt (xem README.md mục checklist mới): (a) đổi tab/app KHÔNG đổi thiết bị
phát; (b) chủ động đổi thiết bị phát (Cài đặt > Âm thanh, hoặc rút/cắm tai
nghe) giữa lúc ghi.

## Mục 15 — `suggest_answer()` trả lời SAI ngôn ngữ với hội thoại CJK — 🔒 Chốt mới (phản hồi test thật, kèm ảnh chụp UI)

### 15.1 Bối cảnh phát hiện — đã loại trừ lỗi wiring TRƯỚC khi sửa prompt

Người dùng gửi 5 ảnh chụp UI thật: với hội thoại tiếng Anh, khung "Gợi ý
trả lời" hiện ĐÚNG bằng tiếng Việt (user_native_lang) như hợp đồng Mục 4 đã
chốt. Nhưng với hội thoại tiếng Trung/Nhật/Hàn, khung gợi ý lại hiện CHÍNH
ngôn ngữ hội thoại đó (Hàn/Nhật/Trung) — người dùng (không biết CJK) không
đọc/sửa được, và bước "Dịch & Sẵn sàng nói" sau đó trở thành dịch CJK→CJK
(vô nghĩa, vì target_lang = source_lang của câu hỏi = ngôn ngữ model đã
lỡ dùng).

Đã kiểm tra TRƯỚC khi đụng vào prompt: `ui/main_window.py._start_suggest_worker()`
luôn truyền đúng `native_lang = self._current_native_lang` (giá trị combo
box, vd "vi") vào `suggest_answer()` — KHÔNG có lỗi wiring/đọc nhầm biến.
Đây là hành vi MODEL: khi `context_text`/`question_text` đưa vào toàn chữ
CJK, model (đặc biệt model fallback nhỏ `llama-3.1-8b-instant` khi 429,
nhưng không loại trừ cả model chính) có xu hướng "mirror" lại ngôn ngữ hội
thoại thay vì tuân thủ chặt câu lệnh "trả lời bằng {native_name}" trong
system prompt — hành vi này KHÔNG xảy ra rõ với hội thoại tiếng Anh.

### 15.2 Giải pháp 2 lớp (`app/ai/groq_provider.py`)

**Lớp 1 — Prompt**: tách `_build_suggest_answer_system_prompt()` (method
riêng, dùng chung lần gọi đầu + lần retry), thêm 1 câu "OUTPUT LANGUAGE
RULE" làm CÂU ĐẦU TIÊN của system prompt (vị trí model "chú ý" nhiều nhất),
lặp lại yêu cầu ngôn ngữ ở Rule 3 và câu cuối (không đổi), thêm 1 dòng
reminder ngay trong user message (gần điểm model bắt đầu sinh token nhất)
— tăng tổng số lần nhắc ngôn ngữ đầu ra từ 2 lên 5 trong 1 lượt gọi.

**Lớp 2 — Lưới an toàn (defense-in-depth)**: `_looks_like_wrong_script(text,
native_lang)` — heuristic dựa trên Unicode range (Han `0x4E00-0x9FFF`, Kana
`0x3040-0x30FF`, Hangul `0xAC00-0xD7A3`), KHÔNG thêm dependency nhận diện
ngôn ngữ đầy đủ (langdetect/fasttext...). Tỉ lệ ký tự "script lạ" (so với
`native_lang`) vượt `_WRONG_SCRIPT_RATIO_THRESHOLD = 0.15` → coi là sai
ngôn ngữ. `native_lang="zh"` vẫn cho phép chữ Hán (script đúng của tiếng
Trung), chỉ Kana/Hangul lẫn vào mới bị coi là lệch. `native_lang` lạ (chưa
có trong `_NATIVE_LANG_OPTIONS`) → luôn trả `False` (không đủ thông tin,
thà bỏ qua còn hơn báo nhầm).

Nếu `_looks_like_wrong_script()` trả `True` ngay sau lần gọi đầu:
`suggest_answer()` tự RETRY ĐÚNG 1 lần (không lặp vô hạn — tốn quota
free-tier vô ích nếu model nhất quyết sai) với: (a) `temperature` hạ từ 0.4
xuống 0.2 (ít "sáng tạo"/lệch hướng hơn, tăng khả năng tuân thủ rule), (b)
user message thêm đoạn "CRITICAL CORRECTION NEEDED" nêu RÕ lần trước bị từ
chối vì sai ngôn ngữ. Nếu lần retry VẪN sai script: vẫn trả về kết quả đó
(không raise `ProviderError`) — người dùng giữa cuộc họp cần CÓ gì để
đọc/sửa hơn là 1 lỗi chặn hẳn, dù không đảm bảo 100% lần retry sẽ đúng.

### 15.3 Test đã verify (mock, KHÔNG cần network)

`tests/test_groq_provider_offline.py`:
`test_looks_like_wrong_script_phat_hien_dung_case_thuc_te_da_gap` (dùng
ĐÚNG các câu tiếng Hàn/Nhật/Trung từ ảnh chụp UI người dùng gửi làm dữ liệu
test + đối chứng không báo nhầm với câu trả lời đúng/câu có vài ký tự CJK
lẫn ngắn), `test_suggest_answer_system_prompt_co_output_language_rule_ro_rang`,
`test_suggest_answer_tu_dong_retry_1_lan_khi_phat_hien_sai_script`,
`test_suggest_answer_khong_retry_khi_lan_dau_da_dung_script` (đối chứng
quan trọng — không tốn thêm 1 lượt gọi nếu lần đầu đã đúng, vd hội thoại
tiếng Anh như trước nay vẫn hoạt động tốt),
`test_suggest_answer_retry_van_sai_script_thi_van_tra_ve_khong_raise`,
`test_suggest_answer_retry_dung_temperature_thap_hon_va_co_nhac_loi_sai`.

⚠️ **CHƯA verify bằng Groq thật trong sandbox này** (không network) — chỉ
verify được ĐÚNG LOGIC retry/heuristic bằng response giả lập. Cần bạn tự
test lại CHÍNH XÁC các đoạn hội thoại Trung/Nhật/Hàn đã báo lỗi (cùng video,
cùng đoạn nếu có thể) để xác nhận: (a) gợi ý có ra ĐÚNG tiếng Việt không kể
cả lần đầu (không cần tới retry), (b) nếu vẫn lệch, báo lại NGUYÊN VĂN câu
trả lời sai để tinh chỉnh `_WRONG_SCRIPT_RATIO_THRESHOLD` hoặc viết lại
tiếp prompt (file `app/ai/groq_provider.py`, không cần sửa nơi khác).

## Mục 16 — Delay 6-9s khi chuyển ngôn ngữ/tab giữa lúc ghi — 🔒 Chốt mới (phản hồi test thật)

### 16.1 Phân tích nguyên nhân — KHÔNG phải lỗi "model chậm" như nghi vấn ban đầu

Người dùng hỏi đúng câu hỏi cần trả lời rõ: "có phải do model không?" — câu
trả lời: **không chỉ vậy, và không phải nguyên nhân chính.** 2 nguồn cộng
dồn:

1. **Độ trễ network vốn có** (đã ghi nhận từ PROJECT_SPEC.md Mục 2 #4 ngay
   từ đầu dự án): mỗi segment cần 1-2 lệnh gọi cloud TUẦN TỰ, đồng bộ
   (`transcribe()` rồi `translate()` nếu khác ngôn ngữ đích) — mỗi lệnh
   ~1-4s tuỳ tải Groq lúc đó, CỘNG DỒN tuần tự (không chạy song song, xem
   CONTRACTS.md Mục 3 — thiết kế CÓ CHỦ Ý để tránh phức tạp threading).
   Đây là giới hạn ĐÃ BIẾT của free-tier cloud pipeline, không có lever
   miễn phí nào xoá hẳn được (xem Vòng 5, quyết định không tối ưu thêm).

2. **🔒 Nguyên nhân CHÍNH gây ĐÚNG TRIỆU CHỨNG "delay nặng hơn rõ rệt khi
   chuyển ngôn ngữ/tab"** (mới xác định trong phiên này): `audio/vad.py`
   (`VadSegmenter`) cắt segment theo khoảng lặng (`silence_ms`), nhưng khi
   chuyển tab/nguồn phát mà KHÔNG có khoảng lặng thật giữa 2 đoạn audio
   (rất phổ biến — video/tab mới phát tiếp ngay, không dừng), VAD KHÔNG cắt
   được theo silence — phải đợi tới TRẦN `max_segment_ms` (cũ: 15000ms =
   15 GIÂY) mới ép cắt. Segment 15 giây dài hơn NHIỀU lần segment bình
   thường (~1-3 giây) — lệnh `transcribe()` cho 1 file audio dài hơn mất
   nhiều thời gian xử lý/upload hơn ĐÁNG KỂ so với segment ngắn, CỘNG DỒN
   với `translate()` ngay sau đó → khớp đúng con số 6-9s người dùng quan
   sát được (không phải ngẫu nhiên — đây CHÍNH LÀ lúc model phải xử lý 1
   cục audio bất thường dài, đúng vào thời điểm chuyển ngôn ngữ/tab vì đó
   là lúc silence-based cutting thất bại).

   ⚠️ Phát hiện PHỤ liên quan (KHÔNG sửa trong phiên này, ghi nhận để biết):
   `AudioWorker.run()` (`ui/main_window.py`) đọc `stream_loopback_chunks()`
   và xử lý AI (`pipeline.feed_chunk()`) TRÊN CÙNG 1 vòng lặp/thread, tuần
   tự — trong lúc 1 segment đang chờ network, generator audio KHÔNG được
   đọc tiếp (đây là thiết kế Phase 1, CONTRACTS.md Mục 3, đã qua nhiều vòng
   test mà không bị báo lỗi). Việc này CÓ THỂ khuếch đại độ trễ thêm nếu
   nhiều segment dồn cục đúng lúc audio bị block, nhưng CHƯA đủ chứng cứ
   để khẳng định đây là nguyên nhân CHÍNH (khác với #2 ở trên, đã có suy
   luận trực tiếp khớp với số liệu 6-9s người dùng báo) — **CỐ TÌNH KHÔNG
   tách audio capture ra 1 thread riêng trong phiên này**: đây là thay đổi
   kiến trúc lớn hơn (cần thêm queue/buffer giữa 2 thread), KHÔNG thể
   verify trong sandbox này (không có audio hardware), và động vào đúng
   phần code đã ổn định qua nhiều vòng test thật của bạn — rủi ro thêm bug
   MỚI không tương xứng với lợi ích chưa chắc chắn. Nếu sau khi hạ
   `max_segment_ms` (mục 16.2) vẫn còn delay rõ rệt ngoài mong đợi, đây sẽ
   là hướng cần làm TIẾP (tách thread, có kiểm soát rủi ro kỹ hơn).

### 16.2 Giải pháp đã áp dụng (`app/audio/vad.py`)

Giảm default `max_segment_ms` từ **15000ms → 8000ms** — giảm gần 1 nửa độ
trễ TỆ NHẤT khi rơi vào case ép-cắt-do-không-có-khoảng-lặng. Đánh đổi: 1
câu nói thật liên tục >8s (hiếm hơn nhiều so với hội thoại thông thường có
ngắt nghỉ) sẽ bị cắt thành 2 bubble — hợp lý cho 1 app trợ lý họp cần phản
hồi gần thời gian thực hơn là giữ nguyên 1 câu dài cho đẹp ngữ pháp.
`silence_ms`/`min_speech_ms`/`padding_ms`/`aggressiveness` giữ nguyên —
KHÔNG đụng tới các tham số khác đã qua nhiều vòng tinh chỉnh test thật
trước đó (Vòng 1, silence_ms 600→350ms).

### 16.3 Test đã verify

`tests/test_vad.py`: `test_default_max_segment_ms_la_8000` (xác nhận default
mới). `test_max_segment_ms_ep_cat_khi_noi_lien_tuc_khong_ngung` (test cũ,
vẫn pass — dùng `max_segment_ms` truyền RÕ qua tham số, không phụ thuộc
default, nên không bị ảnh hưởng bởi thay đổi này).

⚠️ **CHƯA verify được bằng audio/network thật trong sandbox này** (không
audio hardware, không network ra ngoài) — chỉ verify được ĐÚNG LOGIC cắt
segment theo trần mới. Cần bạn tự test LẠI ĐÚNG kịch bản đã báo (chuyển từ
tab/ngôn ngữ A sang B giữa lúc ghi) để xác nhận độ trễ có giảm rõ rệt
không; nếu vẫn ngoài mong đợi, báo lại + xem xét hướng tách audio capture
thread (mục 16.1, phát hiện phụ) cho phiên sau. Nếu ngược lại thấy câu nói
dài bị cắt cụt PHIỀN hơn lợi ích giảm delay mang lại, tăng số 8000 này lên
(file `app/audio/vad.py`, tham số `max_segment_ms`, KHÔNG cần sửa nơi khác).


---

## Mục 17 — 🔒 Multi-provider AI: Groq/OpenAI/Gemini (MỚI)

### 17.1 Bối cảnh/yêu cầu

Trước đây app CHỈ chạy được với 1 API key Groq duy nhất (hardcode ngầm
trong `GroqProvider`). Khi đóng gói `.exe` phân phối cho nhiều người dùng,
một số người có sẵn API key của OpenAI (đã trả phí ChatGPT/API) hoặc
Gemini (free tier Google) thay vì Groq — yêu cầu: dán key của BẤT KỲ
provider nào trong 3 provider trên vào ⚙️ Cài đặt, app chạy được NGAY,
không cần biết khái niệm AIProvider/base_url.

### 17.2 Kiến trúc

```
app/ai/
  base_provider.py        🔒 (không đổi) — interface AIProvider 4 method
  openai_compat_base.py    MỚI — translate()/suggest_answer()/summarize()
                           DÙNG CHUNG cho mọi provider đi qua SDK `openai`
                           (Groq/OpenAI/Gemini-qua-lớp-tương-thích).
  whisper_utils.py         MỚI — parse response Whisper verbose_json
                           (segments/avg_logprob/no_speech_prob) DÙNG
                           CHUNG cho Groq + OpenAI (cùng model gốc Whisper).
  groq_provider.py         GroqProvider(OpenAICompatProvider) — transcribe()
                           riêng (whisper-large-v3, có fallback turbo khi 429).
  openai_provider.py       MỚI — OpenAIProvider(OpenAICompatProvider) —
                           transcribe() riêng (whisper-1, KHÔNG fallback).
  gemini_provider.py       MỚI — GeminiProvider(OpenAICompatProvider) —
                           transcribe() RIÊNG HOÀN TOÀN (REST generateContent
                           qua httpx, KHÔNG qua SDK openai — xem 17.3).
  provider_factory.py      MỚI — create_provider() / display_name(): 1 điểm
                           DUY NHẤT quyết định provider nào được tạo ra.
```

`ui/main_window.py`: 5 chỗ `GroqProvider()` cũ → `create_provider()` (đọc
provider "đang dùng" qua `config_store.get_active_provider()`, mặc định
"groq" — tương thích ngược 100% với người dùng cũ).

### 17.3 ⚠️ Quyết định kiến trúc quan trọng nhất: Gemini KHÔNG có "Whisper"

Đã xác nhận qua tài liệu chính thức Google (05-06/2026): lớp tương thích
OpenAI của Gemini (`generativelanguage.googleapis.com/v1beta/openai/`) chỉ
phủ chat completions/embeddings/image generation — **KHÔNG phủ
`audio.transcriptions`**. Gemini xử lý audio qua `generateContent` đa
phương thức (gửi audio như 1 phần nội dung kèm prompt), không có
`segments`/`avg_logprob`/`no_speech_prob` kiểu Whisper.

Hệ quả: `GeminiProvider.transcribe()` viết HOÀN TOÀN riêng — gọi REST
`generateContent` qua `httpx`, yêu cầu model trả JSON có cấu trúc
(`responseSchema`) gồm transcript + ngôn ngữ + cờ tự-báo-cáo
`is_silence_or_nonspeech`. Hệ quả tiếp:
- `confidence` của Gemini là **SỐ CỐ ĐỊNH 0.75 (placeholder, KHÔNG đo
  được)** — nói thật, không nhận vơ (cùng tinh thần "mã hoá" ở
  `config_store.py`). Gemini không expose avg_logprob theo nghĩa tương
  đương Whisper qua đường này.
- `no_speech_prob` của Gemini là **tín hiệu NHỊ PHÂN** (0.0 hoặc 1.0, từ
  cờ tự-báo-cáo của model) — KHÁC no_speech_prob LIÊN TỤC thật của
  Whisper (Groq/OpenAI). Vẫn hoạt động đúng với ngưỡng lọc
  `NO_SPEECH_PROB_DROP_THRESHOLD=0.6` ở `pipeline.py` vì 0.0/1.0 đều nằm
  rõ về 1 phía ngưỡng, nhưng KÉM MỊN hơn.
- Rate limit (429) ở `transcribe()` Gemini KHÔNG có model dự phòng để tự
  fallback (khác Groq/OpenAI có model rẻ hơn) — raise thẳng ProviderError.

⚠️ **CHƯA verify được bằng audio Gemini thật trong sandbox này** (không
network) — cần bạn tự test lại đúng kịch bản đã dùng để verify Groq
(đoạn im lặng/nhạc nền, Mục 11) để đối chứng độ chính xác của tín hiệu
tự-báo-cáo này.

### 17.4 `config_store.py` — lưu nhiều key độc lập

Định dạng file MỚI (`{"active_provider": ..., "providers": {"groq": {...},
"openai": {...}, "gemini": {...}}}`) thay cho định dạng cũ (flat, chỉ
Groq). **Tương thích ngược BẮT BUỘC**: `load_api_key(provider="groq",
base_dir=None)` vẫn đọc được file ĐỊNH DẠNG CŨ của người dùng Vòng 6 (coi
là "chỉ có Groq"); `save_api_key()` tự "migrate-on-write" sang định dạng
mới, KHÔNG làm mất key Groq đã lưu trước đó. Mọi hàm cũ (`save_api_key`,
`load_api_key`, `clear_api_key`) gọi KHÔNG truyền `provider=` vẫn hoạt
động NGUYÊN VẸN (ngầm định "groq") — `tests/test_config_store.py` (12
test CŨ) PASS KHÔNG cần sửa 1 dòng.

Thêm: `get_active_provider()`, `set_active_provider()`,
`list_configured_providers()` — dùng ở `ui/settings_dialog.py` (dropdown
chọn provider) và `provider_factory.create_provider()`.

### 17.5 Refactor `groq_provider.py` — KHÔNG đổi hành vi

`translate()`/`suggest_answer()`/`summarize()` (và mọi helper liên quan:
`_language_name`, `_looks_like_wrong_script`, `_call_with_rate_limit_fallback`,
`_auth_error_hint`, `_coerce_to_string_list`) di chuyển (move, KHÔNG
rewrite) sang `openai_compat_base.py`. Phần parse Whisper
(`_encode_wav_bytes`, `_estimate_confidence`, `_estimate_no_speech_prob`,
`_normalize_language_to_iso`) di chuyển sang `whisper_utils.py`.
`groq_provider.py` import lại (re-export) mọi tên này — toàn bộ 39 test
trong `tests/test_groq_provider_offline.py` (test cũ, có TỪ TRƯỚC đợt
refactor này) **PASS 100% KHÔNG sửa 1 dòng nào trong file test** (đã tự
chạy lại xác nhận trong sandbox này bằng shim `openai`/`httpx` nội bộ,
KHÔNG gọi network thật — xem `/home/claude/shims` lúc làm, KHÔNG đóng gói
vào bản phân phối).

⚠️ Rủi ro đã gặp + tự sửa trong lúc làm: lúc viết lại `translate()` ở
`openai_compat_base.py`, ban đầu đã PARAPHRASE nhầm (không copy verbatim)
đoạn prompt gốc — bị `test_translate_prompt_yeu_cau_giu_dung_ngoi_xung_ho`
bắt được ngay (assert thiếu cụm "never shift" trong prompt). Đã sửa lại
ĐÚNG verbatim từ bản gốc trước khi refactor. Đây là lý do **BẮT BUỘC** phải
tự chạy lại toàn bộ test cũ sau bất kỳ refactor "di chuyển code" nào,
không chỉ tin code "trông giống" là đủ.

### 17.6 Test mới

`tests/test_openai_provider_offline.py` (8 test), `tests/test_gemini_provider_offline.py`
(7 test, monkeypatch `provider._post_generate_content()` thay vì giả lập
`httpx.Response` đầy đủ), `tests/test_provider_factory_offline.py` (10
test) — đều PASS trong sandbox này (shim nội bộ, không network thật).
`tests/test_config_store.py` thêm 12 test multi-provider MỚI (tổng 24,
giữ nguyên 12 test cũ).

⚠️ **Đã sửa 1 regression PHÁT HIỆN ĐƯỢC nhờ rà soát kỹ trước khi giao**:
`tests/test_ui_smoke.py` (cần PySide6, KHÔNG tự chạy được trong sandbox
này) có 27 chỗ monkeypatch `mw_module.GroqProvider` (tên import cũ trong
`main_window.py`) — sau khi đổi `main_window.py` sang `create_provider()`,
tên `GroqProvider` không còn tồn tại trong namespace đó, mọi chỗ
monkeypatch này sẽ AttributeError. Đã sed toàn bộ 27 chỗ thành
`mw_module.create_provider` (các fake provider class vẫn nhận `*args,
**kwargs` ở `__init__`, gọi `create_provider()` 0 tham số tương đương
gọi thẳng class đó — hành vi giữ nguyên) — **CHƯA tự chạy lại được file
này trong sandbox (thiếu PySide6/môi trường đồ hoạ)**, cần bạn tự chạy
`python tests/test_ui_smoke.py` trên máy có PySide6 để xác nhận lần cuối.

### 17.7 ⚠️ Việc CHƯA làm / cần bạn tự xác nhận trước khi launch

1. **Chưa gọi API OpenAI/Gemini thật** — toàn bộ trên đã verify ĐÚNG LOGIC
   wrapping/parsing (qua mock/shim), CHƯA verify shape response THẬT của
   `whisper-1` (OpenAI) và `generateContent` (Gemini) khớp 100% với giả
   định trong code. Làm TRƯỚC khi launch: tự lấy 1 key OpenAI + 1 key
   Gemini thật, đổi provider trong Settings, ghi thử 1 đoạn ngắn, đối
   chiếu transcript/dịch/gợi ý trả lời có hợp lý không — giống quy trình
   đã làm để verify Groq lúc trước (Mục 4/11).
2. **Tên model** (`gpt-5-mini`/`gpt-5-nano`, `gemini-2.5-flash`/
   `gemini-2.0-flash`) là lựa chọn dựa trên thông tin có tại thời điểm
   làm (06/2026) — đổi RẤT NHANH, kiểm tra lại trước khi launch + định kỳ
   sau đó (cùng cảnh báo PROJECT_SPEC.md mục 8 đã có với Groq).
3. **Giá/free-tier** của OpenAI (trả phí, không free như Groq) và Gemini
   (free tier giới hạn, do Google tự quy định) đã ghi rõ trong Settings UI
   — nhưng SỐ LIỆU CỤ THỂ (quota/giá) KHÔNG hardcode trong app (đổi liên
   tục) — `ui/settings_dialog.py` chỉ nói ĐỊNH TÍNH ("trả phí"/"có free
   tier"), người dùng tự xem trang chính thức của từng provider.
4. **DPAPI multi-key**: mỗi key của mỗi provider mã hoá ĐỘC LẬP (xem
   `config_store.py`) — chưa tự test trên Windows thật rằng cả 3 key cùng
   tồn tại + giải mã đúng đồng thời (chỉ verify được nhánh fallback
   plaintext trong sandbox Linux này, như mọi lần trước với DPAPI).
