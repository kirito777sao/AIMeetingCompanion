"""app/ai/openai_compat_base.py
--------------------------------
🔒 MỚI (đợt thêm multi-provider — F14 mở rộng, xem CONTRACTS.md Mục 17).

Bối cảnh: `groq_provider.py` (Groq) đã tồn tại từ Phase 1, dùng SDK
`openai` (OpenAI-compatible) chỉ trỏ `base_url` khác. Khi thêm OpenAI
"thật" và Gemini (qua lớp tương thích OpenAI của Google,
`https://generativelanguage.googleapis.com/v1beta/openai/` — CHỈ tương
thích cho chat.completions, KHÔNG cho audio.transcriptions, xem
`gemini_provider.py`), phần `translate()`/`suggest_answer()`/`summarize()`
của 3 provider này **GIỐNG NHAU 100%** (cùng 1 SDK, cùng shape request/
response, chỉ khác `base_url` + tên model) — viết 3 lần riêng là sao chép
~400 dòng prompt/logic 3 lần, rủi ro lệch hành vi khi sửa 1 nơi quên sửa
nơi khác (vd lần tới lại phát hiện bug ngôn ngữ sai như CONTRACTS.md Mục
15 — phải nhớ sửa cả 3 file).

`OpenAICompatProvider` (lớp dưới) gom phần CHUNG đó lại 1 nơi. Mỗi
provider cụ thể (`GroqProvider`, `OpenAIProvider`, `GeminiProvider`) chỉ
cần kế thừa lớp này + tự cung cấp:
    - `self._client` (instance `openai.OpenAI`, đã trỏ đúng `base_url`).
    - `self._translate_model` / `self._translate_fallback_model`.
    - tự implement `transcribe()` riêng (STT KHÁC nhau quá nhiều giữa các
      provider để gộp chung — xem docstring `AIProvider.transcribe()`).

⚠️ KHÔNG đổi 1 ký tự nào trong các đoạn prompt/logic so với
`groq_provider.py` bản TRƯỚC đợt refactor này — đây là di chuyển vị trí
code thuần (move, không rewrite), để giữ nguyên hành vi đã chốt (🔒 Phase
2/3) + giữ nguyên toàn bộ `tests/test_groq_provider_offline.py` PASS
KHÔNG cần sửa gì (file test đó import 1 số tên trực tiếp từ
`app.ai.groq_provider` — `groq_provider.py` sau refactor vẫn `import` lại
(re-export) đúng các tên đó, xem cuối file `groq_provider.py`).
"""

from __future__ import annotations

import json
from typing import Any

import openai

from app.ai.base_provider import AIProvider, ProviderError, SummaryResult, TranscriptionResult

# Map mã ISO 639-1 dùng trong dự án -> tên ngôn ngữ tiếng Anh, đưa vào
# prompt dịch cho model hiểu rõ hơn là chỉ đưa mã 2 ký tự trần.
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "vi": "Vietnamese",
    "zh": "Chinese",
}


def _language_name(code: str) -> str:
    """Trả tên ngôn ngữ đọc được để đưa vào prompt; fallback về chính mã nếu lạ."""
    return _LANGUAGE_NAMES.get(code, code)


# 🔒 (CONTRACTS.md Mục 15) — heuristic phát hiện suggest_answer() trả lời
# SAI ngôn ngữ (bug thật người dùng báo + chụp ảnh UI xác nhận): khi cuộc
# hội thoại là tiếng Trung/Nhật/Hàn, model có xu hướng "mirror" lại NGUYÊN
# ngôn ngữ hội thoại trong context_text/question_text thay vì tuân thủ
# system prompt yêu cầu trả lời bằng user_native_lang.
#
# CHỦ Ý KHÔNG thêm dependency nhận diện ngôn ngữ đầy đủ (langdetect/
# fasttext...) cho việc này — chỉ cần phân biệt ĐÚNG 3 SCRIPT rõ rệt liên
# quan tới 3 ngôn ngữ mẹ đẻ hiện hỗ trợ (vi/en dùng chữ Latin, zh dùng chữ
# Hán) — đủ để bắt đúng case THẬT đã gặp, dùng làm tín hiệu retry trong
# suggest_answer().
_HAN_RANGE = (0x4E00, 0x9FFF)      # chữ Hán (dùng chung Trung/Nhật/Hàn-Hanja)
_KANA_RANGE = (0x3040, 0x30FF)     # Hiragana + Katakana (đặc trưng tiếng Nhật)
_HANGUL_RANGE = (0xAC00, 0xD7A3)   # âm tiết Hangul (đặc trưng tiếng Hàn)

