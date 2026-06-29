# AI Meeting Companion

> **Cảnh báo sử dụng**: Công cụ này hỗ trợ cá nhân ghi chú & chuẩn bị, người dùng
> cần tuân thủ quy định nội bộ công ty và pháp luật về ghi âm tại nơi làm việc.

Trạng thái hiện tại: **Phase 0 + Phase 1 + Phase 2 + Phase 3 (đủ 4/4 bước, F10+F11+F13) hoàn thiện — Vòng 6 đã được bạn test thật và XÁC NHẬN PASS cả 4 checkpoint.** Vòng 7: đã sửa 2 vấn đề bạn báo sau khi dùng thật (gợi ý trả lời sai ngôn ngữ với hội thoại Trung/Nhật/Hàn + delay 6-9s khi chuyển ngôn ngữ/tab) — ⚠️ **CHƯA được bạn retest/xác nhận pass** (xem mục "Vòng 7" để biết cách retest). Vòng 8 (MỚI NHẤT, dưới đây): theo yêu cầu của bạn, đã thêm hỗ trợ multi-provider AI (Groq/OpenAI/Gemini — dán key của BẤT KỲ provider nào vào ⚙️ Cài đặt là dùng được, không chỉ Groq) TRƯỚC khi trả lời câu hỏi "có cần làm Phase 4 không" — xem mục "Vòng 8" + phần cuối README để biết đề xuất thứ tự Phase 4 còn lại.

## Vòng 8 — Multi-provider AI: Groq/OpenAI/Gemini (CONTRACTS.md Mục 17, MỚI)

⚠️ **Làm TRƯỚC khi trả lời câu hỏi Phase 4** theo đúng yêu cầu của bạn (đọc
toàn bộ project trước, rồi mới đề xuất Phase 4 — xem cuối README). Đây là
mở rộng F14 (Settings UI nhập API key, Vòng 6), KHÔNG phải 1 phase mới
trong PROJECT_SPEC.md.

**Vấn đề trước Vòng 8**: app chỉ chạy được với API key Groq — nếu người
dùng cuối chỉ có key OpenAI (đã trả phí ChatGPT/API từ trước) hoặc Gemini
(free tier Google), họ KHÔNG dùng được app.

**Đã làm**: thêm dropdown chọn provider trong ⚙️ Cài đặt (Groq/OpenAI/
Gemini), mỗi provider lưu key riêng (đổi qua lại không mất key đã nhập của
provider khác), `provider_factory.create_provider()` là 1 điểm DUY NHẤT
quyết định provider nào chạy. Refactor `groq_provider.py` thành 2 module
dùng chung (`openai_compat_base.py` cho phần dịch/gợi ý/tóm tắt,
`whisper_utils.py` cho phần parse STT) để KHÔNG sao chép code 3 lần cho 3
provider — xem CONTRACTS.md Mục 17 để biết đầy đủ chi tiết kiến trúc +
khác biệt quan trọng của Gemini (KHÔNG có API kiểu Whisper cho STT, xử lý
riêng qua REST `generateContent`).

⚠️ **CHƯA gọi API OpenAI/Gemini thật trong sandbox này** (không network) —
mọi thứ trên đã verify ĐÚNG LOGIC qua 25 test mới (offline/mock, xem
CONTRACTS.md Mục 17.6), nhưng CHƯA xác nhận shape response thật của
`whisper-1`/`generateContent` khớp 100% giả định trong code. **Trước khi
coi Vòng 8 "xong"**, cần bạn tự test với key OpenAI + key Gemini THẬT (đổi
provider trong Settings, ghi thử 1 đoạn ngắn mỗi provider, đối chiếu
transcript/dịch/gợi ý có hợp lý không) — đúng quy trình đã làm để verify
Groq lúc trước.

### Retest cần làm cho Vòng 8 (checklist)

- [ ] Mở ⚙️ Cài đặt — đổi qua "OpenAI", dán key OpenAI thật, bấm Lưu — báo
      đúng trạng thái mã hoá/đã lưu, KHÔNG mất key Groq cũ khi đổi lại.
- [ ] Ghi 1 đoạn ngắn với provider=OpenAI đang chọn — transcript/dịch/gợi
      ý trả lời ra đúng, không lỗi.
- [ ] Tương tự với "Gemini" — đặc biệt thử 1 đoạn IM LẶNG/nhạc nền để xem
      `is_silence_or_nonspeech` có lọc đúng không (so với hành vi
      `no_speech_prob` của Groq đã biết).
- [ ] Đổi lại "Groq" — xác nhận app vẫn chạy như Vòng 6/7 (không có
      regression do refactor `groq_provider.py`).
- [ ] (Nếu có PySide6 sẵn) chạy lại `python tests/test_ui_smoke.py` —
      file này KHÔNG tự chạy được trong sandbox lúc làm Vòng 8 (thiếu
      PySide6), đã sửa 27 chỗ monkeypatch theo refactor nhưng CHƯA tự xác
      nhận lại bằng cách chạy thật.

## Vòng 7 — Sửa 2 vấn đề sau khi Vòng 6 đã pass (CONTRACTS.md Mục 15-16)

### 1. "Nhờ AI trả lời" gợi ý SAI ngôn ngữ khi hội thoại là Trung/Nhật/Hàn (CONTRACTS.md Mục 15)

**Bug đã xác nhận qua ảnh chụp UI thật**: với hội thoại tiếng Anh, khung
gợi ý hiện ĐÚNG tiếng Việt (ngôn ngữ mẹ đẻ bạn chọn) như thiết kế — nhưng
với hội thoại tiếng Trung/Nhật/Hàn, khung gợi ý lại hiện CHÍNH ngôn ngữ hội
thoại đó, bạn không đọc được để sửa, và bước dịch ngược sau đó thành dịch
CJK→CJK vô nghĩa. Đã xác nhận KHÔNG phải lỗi code đọc nhầm ngôn ngữ mẹ đẻ
(wiring đúng) — đây là model không tuân thủ chặt prompt khi ngữ cảnh đưa
vào toàn chữ CJK.

**Đã sửa 2 lớp**: (1) viết lại prompt, nhắc RÕ "luôn trả lời bằng ngôn ngữ
mẹ đẻ, bất kể hội thoại là ngôn ngữ gì" ngay từ câu ĐẦU TIÊN + lặp lại
nhiều lần; (2) thêm lưới an toàn tự kiểm tra kết quả trả về, nếu phát hiện
vẫn lệch ngôn ngữ thì TỰ ĐỘNG thử lại đúng 1 lần với yêu cầu mạnh hơn —
hoàn toàn tự động, bạn không cần làm gì thêm.

