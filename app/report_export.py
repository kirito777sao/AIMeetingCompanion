"""
app/report_export.py
----------------------
Phase 3 Bước 3/4 (F11): xuất báo cáo cuộc họp (ĐÃ tổng hợp — overview/
decisions/action_items, KHÔNG phải transcript thô) ra file .docx và .pdf để
chia sẻ cho người không dùng app này (sếp/đồng nghiệp). Theo đúng kiến trúc
PROJECT_SPEC.md Mục 6 (L "LLM tổng hợp biên bản" -> M "Export .docx/.pdf"):
export đọc từ `ReportRecord` ĐÃ LƯU (storage/db.py), không tự gọi AI, không
tự đọc transcript — module này hoàn toàn KHÔNG phụ thuộc Qt/PySide6, network,
hay AIProvider, để test được logic build nội dung file độc lập (cùng triết lý
tách module với report.py).

⚠️ BÀI HỌC FONT TIẾNG VIỆT đã gặp THẬT ở suggestion_drawer.py/theme.qss
(CONTRACTS.md Mục 4 — QTextEdit từng mất dấu vì font "Be Vietnam Pro"/
"Inter" không có sẵn trên Windows) LẶP LẠI Ở ĐÂY, nghiêm trọng hơn cho PDF:

- **.docx (python-docx)**: Word/LibreOffice tự fallback sang font hệ thống
  lúc RENDER nếu font khai báo không tồn tại — văn bản Unicode (kể cả dấu
  tiếng Việt) vẫn lưu đúng trong file, hiển thị an toàn với hầu hết font
  Windows. Vẫn set style mặc định "Segoe UI" cho ĐỒNG BỘ hình ảnh với UI
  app, nhưng đây không phải yêu cầu kỹ thuật bắt buộc như PDF dưới đây.

- **.pdf (reportlab)**: KHÁC HẲN VỀ BẢN CHẤT — core font tích hợp sẵn của
  reportlab (Helvetica, Times-Roman, ...) CHỈ map glyph theo bảng mã
  Latin-1/WinAnsi, không có sẵn glyph cho ký tự có dấu tiếng Việt (ví dụ
  "ạ", "ầ", "ẫ") -- PDF xuất ra sẽ THIẾU ký tự/hiện sai mà KHÔNG báo lỗi gì
  (lỗi câm, người dùng tự phát hiện khi mở file). PHẢI tự register 1 font
  TrueType Unicode bằng `reportlab.pdfbase.ttfonts.TTFont` TRƯỚC khi vẽ.

  Chọn ĐÚNG font "Segoe UI" từ `C:\\Windows\\Fonts\\segoeui.ttf` — font NÀY
  đã được CHÍNH dự án này xác nhận render đúng dấu tiếng Việt thật (xem
  theme.qss/CONTRACTS.md), nhất quán hơn nhiều so với tự chọn 1 font Unicode
  khác (vd DejaVu Sans) rồi phải đóng gói thêm file font vào project (tốn
  dung lượng, rủi ro license, lại một biến số mới chưa verify). Vì app CHỈ
  hỗ trợ Windows 10/11 (yêu cầu hệ thống đã chốt từ Phase 0, README mục
  "Yêu cầu hệ thống"), dùng đường dẫn TUYỆT ĐỐI tới font hệ thống Windows là
  AN TOÀN — không cần lo "không portable" vì app vốn không chạy ngoài
  Windows.

  Nếu KHÔNG tìm thấy font này (cài Windows lỗi hi hữu thiếu font hệ thống,
  hoặc gọi nhầm trên Linux/Mac) -> raise `ReportExportError` NGAY, RÕ RÀNG,
  KHÔNG để PDF xuất ra với chữ lỗi câm mà người dùng không hiểu vì sao.

  ⚠️ CHƯA verify được trên Windows thật trong sandbox này (không có font hệ
  thống Windows, không có network ra ngoài) — `tests/test_report_export.py`
  chỉ verify được: (a) logic build nội dung đúng (overview/decisions/action
  items, escape ký tự đặc biệt, mark hoàn thành "[x]"/"[ ]"), (b) ĐÚNG hành
  vi raise lỗi rõ ràng khi thiếu font (giả lập bằng cách trỏ đường dẫn font
  sang 1 font TTF khác có sẵn trong sandbox để verify pipeline registration+
  generate PDF THẬT chạy được về mặt kỹ thuật — KHÔNG verify được đúng chữ
  "Segoe UI" thật trên Windows có còn đúng dấu hay không, cần bạn tự mở file
  xuất ra bằng Word/Acrobat để xác nhận lại bằng mắt.
"""

