"""
ui/settings_dialog.py
-----------------------
🔒 MỚI (F14 — PROJECT_SPEC.md mục 4/10.4, xem CONTRACTS.md Mục 12) — màn
hình "Cài đặt" cho người dùng CUỐI tự nhập API key của họ.

🔒 MỞ RỘNG (đợt thêm multi-provider — Groq/OpenAI/Gemini, xem CONTRACTS.md
Mục 17): trước đây màn hình này CHỈ có 1 ô nhập key, ngầm định luôn là
Groq. Giờ thêm 1 dropdown chọn PROVIDER trước — người dùng có sẵn key của
Groq HOẶC OpenAI HOẶC Gemini (vd đã trả phí ChatGPT Plus từ trước, không
muốn tạo thêm tài khoản Groq) đều dán key của HỌ vào được, KHÔNG cần biết
khái niệm "AIProvider"/"base_url" là gì — đổi dropdown, dán key, bấm Lưu,
xong.

Bối cảnh (xem app/config_store.py để biết đầy đủ lý do/thiết kế lưu trữ):
lúc dev, đặt key trong `.env` là đủ. Khi đóng gói `.exe` phân phối cho
người khác, KHÔNG thể kèm sẵn key của người phát triển trong bản phân phối
— mỗi người dùng phải tự lấy API key CỦA HỌ và nhập vào đây; hệ thống lưu
lại cục bộ trên máy họ (MỖI provider 1 entry riêng, đổi qua lại không mất
key đã nhập của provider khác — xem `config_store.py`), đọc lại mỗi lần mở
app, KHÔNG cần sửa code/build lại.

UI theo đúng mô tả PROJECT_SPEC.md mục 10.4: input API key dạng ẨN (mask)
kèm icon hình mắt để bật/tắt hiện rõ — giống ô nhập password thông thường.

🔒 MỞ RỘNG (Backlog #4, CONTRACTS.md Mục 31): thêm 4 ô nhập model
(stt_model/stt_fallback_model/translate_model/translate_fallback_model)
— để trống = dùng default (placeholder hiện đúng default hiện tại của
provider đang chọn), điền vào = ghi đè qua `config_store.save_model_overrides()`,
KHÔNG cần sửa `.env`/code. Mục đích: nếu 1 provider decommission model
(đã xảy ra 2 lần với Groq, xem Mục 19), người dùng CUỐI (bản `.exe` không
có `.env`) tự đổi được ngay trên máy họ, không phải chờ bản cập nhật.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app import config_store
from app.ai.provider_factory import display_name, get_default_models_for_display
from app.ui.capture_protection import HOTKEY_LABEL, get_controller as get_capture_controller

# 🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- (field, nhãn hiển thị) theo
# ĐÚNG thứ tự `_MODEL_OVERRIDE_FIELDS` (config_store.py) -- 1 nguồn DUY
# NHẤT, thêm field model thứ 5 sau này CHỈ cần thêm 1 dòng ở đây.
_MODEL_FIELDS: tuple[tuple[str, str], ...] = (
    ("stt_model", "STT model (ưu tiên)"),
    ("stt_fallback_model", "STT model dự phòng"),
    ("translate_model", "Chat model (ưu tiên)"),
    ("translate_fallback_model", "Chat model dự phòng"),
)

# 🔒 1 nguồn DUY NHẤT cho mọi thông tin hiển thị riêng từng provider — thêm
# provider thứ 4 sau này CHỈ cần thêm 1 entry ở đây + 1 class AIProvider
# mới (xem provider_factory.py), KHÔNG cần sửa logic UI bên dưới.
_PROVIDER_INFO: dict[str, dict[str, str]] = {
    "groq": {
        "keys_url": "https://console.groq.com/keys",
        "placeholder": "gsk_...",
        "note": (
            "✅ Free tier — đủ dùng cho cá nhân/nhóm nhỏ. Có thể bị giới hạn "
            "tần suất (lỗi 429) vào giờ cao điểm, app sẽ tự thử lại với model "
            "dự phòng nhẹ hơn."
        ),
    },
    "openai": {
        "keys_url": "https://platform.openai.com/api-keys",
        "placeholder": "sk-...",
        "note": (
            "💳 TRẢ PHÍ theo lượng dùng (usage-based) — KHÔNG miễn phí như "
            "Groq. Phù hợp nếu bạn đã có sẵn tài khoản/API key OpenAI. Bạn tự "
            "theo dõi chi phí tại platform.openai.com/usage."
        ),
    },
    "gemini": {
        "keys_url": "https://aistudio.google.com/apikey",
        "placeholder": "AIza...",
        "note": (
            "✅ Có free tier (giới hạn theo phút/ngày, do Google tự quy định, "
            "có thể đổi). ⚠️ Phần nhận diện giọng nói (STT) của Gemini đo độ "
            "tin cậy KHÔNG chi tiết bằng Groq/OpenAI (Gemini không có API kiểu "
            "Whisper) — vẫn dùng tốt cho dịch/gợi ý trả lời/tóm tắt."
        ),
    },
}
_PROVIDER_ORDER = ("groq", "openai", "gemini")


class SettingsDialog(QDialog):
    """Không-modal (show(), không exec()), cùng pattern các dialog khác."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("⚙️ Cài đặt")
        self.resize(520, 480)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Chọn nhà cung cấp AI và dán API key CỦA BẠN — mỗi người dùng tự "
            "lấy key riêng (của Groq, OpenAI, hoặc Gemini — chọn 1 trong 3) "
            "và tự chịu trách nhiệm về việc sử dụng model AI của mình."
        ))

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Nhà cung cấp:"))
        self._provider_combo = QComboBox()
        for provider_id in _PROVIDER_ORDER:
            self._provider_combo.addItem(display_name(provider_id), userData=provider_id)
        provider_row.addWidget(self._provider_combo, stretch=1)
        layout.addLayout(provider_row)

        self._link_button = QPushButton()
        self._link_button.clicked.connect(self._on_link_clicked)
        layout.addWidget(self._link_button)

        input_row = QHBoxLayout()
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        input_row.addWidget(self._key_edit, stretch=1)

        self._toggle_visibility_button = QPushButton("👁")
        self._toggle_visibility_button.setCheckable(True)
        self._toggle_visibility_button.setToolTip("Hiện/ẩn API key")
        self._toggle_visibility_button.setFixedWidth(36)
        self._toggle_visibility_button.toggled.connect(self._on_toggle_visibility)
        input_row.addWidget(self._toggle_visibility_button)
        layout.addLayout(input_row)

        self._provider_note_label = QLabel("")
        self._provider_note_label.setWordWrap(True)
        self._provider_note_label.setObjectName("StatusLabel")
        layout.addWidget(self._provider_note_label)

        storage_note = (
            "🔒 Mỗi key sẽ được mã hoá cục bộ bằng Windows DPAPI (gắn với tài "
            "khoản Windows hiện tại)."
            if config_store.is_encrypted_storage_available()
            else "⚠️ Máy/môi trường này không hỗ trợ mã hoá DPAPI — key sẽ "
            "được lưu dạng văn bản thường, CHỈ cục bộ trên máy này (không "
            "hardcode, không kèm trong file .exe phân phối), nhưng KHÔNG "
            "mã hoá thật. Chỉ nên dùng trên máy cá nhân tin cậy."
        )
        note_label = QLabel(storage_note)
        note_label.setWordWrap(True)
        note_label.setObjectName("StatusLabel")
        layout.addWidget(note_label)

        # 🔒 MỚI (Mục 41) -- ẩn cửa sổ khỏi screen share. Áp NGAY khi tick
        # (không cần nút Lưu), cùng trạng thái với phím tắt toàn cục.
        self._capture_controller = get_capture_controller()
        self._capture_checkbox = QCheckBox(
            f"Ẩn cửa sổ app khỏi screen share/recording (phím tắt: {HOTKEY_LABEL})"
        )
        layout.addWidget(self._capture_checkbox)
        self._capture_note = QLabel("")
        self._capture_note.setWordWrap(True)
        self._capture_note.setObjectName("StatusLabel")
        layout.addWidget(self._capture_note)
        if self._capture_controller is None:
            self._capture_checkbox.setEnabled(False)
            self._capture_note.setText(
                "Chỉ hỗ trợ Windows 10 bản 2004 trở lên (không khả dụng trên máy này)."
            )
        else:
            self._capture_checkbox.toggled.connect(self._on_capture_toggled)
            self._capture_controller.changed.connect(self._sync_capture_checkbox)
            self._sync_capture_checkbox()

        # 🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- 4 ô model nâng cao,
        # để trống = dùng default (placeholder hiện đúng default hiện tại).
        model_section_label = QLabel(
            "Model nâng cao (tuỳ chọn — để trống dùng mặc định; chỉ đổi nếu "
            "provider decommission model gây lỗi):"
        )
        model_section_label.setWordWrap(True)
        layout.addWidget(model_section_label)

        model_form = QFormLayout()
        self._model_edits: dict[str, QLineEdit] = {}
        for field, label in _MODEL_FIELDS:
            edit = QLineEdit()
            model_form.addRow(label, edit)
            self._model_edits[field] = edit
        layout.addLayout(model_form)

        restore_defaults_button = QPushButton("Khôi phục mặc định (model)")
        restore_defaults_button.clicked.connect(self._on_restore_defaults_clicked)
        layout.addWidget(restore_defaults_button)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        button_row = QHBoxLayout()
        clear_button = QPushButton("Xoá key đã lưu (provider đang chọn)")
        clear_button.clicked.connect(self._on_clear_clicked)
        button_row.addWidget(clear_button)
        button_row.addStretch(1)
        save_button = QPushButton("Lưu")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        # Chọn sẵn đúng provider người dùng đang dùng (mặc định "groq" nếu
        # chưa từng cài đặt gì, xem config_store.get_active_provider()) +
        # nạp key đã lưu (nếu có) của provider đó -- PHẢI nối SAU khi mọi
        # widget ở trên đã tồn tại (currentIndexChanged bắn ngay khi addItem
        # ở trên, lúc đó self._key_edit chưa kịp tạo nếu nối sớm hơn).
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        active = config_store.get_active_provider()
        initial_index = max(self._provider_combo.findData(active), 0)
        self._provider_combo.setCurrentIndex(initial_index)
        self._refresh_provider_fields()

    def showEvent(self, event) -> None:  # noqa: N802 - tên hàm theo Qt convention
        """🔒 MỚI (Mục 34) -- dialog này giờ được `MainWindow` TÁI SỬ DỤNG
        (singleton, xem `_on_settings_clicked`) thay vì tạo instance mới mỗi
        lần bấm nút -- nạp lại field hiện tại MỖI LẦN cửa sổ được show() lại
        (không chỉ lúc khởi tạo), phòng trường hợp active_provider/key đã
        đổi qua nguồn khác từ lần đóng dialog trước tới giờ."""
        super().showEvent(event)
        self._refresh_provider_fields()
        self._sync_capture_checkbox()  # phím tắt có thể đã đổi trạng thái khi dialog đang đóng

    def _on_capture_toggled(self, checked: bool) -> None:
        if self._capture_controller is not None:
            self._capture_controller.set_enabled(checked)  # phát `changed` -> tự đồng bộ nhãn

    def _sync_capture_checkbox(self, *_args) -> None:
        ctrl = self._capture_controller
        if ctrl is None:
            return
        self._capture_checkbox.blockSignals(True)
        self._capture_checkbox.setChecked(ctrl.enabled)
        self._capture_checkbox.blockSignals(False)
        if ctrl.enabled and ctrl.ok:
            text = (
                "🛡 Đang ẩn khỏi screen capture. Không chặn được quay bằng điện "
                "thoại/capture card. Tắt giữa buổi share = cửa sổ lộ NGAY."
            )
        elif ctrl.enabled:
            text = (
                "⚠ KHÔNG áp dụng được (cần Windows 10 bản 2004+) — cửa sổ VẪN "
                "HIỆN trong screen share. Xem app.log."
            )
        else:
            text = "Cửa sổ đang HIỆN bình thường trong screen share."
        self._capture_note.setText(text)

    def _current_provider(self) -> str:
        return self._provider_combo.currentData()

    def _on_provider_changed(self, _index: int) -> None:
        self._refresh_provider_fields()

    def _refresh_provider_fields(self) -> None:
        """Cập nhật link/placeholder/note/nội dung ô key cho ĐÚNG provider
        vừa chọn trong dropdown -- gọi lại mỗi lần đổi dropdown."""
        provider = self._current_provider()
        info = _PROVIDER_INFO[provider]
        name = display_name(provider)

        self._link_button.setText(f"🔗 Lấy API key {name} tại {info['keys_url'].split('//')[1]}")
        self._key_edit.setPlaceholderText(info["placeholder"])
        self._provider_note_label.setText(info["note"])

        existing = config_store.load_api_key(provider=provider)
        self._key_edit.setText(existing or "")

        # 🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- placeholder = default
        # HIỆN TẠI của provider này (chỉ để hiện gợi ý, KHÔNG quyết định
        # hành vi thật -- xem docstring `_DEFAULT_MODELS_FOR_DISPLAY`),
        # text = override đã lưu (nếu có), để trống nếu chưa từng override.
        defaults = get_default_models_for_display(provider)
        overrides = config_store.load_model_overrides(provider)
        for field, edit in self._model_edits.items():
            edit.setPlaceholderText(defaults.get(field, ""))
            edit.setText(overrides.get(field, ""))

        self._set_status("", is_error=False)

    def _on_link_clicked(self) -> None:
        info = _PROVIDER_INFO[self._current_provider()]
        QDesktopServices.openUrl(QUrl(info["keys_url"]))

    def _on_toggle_visibility(self, checked: bool) -> None:
        self._key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_save_clicked(self) -> None:
        provider = self._current_provider()
        api_key = self._key_edit.text().strip()
        if not api_key:
            self._set_status("Chưa nhập API key.", is_error=True)
            return
        try:
            encrypted = config_store.save_api_key(api_key, provider=provider)
        except config_store.ConfigStoreError as exc:
            self._set_status(f"Không lưu được: {exc}", is_error=True)
            return

        # 🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- lưu cùng lúc với API
        # key (1 nút Lưu duy nhất, đúng UX hiện có -- KHÔNG thêm nút Lưu
        # thứ 2 riêng cho model, tránh người dùng bấm nhầm nút, tưởng đã
        # lưu model nhưng quên bấm Lưu key hoặc ngược lại). Field để trống
        # tự động bị `save_model_overrides()` loại khỏi override (Mục 31).
        model_overrides = {field: edit.text() for field, edit in self._model_edits.items()}
        try:
            config_store.save_model_overrides(provider, model_overrides)
        except config_store.ConfigStoreError as exc:
            self._set_status(f"Đã lưu API key nhưng KHÔNG lưu được model: {exc}", is_error=True)
            return

        name = display_name(provider)
        msg = (
            f"Đã lưu key {name} (đã mã hoá) và đặt {name} làm provider đang dùng."
            if encrypted
            else f"Đã lưu key {name} (dạng văn bản thường, xem ghi chú trên) và "
            f"đặt {name} làm provider đang dùng."
        )
        self._set_status(msg, is_error=False)

    def _on_clear_clicked(self) -> None:
        provider = self._current_provider()
        try:
            config_store.clear_api_key(provider=provider)
        except config_store.ConfigStoreError as exc:
            self._set_status(f"Không xoá được: {exc}", is_error=True)
            return
        self._key_edit.clear()
        self._set_status(f"Đã xoá API key {display_name(provider)} đã lưu.", is_error=False)

    def _on_restore_defaults_clicked(self) -> None:
        """🔒 MỚI (Backlog #4, CONTRACTS.md Mục 31) -- xoá TOÀN BỘ model
        override đã lưu của provider ĐANG CHỌN, quay lại default hardcode.
        KHÔNG đụng API key (2 khái niệm khác nhau, xem docstring nút này ở
        `__init__`) -- KHÔNG đụng override của provider khác."""
        provider = self._current_provider()
        try:
            config_store.clear_model_overrides(provider)
        except config_store.ConfigStoreError as exc:
            self._set_status(f"Không khôi phục được: {exc}", is_error=True)
            return
        for edit in self._model_edits.values():
            edit.clear()
        self._set_status(
            f"Đã khôi phục model mặc định cho {display_name(provider)}.", is_error=False,
        )

    def _set_status(self, text: str, is_error: bool) -> None:
        self._status_label.setText(text)
        self._status_label.setProperty("isError", is_error)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
