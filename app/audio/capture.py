"""
audio/capture.py
-----------------
Phase 0: thu âm "loopback" — tức là ghi lại âm thanh hệ thống ĐANG PHÁT RA LOA
(âm Zoom/Teams/Meet, video YouTube, v.v.), KHÔNG phải ghi từ micro.

Chiến lược 2 lớp (đúng theo TECH STACK bắt buộc trong spec):
  1) Thử `soundcard` trước (đơn giản, cross-platform-ish, nhưng đôi khi
     loopback trên Windows không ổn định ở vài driver).
  2) Nếu lỗi -> fallback sang `pyaudiowpatch` (dùng WASAPI loopback trực
     tiếp, ổn định hơn trên Windows nhưng chỉ chạy được trên Windows).

Vì sao tách thành 2 hàm riêng + 1 hàm điều phối: để ai/base_provider.py và
UI ở các Phase sau KHÔNG BAO GIỜ cần biết đang dùng lib nào — chỉ gọi
record_system_audio() hoặc (ở Phase 1) stream_loopback_chunks().

Phase 1 bổ sung: stream_loopback_chunks() — generator audio liên tục dùng
cho vad.py. Hợp đồng (xem CONTRACTS.md Mục 2): mọi chunk trả ra LUÔN là
float32 [-1,1], mono, đã resample về target_samplerate — bất kể device gốc
là bao nhiêu channel/Hz. Lý do chuẩn hoá ngay tại lớp audio (không đẩy qua
vad.py): webrtcvad/Silero VAD và Groq Whisper đều làm việc tốt nhất với
mono 16kHz; chuẩn hoá 1 lần duy nhất ở đây giúp vad.py, groq_provider.py,
local_whisper_provider.py không ai phải tự resample lại — tránh trùng logic,
tránch lệch nếu mai sau đổi device/lib audio.
"""

from __future__ import annotations

import platform
import queue
import time
import wave
from pathlib import Path
from typing import Iterator, Optional

import numpy as np


class AudioCaptureError(RuntimeError):
    """Lỗi khi không thể thu âm hệ thống (thiếu quyền, không tìm thấy device, v.v.)."""


class AudioDeviceChangedError(AudioCaptureError):
    """🔒 MỚI -- phản hồi test thật: "đổi sang ứng dụng khác/trình duyệt
    khác để mở thì không nhận diện được, trả về câu rất không liên quan".

    Khác với hầu hết lỗi audio khác (thiết bị mất hẳn, driver lỗi -- những
    lỗi KHÔNG tự phục hồi được), trường hợp NÀY là Windows đã đổi default
    PLAYBACK device giữa lúc đang ghi (vd cắm/rút tai nghe Bluetooth, chuyển
    loa, hoặc 1 app khác chiếm exclusive mode khiến Windows tự đổi default
    output) -- HOÀN TOÀN có thể tự phục hồi: chỉ cần mở lại stream loopback
    trỏ đúng device MỚI là tiếp tục nhận diện bình thường.

    ⚠️ LƯU Ý QUAN TRỌNG về phạm vi sửa thật: WASAPI loopback gắn với 1
    DEVICE đầu ra, KHÔNG gắn với 1 ỨNG DỤNG/TAB nguồn phát. Nếu người dùng
    chỉ đổi TAB/app phát âm thanh nhưng default playback device của Windows
    KHÔNG đổi (cùng loa/tai nghe), lý thuyết loopback vẫn nhận được audio
    như cũ -- lỗi này sẽ KHÔNG fire, và việc "không nhận diện được" khi đó
    PHẢI có nguyên nhân khác (vd chính app/tab mới phát âm lượng quá nhỏ,
    hoặc dùng exclusive mode riêng). CHƯA verify được trên Windows thật
    trong sandbox này (không có audio hardware) -- cần bạn tự test lại
    CHÍNH XÁC theo 2 kịch bản tách biệt khi retest (xem README.md mục
    checklist mới): (a) đổi tab/app nhưng KHÔNG đổi thiết bị phát -- nếu
    vẫn lỗi, đây là lỗi KHÁC, fix này không áp dụng; (b) chủ động đổi
    thiết bị phát (vd Cài đặt > Âm thanh > đổi output, hoặc rút/cắm tai
    nghe) giữa lúc ghi -- đây mới là đúng kịch bản fix này nhằm tới.
    """


def _assert_windows() -> None:
    # Loopback WASAPI chỉ có ý nghĩa trên Windows. Cảnh báo sớm để không tốn
    # thời gian debug trên Linux/Mac.
    if platform.system() != "Windows":
        raise AudioCaptureError(
            "Thu âm loopback hệ thống (WASAPI) chỉ hỗ trợ trên Windows. "
            f"Hệ điều hành hiện tại: {platform.system()}."
        )


