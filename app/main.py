"""
app/main.py
-----------
Entry point Phase 1. Chạy:

    python -m app.main

(Không chạy `python app/main.py` trực tiếp -- sẽ lỗi import `from app...`
vì khi đó Python không coi `app/` là 1 package nằm trong project root.)
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow

_THEME_PATH = Path(__file__).parent / "ui" / "theme.qss"


def main() -> int:
    load_dotenv()  # đọc GROQ_API_KEY/OPENAI_API_KEY/GEMINI_API_KEY/AI_PROVIDER từ .env (xem .env.example)

    app = QApplication(sys.argv)

    try:
        app.setStyleSheet(_THEME_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"Cảnh báo: không đọc được theme.qss ({exc}), dùng style mặc định.")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