**Tự test lại**: mở lại đúng các video tiếng Trung/Nhật/Hàn đã gặp lỗi
trước đây, bấm "Nhờ AI trả lời" — khung gợi ý PHẢI hiện tiếng Việt (đọc
được, sửa được), sau đó bấm "Dịch & Sẵn sàng nói" PHẢI ra đúng tiếng
Trung/Nhật/Hàn tương ứng (không phải dịch CJK→CJK nữa). Test lại cả hội
thoại tiếng Anh để xác nhận KHÔNG bị ảnh hưởng (vẫn hoạt động như trước).

⚠️ Lưới an toàn ở bước (2) chỉ là heuristic (nhận diện script chữ, không
phải nhận diện ngôn ngữ đầy đủ) và retry tối đa 1 lần — nếu vẫn gặp lệch
ngôn ngữ sau khi retry, báo lại NGUYÊN VĂN câu trả lời sai để tinh chỉnh
tiếp (xem CONTRACTS.md Mục 15.3).

### 2. Delay 6-9s khi chuyển ngôn ngữ/tab giữa lúc ghi (CONTRACTS.md Mục 16)

**Trả lời thẳng câu hỏi bạn đặt ra ("có phải do model không?")**: không
hẳn, và không phải nguyên nhân chính. Có 2 nguồn cộng dồn: (a) độ trễ
network vốn có của pipeline free-tier (mỗi câu cần 1-2 lệnh gọi cloud tuần
tự, ~1-4s mỗi lệnh — giới hạn đã biết từ đầu dự án, không có cách miễn phí
xoá hẳn); (b) **nguyên nhân chính khớp đúng con số 6-9s bạn quan sát**: khi
chuyển tab/ngôn ngữ mà KHÔNG có khoảng lặng thật giữa 2 đoạn audio (rất
phổ biến — video mới phát tiếp ngay), bộ phận cắt câu (VAD) không cắt được
theo khoảng lặng như bình thường, phải đợi tới TRẦN tối đa (cũ: 15 giây)
mới ép cắt — 1 đoạn audio 15 giây mất nhiều thời gian xử lý hơn ĐÁNG KỂ so
với câu ngắn bình thường, đúng vào lúc bạn đang chờ thấy nội dung mới.

**Đã sửa**: hạ trần đó từ 15 giây xuống 8 giây — giảm gần 1 nửa độ trễ TỆ
NHẤT của đúng trường hợp này. Đánh đổi: nếu 1 người nói liên tục không
ngừng nghỉ >8 giây (hiếm hơn nhiều so với hội thoại có ngắt nghỉ bình
thường), câu đó sẽ bị tách thành 2 bubble thay vì 1 — hợp lý cho 1 app cần
phản hồi gần thời gian thực.

**Tự test lại**: lặp lại đúng kịch bản đã gặp (mở video A, để 1 lúc, chuyển
ngay sang video/tab B ngôn ngữ khác KHÔNG dừng/tắt tiếng A trước) — độ trễ
ngay sau lúc chuyển PHẢI giảm rõ rệt so với trước (không còn ở mức 6-9s).

⚠️ Nếu retest vẫn thấy delay rõ rệt ngoài mong đợi: rất có thể cần thêm 1
bước nữa (tách việc thu âm ra 1 luồng xử lý riêng, không bị giữ lại trong
lúc đợi AI xử lý câu trước) — đây là thay đổi kiến trúc lớn hơn, CHƯA làm
trong phiên này (xem CONTRACTS.md Mục 16.1 "phát hiện phụ" để biết lý do
cụ thể), cần bạn xác nhận mức độ delay còn lại trước khi quyết định có làm
tiếp không. Nếu ngược lại thấy câu nói dài bị cắt cụt PHIỀN hơn lợi ích
giảm delay, báo lại để tăng số 8 giây này lên một chút.

---

**Checkpoint cần xác nhận trước khi tiếp tục Phase 4**:
1. Mục 1 — gợi ý trả lời ra ĐÚNG tiếng mẹ đẻ với MỌI ngôn ngữ hội thoại (Anh/Trung/Nhật/Hàn), không chỉ tiếng Anh như trước.
2. Mục 2 — delay khi chuyển ngôn ngữ/tab giảm rõ rệt so với mức 6-9s đã báo.

## Vòng 6 — Retest sau khi sửa 4 vấn đề + Bước 4/4 (F13) + Settings API key (F14)

Bạn đã test Bước 3/4 thật trên Windows và báo lại nhiều vấn đề. Tóm tắt đã
sửa gì + cách tự retest từng vấn đề (chi tiết kỹ thuật đầy đủ ở
CONTRACTS.md Mục 11-14):

### 1. Rác/hallucination khi im lặng + sai ngôn ngữ (CONTRACTS.md Mục 11)

**Đã sửa**: lọc dựa trên `no_speech_prob` (tín hiệu RIÊNG, KHÁC độ tin cậy
hiện có) — đoạn audio Whisper tự đánh giá "rất có thể không có ai nói" sẽ
bị bỏ qua hoàn toàn (không hiện bubble, không lưu DB), **không** dùng độ
tin cậy chung để lọc (tránh lọc nhầm câu ngắn nhưng thật).

**Tự test lại**: mở video có đoạn im lặng/nhạc nền dài (không lời) — đoạn
đó phải KHÔNG còn hiện bubble rác nào nữa. Mở lại đúng đoạn hội thoại
ngắn/giọng nói thật bị cắt ngắn trước đây (vd 1 từ đơn) — PHẢI vẫn hiện
bình thường (không bị lọc nhầm). Nếu vẫn còn lọt rác HOẶC ngược lại mất câu
thật, báo lại — chỉnh 1 dòng `NO_SPEECH_PROB_DROP_THRESHOLD` trong
`app/pipeline.py` (mặc định 0.6), không cần sửa code nơi khác.

⚠️ Không kỳ vọng hết SẠCH mọi trường hợp sai ngôn ngữ — chỉ sửa đúng case
"sai VÌ audio gốc là im lặng/nhạc nền". Giọng nói thật rõ ràng mà vẫn bị
nhận sai ngôn ngữ (accent nặng, nói xen 2 ngôn ngữ trong 1 câu) là hạn chế
khác, chưa có cách sửa triệt để ở V1.

### 2. Không nhận diện được khi đổi ứng dụng/trình duyệt (CONTRACTS.md Mục 14)

