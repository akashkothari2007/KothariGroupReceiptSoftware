import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

import fitz  # pymupdf — already installed for receipt processing


def _fmt_money(val):
    if val is None:
        return "$0.00"
    sign = "-" if val < 0 else ""
    return f"{sign}${abs(val):,.2f}"


def _fmt_date(d):
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return d
    return d.strftime("%b %d, %Y")


def _fmt_datetime(dt):
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt
    return dt.strftime("%b %d, %Y at %I:%M %p")


def generate_pdf(
    company_name: str,
    statement_filename: str,
    cycle_start,
    cycle_end,
    transactions: list[dict],
    created_by: str = None,
    created_at=None,
    approved_by: str = None,
    approved_at=None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=2,
        textColor=colors.HexColor("#111827"),
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=4,
    )
    right_style = ParagraphStyle(
        "RightAlign",
        parent=styles["Normal"],
        fontSize=9,
        alignment=TA_RIGHT,
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )
    bold_cell = ParagraphStyle(
        "BoldCell",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )
    bold_right = ParagraphStyle(
        "BoldRight",
        parent=right_style,
        fontName="Helvetica-Bold",
        fontSize=9,
    )
    footer_style = ParagraphStyle(
        "FooterInfo",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#9ca3af"),
        alignment=TA_CENTER,
        leading=12,
    )

    elements = []

    elements.append(Paragraph(f"Expense Report — {company_name}", title_style))

    period = ""
    if cycle_start and cycle_end:
        period = f"{_fmt_date(cycle_start)} to {_fmt_date(cycle_end)}"
    elif cycle_start:
        period = f"From {_fmt_date(cycle_start)}"

    subtitle_parts = []
    if statement_filename:
        subtitle_parts.append(statement_filename)
    if period:
        subtitle_parts.append(period)
    subtitle_parts.append(f"Generated {datetime.now().strftime('%b %d, %Y')}")
    elements.append(Paragraph(" | ".join(subtitle_parts), subtitle_style))
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(
        width="100%", thickness=1,
        color=colors.HexColor("#e5e7eb"),
        spaceAfter=12,
    ))

    header_row = [
        Paragraph("Date", bold_cell),
        Paragraph("Merchant", bold_cell),
        Paragraph("Description", bold_cell),
        Paragraph("GL Code", bold_cell),
        Paragraph("Amount", bold_right),
        Paragraph("Tax", bold_right),
    ]

    col_widths = [70, 130, 150, 90, 75, 65]

    data_rows = [header_row]
    total_amount = 0
    total_tax = 0

    for tx in sorted(transactions, key=lambda t: t.get("transaction_date") or ""):
        amt = tx.get("amount_cad") or 0
        tax = tx.get("tax_amount") or 0
        total_amount += amt
        total_tax += tax

        gl = tx.get("gl_code") or tx.get("gl_code_name") or ""

        data_rows.append([
            Paragraph(_fmt_date(tx.get("transaction_date")), cell_style),
            Paragraph(tx.get("merchant") or "", cell_style),
            Paragraph(tx.get("description") or "", cell_style),
            Paragraph(gl, cell_style),
            Paragraph(_fmt_money(amt), right_style),
            Paragraph(_fmt_money(tax) if tax else "—", right_style),
        ])

    net_amount = total_amount - total_tax

    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9fafb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]

    for i in range(1, len(data_rows)):
        if i % 2 == 0:
            style_commands.append(
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f9fafb"))
            )

    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_commands))
    elements.append(table)

    elements.append(Spacer(1, 16))

    summary_data = [
        [
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("Subtotal", bold_cell),
            Paragraph(_fmt_money(total_amount), bold_right),
            Paragraph("", right_style),
        ],
        [
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("Total Tax", bold_cell),
            Paragraph("", right_style),
            Paragraph(_fmt_money(total_tax), bold_right),
        ],
        [
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("Net Total", ParagraphStyle(
                "NetTotal", parent=bold_cell, fontSize=11,
                textColor=colors.HexColor("#111827"),
            )),
            Paragraph(_fmt_money(net_amount), ParagraphStyle(
                "NetTotalVal", parent=bold_right, fontSize=11,
                textColor=colors.HexColor("#111827"),
            )),
            Paragraph("", right_style),
        ],
    ]

    summary_style = TableStyle([
        ("LINEABOVE", (3, 0), (-1, 0), 1, colors.HexColor("#d1d5db")),
        ("LINEABOVE", (3, 2), (-1, 2), 2, colors.HexColor("#111827")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])

    summary_table = Table(summary_data, colWidths=col_widths)
    summary_table.setStyle(summary_style)
    elements.append(summary_table)

    elements.append(Spacer(1, 24))

    footer_lines = []
    footer_lines.append(
        f"{len(transactions)} transaction{'s' if len(transactions) != 1 else ''} | {company_name}"
    )
    if created_by:
        footer_lines.append(
            f"Created by {created_by}" + (f" on {_fmt_datetime(created_at)}" if created_at else "")
        )
    if approved_by:
        footer_lines.append(
            f"Approved by {approved_by}" + (f" on {_fmt_datetime(approved_at)}" if approved_at else "")
        )

    elements.append(Paragraph("<br/>".join(footer_lines), footer_style))

    doc.build(elements)
    return buf.getvalue()


def append_receipts(report_pdf_bytes: bytes, receipt_files: list[dict]) -> bytes:
    """Append receipt images/PDFs to the end of the report PDF.

    Each entry in receipt_files: {merchant, date, file_bytes, file_type}
    """
    report = fitz.open(stream=report_pdf_bytes, filetype="pdf")
    page_w, page_h = letter  # 612 x 792

    for receipt in receipt_files:
        file_bytes = receipt["file_bytes"]
        file_type = (receipt.get("file_type") or "").lower()
        merchant = receipt.get("merchant") or "Unknown"
        date = receipt.get("date") or ""

        header_text = f"Receipt — {merchant}"
        if date:
            header_text += f"  ({date})"

        if file_type in ("text/html", "html"):
            # Email body receipt — render key info as a text page
            _append_html_receipt_page(report, receipt, header_text, page_w, page_h)
        elif file_type in ("application/pdf", "pdf"):
            # PDF receipt — merge pages directly
            try:
                receipt_doc = fitz.open(stream=file_bytes, filetype="pdf")
                for i in range(len(receipt_doc)):
                    report.insert_pdf(receipt_doc, from_page=i, to_page=i)
                    # Add header to the inserted page
                    inserted_page = report[-1]
                    inserted_page.insert_text(
                        fitz.Point(36, 24),
                        header_text,
                        fontname="helv",
                        fontsize=9,
                        color=(0.4, 0.4, 0.4),
                    )
                receipt_doc.close()
            except Exception:
                # If PDF is corrupt, try as image fallback
                _append_image_page(report, file_bytes, header_text, page_w, page_h)
        else:
            # Image receipt (jpg, png, heic, etc.)
            _append_image_page(report, file_bytes, header_text, page_w, page_h)

    out = io.BytesIO()
    report.save(out)
    report.close()
    return out.getvalue()


def _append_image_page(doc, image_bytes: bytes, header_text: str, page_w: float, page_h: float):
    """Add a new page with the receipt image scaled to fit."""
    page = doc.new_page(width=page_w, height=page_h)

    # Header
    page.insert_text(
        fitz.Point(36, 24),
        header_text,
        fontname="helv",
        fontsize=9,
        color=(0.4, 0.4, 0.4),
    )

    # Image area with margins (36pt sides, 40pt top for header, 36pt bottom)
    margin = 36
    top_margin = 40
    img_area_w = page_w - 2 * margin
    img_area_h = page_h - top_margin - margin

    try:
        img = fitz.open(stream=image_bytes, filetype="png")
        if img.page_count == 0:
            # Try as jpeg
            img.close()
            img = fitz.open(stream=image_bytes, filetype="jpeg")

        pdfbytes = img.convert_to_pdf()
        img.close()
        img_pdf = fitz.open(stream=pdfbytes, filetype="pdf")
        img_page = img_pdf[0]

        # Get image dimensions and scale to fit
        img_w = img_page.rect.width
        img_h = img_page.rect.height

        scale_x = img_area_w / img_w
        scale_y = img_area_h / img_h
        scale = min(scale_x, scale_y, 1.0)  # don't upscale

        final_w = img_w * scale
        final_h = img_h * scale

        # Center horizontally, top-align below header
        x = margin + (img_area_w - final_w) / 2
        y = top_margin

        rect = fitz.Rect(x, y, x + final_w, y + final_h)
        page.show_pdf_page(rect, img_pdf, 0)
        img_pdf.close()
    except Exception:
        page.insert_text(
            fitz.Point(margin, top_margin + 20),
            "[Receipt image could not be loaded]",
            fontname="helv",
            fontsize=11,
            color=(0.7, 0.2, 0.2),
        )


def _append_html_receipt_page(doc, receipt: dict, header_text: str, page_w: float, page_h: float):
    """For email body receipts stored as HTML — strip tags and render the text content."""
    import re as _re

    page = doc.new_page(width=page_w, height=page_h)

    page.insert_text(
        fitz.Point(36, 24),
        header_text,
        fontname="helv",
        fontsize=9,
        color=(0.4, 0.4, 0.4),
    )

    # Strip HTML to plain text
    html = receipt.get("file_bytes", b"")
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    text_content = _re.sub(r"<[^>]+>", " ", html)
    text_content = _re.sub(r"\s+", " ", text_content).strip()

    # Truncate if too long
    if len(text_content) > 3000:
        text_content = text_content[:3000] + "..."

    # Wrap text into lines that fit the page
    margin = 36
    y = 50
    max_width = page_w - 2 * margin
    font_size = 9
    line_height = 13

    words = text_content.split()
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        tw = fitz.get_text_length(test, fontname="helv", fontsize=font_size)
        if tw > max_width and line:
            page.insert_text(
                fitz.Point(margin, y),
                line,
                fontname="helv",
                fontsize=font_size,
            )
            y += line_height
            line = word
            if y > page_h - margin:
                break
        else:
            line = test
    if line and y <= page_h - margin:
        page.insert_text(
            fitz.Point(margin, y),
            line,
            fontname="helv",
            fontsize=font_size,
        )


def add_watermark(pdf_bytes: bytes, text: str = "PENDING APPROVAL") -> bytes:
    """Overlay a faded diagonal watermark on every page of an existing PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        rect = page.rect
        cx, cy = rect.width / 2, rect.height / 2

        tw = fitz.get_text_length(text, fontname="helv", fontsize=54)
        x = cx - tw / 2

        page.insert_text(
            fitz.Point(x, cy),
            text,
            fontname="helv",
            fontsize=54,
            color=(0.85, 0.85, 0.85),
            rotate=0,
            overlay=True,
        )

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()
