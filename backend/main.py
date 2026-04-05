from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from db import engine
from routers.uploads import router as uploads_router
from routers.statements import router as statements_router
from routers.transactions import router as transactions_router
from routers.lookups import router as lookups_router

app = FastAPI(title="Kothari Group Expenses")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(uploads_router)
app.include_router(statements_router)
app.include_router(transactions_router)
app.include_router(lookups_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
