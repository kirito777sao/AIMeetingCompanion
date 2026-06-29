"""
Unit test cho app/audio/capture.py -- PHẦN MỚI: phát hiện đổi default
playback device giữa lúc đang ghi (AudioDeviceChangedError, CONTRACTS.md
Mục 14).

⚠️ Test này mock TOÀN BỘ package `soundcard` (không có audio hardware thật
trong sandbox/CI) -- verify được ĐÚNG LOGIC phát hiện đổi device, KHÔNG
verify được hành vi WASAPI thật trên Windows (vd format `speaker.id` thật
trả về từ Windows có đúng như giả định không). Cần bạn tự test lại trên
Windows thật theo README.md mục checklist mới (đổi thiết bị phát giữa lúc
ghi, xem app có tiếp tục nhận diện được không, có log/biểu hiện gì bất
thường không).

KHÔNG test `_stream_with_pyaudiowpatch` (logic tương tự nhưng mock
pyaudiowpatch phức tạp hơn nhiều do dùng callback + queue + nhiều field
device dict) -- chấp nhận rủi ro chưa test nhánh đó, ưu tiên thời gian cho
nhánh soundcard (mặc định/ưu tiên thử trước theo `order` ở
`stream_loopback_chunks()`).
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402


class _FakeSpeaker:
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


class _FakeRecorder:
    """Mock context manager cho `mic.recorder(...)`. Mỗi `.record()` trả
    về numframes frame stereo float32 = 0 (im lặng -- nội dung audio không
    quan trọng cho test này, chỉ test logic phát hiện đổi device)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def record(self, numframes):
        return np.zeros((numframes, 2), dtype=np.float32)


class _FakeMic:
    def recorder(self, samplerate, channels):
        return _FakeRecorder()


def _install_fake_soundcard(speaker_sequence):
    """Cài 1 module `soundcard` giả vào sys.modules. `speaker_sequence` là
    list các _FakeSpeaker sẽ được trả về LẦN LƯỢT qua các lần gọi
    `default_speaker()` (lần gọi cuối lặp lại giá trị cuối list)."""
    calls = {"count": 0}

    def default_speaker():
        idx = min(calls["count"], len(speaker_sequence) - 1)
        calls["count"] += 1
        return speaker_sequence[idx]

    def get_microphone(id, include_loopback=True):
        return _FakeMic()

    fake_module = types.ModuleType("soundcard")
    fake_module.default_speaker = default_speaker
    fake_module.get_microphone = get_microphone
    sys.modules["soundcard"] = fake_module


def _remove_fake_soundcard():
    sys.modules.pop("soundcard", None)


def test_khong_doi_device_thi_khong_raise_qua_nhieu_chunk():
    from app.audio.capture import AudioDeviceChangedError, _stream_with_soundcard

    speaker = _FakeSpeaker("dev-A", "Loa A")
    # default_speaker() được gọi: 1 lần lúc mở stream + ĐỊNH KỲ mỗi
    # check_every_n_chunks (=10 với chunk_ms=100) -- giả lập device GIỮ
    # NGUYÊN xuyên suốt nhiều lần gọi.
    _install_fake_soundcard([speaker] * 200)
    try:
        gen = _stream_with_soundcard(target_sr=16000, chunk_ms=100, mono=True)
        for _ in range(35):  # > 3 lần check_every_n_chunks (10) -- đủ để bắt sai nếu có
            chunk = next(gen)
            assert chunk.dtype == np.float32
    finally:
        _remove_fake_soundcard()
    print("OK: test_khong_doi_device_thi_khong_raise_qua_nhieu_chunk")


