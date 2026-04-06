# Kothari Group Expenses

Internal tool for processing American Express statements, matching receipts, splitting taxes, and assigning expenses to companies and GL codes. Built for Anupam Kothari to manage multi-company expense reporting.

## What it does

1. Upload an Amex CSV statement — transactions get parsed and stored
2. Upload receipts (photos, PDFs) — AI extracts merchant, date, amounts, tax, country
3. Auto-matching links receipts to transactions based on amount, merchant name, and date
4. Tax is auto-filled: Canadian receipts copy the tax amount, foreign receipts set tax to $0 (can't claim back)
5. Assign each transaction a company and GL code (will support auto-assignment via vendor mappings later)
6. Eventually: generate per-company expense reports for accountants

## How matching works

Matching runs automatically on two triggers:

- **Statement uploaded** — all new transactions are scored against unmatched receipts (and any "unsure" matches get re-evaluated in case a better match exists now)
- **Receipt AI extraction completes** — the new receipt is scored against all unmatched transactions (plus any "unsure" ones)

Scoring is based on three signals:

| Signal | Points |
|---|---|
| Amount match (correct currency, exact) | 50 |
| Amount match (correct currency, within 5%) | 25 |
| Amount match (wrong currency, coincidental) | 15 |
| Merchant keyword overlap | 30 |
| Same day | 15 |
| Within 1-3 days | 10 |

Score >= 65 = auto-match. Score 40-64 = "unsure" (flagged for human review). Below 40 = no match.

Country matters: a US receipt matching a CAD amount is suspicious (cross-currency = only 15 points), but matching the foreign amount is correct (full 50 points). This prevents false positives like a $300 CAD donation matching a $300 USD hotel booking.

You can also manually match from the transaction table — click "Link" on any unmatched transaction and pick a receipt. Click the X to unmatch.

## Tech stack

- **Frontend**: React + Vite (single page, App.jsx)
- **Backend**: FastAPI + SQLAlchemy (raw SQL, no ORM models)
- **Database**: Supabase PostgreSQL (connected via pgbouncer, NullPool)
- **Storage**: Supabase Storage (private bucket, signed URLs for access)
- **AI**: Azure OpenAI GPT-4.1 mini (vision API for receipt OCR)
- **Deployment**: Docker Compose

## File structure

```
backend/
  main.py                  — FastAPI app, CORS, router registration
  db.py                    — SQLAlchemy engine (NullPool for Supabase pgbouncer)
  routers/
    uploads.py             — POST /upload/statement (Amex CSV parser)
    statements.py          — GET/DELETE statements, GET transactions
    transactions.py        — PATCH transactions, POST/DELETE match
    receipts.py            — CRUD receipts, signed URL generation
    lookups.py             — GET companies, GL codes
  services/
    ai.py                  — Azure OpenAI vision API caller (3x retry)
    prompts.py             — Receipt extraction prompt
    receipt_extractor.py   — Background task: download → convert → AI → update
    matcher.py             — Scoring engine (pure logic, no DB)
    match_writer.py        — Writes match results to DB, handles tax auto-fill
    match_run.py           — Orchestrator: fetches candidates, runs matcher, applies results

frontend/src/
  App.jsx                  — Everything: tabs, transaction table, receipt cards, modals
  App.css                  — All styles
```

## Running it

```bash
docker compose up --build
```

Frontend: http://localhost:5173
Backend: http://localhost:8000
Health check: http://localhost:8000/health

Needs a `.env` in `backend/` with:
```
DATABASE_URL="postgresql://..."
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=...
AZURE_VISION_API_URL="https://..."
AZURE_VISION_API_KEY=...
```

## What's not built yet

- Auth (single user for now, no login)
- Vendor mappings (auto-assign company + GL code based on merchant)
- Per-company expense reports (CSV/PDF export)
- Receipt image compression (for storage savings at scale)
- Pagination on receipts list
- Multi-card support (currently Amex only)