def _save_wav(path: str | Path, audio: np.ndarray, samplerate: int) -> None:
    """Lưu numpy array (float32, [-1, 1]) thành file WAV PCM 16-bit chuẩn."""
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    n_channels = audio.shape[1]

    audio_clipped = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_int16.tobytes())


def _record_with_soundcard(output_path: str | Path, duration: float, samplerate: int) -> None:
    import soundcard as sc  # import trong hàm để không bắt buộc cài nếu dùng nhánh fallback

    speaker = sc.default_speaker()
    if speaker is None:
        raise AudioCaptureError("Không tìm thấy speaker (output device) mặc định.")

    # Trên Windows, mic loopback tương ứng CÙNG id với speaker khi include_loopback=True
    mic = sc.get_microphone(id=str(speaker.id), include_loopback=True)
    channels = 2
    chunk_frames = max(samplerate // 10, 1)  # đọc theo từng chunk ~0.1s

    frames = []
    with mic.recorder(samplerate=samplerate, channels=channels) as rec:
        start = time.time()
        while time.time() - start < duration:
            frames.append(rec.record(numframes=chunk_frames))

    audio = np.concatenate(frames, axis=0)
    _save_wav(output_path, audio, samplerate)


def _record_with_pyaudiowpatch(output_path: str | Path, duration: float, samplerate: int) -> None:
    import pyaudiowpatch as pyaudio  # type: ignore

    p = pyaudio.PyAudio()
    try:
        # Lấy WASAPI loopback device tương ứng với output device mặc định
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

        if not default_speakers.get("isLoopbackDevice", False):
            for loopback in p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    default_speakers = loopback
                    break
            else:
                raise AudioCaptureError(
                    "Không tìm thấy WASAPI loopback device khớp với output mặc định."
                )

        channels = int(default_speakers["maxInputChannels"])
        rate = int(default_speakers["defaultSampleRate"])

        frames = []
        chunk = 1024

        def _callback(in_data, frame_count, time_info, status):
            frames.append(np.frombuffer(in_data, dtype=np.int16))
            return (in_data, pyaudio.paContinue)

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            frames_per_buffer=chunk,
            input=True,
            input_device_index=default_speakers["index"],
            stream_callback=_callback,
        )
        stream.start_stream()
        time.sleep(duration)
        stream.stop_stream()
        stream.close()

        audio_int16 = np.concatenate(frames).reshape(-1, channels)
        audio_float = audio_int16.astype(np.float32) / 32767.0
        _save_wav(output_path, audio_float, rate)
    finally:
        p.terminate()


def record_system_audio(
    output_path: str | Path,
    duration: float = 10.0,
    samplerate: int = 48000,
    prefer: Optional[str] = None,
) -> str:
    """
    Ghi âm `duration` giây audio hệ thống (loopback), lưu thành file WAV tại output_path.

    prefer: "soundcard" | "pyaudiowpatch" | None (None = tự thử soundcard trước,
            fallback pyaudiowpatch nếu lỗi).

    Trả về: output_path (str) khi thành công. Raise AudioCaptureError khi cả 2 lib đều lỗi.
    """
    _assert_windows()
    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    order = [prefer] if prefer else ["soundcard", "pyaudiowpatch"]
    last_error: Exception | None = None

    for lib in order:
        try:
            if lib == "soundcard":
                _record_with_soundcard(output_path, duration, samplerate)
            elif lib == "pyaudiowpatch":
                _record_with_pyaudiowpatch(output_path, duration, samplerate)
            else:
                continue
            return output_path
        except Exception as exc:  # noqa: BLE001 - cần thử lib kế tiếp khi lỗi
            last_error = exc
            continue

    raise AudioCaptureError(
        f"Thu âm loopback thất bại với cả soundcard và pyaudiowpatch. Lỗi cuối: {last_error}"
    )


# =============================================================================
# PHASE 1 — streaming audio cho VAD (mới, KHÔNG đổi gì ở phần trên)
# =============================================================================


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Downmix về mono bằng trung bình các channel. Đơn giản, đủ tốt cho STT
    (không cần giữ stereo image, khác với mixing nhạc)."""
    if audio.ndim == 1:
        return audio.astype(np.float32)
    return audio.mean(axis=1).astype(np.float32)


def _resample_linear(audio_mono: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample mono float32 bằng nội suy tuyến tính (np.interp).

    Vì sao không dùng scipy/librosa: tránh thêm dependency nặng chỉ để đổi
    sample rate cho mục đích STT (không phải audio mastering) — np.interp đủ
    chính xác và đã có sẵn qua numpy (đang là dependency bắt buộc rồi).
    """
    if orig_sr == target_sr or len(audio_mono) == 0:
        return audio_mono.astype(np.float32)

    duration = len(audio_mono) / orig_sr
    n_target = max(int(round(duration * target_sr)), 1)
    x_old = np.linspace(0.0, duration, num=len(audio_mono), endpoint=False)
    x_new = np.linspace(0.0, duration, num=n_target, endpoint=False)
    return np.interp(x_new, x_old, audio_mono).astype(np.float32)