**Đã sửa MỘT PHẦN, cần bạn tự phân biệt rõ 2 kịch bản khi retest** — quan
trọng:
- **(a) Đổi tab/app phát nhưng KHÔNG đổi thiết bị phát ra loa** (vẫn cùng
  loa/tai nghe): loopback WASAPI gắn với THIẾT BỊ, không gắn với app/tab —
  fix này KHÔNG áp dụng cho case này. Nếu vẫn lỗi ở case (a), đây là lỗi
  KHÁC (báo lại kèm rõ: app/tab cụ thể nào, có đang để âm lượng quá nhỏ
  không), tôi chưa sửa được trong vòng này.
- **(b) Chủ động đổi thiết bị phát** (Cài đặt Windows > Âm thanh > đổi
  output, hoặc rút/cắm tai nghe Bluetooth) giữa lúc đang ghi: app giờ tự
  phát hiện và mở lại đúng thiết bị mới, KHÔNG kết thúc phiên họp, KHÔNG
  cần bạn bấm lại "Bắt đầu ghi". Hãy thử ĐÚNG case (b) này khi retest.

⚠️ Phần phát hiện đổi device chỉ verify được bằng cách giả lập trong
sandbox (`tests/test_capture.py`) — CHƯA chạy thật với audio hardware
Windows, có thể còn quirk chưa lường tới.

### 3. Không xem được báo cáo của các phiên họp CŨ (CONTRACTS.md Mục 13 — đây CHÍNH LÀ Bước 4/4, F13)

**Đã sửa bằng cách làm luôn F13** (nút "🕓 Lịch sử", MỚI, cạnh nút "📄 Xem
báo cáo"): luôn bật, không cần đang ghi âm gì cả, mở ra danh sách MỌI phiên
họp đã từng ghi (kể cả phiên đã đóng app từ lâu) + ô tìm theo nội dung đã
nói + bấm "Xem báo cáo" cho TỪNG phiên, kể cả khi đang/không đang chạy 1
phiên khác.

**Tự test lại đúng theo mô tả bạn đã báo**: ghi 1 phiên, kết thúc, **tắt
HẲN app** (đóng cửa sổ, không chỉ đóng tab báo cáo), mở lại app, bấm
"🕓 Lịch sử" — phiên vừa ghi PHẢI xuất hiện trong danh sách, bấm "Xem báo
cáo" PHẢI thấy ĐẦY ĐỦ nội dung + đúng trạng thái checkbox việc-cần-làm đã
tick trước đó (không bị mất, không cần bắt đầu ghi phiên mới mới xem được).
Thử tìm bằng vài từ đã nói trong phiên đó ở ô tìm kiếm.

### 4. Cài đặt API key cho người dùng cuối khi đóng gói .exe (F14, mới — CONTRACTS.md Mục 12)

**Mới làm**: nút "⚙️ Cài đặt" (MỚI) — nhập Groq API key của BẠN (ẩn dạng
mật khẩu, có icon 👁 bật/tắt hiện rõ), lưu cục bộ trên máy, đọc lại mỗi lần
mở app — **không cần sửa code/`.env`/build lại app mỗi lần đổi key**, đúng
chuẩn bị cho lúc đóng gói `.exe` đưa người khác dùng (mỗi người tự nhập key
của họ, tự chịu trách nhiệm dùng model AI của mình).

**Tự test lại**: vào "⚙️ Cài đặt", nhập 1 key test (không cần đúng key
thật) bấm Lưu — xem dòng ghi chú có hiện "🔒 Sẽ được mã hoá cục bộ bằng
Windows DPAPI" không (PHẢI hiện đúng câu này trên Windows — nếu hiện cảnh
báo "không hỗ trợ mã hoá" thì báo lại, có thể máy bạn chặn DPAPI vì lý do
nào đó). Tắt HẲN app, mở lại, vào lại "⚙️ Cài đặt" — key đã nhập phải vẫn
còn (bấm 👁 để xem lại đúng key). Xoá `.env`/biến `GROQ_API_KEY` (hoặc đổi
tên file `.env` tạm thời) rồi chạy ghi âm thử — app PHẢI vẫn hoạt động bình
thường bằng key đã lưu qua Settings (xác nhận đúng thứ tự ưu tiên đọc key).

⚠️ Nhánh mã hoá DPAPI thật CHƯA verify được trong sandbox này (không có
Windows) — chỉ verify được logic ở nhánh fallback. Đây là điểm CẦN bạn xác
nhận kỹ nhất trong 4 mục ở Vòng 6.

---

**Checkpoint cần xác nhận trước khi tiếp tục Phase 4**:
1. Mục 1 — không còn rác/hallucination rõ rệt khi im lặng, không mất câu ngắn thật.
2. Mục 2 — case (b) (đổi thiết bị phát) tự phục hồi, không cần bấm lại "Bắt đầu ghi".
3. Mục 3 — xem lại được ĐẦY ĐỦ báo cáo + checkbox của phiên CŨ sau khi tắt/mở lại app.
4. Mục 4 — Settings lưu/đọc lại đúng key, đúng thứ tự ưu tiên so với `.env`, ghi chú mã hoá hiện đúng trạng thái thật.

## Phase 3 — Bước 3 (LỊCH SỬ, đã pass — giữ lại tham khảo): test xuất file + tick action item

1. Chạy app như Phase 1/2, bắt đầu ghi 1 phiên, bấm **"📄 Xem báo cáo"** — lần ĐẦU vẫn gọi AI tổng hợp như Bước 2/4 (1 dòng nhỏ "Tạo lúc (UTC): ..." mới xuất hiện trên đầu báo cáo).
2. Đóng dialog, bấm **"📄 Xem báo cáo"** LẠI — phải hiện báo cáo NGAY (không chờ "Đang tải..." lâu như lần 1), vì đã đọc từ cache `meeting_reports`, KHÔNG gọi lại AI (tự kiểm tra dashboard Groq không tăng thêm request nào cho hành động mở lại này).
3. Tick vài checkbox ở mục "📌 Việc cần làm" — đóng app HẲN (tắt hẳn `python -m app.main`), mở lại, bấm "Xem báo cáo" lần nữa — các checkbox đã tick phải CÒN NGUYÊN (xác nhận đã lưu DB thật, không chỉ lưu tạm trong RAM).
4. Bấm **"🔄 Tạo báo cáo mới"** — phải gọi AI lại (đợi "Đang tải..." như lần đầu), nội dung có thể đổi, và mọi checkbox phải VỀ LẠI chưa tick (đây là hành vi ĐÚNG THIẾT KẾ — xem CONTRACTS.md Mục 10.3 — không phải bug).
5. Bấm **"💾 Xuất .docx"** và **"💾 Xuất .pdf"** riêng — chọn nơi lưu — mở CẢ HAI file vừa xuất bằng Word và trình đọc PDF (Acrobat/Edge...), kiểm tra:
   - Đủ 3 mục Tóm tắt/Quyết định/Việc cần làm + đúng dấu "[x]"/"[ ]" cho action item đã tick/chưa tick.
   - **Dấu tiếng Việt hiển thị ĐÚNG trong CẢ HAI file** (đây là phần rủi ro nhất — xem CONTRACTS.md Mục 10.5, PDF cần register font `Segoe UI` từ máy bạn, sandbox không tự verify được phần này).

