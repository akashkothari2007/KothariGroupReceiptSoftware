from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# NullPool: no local pooling — Supabase already runs pgbouncer.
# Each request gets a fresh connection that's closed immediately after use.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, poolclass=NullPool)