_WRONG_SCRIPT_RATIO_THRESHOLD = 0.15


def _script_char_counts(text: str) -> tuple[int, int, int, int]:
    """Đếm thô (tổng_ký_tự_chữ, han, kana, hangul) trong `text`.

    Chỉ đếm ký tự `str.isalpha()` (bỏ số/dấu câu/khoảng trắng) để tỉ lệ
    không bị pha loãng bởi ký tự không mang thông tin ngôn ngữ/script.
    """
    total = han = kana = hangul = 0
    for ch in text:
        if not ch.isalpha():
            continue
        total += 1
        cp = ord(ch)
        if _HAN_RANGE[0] <= cp <= _HAN_RANGE[1]:
            han += 1
        elif _KANA_RANGE[0] <= cp <= _KANA_RANGE[1]:
            kana += 1
        elif _HANGUL_RANGE[0] <= cp <= _HANGUL_RANGE[1]:
            hangul += 1
    return total, han, kana, hangul


def _looks_like_wrong_script(text: str, native_lang: str) -> bool:
    """True nếu `text` có tỉ lệ ký tự script "lạ" (so với `native_lang`)
    vượt `_WRONG_SCRIPT_RATIO_THRESHOLD` — dấu hiệu suggest_answer() đã trả
    lời SAI ngôn ngữ (mirror theo hội thoại CJK thay vì user_native_lang).

    KHÔNG phải bộ nhận diện ngôn ngữ chuẩn/chính xác tuyệt đối — chỉ đủ
    NHẠY để bắt đúng case lệch SCRIPT rõ ràng đã gặp thật, dùng làm tín hiệu
    quyết định có retry suggest_answer() 1 lần với prompt mạnh hơn hay
    không. Một vài ký tự CJK lẫn vào (vd trích 1 từ tiếng Trung trong câu
    trả lời tiếng Việt) KHÔNG đủ vượt ngưỡng 15% nên không bị báo nhầm.

    `native_lang` không nằm trong 3 mã đã biết script (vi/en/zh) -> luôn
    trả False (không đủ thông tin để đoán "script đúng" của ngôn ngữ đó,
    thà bỏ qua còn hơn báo sai).
    """
    total, han, kana, hangul = _script_char_counts(text)
    if total == 0:
        return False
    if native_lang in ("vi", "en"):
        foreign = han + kana + hangul
    elif native_lang == "zh":
        # Chữ Hán (han) là script ĐÚNG của tiếng Trung -- chỉ Kana/Hangul
        # lẫn vào mới là dấu hiệu lệch (model trả lời bằng tiếng Nhật/Hàn).
        foreign = kana + hangul
    else:
        return False
    return (foreign / total) > _WRONG_SCRIPT_RATIO_THRESHOLD