def _normalize_chunk(raw: np.ndarray, capture_sr: int, target_sr: int, mono: bool) -> np.ndarray:
    """Áp chuẩn hoá (mono + resample) lên 1 chunk thô. Dùng chung cho cả 2
    nhánh soundcard/pyaudiowpatch để không lặp logic."""
    if mono:
        return _resample_linear(_to_mono(raw), capture_sr, target_sr)
    # Trường hợp hiếm cần giữ nhiều channel: resample riêng từng channel.
    channels = raw.shape[1] if raw.ndim > 1 else 1
    raw_2d = raw.reshape(-1, channels)
    resampled = [_resample_linear(raw_2d[:, ch], capture_sr, target_sr) for ch in range(channels)]
    return np.stack(resampled, axis=1)


def _stream_with_soundcard(target_sr: int, chunk_ms: int, mono: bool) -> Iterator[np.ndarray]:
    import soundcard as sc

    speaker = sc.default_speaker()
    if speaker is None:
        raise AudioCaptureError("Không tìm thấy speaker (output device) mặc định.")
    mic = sc.get_microphone(id=str(speaker.id), include_loopback=True)

    capture_sr = 48000  # samplerate ổn định để soundcard thu, chuẩn hoá sau ở _normalize_chunk
    chunk_frames = max(int(capture_sr * chunk_ms / 1000), 1)

    # 🔒 MỚI -- xem AudioDeviceChangedError. Kiểm tra ĐỊNH KỲ (~1 lần/giây,
    # KHÔNG mỗi chunk -- sc.default_speaker() phải hỏi lại Windows, có
    # overhead, không nên gọi 10 lần/giây với chunk_ms=100 mặc định) xem
    # default speaker còn ĐÚNG cái lúc mở stream phía trên không.
    check_every_n_chunks = max(int(1000 / chunk_ms), 1)
    chunks_since_check = 0

    with mic.recorder(samplerate=capture_sr, channels=2) as rec:
        while True:
            raw = rec.record(numframes=chunk_frames)  # shape (chunk_frames, 2), float32 [-1,1]

            chunks_since_check += 1
            if chunks_since_check >= check_every_n_chunks:
                chunks_since_check = 0
                current_speaker = sc.default_speaker()
                if current_speaker is None or str(current_speaker.id) != str(speaker.id):
                    raise AudioDeviceChangedError(
                        f"Thiết bị phát âm thanh mặc định đã đổi (từ "
                        f"{speaker.name!r} sang "
                        f"{getattr(current_speaker, 'name', 'không xác định')!r}) "
                        f"giữa lúc đang ghi."
                    )

            yield _normalize_chunk(raw, capture_sr, target_sr, mono)


def _stream_with_pyaudiowpatch(target_sr: int, chunk_ms: int, mono: bool) -> Iterator[np.ndarray]:
    import pyaudiowpatch as pyaudio  # type: ignore

    p = pyaudio.PyAudio()
    q: "queue.Queue[bytes]" = queue.Queue()

    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

        if not default_speakers.get("isLoopbackDevice", False):
            for loopback in p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    default_speakers = loopback
                    break
            else:
                raise AudioCaptureError(
                    "Không tìm thấy WASAPI loopback device khớp với output mặc định."
                )

        channels = int(default_speakers["maxInputChannels"])
        capture_sr = int(default_speakers["defaultSampleRate"])
        frames_per_chunk = max(int(capture_sr * chunk_ms / 1000), 1)
        # 🔒 MỚI -- xem AudioDeviceChangedError + ghi chú tương tự ở
        # _stream_with_soundcard(). Lưu lại index device output mặc định
        # LÚC MỞ stream để đối chiếu định kỳ.
        original_default_output_index = wasapi_info["defaultOutputDevice"]
        last_device_check_time = time.time()

        def _callback(in_data, frame_count, time_info, status):
            # Callback chạy trên thread riêng của PortAudio — chỉ đẩy vào
            # queue, KHÔNG xử lý nặng ở đây để tránh underrun/glitch audio.
            q.put(in_data)
            return (in_data, pyaudio.paContinue)

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=capture_sr,
            frames_per_buffer=frames_per_chunk,
            input=True,
            input_device_index=default_speakers["index"],
            stream_callback=_callback,
        )
        stream.start_stream()
        try:
            while stream.is_active():
                raw_bytes = q.get()

                now = time.time()
                if now - last_device_check_time >= 1.0:  # ~1 lần/giây, xem lý do ở trên
                    last_device_check_time = now
                    current_wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                    if current_wasapi_info["defaultOutputDevice"] != original_default_output_index:
                        raise AudioDeviceChangedError(
                            "Thiết bị phát âm thanh mặc định (WASAPI) đã đổi "
                            "giữa lúc đang ghi."
                        )

                audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, channels)
                audio_float = audio_int16.astype(np.float32) / 32767.0
                yield _normalize_chunk(audio_float, capture_sr, target_sr, mono)
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        p.terminate()


