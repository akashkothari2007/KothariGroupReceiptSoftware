import io
import os
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from supabase import create_client
from db import engine
from middleware.auth import get_current_user, require_admin
from services.expense_report_handler import generate_pdf, add_watermark, append_receipts

logger = logging.getLogger("expense_reports")

router = APIRouter(
    prefix="/expense-reports",
    tags=["expense-reports"],
    dependencies=[Depends(get_current_user)],
)

_supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
BUCKET = "receipts"
STORAGE_PREFIX = "expense-reports"


def _fetch_transactions(conn, statement_id: str, company_id: str):
    """Shared query for fetching transactions + GL code display + receipt info."""
    rows = conn.execute(
        text("""
            SELECT t.transaction_date, t.merchant, t.description,
                   t.amount_cad, t.tax_amount,
                   g.code, g.name,
                   t.matched_receipt_id, r.image_url, r.file_type
            FROM transactions t
            LEFT JOIN gl_codes g ON g.id = t.gl_code_id
            LEFT JOIN receipts r ON r.id = t.matched_receipt_id
            WHERE t.statement_id = :sid AND t.company_id = :cid
            ORDER BY t.transaction_date, t.merchant
        """),
        {"sid": statement_id, "cid": company_id},
    ).fetchall()

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
            "receipt_storage_path": r[8],
            "receipt_file_type": r[9],
        })
    return transactions


