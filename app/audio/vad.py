"""
audio/vad.py
------------
Cắt luồng audio mono 16kHz LIÊN TỤC (từ capture.stream_loopback_chunks())
thành các SEGMENT hoàn chỉnh theo khoảng lặng, dùng webrtcvad.

Vì sao thiết kế feed()/flush() chứ KHÔNG phải generator:
Ở Phase 1 bước 3-4 (wiring với main_window.py), audio capture sẽ chạy trên
1 thread riêng (Qt main thread không nên bị block bởi 1 generator vô hạn).
Pattern chuẩn: thread audio gọi `segmenter.feed(chunk)` mỗi khi có chunk mới
từ stream_loopback_chunks(); feed() trả về NGAY list segment vừa chốt xong
(nếu có) để code gọi nó tự quyết định cách đẩy qua UI (vd Qt Signal) —
VadSegmenter không biết và không cần biết gì về Qt/threading.

webrtcvad yêu cầu: PCM16 mono, samplerate thuộc {8000,16000,32000,48000},
mỗi frame đưa vào is_speech() phải đúng 10/20/30ms. capture.py luôn trả
float32 [-1,1] mono 16kHz (CONTRACTS.md Mục 2) — vad.py tự lo cắt nhỏ thành
frame đúng kích cỡ + đổi int16 cho webrtcvad, caller không cần biết chi tiết
này, chỉ gọi feed()/flush().
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import webrtcvad


class VadSegmenterError(RuntimeError):
    """Lỗi cấu hình hoặc dữ liệu đầu vào không hợp lệ cho VadSegmenter."""


_VALID_SAMPLERATES = (8000, 16000, 32000, 48000)
_VALID_FRAME_MS = (10, 20, 30)


class VadSegmenter:
    """
    Nhận liên tục chunk audio mono float32 [-1,1] qua feed(), trả về list các
    SEGMENT hoàn chỉnh (mỗi segment = 1 đoạn nói, đã cắt theo khoảng lặng).

    Segment trả ra LUÔN là: numpy float32 [-1,1], mono, CÙNG samplerate đầu
    vào (không resample lại — capture.py đã chuẩn hoá việc đó rồi, vad.py
    không động vào sample rate).
    """

    def __init__(
        self,
        samplerate: int = 16000,
        frame_ms: int = 20,
        aggressiveness: int = 2,
        silence_ms: int = 350,
        min_speech_ms: int = 250,
        max_segment_ms: int = 8000,
        padding_ms: int = 200,
    ) -> None:
        """
        samplerate: phải khớp với samplerate thật của chunk đưa vào feed()
            (mặc định 16000, khớp target_samplerate mặc định của
            stream_loopback_chunks()). Khác samplerate -> webrtcvad lỗi.
        frame_ms: độ dài 1 frame VAD xét speech/silence (chỉ 10/20/30 hợp lệ).
        aggressiveness: 0 (ít cắt nhầm thành im lặng) .. 3 (cắt mạnh tay nhất,
            hay dùng cho audio ồn). Mặc định 2 — cân bằng.
        silence_ms: khoảng lặng liên tục bao lâu thì coi là 1 câu đã kết thúc.
            Mặc định 350ms (giảm từ 600ms ban đầu sau khi test thật trên
            Windows: với audio 2 người nói nối tiếp nhanh — vd podcast 2
            host — 600ms làm VAD gộp cả lời 2 người vào 1 segment, vì
            khoảng nghỉ giữa lượt nói tự nhiên thường NGẮN hơn 600ms).
            ⚠️ Đây KHÔNG phải fix triệt để: VAD vẫn không biết "ai" đang
            nói, chỉ đang cắt theo khoảng lặng NGẮN HƠN để tăng khả năng
            bắt được ranh giới lượt nói. Trade-off đánh đổi: 350ms cũng dễ
            cắt cụt câu của CÙNG 1 người nếu họ ngừng nghỉ giữa câu (vd suy
            nghĩ, hít thở) — có thể làm 1 câu bị tách thành nhiều bubble
            không cần thiết. Cần bạn tự test thật để xem 350ms có hợp với
            cách nói của bạn/đối tác hay không, có thể cần tinh chỉnh lại.
        min_speech_ms: đoạn nói ngắn hơn mức này bị coi là nhiễu, không trả
            ra segment (tránh gửi STT những đoạn quá ngắn vô nghĩa).
        max_segment_ms: trần độ dài 1 segment — nếu người nói liên tục không
            ngừng, vẫn ép cắt ở đây để UI không phải chờ quá lâu mới thấy
            transcript (đáp ứng NFR ≤2s của spec — segment quá dài sẽ phá vỡ
            mục tiêu đó dù VAD không thấy khoảng lặng).
            ⚠️ **Giảm từ 15000ms xuống 8000ms** (CONTRACTS.md Mục 16) sau
            phản hồi test thật: delay nặng (~6-9s) khi audio KHÔNG có
            khoảng lặng rõ ràng ngay tại điểm chuyển ngôn ngữ/đổi tab (vd
            tiếng Anh sang tiếng Trung) — vì 2 nguồn audio liên tục nối
            nhau không có khoảng nghỉ, VAD không cắt được theo silence_ms,
            phải đợi tới TRẦN max_segment_ms (cũ: 15s) mới ép cắt. Segment
            càng dài thì lệnh transcribe()+translate() (network, blocking)
            càng lâu — cộng dồn đúng vào lúc người dùng đang chờ thấy nội
            dung mới. Hạ trần xuống 8s giảm gần 1 nửa độ trễ TỆ NHẤT của
            trường hợp này, đổi lại: 1 câu nói thật liên tục >8s (hiếm hơn
            nhiều so với hội thoại thông thường) sẽ bị cắt thành 2 bubble
            thay vì 1 — đánh đổi hợp lý cho 1 app trợ lý họp cần phản hồi
            gần thời gian thực hơn là 1 bản ghi đầy đủ ngữ pháp tuyệt đối.
            **CHƯA verify được bằng audio/network thật trong sandbox này**
            — cần bạn tự quan sát lại đúng tình huống đã báo (chuyển ngôn
            ngữ/tab) xem độ trễ có giảm rõ rệt không; nếu vẫn còn delay
            ngoài mong đợi HOẶC ngược lại câu bị cắt cụt quá thường xuyên,
            chỉnh số 8000 này (file này, KHÔNG cần sửa nơi khác — xem
            CONTRACTS.md Mục 16 để biết đầy đủ phân tích nguyên nhân, KHÔNG
            chỉ do "model chậm" như nghi vấn ban đầu).
        padding_ms: giữ lại 1 đoạn audio ngắn TRƯỚC khi speech bắt đầu (tránh
            cắt cụt đầu câu) và SAU khi speech kết thúc (tránh cắt cụt đuôi
            câu) — không giữ nguyên toàn bộ khoảng lặng silence_ms vào segment.
        """
        if samplerate not in _VALID_SAMPLERATES:
            raise VadSegmenterError(
                f"samplerate={samplerate} không hợp lệ cho webrtcvad. "
                f"Phải là một trong {_VALID_SAMPLERATES}."
            )
        if frame_ms not in _VALID_FRAME_MS:
            raise VadSegmenterError(
                f"frame_ms={frame_ms} không hợp lệ. Phải là một trong {_VALID_FRAME_MS}."
            )
        if not (0 <= aggressiveness <= 3):
            raise VadSegmenterError("aggressiveness phải trong khoảng 0-3.")

        self._sr = samplerate
        self._frame_size = int(samplerate * frame_ms / 1000)  # số sample / frame VAD
        self._vad = webrtcvad.Vad(aggressiveness)

        self._silence_frames_limit = max(int(round(silence_ms / frame_ms)), 1)
        self._min_speech_frames = max(int(round(min_speech_ms / frame_ms)), 1)
        self._max_segment_frames = max(int(round(max_segment_ms / frame_ms)), 1)
        self._padding_frames = max(int(round(padding_ms / frame_ms)), 0)

        self._sample_buffer = np.zeros(0, dtype=np.float32)  # mẫu lẻ chưa đủ 1 frame VAD
        self._pre_buffer: List[np.ndarray] = []   # vài frame im lặng gần nhất, đệm trước khi nói
        self._active_frames: List[np.ndarray] = []  # frame thuộc đoạn nói hiện tại
        self._is_speaking = False
        self._silence_run = 0
        self._speech_frame_count = 0

    def feed(self, chunk: np.ndarray) -> List[np.ndarray]:
        """Đẩy 1 chunk mono float32 [-1,1] (độ dài bất kỳ, KHÔNG cần chia hết
        cho frame_size — vad.py tự đệm) vào segmenter.

        Trả về list segment HOÀN CHỈNH vừa chốt xong trong lần feed này.
        Thường rỗng (chưa đủ điều kiện chốt) hoặc 1 phần tử; có thể >1 nếu
        chunk truyền vào đủ dài để bao trùm nhiều khoảng lặng liên tiếp.
        """
        if chunk.ndim != 1:
            raise VadSegmenterError(f"feed() chỉ nhận mono 1D, nhận được shape {chunk.shape}.")

        self._sample_buffer = np.concatenate([self._sample_buffer, chunk.astype(np.float32)])
        finished: List[np.ndarray] = []

        while len(self._sample_buffer) >= self._frame_size:
            frame = self._sample_buffer[: self._frame_size]
            self._sample_buffer = self._sample_buffer[self._frame_size :]
            result = self._process_frame(frame)
            if result is not None:
                finished.append(result)

        return finished

    def flush(self) -> Optional[np.ndarray]:
        """Gọi khi dừng ghi/kết thúc họp để lấy đoạn nói còn dở (nếu có) —
        không chờ khoảng lặng tiếp theo vì sẽ không bao giờ tới. Trả về None
        nếu không có đoạn nói nào đang mở hoặc đoạn đó quá ngắn (< min_speech_ms)."""
        segment = None
        if self._is_speaking and self._speech_frame_count >= self._min_speech_frames:
            segment = np.concatenate(self._active_frames).astype(np.float32)
        self._reset_segment_state()
        return segment

    # -- nội bộ --------------------------------------------------------

    def _process_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        frame_int16 = (np.clip(frame, -1.0, 1.0) * 32767.0).astype(np.int16)
        is_speech = self._vad.is_speech(frame_int16.tobytes(), self._sr)

        if not self._is_speaking:
            if is_speech:
                # Bắt đầu 1 đoạn nói mới: lấy luôn pre_buffer (vài frame im lặng
                # ngay trước đó) để không cắt cụt đầu câu.
                self._is_speaking = True
                self._active_frames = list(self._pre_buffer) + [frame]
                self._speech_frame_count = 1
                self._silence_run = 0
                self._pre_buffer = []
            else:
                self._pre_buffer.append(frame)
                if len(self._pre_buffer) > self._padding_frames:
                    self._pre_buffer.pop(0)
            return None

        # Đang trong 1 đoạn nói
        self._active_frames.append(frame)
        if is_speech:
            self._silence_run = 0
            self._speech_frame_count += 1
        else:
            self._silence_run += 1

        hit_silence_limit = self._silence_run >= self._silence_frames_limit
        hit_max_length = len(self._active_frames) >= self._max_segment_frames

        if not (hit_silence_limit or hit_max_length):
            return None

        # Chốt segment: nếu chốt do im lặng, chỉ giữ padding_ms cuối thay vì
        # toàn bộ silence_ms (tránh segment có quá nhiều khoảng lặng vô ích
        # khi gửi STT — tốn quota free-tier và tăng độ trễ không cần thiết).
        frames_to_keep = self._active_frames
        if hit_silence_limit and not hit_max_length:
            keep_silence = min(self._silence_run, self._padding_frames)
            cut_index = len(self._active_frames) - self._silence_run + keep_silence
            frames_to_keep = self._active_frames[:cut_index]

        segment = None
        if self._speech_frame_count >= self._min_speech_frames and frames_to_keep:
            segment = np.concatenate(frames_to_keep).astype(np.float32)

        self._reset_segment_state()
        return segment

    def _reset_segment_state(self) -> None:
        self._is_speaking = False
        self._active_frames = []
        self._pre_buffer = []
        self._silence_run = 0
        self._speech_frame_count = 0
