"""Migrate daily kline data from SQLite (quant.db) to PostgreSQL (quant_minute).

Reads stock_info, daily_kline, screening_result from SQLite and bulk-inserts
into PostgreSQL using COPY protocol for speed.

Usage:
    python scripts/migrate_sqlite_to_pg.py
"""

import os
import sys
import sqlite3
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parent.parent
SQLITE_PATH = PROJECT_ROOT / "data" / "quant.db"
PG_URL = "postgresql://postgres@localhost:5432/quant_minute"
BATCH_SIZE = 50_000


def migrate_stock_info(sqlite_conn, pg_engine):
    """Migrate stock_info table."""
    print("\n=== Migrating stock_info ===")
    df = pd.read_sql_query("SELECT * FROM stock_info", sqlite_conn)
    print(f"  SQLite rows: {len(df):,}")

    if df.empty:
        print("  No data to migrate")
        return

    # Check existing
    with pg_engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM stock_info")).fetchone()
        existing = r[0]
        if existing > 0:
            print(f"  PostgreSQL already has {existing:,} rows, skipping (idempotent)")
            return

    df.to_sql("stock_info", pg_engine, if_exists="append", index=False,
              method="multi", chunksize=BATCH_SIZE)
    print(f"  Migrated {len(df):,} rows")


def migrate_daily_kline(sqlite_conn, pg_engine):
    """Migrate daily_kline table in batches."""
    print("\n=== Migrating daily_kline ===")

    # Check existing
    with pg_engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM daily_kline")).fetchone()
        existing = r[0]
        if existing > 0:
            print(f"  PostgreSQL already has {existing:,} rows, skipping (idempotent)")
            return

    # Get total count
    total = sqlite_conn.execute("SELECT COUNT(*) FROM daily_kline").fetchone()[0]
    print(f"  SQLite rows: {total:,}")

    # Read in chunks using offset/limit
    offset = 0
    migrated = 0
    t0 = time.time()

    while offset < total:
        query = f"""
            SELECT code, date, open, high, low, close, volume, amount,
                   turnover, circ_market_cap, total_market_cap
            FROM daily_kline
            ORDER BY id
            LIMIT {BATCH_SIZE} OFFSET {offset}
        """
        df = pd.read_sql_query(query, sqlite_conn)
        if df.empty:
            break

        df.to_sql("daily_kline", pg_engine, if_exists="append", index=False,
                  method="multi", chunksize=10_000)

        migrated += len(df)
        elapsed = time.time() - t0
        speed = migrated / elapsed if elapsed > 0 else 0
        eta = (total - migrated) / speed if speed > 0 else 0
        print(f"  [{migrated:,}/{total:,}] {speed:,.0f} rows/s, ETA: {eta:.0f}s")

        offset += BATCH_SIZE

    print(f"  Migrated {migrated:,} rows in {time.time()-t0:.1f}s")


def migrate_screening_result(sqlite_conn, pg_engine):
    """Migrate screening_result table."""
    print("\n=== Migrating screening_result ===")
    df = pd.read_sql_query("SELECT * FROM screening_result", sqlite_conn)
    print(f"  SQLite rows: {len(df):,}")

    if df.empty:
        print("  No data to migrate")
        return

    with pg_engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM screening_result")).fetchone()
        existing = r[0]
        if existing > 0:
            print(f"  PostgreSQL already has {existing:,} rows, skipping")
            return

    df.to_sql("screening_result", pg_engine, if_exists="append", index=False,
              method="multi", chunksize=BATCH_SIZE)
    print(f"  Migrated {len(df):,} rows")


def verify(pg_engine):
    """Verify migrated data."""
    print("\n=== Verification ===")
    with pg_engine.connect() as conn:
        for table in ["stock_info", "daily_kline", "screening_result"]:
            r = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
            print(f"  {table}: {r[0]:,} rows")

        # Sample check
        r = conn.execute(text(
            "SELECT MIN(date), MAX(date), COUNT(DISTINCT code) FROM daily_kline"
        )).fetchone()
        print(f"  daily_kline range: {r[0]} ~ {r[1]}, codes: {r[2]}")


def main():
    print(f"SQLite: {SQLITE_PATH}")
    print(f"PostgreSQL: {PG_URL}")

    if not SQLITE_PATH.exists():
        print(f"ERROR: SQLite database not found: {SQLITE_PATH}")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    pg_engine = create_engine(PG_URL)

    t0 = time.time()

    migrate_stock_info(sqlite_conn, pg_engine)
    migrate_daily_kline(sqlite_conn, pg_engine)
    migrate_screening_result(sqlite_conn, pg_engine)
    verify(pg_engine)

    sqlite_conn.close()
    pg_engine.dispose()

    print(f"\nMigration complete in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