def test_doi_device_giua_luc_dang_doc_raise_dung_loai_loi():
    from app.audio.capture import AudioDeviceChangedError, _stream_with_soundcard

    speaker_a = _FakeSpeaker("dev-A", "Loa A")
    speaker_b = _FakeSpeaker("dev-B", "Tai nghe Bluetooth B")
    # Lần gọi đầu (lúc mở stream) trả speaker_a. Các lần SAU (lúc kiểm tra
    # định kỳ) trả speaker_b -- mô phỏng ĐÚNG kịch bản "đổi device giữa
    # lúc đang ghi".
    _install_fake_soundcard([speaker_a] + [speaker_b] * 200)
    try:
        gen = _stream_with_soundcard(target_sr=16000, chunk_ms=100, mono=True)
        raised = False
        try:
            for _ in range(15):  # check_every_n_chunks=10 với chunk_ms=100 -- chắc chắn fire trong 15 lần
                next(gen)
        except AudioDeviceChangedError as exc:
            raised = True
            assert "Loa A" in str(exc) and "Bluetooth B" in str(exc), (
                f"Message nên nêu rõ TÊN device cũ/mới để dễ debug, nhận: {exc}"
            )
        assert raised, "Phải raise AudioDeviceChangedError khi device đổi giữa lúc đang ghi."
    finally:
        _remove_fake_soundcard()
    print("OK: test_doi_device_giua_luc_dang_doc_raise_dung_loai_loi")


def test_audio_device_changed_error_la_subclass_cua_audio_capture_error():
    # Đảm bảo code cũ bắt `except AudioCaptureError` (vd record_system_audio())
    # vẫn vô tình bắt được luôn AudioDeviceChangedError nếu lỡ gọi nhầm chỗ
    # -- KHÔNG để lỗi mới này "lách" qua mọi except AudioCaptureError đã có.
    from app.audio.capture import AudioCaptureError, AudioDeviceChangedError

    assert issubclass(AudioDeviceChangedError, AudioCaptureError)
    print("OK: test_audio_device_changed_error_la_subclass_cua_audio_capture_error")


def test_stream_loopback_chunks_khong_nuot_audio_device_changed_error_de_doi_lib():
    # 🔒 QUAN TRỌNG -- xem comment trong stream_loopback_chunks(): KHÁC với
    # mọi exception khác (bị nuốt để "thử lib kế tiếp"), AudioDeviceChangedError
    # PHẢI raise THẲNG lên caller, KHÔNG được âm thầm chuyển sang
    # pyaudiowpatch. Test bằng cách buộc prefer="soundcard" (chỉ 1 lib
    # trong `order`, nên dù có nuốt hay không cũng raise -- test này chủ
    # yếu khẳng định ĐÚNG LOẠI exception thoát ra, không bị wrap lại thành
    # AudioCaptureError generic mất thông tin gốc).
    import app.audio.capture as capture_module
    from app.audio.capture import AudioDeviceChangedError, stream_loopback_chunks

    speaker_a = _FakeSpeaker("dev-A", "Loa A")
    speaker_b = _FakeSpeaker("dev-B", "Loa B")
    _install_fake_soundcard([speaker_a] + [speaker_b] * 200)
    # stream_loopback_chunks() gọi _assert_windows() đầu tiên -- sandbox
    # test này chạy Linux, giả lập "đang chạy Windows" CHỈ trong test này
    # để vượt qua guard đó (KHÔNG liên quan logic đang test: phát hiện đổi
    # device). Khôi phục lại giá trị gốc trong finally.
    original_platform_system = capture_module.platform.system
    capture_module.platform.system = lambda: "Windows"
    try:
        gen = stream_loopback_chunks(target_samplerate=16000, chunk_ms=100, prefer="soundcard")
        raised_type = None
        try:
            for _ in range(15):
                next(gen)
        except Exception as exc:  # noqa: BLE001 - cần bắt để kiểm tra ĐÚNG type
            raised_type = type(exc)
        assert raised_type is AudioDeviceChangedError, (
            f"Phải raise ĐÚNG AudioDeviceChangedError (không bị wrap lại "
            f"thành AudioCaptureError generic), nhận {raised_type}."
        )
    finally:
        capture_module.platform.system = original_platform_system
        _remove_fake_soundcard()
    print("OK: test_stream_loopback_chunks_khong_nuot_audio_device_changed_error_de_doi_lib")


if __name__ == "__main__":
    test_khong_doi_device_thi_khong_raise_qua_nhieu_chunk()
    test_doi_device_giua_luc_dang_doc_raise_dung_loai_loi()
    test_audio_device_changed_error_la_subclass_cua_audio_capture_error()
    test_stream_loopback_chunks_khong_nuot_audio_device_changed_error_de_doi_lib()
    print("\n=== TẤT CẢ TEST CAPTURE (mock soundcard) PASS ===")
