"""
ui/audio_only_bubble.py
------------------------
🔒 MỚI (CONTRACTS.md Mục 23) — indicator NHẸ hiện khi pipeline phát hiện 1
đoạn audio (VAD coi là "có nói") nhưng Whisper tự đánh giá KHÔNG phải giọng
nói thật (no_speech_prob cao, hoặc text rỗng) — thường là nhạc không lời/
tạp âm. Trước đây các segment này bị bỏ qua HOÀN TOÀN (không hiện gì) —
người dùng phản hồi cần biết pipeline vẫn đang nghe được audio, không phải
app bị treo/im lặng bất thường khi gặp đoạn nhạc/tạp âm dài.

CỐ Ý là 1 widget RIÊNG, KHÔNG tái dùng `TranscriptBubble` — không có nội
dung/ngôn ngữ/nút "Nhờ AI trả lời" nào để hiện (không có text thật), thêm
nhánh rẽ vào `TranscriptBubble` sẽ làm phức tạp hoá 1 class vốn đã lớn cho
1 trường hợp hoàn toàn khác về bản chất.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class AudioOnlyBubble(QWidget):
    """1 dòng nhỏ, gọn hơn nhiều so với `TranscriptBubble` — chỉ timestamp +
    chip "🔊 [Âm thanh]" + tooltip giải thích. KHÔNG lưu state gì (không có
    `original_text` thật để giữ), không có signal nào."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AudioOnlyBubble")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        ts_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        ts_label.setObjectName("BubbleTimestamp")
        layout.addWidget(ts_label)

        chip = QLabel("🔊 [Âm thanh]")
        chip.setObjectName("AudioOnlyChip")
        chip.setToolTip(
            "Phát hiện âm thanh (có thể nhạc không lời/tạp âm) nhưng không "
            "phải giọng nói rõ ràng — không được ghi vào transcript. Nếu "
            "đây là lời nói thật bị bỏ sót, hãy thử nói to/rõ hơn hoặc giảm "
            "tiếng ồn nền."
        )
        layout.addWidget(chip)
        layout.addStretch(1)