def _coerce_to_string_list(value: Any, field_name: str, provider_label: str = "AI") -> list[str]:
    """Chuẩn hoá field "decisions"/"action_items" của summarize() thành
    list[str] — schema CHÍNH THỨC (xem CONTRACTS.md Mục 4) là JSON array,
    nhưng vẫn CHẤP NHẬN string (tương thích ngược, phòng model lỡ trả
    sai format ở 1 lần gọi nào đó — free-tier model nhỏ không đáng tin
    tuyệt đối, xem docstring `summarize()`).

    - list -> giữ từng phần tử, ép str + strip, BỎ phần tử rỗng sau strip.
    - str -> tách theo dòng, bỏ tiền tố "- "/"-"/"* " hay gặp nếu model
      lỡ trả kiểu cũ, bỏ dòng rỗng. Một string KHÔNG xuống dòng (1 câu
      ngắn) vẫn được coi là list 1 phần tử, không bị coi là rỗng.
    - kiểu khác (số, bool, dict, None...) -> raise ProviderError, KHÔNG
      đoán mò tiếp — đây là lỗi format model không thể tự sửa bằng
      heuristic, cần biết ngay để xem lại prompt/dữ liệu thật.
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        lines = [line.strip().lstrip("-*").strip() for line in value.splitlines()]
        return [line for line in lines if line]
    raise ProviderError(
        f'{provider_label} summarize trả field "{field_name}" kiểu không hỗ trợ '
        f"({type(value).__name__}), cần list[str] hoặc str. Nội dung: {value!r}"
    )


def _auth_error_hint(
    provider_label: str, api_label: str, env_var_name: str, keys_url: str, exc: Exception,
) -> str:
    """Message lỗi 401 dễ hiểu hơn nguyên JSON lỗi thô -- 401 nghĩa là
    REQUEST ĐÃ TỚI ĐƯỢC server (không phải lỗi mạng/code) nhưng bị từ chối
    vì key sai/hết hạn/bị xoá. Phân biệt rõ với các lỗi khác để người dùng
    không tốn công debug nhầm hướng (vd nghĩ là lỗi audio/code).

    Tổng quát hoá từ message gốc của `groq_provider.py` (CONTRACTS.md Mục
    4) để dùng chung cho cả 3 provider — với Groq, gọi hàm này với đúng
    `env_var_name="GROQ_API_KEY"`/`keys_url="https://console.groq.com/keys"`
    tạo ra ĐÚNG message như bản gốc (test cũ kiểm tra theo substring, không
    đổi hành vi).
    """
    return (
        f"{provider_label} {api_label} API từ chối API key (lỗi 401 - Invalid "
        "API Key). Đây là lỗi CẤU HÌNH, không phải lỗi audio/code: (1) vào ⚙️ "
        "Cài đặt trong app kiểm tra lại key đã dán đủ ký tự, không dính dấu "
        f"ngoặc/khoảng trắng thừa (hoặc nếu đang dev từ source: mở file .env, "
        f"kiểm tra biến {env_var_name}); (2) vào {keys_url} xem key còn tồn "
        "tại/chưa bị revoke; (3) nếu vừa tạo key mới, nhớ lưu lại trong Settings "
        f"(hoặc file .env) rồi chạy lại app (key cũ không tự refresh). Lỗi gốc: {exc}"
    )


def _call_with_rate_limit_fallback(
    call_fn: Any, primary_model: str, fallback_model: str, error_label: str,
) -> tuple[Any, str]:
    """Gọi `call_fn(model)` với `primary_model` trước; nếu server trả 429
    (`openai.RateLimitError` — đúng nghĩa "hết quota free tier ở model này
    NGAY LÚC NÀY", KHÁC với 400/401/lỗi mạng), tự động thử lại NGAY 1 lần
    với `fallback_model`. KHÔNG fallback cho bất kỳ lỗi nào khác — đổi
    model không giải quyết được lỗi auth/network/bad-request, fallback
    trong các trường hợp đó chỉ che giấu lỗi thật + tốn thêm 1 lượt gọi.

    Trả về `(response, model_đã_dùng)`.

    Nếu `fallback_model` CŨNG bị 429 (hoặc trùng `primary_model`, tức
    không có fallback thật), để lỗi RateLimitError đó tự bay lên cho
    caller xử lý như mọi lỗi khác — KHÔNG lặp vô hạn, KHÔNG tự bịa kết
    quả giả khi cả 2 model đều hết quota.

    ⚠️ Dùng được CHUNG cho Groq/OpenAI/Gemini-qua-lớp-tương-thích vì cả 3
    đều đi qua CÙNG 1 SDK `openai` -- exception `openai.RateLimitError`
    được SDK raise dựa trên HTTP status code (429) của response nhận
    được, KHÔNG phụ thuộc server thật là Groq/OpenAI/Google. Vẫn CHƯA
    verify được 100% Google trả đúng status code 429 (so với có thể trả
    400/khác) cho trường hợp hết quota qua lớp tương thích này — cần bạn
    tự quan sát log thật nếu dùng Gemini và gặp giới hạn free tier.
    """
    try:
        return call_fn(primary_model), primary_model
    except openai.RateLimitError:
        if not fallback_model or fallback_model == primary_model:
            raise
        return call_fn(fallback_model), fallback_model


class OpenAICompatProvider(AIProvider):
    """Phần CHUNG của mọi provider đi qua SDK `openai` cho phần chat
    (translate/suggest_answer/summarize) -- KHÔNG tự implement
    `transcribe()` (để subclass quyết định, xem docstring đầu file).

    Subclass PHẢI set trước khi gọi các method chat:
        self._client: instance `openai.OpenAI` đã trỏ đúng base_url + key.
        self._translate_model: str — model chat ưu tiên.
        self._translate_fallback_model: str — model chat dự phòng khi 429
            (đặt "" hoặc bằng `_translate_model` để tắt fallback).
        self._provider_label: str — tên hiển thị trong message lỗi (vd
            "Groq", "OpenAI", "Gemini").
    """

    _provider_label: str = "AI"

    def _chat_complete(
        self, messages: list[dict], error_label: str, temperature: float,
        response_format: dict | None = None,
    ) -> str:
        """Helper nội bộ dùng chung cho translate()/suggest_answer()/
        summarize() — gọi chat.completions.create + xử lý lỗi + parse
        content, tránh lặp code (cùng pattern gọi/parse, chỉ khác prompt).

        `response_format`: dùng cho summarize() để bắt model trả JSON đúng
        cấu trúc (`{"type": "json_object"}`) — model OpenAI-compatible hỗ
        trợ tham số này sẽ tuân thủ chặt hơn là chỉ "yêu cầu" JSON trong
        prompt. translate()/suggest_answer() không cần (trả text thường).
        """
        def _call(model: str):
            kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
            if response_format is not None:
                kwargs["response_format"] = response_format
            return self._client.chat.completions.create(**kwargs)

        try:
            response, _used_model = _call_with_rate_limit_fallback(
                _call, self._translate_model, self._translate_fallback_model, error_label,
            )
        except openai.AuthenticationError as exc:
            raise ProviderError(self._auth_error_hint(error_label, exc)) from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"{self._provider_label} {error_label} API lỗi: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"{self._provider_label} {error_label} lỗi không xác định: {exc}") from exc

        choices = getattr(response, "choices", None)
        if not choices:
            raise ProviderError(
                f"{self._provider_label} {error_label} trả về response rỗng, không có choices."
            )
        content = choices[0].message.content
        if content is None:
            raise ProviderError(f"{self._provider_label} {error_label} trả về content rỗng.")
        return content.strip()

    def _auth_error_hint(self, api_label: str, exc: Exception) -> str:
        """Subclass override để truyền đúng `env_var_name`/`keys_url` của
        chính nó vào `_auth_error_hint()` (hàm module-level ở trên)."""
        raise NotImplementedError

    def translate(
        self, text: str, source_lang: str, target_lang: str, context_text: str = ""
    ) -> str:
        """Xem docstring đầy đủ ở AIProvider.translate().

        ⚠️ Lịch sử sửa prompt đầy đủ (4 lần, sau phản hồi test thật) —
        xem `CONTRACTS.md` + lịch sử trước khi `openai_compat_base.py`
        tồn tại (README.md mục "Lịch sử sửa lỗi", Vòng 1-4) — KHÔNG lặp
        lại ở đây, logic/text GIỮ NGUYÊN 100%, chỉ đổi vị trí file.
        """
        source_name = _language_name(source_lang)
        target_name = _language_name(target_lang)
        system_prompt = (
            f"You are interpreting live spoken conversation in real time, NOT "
            f"translating a written document. Translate the user's {source_name} "
            f"text into natural, idiomatic {target_name} — the way a native "
            f"speaker would actually SAY it out loud in this exact situation, not "
            f"a literal word-for-word translation. Preserve the original meaning "
            f"and tone precisely; do not add or drop information.\n\n"
            f"To sound like a real bilingual interpreter instead of a literal "
            f"converter, follow these 4 rules:\n"
            f"1. Reflow sentence structure freely — {target_name} often orders "
            f"ideas differently than {source_name}. You may merge two short "
            f"source sentences, split one long one, or reorder clauses, AS LONG "
            f"AS every piece of meaning survives and nothing is added.\n"
            f"2. Translate idioms, fixed expressions, and filler speech "
            f"(\"you know\", \"like\", \"I mean\", hedges, hesitations) into the "
            f"equivalent NATURAL expression or natural spoken filler a "
            f"{target_name} speaker would actually use in that spot — never "
            f"render them word-for-word if a literal rendering would sound "
            f"foreign or stilted.\n"
            f"3. Match register and tone exactly: casual stays casual (use "
            f"contractions/colloquial wording where natural), formal stays "
            f"formal — do not upgrade casual speech into stiff written-style "
            f"{target_name}, and do not invent a tone that wasn't there.\n"
            f"4. Prefer the phrasing an ordinary {target_name} speaker would use "
            f"in daily conversation over the most literal dictionary-accurate "
            f"phrasing, whenever both convey the same meaning — natural beats "
            f"literal.\n\n"
            f"CRITICAL — preserve grammatical person and direction of address "
            f"EXACTLY as in the original: if the original speaks TO someone "
            f"(\"you\"), the translation must still speak TO that same someone — "
            f"never shift it into the speaker's own first-person voice ('I/me'), "
            f"and never shift between 'I' and 'you' in either direction. Keep "
            f"who-is-speaking-to-whom identical to the source, even across a "
            f"long passage with multiple sentences. This rule is NEVER "
            f"overridden by the naturalness rules above.\n\n"
            f"You may be given some PRIOR conversation context before the actual "
            f"text to translate. Use it ONLY to pick natural, consistent wording "
            f"(matching terminology, tone, and flow already established in the "
            f"conversation) — do NOT translate the context itself, and do NOT "
            f"mention or repeat it in your output.\n\n"
            f"Output ONLY the translated text of the marked portion, with no "
            f"explanation, no quotes, no extra text."
        )
        if context_text:
            user_content = (
                f"[Prior context, do NOT translate this part — for your "
                f"understanding only]\n{context_text}\n\n"
                f"[Translate ONLY this part]\n{text}"
            )
        else:
            user_content = text
        return self._chat_complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            error_label="translate",
            temperature=0.3,
        )

    def suggest_answer(
        self, question_text: str, context_text: str, user_native_lang: str
    ) -> str:
        """Xem docstring đầy đủ ở AIProvider.suggest_answer().

        🔒 Logic + prompt GIỮ NGUYÊN 100% so với `groq_provider.py` trước
        đợt refactor multi-provider — bao gồm lưới an toàn chống trả lời
        sai ngôn ngữ (CONTRACTS.md Mục 15), chỉ đổi vị trí file để dùng
        CHUNG cho Groq/OpenAI/Gemini.
        """
        native_name = _language_name(user_native_lang)
        system_prompt = self._build_suggest_answer_system_prompt(native_name)
        user_content = (
            f"Recent conversation context:\n{context_text}\n\n"
            f"What was just said (needs a response): {question_text}\n\n"
            f"(Reminder: your reply must be written in {native_name}, no "
            f"matter what language the text above is in.)"
        )
        answer = self._chat_complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            error_label="suggest_answer",
            temperature=0.4,
        )
        if _looks_like_wrong_script(answer, user_native_lang):
            forceful_user_content = (
                f"{user_content}\n\n"
                f"CRITICAL CORRECTION NEEDED: your previous attempt was "
                f"rejected because it was NOT written in {native_name} — it "
                f"mirrored the conversation's language instead. Try again. "
                f"This time your ENTIRE reply must be in {native_name} ONLY, "
                f"with no Chinese/Japanese/Korean characters unless "
                f"{native_name} itself is written with them."
            )
            answer = self._chat_complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": forceful_user_content},
                ],
                error_label="suggest_answer",
                temperature=0.2,
            )
        return answer

    @staticmethod
    def _build_suggest_answer_system_prompt(native_name: str) -> str:
        """Tách riêng thành method để TÁI DÙNG nguyên giữa lần gọi đầu và
        lần retry (CONTRACTS.md Mục 15) — tránh lặp đoạn prompt dài 2 lần
        trong suggest_answer(), dễ đọc/sửa hơn khi cần tinh chỉnh tiếp."""
        return (
            f"OUTPUT LANGUAGE RULE (read this first, it overrides everything "
            f"else below): write your ENTIRE reply in {native_name}, no "
            f"matter what language the conversation below is in. Whether the "
            f"conversation is in English, Chinese, Japanese, Korean, or any "
            f"other language, that does NOT change your output language — "
            f"it is ALWAYS {native_name}. Never mirror or switch into the "
            f"conversation's language.\n\n"
            f"You are drafting what a non-native speaker should SAY OUT LOUD "
            f"RIGHT NOW, in response to something just said to them in a live "
            f"meeting. They will read this almost immediately — this is spoken "
            f"reply material, not a written essay.\n\n"
            f"Output ONLY the reply itself, in {native_name}, as if they are "
            f"about to say it. NEVER start with throat-clearing like \"I "
            f"appreciate this question\", \"That's interesting\", \"Let me "
            f"think about this\", or any description of your own reasoning "
            f"process — go straight to the substance.\n\n"
            f"Rule 1: if this is general/factual/technical knowledge you "
            f"genuinely know (concepts, definitions, how something works), "
            f"answer it DIRECTLY and ACCURATELY. Do not stall or hedge on "
            f"things you actually know.\n"
            f"Rule 2: if it needs SPECIFIC personal/company facts you cannot "
            f"know (exact numbers, names, dates, decisions tied to their "
            f"situation), do not invent them — say what you reasonably can, "
            f"and insert ONE short bracketed placeholder WRITTEN IN "
            f"{native_name} for the missing specific (the equivalent of "
            f"\"[exact number]\"), so they can fill it in in one second.\n"
            f"Rule 3: 1-3 short sentences, natural spoken {native_name}, the "
            f"way a real person actually talks in a meeting — not a list, not "
            f"formal written style.\n\n"
            f"The text below may be a clean question, a question cut off "
            f"mid-sentence, or just a remark needing a follow-up — live "
            f"speech is messy, and it may be in ANY language. Use it ONLY to "
            f"figure out what response is needed — your OUTPUT is still "
            f"always {native_name} per the rule above, regardless of the "
            f"conversation's language.\n\n"
            f"Output ONLY the reply text, no explanation, no quotes — and "
            f"remember: {native_name} only, never the conversation's language."
        )

    def summarize(self, transcript_text: str, user_native_lang: str) -> SummaryResult:
        """🔒 Xem docstring đầy đủ ở AIProvider.summarize(). Logic GIỮ
        NGUYÊN 100% so với `groq_provider.py` trước đợt refactor — bao gồm
        lý do dùng JSON array of strings cho decisions/action_items (xem
        CONTRACTS.md Mục 4), chỉ đổi vị trí file.
        """
        native_name = _language_name(user_native_lang)
        system_prompt = (
            f"You are summarizing a real, live-transcribed meeting for someone "
            f"who could not take full notes themselves. The transcript may "
            f"contain speech-recognition errors, sentence fragments, or mixed "
            f"languages — use your best judgment to understand what was "
            f"actually meant, but do NOT invent information that isn't there.\n\n"
            f"Write the summary in {native_name}, regardless of what language(s) "
            f"the transcript is in. Be concise and factual.\n\n"
            f"Respond with a JSON object with EXACTLY these 3 keys:\n"
            f'- "overview": a single string, 2-5 sentences, summarizing what was '
            f"discussed, in {native_name}.\n"
            f'- "decisions": a JSON ARRAY of short strings, one per decision '
            f"actually made (each string is ONE concrete decision, no line "
            f'breaks inside it). If no clear decision was made, return an EMPTY '
            f"array `[]` — do NOT invent one just to fill the list.\n"
            f'- "action_items": a JSON ARRAY of short strings, one per action '
            f"item or follow-up actually mentioned (include who is responsible "
            f"if that was mentioned, inside the same short string). If none, "
            f"return an EMPTY array `[]`.\n\n"
            f"Output ONLY the JSON object, no explanation, no markdown code fences."
        )
        raw = self._chat_complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript_text},
            ],
            error_label="summarize",
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"{self._provider_label} summarize trả về JSON không hợp lệ: "
                f"{exc}. Nội dung thô: {raw[:300]!r}"
            ) from exc

        missing = [k for k in ("overview", "decisions", "action_items") if k not in parsed]
        if missing:
            raise ProviderError(
                f"{self._provider_label} summarize trả JSON thiếu field {missing} "
                f"(nhận được: {list(parsed.keys())})."
            )

        return SummaryResult(
            overview=str(parsed["overview"]).strip(),
            decisions=_coerce_to_string_list(parsed["decisions"], "decisions", self._provider_label),
            action_items=_coerce_to_string_list(
                parsed["action_items"], "action_items", self._provider_label
            ),
        )
