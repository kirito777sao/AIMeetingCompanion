"""
Unit test cho app/audio/vad.py — KHÔNG dùng webrtcvad thật (vì kết quả phân
loại speech/silence của 1 mô hình thật trên audio synthetic không đáng tin
cậy để assert). Thay vào đó, monkeypatch `segmenter._vad` bằng 1 fake VAD có
hành vi is_speech() điều khiển được hoàn toàn theo 1 list True/False định
trước -- mục tiêu là test ĐÚNG logic state machine (feed/flush, pre-buffer,
cắt theo silence, cắt theo max_length), không test độ chính xác của webrtcvad.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from app.audio.vad import VadSegmenter, create_vad_segmenter_from_env  # noqa: E402


class FakeVad:
    """VAD giả: trả về is_speech theo 1 sequence cố định, gọi quá số lần
    chuẩn bị sẽ raise lỗi rõ ràng (để bắt lỗi test tự viết sai, không phải
    lỗi code thật)."""

    def __init__(self, pattern):
        self._pattern = list(pattern)
        self._i = 0

    def is_speech(self, frame_bytes, sample_rate):
        if self._i >= len(self._pattern):
            raise AssertionError(
                f"FakeVad bị gọi quá số lần chuẩn bị ({len(self._pattern)}). "
                "Test setup sai, không phải lỗi VadSegmenter."
            )
        val = self._pattern[self._i]
        self._i += 1
        return val


def make_segmenter(pattern, **kwargs):
    seg = VadSegmenter(**kwargs)
    seg._vad = FakeVad(pattern)  # ghi đè VAD thật bằng FakeVad có kiểm soát
    return seg


def frames_of(n_frames, frame_samples):
    """Sinh n_frames frame audio (mỗi frame là 1 mảng riêng) để feed() từng
    cái một -- mô phỏng đúng cách feed() thực sự được gọi (mỗi lần 1 lượng
    nhỏ, không phải nguyên cục lớn)."""
    return [np.zeros(frame_samples, dtype=np.float32) for _ in range(n_frames)]


def test_silence_only_khong_tra_segment():
    # samplerate=16000, frame_ms=20 -> frame_size = 320 samples
    seg = make_segmenter(pattern=[False] * 30, samplerate=16000, frame_ms=20)
    finished = []
    for fr in frames_of(30, 320):
        finished += seg.feed(fr)
    assert finished == [], "Toàn bộ là im lặng thì không được chốt segment nào."
    assert seg.flush() is None, "flush() khi không có speech đang mở phải trả None."
    print("OK: test_silence_only_khong_tra_segment")


def test_speech_qua_ngan_bi_bo_vi_duoi_min_speech_ms():
    # min_speech_ms=250 mặc định với frame_ms=20 -> cần >= 13 frame speech.
    # Ở đây chỉ có 3 frame speech rồi im lặng dài -> phải bị loại (None), không trả segment.
    pattern = [False, False] + [True, True, True] + [False] * 35
    seg = make_segmenter(pattern=pattern, samplerate=16000, frame_ms=20,
                         silence_ms=600, min_speech_ms=250, padding_ms=200)
    finished = []
    for fr in frames_of(len(pattern), 320):
        finished += seg.feed(fr)
    assert finished == [], (
        f"Đoạn speech chỉ 3 frame (60ms) < min_speech_ms=250ms phải bị loại, "
        f"nhưng lại trả {len(finished)} segment."
    )
    print("OK: test_speech_qua_ngan_bi_bo_vi_duoi_min_speech_ms")


def test_speech_du_dai_duoc_chot_dung_sau_khoang_lang():
    # frame_ms=20, silence_ms=600 -> 30 frame im lặng liên tiếp thì chốt.
    # min_speech_ms=250 -> cần >=13 frame speech để không bị loại.
    n_pre_silence = 5
    n_speech = 20
    n_silence_after = 30  # đúng bằng silence_frames_limit -> phải trigger chốt
    pattern = [False] * n_pre_silence + [True] * n_speech + [False] * n_silence_after
    seg = make_segmenter(pattern=pattern, samplerate=16000, frame_ms=20,
                         silence_ms=600, min_speech_ms=250, padding_ms=200)

    finished = []
    for fr in frames_of(len(pattern), 320):
        finished += seg.feed(fr)

    assert len(finished) == 1, f"Phải chốt đúng 1 segment, nhận được {len(finished)}."
    seg_audio = finished[0]
    # padding_ms=200, frame_ms=20 -> padding_frames=10.
    # Độ dài kỳ vọng: pre_buffer (tối đa padding_frames=10, nhưng chỉ có 5 frame im
    # lặng trước đó nên pre_buffer=5) + n_speech (20) + keep_silence (min(30,10)=10)
    expected_frames = 5 + n_speech + 10
    assert seg_audio.shape[0] == expected_frames * 320, (
        f"Độ dài segment sai: kỳ vọng {expected_frames * 320} samples, "
        f"nhận được {seg_audio.shape[0]}."
    )
    print("OK: test_speech_du_dai_duoc_chot_dung_sau_khoang_lang")


def test_max_segment_ms_ep_cat_khi_noi_lien_tuc_khong_ngung():
    # max_segment_ms=2000ms, frame_ms=20 -> max_segment_frames=100.
    # Cho speech liên tục 150 frame (3s) không có im lặng -> phải bị ép cắt ở frame 100.
    pattern = [True] * 150
    seg = make_segmenter(pattern=pattern, samplerate=16000, frame_ms=20,
                         silence_ms=600, min_speech_ms=250, max_segment_ms=2000,
                         padding_ms=200)
    finished = []
    for fr in frames_of(150, 320):
        finished += seg.feed(fr)

    assert len(finished) >= 1, "Phải có ít nhất 1 segment bị ép cắt do max_segment_ms."
    assert finished[0].shape[0] == 100 * 320, (
        f"Segment đầu tiên phải bị cắt đúng ở max_segment_frames=100 frame, "
        f"nhận được {finished[0].shape[0] // 320} frame."
    )
    print("OK: test_max_segment_ms_ep_cat_khi_noi_lien_tuc_khong_ngung")


def test_flush_tra_ve_doan_noi_dang_mo():
    # Speech đủ dài (>= min_speech_ms) nhưng KHÔNG có khoảng lặng theo sau
    # (cuộc họp kết thúc giữa câu) -> flush() phải trả về đoạn đó, feed() không trả.
    pattern = [True] * 20
    seg = make_segmenter(pattern=pattern, samplerate=16000, frame_ms=20,
                         silence_ms=600, min_speech_ms=250, padding_ms=200)
    finished = []
    for fr in frames_of(20, 320):
        finished += seg.feed(fr)
    assert finished == [], "feed() chưa có khoảng lặng thì chưa được tự chốt."

    flushed = seg.flush()
    assert flushed is not None, "flush() phải trả về đoạn nói đang mở (đủ dài)."
    assert flushed.shape[0] == 20 * 320
    assert seg.flush() is None, "flush() lần 2 (sau khi đã reset) phải trả None."
    print("OK: test_flush_tra_ve_doan_noi_dang_mo")


def test_feed_reject_khong_phai_mono():
    seg = make_segmenter(pattern=[False], samplerate=16000, frame_ms=20)
    try:
        seg.feed(np.zeros((10, 2), dtype=np.float32))
        raise AssertionError("Phải raise VadSegmenterError khi feed() audio không phải mono 1D.")
    except Exception as e:
        assert "mono" in str(e).lower() or "shape" in str(e).lower()
    print("OK: test_feed_reject_khong_phai_mono")


def test_default_silence_ms_la_350():
    seg = VadSegmenter(samplerate=16000, frame_ms=20)
    assert seg._silence_frames_limit == round(350 / 20), (
        "Default silence_ms phải là 350ms sau khi chỉnh (xem docstring VadSegmenter)."
    )
    print("OK: test_default_silence_ms_la_350")


def test_default_max_segment_ms_la_8000():
    # 🔒 MỚI (CONTRACTS.md Mục 16) -- giảm từ 15000ms xuống 8000ms sau phản
    # hồi test thật: delay 6-9s khi audio không có khoảng lặng rõ ràng ngay
    # lúc chuyển ngôn ngữ/tab (VAD phải đợi tới trần này mới ép cắt, segment
    # dài hơn -> transcribe()+translate() lâu hơn). Xem docstring đầy đủ ở
    # VadSegmenter.__init__ (tham số max_segment_ms).
    seg = VadSegmenter(samplerate=16000, frame_ms=20)
    assert seg._max_segment_frames == round(8000 / 20), (
        "Default max_segment_ms phải là 8000ms sau khi chỉnh (xem CONTRACTS.md Mục 16)."
    )
    print("OK: test_default_max_segment_ms_la_8000")


def test_ngan_400ms_giua_2_luot_noi_tach_duoc_voi_nguong_moi_nhung_khong_voi_nguong_cu():
    # Mô phỏng đúng tình huống thật gặp phải (2 host podcast nói nối tiếp,
    # khoảng nghỉ ~400ms giữa lượt nói -- với silence_ms=600 (cũ) sẽ KHÔNG
    # đủ để chốt segment giữa 2 lượt, với silence_ms=350 (mới) sẽ chốt được.
    frame_ms = 20
    n_speech_1 = 20         # lượt nói 1: 400ms
    n_gap = 20               # khoảng nghỉ: 400ms (20 frame x 20ms)
    n_speech_2 = 20          # lượt nói 2: 400ms
    n_trailing_silence = 40  # đủ dài để chốt nốt lượt nói 2 ở CẢ 2 cấu hình

    pattern = [True] * n_speech_1 + [False] * n_gap + [True] * n_speech_2 + [False] * n_trailing_silence

    # --- Ngưỡng MỚI (350ms = 17.5 -> 18 frame) -> 400ms gap (20 frame) ĐỦ để cắt ---
    seg_new = make_segmenter(pattern=list(pattern), samplerate=16000, frame_ms=frame_ms,
                             silence_ms=350, min_speech_ms=250, padding_ms=100)
    events_new = []
    for fr in frames_of(len(pattern), 320):
        events_new += seg_new.feed(fr)
    assert len(events_new) == 2, (
        f"Với silence_ms=350, khoảng nghỉ 400ms phải đủ để tách thành 2 segment riêng, "
        f"nhận {len(events_new)}."
    )

    # --- Ngưỡng CŨ (600ms = 30 frame) -> 400ms gap (20 frame) KHÔNG đủ -> gộp thành 1 ---
    seg_old = make_segmenter(pattern=list(pattern), samplerate=16000, frame_ms=frame_ms,
                             silence_ms=600, min_speech_ms=250, padding_ms=100)
    events_old = []
    for fr in frames_of(len(pattern), 320):
        events_old += seg_old.feed(fr)
    assert len(events_old) == 1, (
        f"Với silence_ms=600 (cũ), khoảng nghỉ 400ms KHÔNG đủ để tách -> phải gộp "
        f"thành 1 segment (đúng y bug đã gặp với Anna/Jake), nhận {len(events_old)}."
    )
    print("OK: test_ngan_400ms_giua_2_luot_noi_tach_duoc_voi_nguong_moi_nhung_khong_voi_nguong_cu")


_VAD_ENV_VARS = (
    "VAD_AGGRESSIVENESS", "VAD_SILENCE_MS", "VAD_MIN_SPEECH_MS",
    "VAD_MAX_SEGMENT_MS", "VAD_PADDING_MS",
)


def _clear_vad_env():
    for name in _VAD_ENV_VARS:
        os.environ.pop(name, None)


def test_create_vad_segmenter_from_env_khong_co_env_dung_default_cu():
    # 🔒 MỚI (Mục 27) -- không có biến môi trường nào đặt -> PHẢI giữ
    # ĐÚNG default hiện tại của VadSegmenter.__init__ (KHÔNG đổi hành vi
    # app hiện tại chỉ vì thêm tính năng đọc env).
    _clear_vad_env()
    try:
        seg = create_vad_segmenter_from_env(samplerate=16000)
        assert seg._sr == 16000
        assert seg._vad.__class__.__name__ == "Vad"  # webrtcvad.Vad thật, không phải fake
        # So khớp gián tiếp qua hành vi: default aggressiveness=2 hợp lệ
        # (không raise), silence_ms=350 -> _silence_frames_limit đúng cũ.
        assert seg._silence_frames_limit == VadSegmenter(samplerate=16000)._silence_frames_limit
        assert seg._min_speech_frames == VadSegmenter(samplerate=16000)._min_speech_frames
        assert seg._max_segment_frames == VadSegmenter(samplerate=16000)._max_segment_frames
        assert seg._padding_frames == VadSegmenter(samplerate=16000)._padding_frames
    finally:
        _clear_vad_env()
    print("OK: test_create_vad_segmenter_from_env_khong_co_env_dung_default_cu")


def test_create_vad_segmenter_from_env_doc_dung_gia_tri_da_dat():
    _clear_vad_env()
    try:
        os.environ["VAD_AGGRESSIVENESS"] = "3"
        os.environ["VAD_SILENCE_MS"] = "500"
        os.environ["VAD_MIN_SPEECH_MS"] = "300"
        os.environ["VAD_MAX_SEGMENT_MS"] = "6000"
        os.environ["VAD_PADDING_MS"] = "150"
        seg = create_vad_segmenter_from_env(samplerate=16000)
        expected = VadSegmenter(
            samplerate=16000, aggressiveness=3, silence_ms=500,
            min_speech_ms=300, max_segment_ms=6000, padding_ms=150,
        )
        assert seg._silence_frames_limit == expected._silence_frames_limit
        assert seg._min_speech_frames == expected._min_speech_frames
        assert seg._max_segment_frames == expected._max_segment_frames
        assert seg._padding_frames == expected._padding_frames
    finally:
        _clear_vad_env()
    print("OK: test_create_vad_segmenter_from_env_doc_dung_gia_tri_da_dat")


def test_create_vad_segmenter_from_env_gia_tri_sai_dinh_dang_fallback_default():
    # Gõ nhầm .env (vd "abc" thay vì số) KHÔNG được làm app crash -- phải
    # fallback về default, không raise.
    _clear_vad_env()
    try:
        os.environ["VAD_AGGRESSIVENESS"] = "not-a-number"
        os.environ["VAD_SILENCE_MS"] = ""
        seg = create_vad_segmenter_from_env(samplerate=16000)
        default = VadSegmenter(samplerate=16000)
        assert seg._silence_frames_limit == default._silence_frames_limit
    finally:
        _clear_vad_env()
    print("OK: test_create_vad_segmenter_from_env_gia_tri_sai_dinh_dang_fallback_default")


if __name__ == "__main__":
    test_silence_only_khong_tra_segment()
    test_speech_qua_ngan_bi_bo_vi_duoi_min_speech_ms()
    test_speech_du_dai_duoc_chot_dung_sau_khoang_lang()
    test_max_segment_ms_ep_cat_khi_noi_lien_tuc_khong_ngung()
    test_flush_tra_ve_doan_noi_dang_mo()
    test_feed_reject_khong_phai_mono()
    test_default_silence_ms_la_350()
    test_default_max_segment_ms_la_8000()
    test_ngan_400ms_giua_2_luot_noi_tach_duoc_voi_nguong_moi_nhung_khong_voi_nguong_cu()
    test_create_vad_segmenter_from_env_khong_co_env_dung_default_cu()
    test_create_vad_segmenter_from_env_doc_dung_gia_tri_da_dat()
    test_create_vad_segmenter_from_env_gia_tri_sai_dinh_dang_fallback_default()
    print("\n=== TẤT CẢ TEST VAD PASS ===")