⚠️ **Lưu ý phát hiện ngoài phạm vi Bước 3/4 (vẫn CHƯA sửa, không liên quan Vòng 6)**: `tests/test_groq_provider_offline.py` có thể FAIL với `TypeError` khi giả lập lỗi 429 trên máy bạn — nguyên nhân là phiên bản mới nhất của thư viện `openai` (SDK) đổi cách khởi tạo `RateLimitError` so với lúc test này được viết, không liên quan code. Báo nếu bạn muốn xử lý riêng (vd ghim chặt phiên bản `openai`).

## Lịch sử sửa lỗi qua các vòng test thật (mới nhất trước)

**Vòng 7** (2 vấn đề mới sau khi Vòng 6 đã pass — xem mục "Vòng 7" ở trên để biết chi tiết cách retest, CONTRACTS.md Mục 15-16 để biết chi tiết kỹ thuật):
- **`suggest_answer()` trả lời sai ngôn ngữ với hội thoại Trung/Nhật/Hàn** (CONTRACTS.md Mục 15) — viết lại prompt nhắc rõ ngôn ngữ đầu ra ngay từ câu đầu + lặp lại nhiều lần, thêm lưới an toàn `_looks_like_wrong_script()` tự retry 1 lần khi phát hiện lệch script. Đã xác nhận TRƯỚC khi sửa: không phải lỗi wiring, đúng là hành vi model.
- **Delay 6-9s khi chuyển ngôn ngữ/tab** (CONTRACTS.md Mục 16) — xác định nguyên nhân chính: VAD phải đợi tới trần `max_segment_ms` (cũ 15s) khi không có khoảng lặng thật giữa 2 nguồn audio liên tiếp, segment dài hơn → transcribe()/translate() lâu hơn. Hạ trần xuống 8s. Ghi nhận thêm 1 nguyên nhân phụ (audio capture + AI processing chạy cùng 1 thread tuần tự) nhưng CỐ TÌNH chưa sửa (rủi ro kiến trúc lớn hơn, không tương xứng với phiên này).

**Vòng 6** (sửa 4 vấn đề từ test Bước 3/4 + Bước 4/4 F13 + Settings F14 — xem mục "Vòng 6" ở trên để biết chi tiết cách retest, CONTRACTS.md Mục 11-14 để biết chi tiết kỹ thuật):
- **Lọc hallucination Whisper trên im lặng/nhạc nền** (`TranscriptionResult.no_speech_prob` MỚI, tách riêng khỏi `confidence` — Mục 11) — sửa ĐÚNG nguyên nhân gốc của CẢ 2 triệu chứng "rác xuất hiện" và "sai ngôn ngữ" cùng lúc (cùng 1 nguồn: audio không có giọng nói thật).
- **Settings UI nhập API key** (`app/config_store.py`, `ui/settings_dialog.py`, F14 MỚI, chưa từng có trong roadmap phase nào — phát hiện khoảng trống khi bạn hỏi về đóng gói .exe) — mã hoá Windows DPAPI khi có thể, fallback plaintext-local có cảnh báo rõ khi không.
- **Lịch sử phiên họp** (`app/ui/history_dialog.py`, F13 — CHÍNH LÀ Bước 4/4, làm luôn vì lỗi "không xem được báo cáo cũ" bạn báo thực chất là tính năng này còn thiếu UI) — `MeetingStore.list_meetings_with_counts()`/`search_meetings()` MỚI.
- **Tự phục hồi khi đổi thiết bị phát giữa lúc ghi** (`AudioDeviceChangedError`, Mục 14) — ⚠️ CHỈ áp dụng đúng case đổi DEVICE, không phải đổi app/tab nguồn phát (xem giải thích chi tiết ở mục "Vòng 6" trên) — CHƯA verify hardware Windows thật.
- `_open_report_for_meeting()` (refactor từ `_on_report_clicked()` cũ) sửa luôn 1 bug ẨN liên quan: export/tổng hợp báo cáo phiên CŨ trước đây vô tình dùng NGÔN NGỮ MẸ ĐẺ của session hiện tại (combo box) thay vì ngôn ngữ thật của phiên đó — phát hiện khi làm Mục 3, tự sửa kèm luôn vì cùng gốc code.

**Vòng 5** (Bước 3/4 — F11 xuất file + cache báo cáo + tick action item):
- **Bạn duyệt Bước 2/4**: 4/4 checkpoint pass, tốc độ chậm hơn 1 chút (đổi STT sang `whisper-large-v3`, Vòng 4) nhưng "trong mức chấp nhận được" — **quyết định KHÔNG tối ưu thêm tốc độ**: không có lever "miễn phí" nào cho việc này (model hosted cố định trên Groq, tốc độ/độ chính xác bị khoá chung vào lựa chọn model); hướng adaptive (turbo trước, escalate khi confidence thấp) là tính năng MỚI chưa verify được, rủi ro không tương xứng với vấn đề chưa thực sự cấp bách — giữ nguyên `whisper-large-v3`.
- **Đối chiếu CONTRACTS.md (đã dựng lại từ trước) với PROJECT_SPEC.md gốc** (bạn gửi bổ sung) — vài lệch đã xác nhận CÓ CHỦ ĐÍCH (STT turbo→full, font Be Vietnam Pro/Inter→Segoe UI) không cần sửa; xác nhận roadmap chính thức Phase 3 = F10+F11+F13 → Bước 3/4 = F11 (xuất file), Bước 4/4 = F13 (lịch sử phiên họp).
- **Bảng `meeting_reports` MỚI** — báo cáo được LƯU sau khi tổng hợp (1 phiên họp giữ đúng 1 báo cáo mới nhất), mở lại dialog đọc cache, KHÔNG gọi lại `summarize()` (tốn quota free-tier + chậm vô ích nếu nội dung không đổi). Nút "🔄 Tạo báo cáo mới" bỏ cache, gọi AI lại, reset toàn bộ tick.
- **Action items thành checkbox tick được** (đúng PROJECT_SPEC.md Mục 10.4 — phát hiện thiếu khi đối chiếu spec gốc) — tick lưu DB ngay, còn nguyên qua lần tắt/mở lại app. Tách riêng `ActionItemRecord`/`ReportRecord` (tầng storage, có `done`) khỏi `SummaryResult` (tầng AI, 🔒 đã chốt, không đổi) — xem CONTRACTS.md Mục 10.2.
- **Xuất báo cáo ra `.docx`/`.pdf`** (`app/report_export.py`, F11) — `.docx` qua `python-docx` (an toàn font), `.pdf` qua `reportlab` (PHẢI tự register font Unicode `Segoe UI` trước khi vẽ, nếu không dấu tiếng Việt lỗi câm — bài học lặp lại từ bug font QTextEdit ở Vòng 3, lần này nghiêm trọng hơn vì PDF không tự fallback font như Word). **CHƯA verify được trên Windows thật** (sandbox không có font hệ thống Windows) — đã verify được: logic build nội dung, hành vi raise lỗi rõ ràng khi thiếu font, và pipeline register-font/build PDF chạy đúng kỹ thuật bằng font thế (DejaVu Sans) có sẵn trong sandbox.
- Phát hiện ngoài phạm vi: `tests/test_groq_provider_offline.py` (không đụng tới ở bước này) fail trong sandbox vì bản `openai` SDK mới nhất đổi cách khởi tạo `RateLimitError` — môi trường/version drift, không phải lỗi do Bước 3/4 (xem mục Bước 3 ở trên).

