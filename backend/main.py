import logging
import threading
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from db import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")
from routers.uploads import router as uploads_router
from routers.statements import router as statements_router
from routers.transactions import router as transactions_router
from routers.lookups import router as lookups_router
from routers.receipts import router as receipts_router
from routers.graph_webhook import router as graph_webhook_router, ensure_subscription_internal

RENEWAL_INTERVAL = 6 * 60 * 60  # 6 hours
_stop_scheduler = threading.Event()


def _subscription_renewal_loop():
    """Background thread: ensure Graph subscription stays alive."""
    time.sleep(30)  # wait for app startup
    while not _stop_scheduler.is_set():
        try:
            result = ensure_subscription_internal()
            logger.info(f"Subscription renewal check: {result}")
        except Exception as e:
            logger.error(f"Subscription renewal failed: {e}", exc_info=True)
        _stop_scheduler.wait(RENEWAL_INTERVAL)


@asynccontextmanager
async def lifespan(app):
    t = threading.Thread(target=_subscription_renewal_loop, daemon=True)
    t.start()
    logger.info("Subscription renewal scheduler started (every 6h)")
    yield
    _stop_scheduler.set()
    logger.info("Subscription renewal scheduler stopped")


app = FastAPI(title="Kothari Group Expenses", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://kothari-group-receipt-software.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(uploads_router)
app.include_router(statements_router)
app.include_router(transactions_router)
app.include_router(lookups_router)
app.include_router(receipts_router)
app.include_router(graph_webhook_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