def stream_loopback_chunks(
    target_samplerate: int = 16000,
    chunk_ms: int = 100,
    mono: bool = True,
    prefer: Optional[str] = None,
) -> Iterator[np.ndarray]:
    """
    Generator yield LIÊN TỤC chunk audio đã chuẩn hoá cho vad.py.

    Hợp đồng cố định (xem CONTRACTS.md Mục 2):
      - dtype luôn float32, range [-1.0, 1.0]
      - mono=True (mặc định) -> shape (n_frames,)
      - mono=False -> shape (n_frames, n_channels)
      - đã resample về target_samplerate, KHÔNG phụ thuộc device gốc bao
        nhiêu Hz/channel.

    target_samplerate mặc định 16000: đây là 1 trong các rate webrtcvad
    CHẤP NHẬN (8000/16000/32000/48000) và cũng là rate chuẩn cho Whisper —
    chọn 16000 để vad.py dùng thẳng, không phải resample lại lần 2.

    prefer: "soundcard" | "pyaudiowpatch" | None (None = tự thử soundcard
            trước, fallback pyaudiowpatch nếu lỗi NGAY LÚC SETUP).

    Lưu ý quan trọng: fallback giữa 2 lib chỉ đáng tin cậy nếu lỗi xảy ra
    TRƯỚC chunk đầu tiên (vd thiếu lib, không tìm thấy device). Nếu 1 lib
    đang stream giữa chừng rồi mới lỗi (vd thiết bị bị rút), generator sẽ
    raise lên cho caller (vad.py) xử lý — không tự âm thầm đổi lib giữa
    dòng audio đang chạy, vì sẽ tạo khoảng hở/méo dữ liệu khó debug.

    ⚠️ NGOẠI LỆ DUY NHẤT (🔒 MỚI -- xem `AudioDeviceChangedError`):
    `AudioDeviceChangedError` (Windows đổi default playback device giữa
    lúc đang ghi) LUÔN được raise THẲNG lên caller ngay khi phát hiện,
    KHÔNG bao giờ rơi vào nhánh "thử lib kế tiếp" ở trên — caller
    (`ui/main_window.py AudioWorker.run()`) bắt riêng exception này để MỞ
    LẠI generator (tiếp tục ghi, KHÔNG kết thúc phiên họp), khác với mọi
    `AudioCaptureError` khác (kết thúc phiên họp, coi như lỗi không tự
    phục hồi được).

    Dừng generator: caller `break` khỏi vòng `for chunk in stream_loopback_chunks(...)`.
    """
    _assert_windows()
    order = [prefer] if prefer else ["soundcard", "pyaudiowpatch"]
    last_error: Exception | None = None

    for lib in order:
        try:
            if lib == "soundcard":
                yield from _stream_with_soundcard(target_samplerate, chunk_ms, mono)
                return
            elif lib == "pyaudiowpatch":
                yield from _stream_with_pyaudiowpatch(target_samplerate, chunk_ms, mono)
                return
        except AudioDeviceChangedError:
            # 🔒 MỚI -- raise THẲNG lên caller (AudioWorker, xem
            # ui/main_window.py), TUYỆT ĐỐI KHÔNG rơi xuống `except
            # Exception` ở dưới để "thử lib kế tiếp" -- đây là lỗi mid-
            # stream RIÊNG, đã có lib hiện tại đang chạy tốt, chỉ là device
            # đích đã đổi; caller biết cách mở lại generator MỚI (tự nhiên
            # sẽ resolve đúng device hiện tại) trên CÙNG lib, không cần và
            # không nên nhảy sang lib khác.
            raise
        except Exception as exc:  # noqa: BLE001 - cần thử lib kế tiếp khi lỗi setup
            last_error = exc
            continue

    raise AudioCaptureError(
        f"Streaming loopback thất bại với cả soundcard và pyaudiowpatch. Lỗi cuối: {last_error}"
    )


if __name__ == "__main__":
    # Test nhanh: thu 10s, lưu test_loopback.wav (giữ nguyên hành vi Phase 0).
    out = record_system_audio("test_loopback.wav", duration=10.0)
    print(f"Đã lưu: {out}")
