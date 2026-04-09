import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user
from services.expense_report_handler import generate_pdf
import io

logger = logging.getLogger("expense_reports")

router = APIRouter(prefix="/expense-reports", tags=["expense-reports"], dependencies=[Depends(get_current_user)])


@router.get("/{statement_id}/pdf")
def download_expense_report_pdf(statement_id: str, company_id: str):
    with engine.connect() as conn:
        stmt = conn.execute(
            text("SELECT filename, cycle_start, cycle_end FROM statements WHERE id = :sid"),
            {"sid": statement_id},
        ).fetchone()

        if not stmt:
            raise HTTPException(status_code=404, detail="Statement not found")

        company = conn.execute(
            text("SELECT name FROM companies WHERE id = :cid"),
            {"cid": company_id},
        ).fetchone()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        rows = conn.execute(
            text("""
                SELECT t.transaction_date, t.merchant, t.description,
                       t.amount_cad, t.tax_amount,
                       g.code, g.name
                FROM transactions t
                LEFT JOIN gl_codes g ON g.id = t.gl_code_id
                WHERE t.statement_id = :sid AND t.company_id = :cid
                ORDER BY t.transaction_date, t.merchant
            """),
            {"sid": statement_id, "cid": company_id},
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No transactions found for this company in this statement")

    transactions = []
    for r in rows:
        gl_display = ""
        if r[5] and r[6]:
            gl_display = f"{r[5]} — {r[6]}"
        elif r[5]:
            gl_display = r[5]

        transactions.append({
            "transaction_date": r[0].isoformat() if r[0] else None,
            "merchant": r[1],
            "description": r[2],
            "amount_cad": float(r[3]) if r[3] is not None else 0,
            "tax_amount": float(r[4]) if r[4] is not None else 0,
            "gl_code": gl_display,
        })

    company_name = company[0]
    statement_filename = stmt[0]
    cycle_start = stmt[1]
    cycle_end = stmt[2]

    logger.info(f"Generating PDF: {company_name}, {len(transactions)} transactions")

    pdf_bytes = generate_pdf(
        company_name=company_name,
        statement_filename=statement_filename,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        transactions=transactions,
    )

    safe_name = company_name.replace(" ", "_").replace("/", "_")
    filename = f"Expense_Report_{safe_name}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