def _fetch_statement(conn, statement_id: str):
    row = conn.execute(
        text("SELECT filename, cycle_start, cycle_end FROM statements WHERE id = :sid"),
        {"sid": statement_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Statement not found")
    return row


def _fetch_company(conn, company_id: str):
    row = conn.execute(
        text("SELECT name FROM companies WHERE id = :cid"),
        {"cid": company_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return row


# ── Live PDF (no storage, for the preview download button) ──────────────

@router.get("/{statement_id}/pdf")
def download_live_pdf(statement_id: str, company_id: str):
    with engine.connect() as conn:
        stmt = _fetch_statement(conn, statement_id)
        company = _fetch_company(conn, company_id)
        transactions = _fetch_transactions(conn, statement_id, company_id)

    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions for this company")

    pdf_bytes = generate_pdf(
        company_name=company[0],
        statement_filename=stmt[0],
        cycle_start=stmt[1],
        cycle_end=stmt[2],
        transactions=transactions,
    )
    pdf_bytes = add_watermark(pdf_bytes, "SNAPSHOT")

    safe = company[0].replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Expense_Report_{safe}_SNAPSHOT.pdf"'},
    )


# ── Finalize (snapshot PDF → storage + DB row) ─────────────────────────

@router.post("/{statement_id}/finalize")
def finalize_report(
    statement_id: str,
    company_id: str,
    user: dict = Depends(get_current_user),
):
    created_by = user.get("email", "unknown")
    now = datetime.now(timezone.utc)

    with engine.connect() as conn:
        stmt = _fetch_statement(conn, statement_id)
        company = _fetch_company(conn, company_id)
        transactions = _fetch_transactions(conn, statement_id, company_id)

    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions for this company")

    total_amount = sum(t["amount_cad"] for t in transactions)
    total_tax = sum(t["tax_amount"] for t in transactions)

    pdf_bytes = generate_pdf(
        company_name=company[0],
        statement_filename=stmt[0],
        cycle_start=stmt[1],
        cycle_end=stmt[2],
        transactions=transactions,
        created_by=created_by,
        created_at=now,
    )

    # Fetch receipt files and append to PDF
    receipt_files = []
    for tx in sorted(transactions, key=lambda t: t.get("transaction_date") or ""):
        path = tx.get("receipt_storage_path")
        if not path:
            continue
        try:
            file_bytes = _supabase.storage.from_(BUCKET).download(path)
            receipt_files.append({
                "merchant": tx.get("merchant") or "Unknown",
                "date": tx.get("transaction_date") or "",
                "file_bytes": file_bytes,
                "file_type": tx.get("receipt_file_type") or "image/jpeg",
            })
        except Exception as e:
            logger.warning(f"Failed to download receipt {path}: {e}")

    if receipt_files:
        pdf_bytes = append_receipts(pdf_bytes, receipt_files)
        logger.info(f"Appended {len(receipt_files)} receipts to report PDF")

    storage_path = f"{STORAGE_PREFIX}/{uuid.uuid4()}.pdf"
    _supabase.storage.from_(BUCKET).upload(storage_path, pdf_bytes, {"content-type": "application/pdf"})
    logger.info(f"Stored finalized PDF: {storage_path}")

    report_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO expense_reports
                    (id, statement_id, company_id, status,
                     total_amount, total_tax, transaction_count,
                     pdf_storage_path, created_by, created_at)
                VALUES
                    (:id, :sid, :cid, 'pending',
                     :total_amount, :total_tax, :tx_count,
                     :path, :created_by, :created_at)
            """),
            {
                "id": report_id,
                "sid": statement_id,
                "cid": company_id,
                "total_amount": total_amount,
                "total_tax": total_tax,
                "tx_count": len(transactions),
                "path": storage_path,
                "created_by": created_by,
                "created_at": now,
            },
        )

    logger.info(f"Finalized report {report_id} for {company[0]}")
    return {
        "id": report_id,
        "status": "pending",
        "company_id": company_id,
        "company_name": company[0],
        "created_by": created_by,
        "created_at": now.isoformat(),
        "total_amount": total_amount,
        "total_tax": total_tax,
        "transaction_count": len(transactions),
    }


# ── List finalized reports for a statement ──────────────────────────────

@router.get("/")
def list_reports(statement_id: str):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT er.id, er.company_id, c.name as company_name,
                       er.status, er.total_amount, er.total_tax,
                       er.transaction_count,
                       er.created_by, er.created_at,
                       er.approved_by, er.approved_at
                FROM expense_reports er
                JOIN companies c ON c.id = er.company_id
                WHERE er.statement_id = :sid
                ORDER BY c.name, er.created_at DESC
            """),
            {"sid": statement_id},
        ).fetchall()

    return [
        {
            "id": r[0],
            "company_id": r[1],
            "company_name": r[2],
            "status": r[3],
            "total_amount": float(r[4]) if r[4] else 0,
            "total_tax": float(r[5]) if r[5] else 0,
            "transaction_count": r[6],
            "created_by": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
            "approved_by": r[9],
            "approved_at": r[10].isoformat() if r[10] else None,
        }
        for r in rows
    ]


# ── Download stored PDF (watermark if pending) ──────────────────────────

@router.get("/{report_id}/download")
def download_report(report_id: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT er.status, er.pdf_storage_path, c.name,
                       er.created_by, er.created_at,
                       er.approved_by, er.approved_at
                FROM expense_reports er
                JOIN companies c ON c.id = er.company_id
                WHERE er.id = :rid
            """),
            {"rid": report_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    status, storage_path, company_name = row[0], row[1], row[2]

    pdf_bytes = _supabase.storage.from_(BUCKET).download(storage_path)

    if status == "pending":
        pdf_bytes = add_watermark(pdf_bytes, "PENDING APPROVAL")

    safe = company_name.replace(" ", "_").replace("/", "_")
    suffix = "_PENDING" if status == "pending" else "_APPROVED"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Expense_Report_{safe}{suffix}.pdf"'},
    )


# ── Approve ─────────────────────────────────────────────────────────────

@router.post("/{report_id}/approve")
def approve_report(report_id: str, user: dict = Depends(require_admin)):
    approved_by = user.get("email", "unknown")
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE expense_reports
                SET status = 'approved', approved_by = :approved_by, approved_at = :approved_at
                WHERE id = :rid AND status = 'pending'
                RETURNING id
            """),
            {"rid": report_id, "approved_by": approved_by, "approved_at": now},
        ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Report not found or already approved")

    logger.info(f"Report {report_id} approved by {approved_by}")
    return {"id": report_id, "status": "approved", "approved_by": approved_by, "approved_at": now.isoformat()}


# ── Delete ──────────────────────────────────────────────────────────────

@router.delete("/{report_id}")
def delete_report(report_id: str):
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT pdf_storage_path FROM expense_reports WHERE id = :rid"),
            {"rid": report_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Report not found")

        conn.execute(
            text("DELETE FROM expense_reports WHERE id = :rid"),
            {"rid": report_id},
        )

    try:
        _supabase.storage.from_(BUCKET).remove([row[0]])
    except Exception as e:
        logger.warning(f"Failed to delete PDF from storage: {e}")

    logger.info(f"Deleted report {report_id}")
    return {"deleted": True}
