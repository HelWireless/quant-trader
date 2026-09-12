"""
Backfill market cap columns from Baidu CSV files.
Updates circ_market_cap and total_market_cap in daily_kline.
"""

import os
import sys
import time
import glob

import pandas as pd
from sqlalchemy import create_engine, text

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CSV_DIR = os.path.join(PROJECT_DIR, "data", "raw", "baidu")
DB_URL = "postgresql://postgres@localhost:5432/quant_minute"


def parse_stock_code(raw_code):
    raw_code = raw_code.strip().lower()
    if raw_code.startswith("sh"):
        return raw_code[2:], "SH"
    elif raw_code.startswith("sz"):
        return raw_code[2:], "SZ"
    elif raw_code.startswith("bj"):
        return raw_code[2:], "BJ"
    return raw_code, ""


def backfill_csv(csv_path, engine):
    try:
        df = pd.read_csv(csv_path, encoding="gbk", low_memory=False)
    except Exception:
        return 0

    if df.empty or len(df.columns) < 12:
        return 0

    cols = df.columns.tolist()
    raw_code = str(df.iloc[0][cols[0]])
    stock_code, _ = parse_stock_code(raw_code)

    dates = df[cols[2]].astype(str).str[:10]
    circ_cap = pd.to_numeric(df[cols[10]], errors="coerce").fillna(0)
    total_cap = pd.to_numeric(df[cols[11]], errors="coerce").fillna(0)

    records = list(zip(
        [stock_code] * len(dates),
        dates.tolist(),
        circ_cap.tolist(),
        total_cap.tolist(),
    ))

    with engine.begin() as conn:
        conn.execute(
            text("""UPDATE daily_kline
                   SET circ_market_cap = :circ, total_market_cap = :total
                   WHERE code = :code AND date = :date"""),
            [{"circ": r[2], "total": r[3], "code": r[0], "date": r[1]} for r in records],
        )
    return len(records)


def main():
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    print(f"Processing {len(csv_files)} CSV files...")

    engine = create_engine(DB_URL)
    total = 0
    t0 = time.time()

    for i, csv_path in enumerate(csv_files):
        updated = backfill_csv(csv_path, engine)
        total += updated

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(csv_files)}] updated {total} rows in {elapsed:.1f}s")

    elapsed = time.time() - t0

    # Verify
    with engine.connect() as conn:
        r = conn.execute(
            text("SELECT COUNT(*) FROM daily_kline WHERE total_market_cap > 0")
        ).fetchone()
    print(f"\nDone: {total} rows updated in {elapsed:.1f}s")
    print(f"Records with market cap data: {r[0]}")
    engine.dispose()


if __name__ == "__main__":
    main()