from __future__ import annotations

import html
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.storage.db import ReportRecord


class ReportExportError(RuntimeError):
    """Lỗi khi xuất file báo cáo: thiếu thư viện, thiếu font hệ thống, hoặc
    lỗi ghi đĩa (đường dẫn không hợp lệ, không có quyền ghi, ...)."""


# Đường dẫn font hệ thống Windows -- xem lý do chọn đúng "Segoe UI" ở
# docstring đầu file. Để dạng module-level CONSTANT (không hardcode trong
# hàm) để test có thể monkeypatch sang font khác khi verify trong sandbox
# không có Windows thật (xem tests/test_report_export.py).
WINDOWS_FONT_REGULAR = r"C:\Windows\Fonts\segoeui.ttf"
WINDOWS_FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
_PDF_FONT_NAME = "SegoeUI"
_PDF_FONT_NAME_BOLD = "SegoeUI-Bold"


def _decision_lines(decisions: list[str]) -> list[str]:
    return list(decisions) if decisions else []


def _action_item_lines(action_items: "list") -> list[tuple[str, bool]]:
    """Trả về list (text, done) -- tách riêng hàm này (không inline ở 2 nơi
    docx/pdf) để logic mark "[x]"/"[ ]" chỉ định nghĩa ĐÚNG 1 chỗ."""
    return [(item.text, item.done) for item in action_items]


# ---------------------------------------------------------------------------
# .docx (python-docx)
# ---------------------------------------------------------------------------


def export_to_docx(
    report: "ReportRecord", meeting_id: int, native_lang_label: str, output_path: str,
) -> None:
    """Xuất `report` ra file .docx tại `output_path`.

    Raises:
        ReportExportError: thiếu thư viện `python-docx`, hoặc lỗi ghi file
            (đường dẫn không hợp lệ/không có quyền ghi).
    """
    try:
        import docx
        from docx.shared import Pt
    except ImportError as exc:
        raise ReportExportError(
            "Thiếu thư viện 'python-docx' — cài bằng `pip install python-docx` "
            "(đã có trong requirements.txt, chạy lại `pip install -r requirements.txt`)."
        ) from exc

    document = docx.Document()
    style = document.styles["Normal"]
    style.font.name = "Segoe UI"  # đồng bộ hình ảnh với UI app, xem docstring đầu file
    style.font.size = Pt(11)

    document.add_heading(f"Báo cáo cuộc họp #{meeting_id}", level=1)
    document.add_paragraph(f"Tạo lúc (UTC): {report.generated_at}")
    document.add_paragraph(f"Ngôn ngữ báo cáo: {native_lang_label}")

    document.add_heading("Tóm tắt", level=2)
    document.add_paragraph(report.overview or "(Không có)")

    document.add_heading("Quyết định", level=2)
    decisions = _decision_lines(report.decisions)
    if decisions:
        for line in decisions:
            document.add_paragraph(line, style="List Bullet")
    else:
        document.add_paragraph("(Không có)")

    document.add_heading("Việc cần làm", level=2)
    action_lines = _action_item_lines(report.action_items)
    if action_lines:
        for text, done in action_lines:
            mark = "[x]" if done else "[ ]"
            document.add_paragraph(f"{mark}  {text}")
    else:
        document.add_paragraph("(Không có)")

    try:
        document.save(output_path)
    except OSError as exc:
        raise ReportExportError(f"Không thể lưu file .docx tại {output_path}: {exc}") from exc


# ---------------------------------------------------------------------------
# .pdf (reportlab)
# ---------------------------------------------------------------------------


def _registered_font_names() -> set[str]:
    from reportlab.pdfbase import pdfmetrics

    return set(pdfmetrics.getRegisteredFontNames())