**Vòng 4** (lỗi JSON `summarize()` + model fallback + UI báo cáo):
- **`summarize()` trả lỗi 400 "Failed to generate JSON" thật** (log + dashboard Groq người dùng gửi khớp nhau) — nguyên nhân: schema cũ bắt `decisions`/`action_items` là 1 string lớn nhiều dòng + tự thêm "- ", model lệch cú pháp JSON khi nhúng cấu trúc đó vào 1 field string. Sửa: đổi 2 field này thành **JSON array of strings** — `SummaryResult.decisions: list[str]`, mỗi phần tử 1 ý ngắn. `[]` = model xác nhận thật không có, không phải lỗi. Parse vẫn tương thích ngược với string kiểu cũ.
- **Lẫn ký tự script khác (CJK) vào bản dịch tiếng Việt** (lỗi hiển thị người dùng báo ban đầu, hoá ra không phải lỗi hiển thị mà là model generate lẫn — xem Vòng 3.5 không ghi riêng, đã sửa cùng đợt) — đã CONFIRM hết qua test thật của bạn.
- **Model STT/dịch "nhảy" giữa `llama-3.3-70b-versatile`/`whisper-large-v3-turbo` trên dashboard** — KHÔNG phải code tự đổi model né limit (lúc đó chưa có); đơn giản là 2 model làm 2 việc khác nhau. Nhân cơ hội này **thêm fallback model TỰ ĐỘNG theo 429 thật**: model chính ưu tiên độ chính xác (`whisper-large-v3` cho STT — đúng phản hồi "nghe sai/sót từ" của bạn; `llama-3.3-70b-versatile` cho dịch/tóm tắt như cũ), tự động thử lại NGAY 1 lần với model phụ (`whisper-large-v3-turbo`/`llama-3.1-8b-instant`) CHỈ KHI gặp 429 — không cần tự sửa code mỗi lần hết quota nữa (xem mục "Nếu gặp lỗi 429" dưới, đã update).
- **`translate()` viết lại prompt lần 4** — vẫn còn "đúng nghĩa nhưng máy móc" dù đã có context (Vòng 3). Thêm 4 quy tắc cụ thể: reflow câu tự do, dịch idiom/filler tự nhiên, giữ đúng register/tone, ưu tiên cách nói tự nhiên hơn nghĩa từ-điển. **Chưa verify chất lượng thật** — cần bạn nghe lại.
- **Bước 2/4 (UI báo cáo)**: `ui/report_view.py` (`ReportDialog`) + nút "📄 Xem báo cáo" + `app/report.py` (helper build transcript dùng chung, tránh lệch logic giữa script test và UI). `OneShotAIWorker.succeeded` đổi `Signal(str)` → `Signal(object)` để mang được `SummaryResult` có cấu trúc (Phase 2 vẫn dùng được bình thường, str vẫn là 1 object).

**Vòng 3** (lỗi ký tự + dịch máy móc):
- **Lỗi ký tự (mất dấu tiếng Việt) trong khung gợi ý** — đã xác nhận KHÔNG phải lỗi dữ liệu bằng cách đọc trực tiếp `meetings.db` bạn gửi (dữ liệu lưu ĐÚNG 100% dấu). Lỗi chỉ ở khâu hiển thị `QTextEdit` — khả năng cao do font "Be Vietnam Pro"/"Inter" trong `theme.qss` không có sẵn trên Windows. Đã sửa: đổi sang "Segoe UI" (chắc chắn có trên Windows) làm font chính + set font TRỰC TIẾP bằng code lên các `QTextEdit`, không qua QSS nữa. **Chưa verify lại được trên Windows thật.**
- **Dịch đúng ngôi nhưng vẫn máy móc, khó hiểu ý** — nguyên nhân gốc: mỗi câu dịch HOÀN TOÀN RIÊNG LẺ, model không biết mạch chuyện trước/sau. Đã thêm `context_text` (optional) vào `translate()` — áp dụng cho cả transcript chính, Suggestion Drawer, và Ask Question.

**Vòng 2** (auto-scroll + dịch sai ngôi + UI Phase 2):
- **Auto-scroll không hoạt động** — `QTimer.singleShot(0, ...)` không đủ tin cậy (0ms không đảm bảo chạy sau khi Qt tính lại layout). Sửa đúng gốc bằng lắng nghe signal `QScrollBar.rangeChanged(min, max)`.
- **Dịch sai ngôi**: "Can you tell us about yourself?" bị dịch thành "Tôi có thể kể về bản thân mình không?" (lật bạn↔tôi). Thêm yêu cầu rõ giữ đúng ngôi/chiều xưng hô trong prompt `translate()`.
- **AI nhận diện câu hỏi kém** (heuristic dấu "?" miss câu hỏi nói nhanh) → quyết định bỏ hẳn gate `is_question`, nút "Nhờ AI trả lời" hiện ở MỌI bubble.
- **Prompt gợi ý trả lời lan man** ("I appreciate this question...") → viết lại, bắt trả lời trực tiếp, 1-3 câu ngắn.
- Thêm tính năng **"❓ Tôi muốn hỏi"** (chiều ngược lại "Nhờ AI trả lời") và bảng `ai_assists` lưu lại lịch sử AI hỗ trợ.

