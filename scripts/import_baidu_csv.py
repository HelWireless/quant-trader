"""
Bulk import Baidu Netdisk CSV data into PostgreSQL database.

CSV format (GBK encoding, columns by position):
  0: stock_code   (e.g. sh600000)
  1: stock_name   (e.g. 浦发银行)
  2: date         (YYYY-MM-DD)
  3: open
  4: high
  5: low
  6: close
  7: prev_close
  8: volume
  9: amount
  10: circulating_market_cap
  11: total_market_cap
  12-24: additional columns (ignored)

Uses INSERT ... ON CONFLICT DO NOTHING for fast upsert on (code, date) unique constraint.
"""

import os
import sys
import time
import glob

import pandas as pd
from sqlalchemy import create_engine, text

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CSV_DIR = os.path.join(PROJECT_DIR, "data", "raw", "baidu")
DB_URL = "postgresql://postgres@localhost:5432/quant_minute"


def parse_stock_code(raw_code: str):
    """Parse 'sh600000' -> ('600000', 'SH'), 'sz000001' -> ('000001', 'SZ')"""
    raw_code = raw_code.strip().lower()
    if raw_code.startswith("sh"):
        return raw_code[2:], "SH"
    elif raw_code.startswith("sz"):
        return raw_code[2:], "SZ"
    elif raw_code.startswith("bj"):
        return raw_code[2:], "BJ"
    else:
        return raw_code, ""


def import_csv_to_db(csv_path: str, engine) -> dict:
    """Import a single CSV file into the database. Returns stats dict."""
    try:
        df = pd.read_csv(csv_path, encoding="gbk", low_memory=False)
    except Exception as e:
        return {"error": f"read error: {e}", "rows": 0}

    if df.empty or len(df.columns) < 10:
        return {"error": "too few columns", "rows": 0}

    # Use column positions (encoding-safe)
    cols = df.columns.tolist()
    code_col = cols[0]   # stock_code
    name_col = cols[1]   # stock_name
    date_col = cols[2]   # date
    open_col = cols[3]   # open
    high_col = cols[4]   # high
    low_col = cols[5]    # low
    close_col = cols[6]  # close
    vol_col = cols[8]    # volume
    amt_col = cols[9]    # amount

    # Extract stock info from first row
    raw_code = str(df.iloc[0][code_col])
    stock_code, market = parse_stock_code(raw_code)
    stock_name = str(df.iloc[0][name_col])

    # Build kline records
    kline_df = pd.DataFrame({
        "code": stock_code,
        "date": df[date_col].astype(str).str[:10],
        "open": pd.to_numeric(df[open_col], errors="coerce").fillna(0),
        "high": pd.to_numeric(df[high_col], errors="coerce").fillna(0),
        "low": pd.to_numeric(df[low_col], errors="coerce").fillna(0),
        "close": pd.to_numeric(df[close_col], errors="coerce").fillna(0),
        "volume": pd.to_numeric(df[vol_col], errors="coerce").fillna(0),
        "amount": pd.to_numeric(df[amt_col], errors="coerce").fillna(0),
    })

    # Drop rows with invalid dates
    kline_df = kline_df[kline_df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]

    inserted = 0
    try:
        with engine.begin() as conn:
            # Insert stock_info (ON CONFLICT DO NOTHING)
            conn.execute(
                text("""INSERT INTO stock_info (code, name, market, updated_at)
                        VALUES (:code, :name, :market, CURRENT_TIMESTAMP)
                        ON CONFLICT (code) DO NOTHING"""),
                {"code": stock_code, "name": stock_name, "market": market},
            )

            # Bulk insert kline records (ON CONFLICT DO NOTHING)
            records = kline_df.values.tolist()
            if records:
                conn.execute(
                    text("""INSERT INTO daily_kline
                            (code, date, open, high, low, close, volume, amount, turnover)
                            VALUES (:code, :date, :open, :high, :low, :close, :volume, :amount, 0)
                            ON CONFLICT (code, date) DO NOTHING"""),
                    [
                        {"code": r[0], "date": r[1], "open": r[2], "high": r[3],
                         "low": r[4], "close": r[5], "volume": r[6], "amount": r[7]}
                        for r in records
                    ],
                )
                inserted = len(records)
    except Exception as e:
        return {"error": f"insert error: {e}", "rows": len(records)}

    return {
        "code": stock_code,
        "name": stock_name,
        "market": market,
        "rows": len(records),
        "inserted": inserted,
    }


def main():
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    print(f"Found {len(csv_files)} CSV files in {CSV_DIR}")
    print(f"Database: {DB_URL}")

    engine = create_engine(DB_URL)

    total_inserted = 0
    total_errors = 0
    t0 = time.time()

    for i, csv_path in enumerate(csv_files):
        result = import_csv_to_db(csv_path, engine)

        if "error" in result:
            total_errors += 1
            if total_errors <= 5:
                print(f"  ERROR {os.path.basename(csv_path)}: {result['error']}")
        else:
            total_inserted += result.get("inserted", 0)

        # Progress every 100 files
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(csv_files)}] imported {total_inserted} rows in {elapsed:.1f}s")

    elapsed = time.time() - t0

    # Final stats
    with engine.connect() as conn:
        stats = conn.execute(text("SELECT COUNT(*) FROM stock_info")).fetchone()[0]
        kline_stats = conn.execute(
            text("SELECT COUNT(*), COUNT(DISTINCT code) FROM daily_kline")
        ).fetchone()

    print(f"\n{'='*50}")
    print(f"Import complete in {elapsed:.1f}s")
    print(f"  CSV files processed: {len(csv_files)}")
    print(f"  Errors: {total_errors}")
    print(f"  New kline rows inserted: {total_inserted}")
    print(f"  Total stock_info records: {stats}")
    print(f"  Total daily_kline records: {kline_stats[0]}")
    print(f"  Stocks with kline data: {kline_stats[1]}")

    engine.dispose()


if __name__ == "__main__":
    main()