def _register_pdf_fonts() -> None:
    """Register font Unicode cho reportlab — xem lý do BẮT BUỘC ở docstring
    đầu file (core font reportlab KHÔNG có glyph dấu tiếng Việt).

    Idempotent: gọi nhiều lần trong cùng tiến trình chỉ register 1 lần (Qt
    app có thể mở/đóng nhiều dialog xuất PDF trong 1 phiên chạy)."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as exc:
        raise ReportExportError(
            "Thiếu thư viện 'reportlab' — cài bằng `pip install reportlab` "
            "(đã có trong requirements.txt, chạy lại `pip install -r requirements.txt`)."
        ) from exc

    if _PDF_FONT_NAME in _registered_font_names():
        return

    if not os.path.exists(WINDOWS_FONT_REGULAR):
        raise ReportExportError(
            f"Không tìm thấy font hệ thống tại {WINDOWS_FONT_REGULAR} — xuất "
            "PDF chỉ hỗ trợ Windows 10/11 (đúng yêu cầu hệ thống của app, "
            "xem README) vì cần font Unicode có sẵn trên máy để hiện đúng "
            "dấu tiếng Việt. KHÔNG tiếp tục xuất bằng font mặc định (sẽ ra "
            "PDF thiếu/sai ký tự một cách lỗi câm, khó phát hiện)."
        )
    pdfmetrics.registerFont(TTFont(_PDF_FONT_NAME, WINDOWS_FONT_REGULAR))
    if os.path.exists(WINDOWS_FONT_BOLD):
        pdfmetrics.registerFont(TTFont(_PDF_FONT_NAME_BOLD, WINDOWS_FONT_BOLD))
    else:
        # Không có bản đậm riêng -- dùng lại font thường cho "đậm" còn hơn
        # raise lỗi chỉ vì thiếu 1 file phụ không ảnh hưởng tới việc ĐỌC ĐƯỢC
        # nội dung (chỉ mất độ đậm thị giác của heading).
        pdfmetrics.registerFont(TTFont(_PDF_FONT_NAME_BOLD, WINDOWS_FONT_REGULAR))


def _escape(text: str) -> str:
    """reportlab `Paragraph` hiểu 1 tập con tag kiểu XML trong text (vd
    `<b>`) -- PHẢI escape `&`/`<`/`>` thô từ transcript/AI output trước khi
    đưa vào Paragraph, nếu không nội dung chứa đúng các ký tự này (hiếm
    nhưng có thể, vd ai đó nói "A & B", hoặc model lỡ sinh dấu "<"/">" nào
    đó) sẽ làm lệch cú pháp markup nội bộ của reportlab, có thể raise lỗi
    parse hoặc hiện sai layout."""
    return html.escape(text, quote=False)


def export_to_pdf(
    report: "ReportRecord", meeting_id: int, native_lang_label: str, output_path: str,
) -> None:
    """Xuất `report` ra file .pdf tại `output_path`.

    Raises:
        ReportExportError: thiếu thư viện `reportlab`, thiếu font hệ thống
            (xem `_register_pdf_fonts()`), hoặc lỗi ghi file.
    """
    _register_pdf_fonts()

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    heading_style = ParagraphStyle(
        "ReportHeading", fontName=_PDF_FONT_NAME_BOLD, fontSize=14, spaceAfter=8, spaceBefore=12,
    )
    body_style = ParagraphStyle(
        "ReportBody", fontName=_PDF_FONT_NAME, fontSize=11, leading=16, spaceAfter=4,
    )

    story = [
        Paragraph(_escape(f"Báo cáo cuộc họp #{meeting_id}"), heading_style),
        Paragraph(_escape(f"Tạo lúc (UTC): {report.generated_at}"), body_style),
        Paragraph(_escape(f"Ngôn ngữ báo cáo: {native_lang_label}"), body_style),
        Spacer(1, 6 * mm),
        Paragraph("Tóm tắt", heading_style),
        Paragraph(_escape(report.overview) or "(Không có)", body_style),
        Paragraph("Quyết định", heading_style),
    ]

    decisions = _decision_lines(report.decisions)
    if decisions:
        for line in decisions:
            story.append(Paragraph(f"•  {_escape(line)}", body_style))
    else:
        story.append(Paragraph("(Không có)", body_style))

    story.append(Paragraph("Việc cần làm", heading_style))
    action_lines = _action_item_lines(report.action_items)
    if action_lines:
        for text, done in action_lines:
            mark = "[x]" if done else "[ ]"
            story.append(Paragraph(f"{mark}  {_escape(text)}", body_style))
    else:
        story.append(Paragraph("(Không có)", body_style))

    try:
        pdf_doc = SimpleDocTemplate(output_path, pagesize=A4)
        pdf_doc.build(story)
    except OSError as exc:
        raise ReportExportError(f"Không thể lưu file .pdf tại {output_path}: {exc}") from exc