**Vòng 1** (lần đầu chạy thật trên Windows):
- `source_lang` Groq trả tên ngôn ngữ đầy đủ (`"English"`) chứ không phải mã ISO (`"en"`) — đã chuẩn hoá.
- Cảnh báo "độ tin cậy thấp" không hiện ra dù confidence thấp — sửa cách render, không phụ thuộc QSS property-selector.
- `VadSegmenter.silence_ms` giảm 600ms→350ms để giảm gộp 2 lượt nói liên tiếp nhanh (không triệt để — vẫn không phân biệt được "ai nói", xem mục dưới).

⚠️ **Lưu ý xuyên suốt**: nhiều fix ở trên tôi chỉ verify được là *code/prompt đã đúng như thiết kế* — KHÔNG thể tự verify chất lượng output thật của Groq trong sandbox này (không có network ra ngoài). Luôn cần bạn xác nhận lại bằng test thật.

### Giới hạn đã biết: KHÔNG phân biệt được người nói (chưa có diarization)
Loopback audio là 1 dòng đã được app họp (Zoom/Teams/Meet) TRỘN SẴN mọi người ở đầu kia trước khi phát ra loa — **không phải do dùng video test**, họp thật nhiều người cũng bị vậy. Diarization thật (F12) cần thêm `pyannote.audio` (kéo theo PyTorch, dependency rất nặng) — tạm xếp Phase 4, ưu tiên làm Phase 2/3 (giá trị cốt lõi) trước. Xem CONTRACTS.md Mục 2.

---

## Yêu cầu hệ thống

