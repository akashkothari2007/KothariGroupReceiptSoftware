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


def generate_pdf(
    company_name: str,
    statement_filename: str,
    cycle_start,
    cycle_end,
    transactions: list[dict],
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
    center_style = ParagraphStyle(
        "CenterAlign",
        parent=styles["Normal"],
        fontSize=9,
        alignment=TA_CENTER,
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

    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        f"{len(transactions)} transaction{'s' if len(transactions) != 1 else ''} | {company_name}",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#9ca3af"), alignment=TA_CENTER),
    ))

    doc.build(elements)
    return buf.getvalue()