- Windows 10/11 (loopback WASAPI chỉ chạy trên Windows — đã verify: trên Linux app báo lỗi rõ ràng "chỉ hỗ trợ trên Windows" thay vì crash, nhưng tất nhiên không ghi được audio thật)
- Python 3.11+
- API key của ÍT NHẤT 1 trong 3 provider AI sau (MỚI Vòng 8 — trước đây chỉ
  hỗ trợ Groq): [Groq](https://console.groq.com/keys) (miễn phí),
  [OpenAI](https://platform.openai.com/api-keys) (trả phí theo usage),
  hoặc [Gemini](https://aistudio.google.com/apikey) (có free tier). Chọn
  provider trong app qua ⚙️ Cài đặt — KHÔNG cần biết trước, đổi qua lại
  được bất kỳ lúc nào.

## Cài đặt

```bash
# 1. Tạo virtual env (khuyến nghị)
python -m venv .venv
.venv\Scripts\activate

# 2. Cài dependencies
pip install -r requirements.txt

# 3. (Chỉ cần nếu dev/test từ source code — người dùng nhận bản .exe
#    đóng gói KHÔNG cần bước này, dùng ⚙️ Cài đặt trong app thay thế)
#    Tạo file .env từ mẫu, điền key thật của 1 trong 3 provider:
copy .env.example .env
# rồi mở .env, sửa GROQ_API_KEY=xxx (hoặc OPENAI_API_KEY=/GEMINI_API_KEY=
# nếu bạn dùng provider khác — chỉ cần điền 1 trong 3, xem .env.example)
```

> Lưu ý đã xử lý: `requirements.txt` trước đây thiếu `webrtcvad`/`openai`
> (dùng trong `vad.py`/`groq_provider.py` nhưng quên thêm vào danh sách cài
> đặt) — đã bổ sung. Cũng đã đổi `webrtcvad` → `webrtcvad-wheels` vì bản gốc
> dùng `pkg_resources` đã bị gỡ khỏi `setuptools` mới, gây lỗi
> `ModuleNotFoundError` ngay khi import trên máy có pip/Python mới.

## Chạy app (Phase 1)

```bash
python -m app.main
```

(Chạy bằng `python -m app.main`, KHÔNG chạy `python app/main.py` trực tiếp,
vì cần Python coi `app/` là package nằm trong project root để các câu lệnh
`from app.xxx import ...` hoạt động.)

**Cách test thật**:
1. Mở sẵn 1 video YouTube tiếng Anh (hoặc bất kỳ ngôn ngữ nào) để có âm phát ra loa.
2. Mở app, chọn "Ngôn ngữ mẹ đẻ của bạn" (mặc định Tiếng Việt), bấm "Bắt đầu ghi".
3. Banner đỏ "Đang ghi âm..." phải xuất hiện ngay.
4. Sau vài giây, transcript gốc + bản dịch phải lần lượt hiện ra dưới dạng từng "bubble".
5. Bấm "Kết thúc họp" để dừng — banner phải biến mất, trạng thái báo "Đã kết thúc phiên họp #N".
6. File `meetings.db` (SQLite) phải xuất hiện ở project root, chứa transcript vừa ghi.

**Checkpoint xác nhận Phase 1 thành công**: transcript + bản dịch hiện đúng,
gần thời gian thực (độ trễ chấp nhận được ~2-4s mỗi câu — không thể tức thời
tuyệt đối với free-tier API, xem CONTRACTS.md/PROJECT_SPEC.md).

## Nếu gặp lỗi 401 (Invalid API Key)

> ℹ️ **MỚI Vòng 8**: hướng dẫn dưới đây viết cho trường hợp chạy từ source
> code với `.env` (dev) + provider Groq. Nếu bạn dùng bản `.exe` đã đóng
> gói, hoặc đang dùng OpenAI/Gemini, sửa qua ⚙️ Cài đặt trong app (chọn
> đúng provider, dán lại key) thay vì sửa `.env` — message lỗi app hiện ra
> sẽ tự nói rõ đang thiếu key của provider nào + link lấy key tương ứng
> (xem `app/ai/openai_compat_base.py::_auth_error_hint`).

Khác với lỗi 429, đây là lỗi **cấu hình `.env`**, không phải bug code hay
audio — request đã tới được Groq nhưng bị từ chối vì key sai/hết hạn. App
giờ sẽ tự báo rõ nguyên nhân hơn nguyên JSON lỗi thô. Kiểm tra theo thứ tự:
1. Mở file `.env` (KHÔNG phải `.env.example`) — đảm bảo `GROQ_API_KEY=` đã
   được thay bằng key THẬT, không còn để nguyên `your_groq_api_key_here`
   (nếu còn để nguyên, app giờ sẽ báo thẳng lỗi này ngay khi bấm "Bắt đầu
   ghi", không cần đợi gọi API mới biết).
2. Vào https://console.groq.com/keys kiểm tra key còn tồn tại, chưa bị xoá/revoke.
3. Nếu vừa tạo key mới: phải **lưu lại file `.env`** rồi **chạy lại app** —
   app chỉ đọc `.env` 1 lần lúc khởi động (`load_dotenv()` trong `main.py`),
   sửa `.env` khi app đang chạy không có tác dụng.

## Nếu gặp lỗi 429 (rate limit free tier)

Đây là giới hạn của Groq free tier, không phải bug code. **Từ Vòng 4, app tự
động xử lý 1 phần**: khi model chính (`whisper-large-v3` cho STT,
`llama-3.3-70b-versatile` cho dịch/gợi ý/tóm tắt) bị 429, `GroqProvider` tự
thử lại NGAY 1 lần với model phụ nhanh hơn/quota khác
(`whisper-large-v3-turbo`/`llama-3.1-8b-instant`) — không cần bạn tự sửa
code mỗi lần nữa. Nếu vẫn thấy lỗi 429 (cả 2 model đều hết quota cùng lúc):
- Đợi vài phút rồi thử lại (free tier reset theo phút/giờ tùy model).
- Muốn đổi hẳn model chính/phụ: truyền `stt_model=`, `stt_fallback_model=`,
  `translate_model=`, `translate_fallback_model=` lúc tạo `GroqProvider()`
  trong `app/ui/main_window.py` (hoặc qua `create_provider(..., stt_model=...)`
  — xem `app/ai/provider_factory.py`, MỚI Vòng 8).
- **MỚI Vòng 8 — cách khác, đơn giản hơn**: đổi hẳn qua provider khác
  (OpenAI/Gemini) trong ⚙️ Cài đặt nếu Groq hết quota thường xuyên — KHÔNG
  cần đợi Phase 4 (`faster-whisper` local) mới có lựa chọn dự phòng.
- Phase 4 (nếu làm) sẽ có thêm fallback `faster-whisper` chạy LOCAL khi mất
  mạng hoàn toàn (multi-provider Vòng 8 vẫn cần network/key của 1 trong 3
  provider — chỉ giải quyết "Groq hết quota", không giải quyết "mất mạng").

## Phase 0 (vẫn giữ, dùng để test riêng phần audio/STT khi cần debug)

```bash
python scripts/test_capture.py        # test riêng audio loopback
python scripts/test_groq_whisper.py   # test riêng gửi 1 file .wav lên Groq
```

## Chạy test (không cần Windows/audio/API key thật — dùng mock)

```bash
python tests/test_vad.py
python tests/test_groq_provider_offline.py
python tests/test_openai_provider_offline.py                # MỚI Vòng 8
python tests/test_gemini_provider_offline.py                 # MỚI Vòng 8
python tests/test_provider_factory_offline.py                  # MỚI Vòng 8
python tests/test_db.py
python tests/test_pipeline.py
python tests/test_report_export.py                        # chạy thật (docx/pdf local, không cần network)
python tests/test_config_store.py                          # Vòng 6 (F14) + MỚI Vòng 8 (multi-provider) — chạy thật, không cần Windows/network
python tests/test_capture.py                                 # MỚI Vòng 6 (Mục 14) — mock soundcard, chạy thật, không cần audio hardware
QT_QPA_PLATFORM=offscreen python tests/test_ui_smoke.py   # bỏ biến QT_QPA_PLATFORM trên Windows có màn hình thật
```

Các test này verify: logic cắt segment của VAD, logic parse/wrap lỗi/prompt
của GroqProvider/OpenAIProvider/GeminiProvider (transcribe/translate/
suggest_answer/summarize, kể cả `no_speech_prob` và lựa chọn provider qua
`provider_factory` MỚI Vòng 8), schema + CRUD của SQLite (kể cả
`ai_assists`/`meeting_reports`/lịch sử-tìm kiếm MỚI Vòng 6), logic ghép nối
toàn pipeline (kể cả gate lọc hallucination MỚI Vòng 6), build nội dung +
hành vi font của file xuất `.docx`/`.pdf`, logic lưu/đọc API key cục bộ
(`config_store.py`, nhánh fallback — KHÔNG verify được nhánh DPAPI thật),
logic phát hiện đổi default playback device (mock `soundcard`, KHÔNG verify
được hardware Windows thật), và toàn bộ wiring UI↔thread↔DB (kể cả Lịch sử/
Settings MỚI Vòng 6) không bị treo/crash. **Chưa và không thể test được
trong sandbox này**: chất lượng output thật của Groq (độ chính xác STT, độ
tự nhiên bản dịch, có bịa thông tin khi tóm tắt không, ngưỡng
`no_speech_prob`/`NO_SPEECH_PROB_DROP_THRESHOLD` có khớp số liệu Groq thật
không), độ trễ network thật, audio loopback thật trên Windows (kể cả tự
phục hồi khi đổi device), mã hoá DPAPI thật, **font "Segoe UI" thật khi
xuất PDF có hiển thị đúng dấu tiếng Việt hay không** (sandbox không có font
hệ thống Windows) — luôn cần bạn tự chạy thật để xác nhận.

---

## Cấu trúc dự án

```
app/
  audio/
    capture.py        # [Phase 0+1, Vòng 6: AudioDeviceChangedError] thu audio loopback + stream cho VAD + tự phục hồi khi đổi device
    vad.py              # [Phase 1, Vòng 7: max_segment_ms 15s→8s] cắt audio thành segment theo khoảng lặng
  ai/
    base_provider.py     # [Vòng 6] TranscriptionResult thêm no_speech_prob
    openai_compat_base.py  # [Vòng 8, MỚI] translate/suggest_answer/summarize DÙNG CHUNG cho Groq/OpenAI/Gemini
    whisper_utils.py         # [Vòng 8, MỚI] parse response Whisper verbose_json DÙNG CHUNG cho Groq/OpenAI
    groq_provider.py     # transcribe/translate/suggest_answer/summarize đã implement, đã unit test (mock)
                          # [Vòng 7] suggest_answer(): prompt + retry chống trả lời sai ngôn ngữ với hội thoại CJK
                          # [Vòng 8] refactor: kế thừa OpenAICompatProvider, dùng whisper_utils — KHÔNG đổi hành vi
    openai_provider.py     # [Vòng 8, MỚI] OpenAIProvider — whisper-1 cho STT, GPT cho dịch/gợi ý/tóm tắt
    gemini_provider.py      # [Vòng 8, MỚI] GeminiProvider — REST generateContent riêng cho STT (Gemini không có API kiểu Whisper)
    provider_factory.py      # [Vòng 8, MỚI] create_provider()/display_name() — 1 điểm duy nhất chọn provider
                          # local_whisper_provider.py: chưa làm, thuộc Phase 4
  config_store.py        # [Vòng 6, F14] lưu API key người dùng cuối — DPAPI (Windows) + fallback local
                          # [Vòng 8] mở rộng: nhiều provider, mỗi provider 1 key riêng + active_provider
  storage/
    db.py                # [Phase 1+2+3, Vòng 6] SQLite: bảng meetings+segments+ai_assists+meeting_reports + list_meetings_with_counts()/search_meetings() (F13)
  pipeline.py             # [Phase 1, Vòng 6: lọc no_speech_prob] ghép VAD+AIProvider+DB, độc lập Qt để test được
  report.py               # [Phase 3] build_transcript_text() dùng chung cho script test + UI
  report_export.py        # [Phase 3 Bước 3/4] xuất ReportRecord ra .docx/.pdf — độc lập Qt/network
  ui/
    main_window.py          # [Phase 1+2+3, Vòng 6] cửa sổ chính + AudioWorker (QThread) + wiring + nút Lịch sử/Cài đặt
    transcript_bubble.py      # [Phase 1+2] widget hiển thị 1 segment + nút "Nhờ AI trả lời"
    suggestion_drawer.py        # [Phase 2] panel soạn gợi ý trả lời, cho sửa, dịch ngược
    ask_question_dialog.py        # [Phase 2] panel "Tôi muốn hỏi" - chiều ngược lại
    report_view.py                  # [Phase 3] ReportDialog — Tóm tắt/Quyết định/Việc cần làm (checkbox) + nút tạo lại/xuất file
    history_dialog.py                 # [Vòng 6, MỚI, F13/Bước 4/4] MeetingHistoryDialog — xem/tìm lại phiên họp cũ
    settings_dialog.py                  # [Vòng 6, F14] SettingsDialog — nhập/đổi API key [Vòng 8: + dropdown chọn provider Groq/OpenAI/Gemini]
    ai_worker.py                          # [Phase 2+3] OneShotAIWorker — chạy 1 lệnh AIProvider bất kỳ trên thread riêng
    theme.qss                              # [Phase 1+2+3] dark-mode theo PROJECT_SPEC.md mục 10
  main.py                                    # [Phase 1] entry point — chạy `python -m app.main`
scripts/
  test_capture.py        # [Phase 0]
  test_groq_whisper.py    # [Phase 0]
  test_suggest_answer.py   # [Phase 2] test riêng suggest_answer() qua terminal, không cần UI
  test_summarize.py         # [Phase 3] test riêng summarize() bằng dữ liệu DB thật
tests/
  test_vad.py                      # unit test VadSegmenter (VAD giả lập, kiểm soát được) — kể cả default max_segment_ms=8000 MỚI (Vòng 7)
  test_groq_provider_offline.py     # unit test GroqProvider (client giả lập) — fallback model + no_speech_prob (Vòng 6) + chống sai ngôn ngữ suggest_answer() (Vòng 7) + refactor dùng chung (Vòng 8, KHÔNG sửa file test)
  test_openai_provider_offline.py    # [Vòng 8, MỚI] unit test OpenAIProvider (client giả lập)
  test_gemini_provider_offline.py     # [Vòng 8, MỚI] unit test GeminiProvider (monkeypatch _post_generate_content)
  test_provider_factory_offline.py     # [Vòng 8, MỚI] unit test create_provider()/display_name()
  test_db.py                         # unit test MeetingStore — kể cả lịch sử/tìm kiếm MỚI (Vòng 6, F13)
  test_pipeline.py                    # unit test ghép nối toàn pipeline — kể cả gate lọc hallucination MỚI (Vòng 6)
  test_report_export.py                # unit test xuất .docx/.pdf — chạy THẬT (local, không cần network)
  test_config_store.py                  # [Vòng 6, MỚI] unit test lưu/đọc API key cục bộ — chạy THẬT (không cần Windows)
  test_capture.py                        # [Vòng 6, MỚI] unit test phát hiện đổi device — mock soundcard, chạy THẬT
  test_transcript_bubble.py            # unit test cảnh báo độ tin cậy thấp
  test_ui_smoke.py                      # smoke test UI thật (kể cả luồng Phase 2/3), chạy headless
CONTRACTS.md              # hợp đồng kỹ thuật giữa các module
.env.example
requirements.txt
```

---

## Đề xuất thứ tự Phase 4 (sau khi đọc toàn bộ PROJECT_SPEC.md/CONTRACTS.md/lịch sử test)

⚠️ Đây là Ý KIẾN, không phải quyết định đã chốt như các Mục khác trong
CONTRACTS.md — bạn là người quyết định cuối cùng cần làm gì, dựa trên thời
gian/mục đích sử dụng thật của BẠN. Lý do đầy đủ + phản biện nằm trong
phần trả lời trực tiếp cho bạn (không lặp lại ở đây) — đây chỉ là bản tóm
tắt thứ tự đề xuất để tham khảo nhanh khi quay lại project sau này.

1. **Đóng gói `.exe` (PyInstaller) + retest Vòng 7/8 trên Windows thật** —
   làm TRƯỚC mọi việc khác trong Phase 4. Lý do: đây là bước "biến code
   thành sản phẩm dùng được", không phải tính năng — và sẽ LỘ RA bug đóng
   gói (DPAPI, đường dẫn font, antivirus false-positive...) mà KHÔNG cách
   nào lường hết được khi chỉ chạy `python -m app.main` từ source.
2. **`faster-whisper` chạy local (F12 trong PROJECT_SPEC.md, fallback khi
   mất mạng/hết quota CẢ 3 provider)** — CHỈ làm nếu sau bước 1 bạn xác
   nhận thực sự cần (vd dùng ở nơi mạng không ổn định). Đây là
   dependency NẶNG (kéo theo PyTorch) ảnh hưởng trực tiếp tới mục tiêu
   ".exe nhẹ/chuyên nghiệp" — không nên làm "cho có" nếu Vòng 8 (multi-
   provider) đã đủ giải quyết nhu cầu thật.
3. **Diarization (phân biệt người nói, F12 còn lại)** — cân nhắc kỹ trước
   khi làm: kéo theo `pyannote.audio` (PyTorch lần 2 nếu bước 2 không
   làm), đổi ngược lại mục tiêu ".exe nhẹ". Chỉ làm nếu use-case thật của
   bạn THỰC SỰ cần biết "ai nói câu nào" (không chỉ "thấy gọn hơn").
4. Các mục nhỏ còn lại (nếu có) trong PROJECT_SPEC.md mục 4 chưa làm — rà
   lại danh sách F1-F14 gốc, đối chiếu với CONTRACTS.md để biết mục nào
   THẬT đã xong/THẬT chưa làm trước khi thêm việc mới.
