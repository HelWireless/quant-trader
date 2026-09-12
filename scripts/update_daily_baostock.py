"""Update daily kline data from BaoStock.

Fetches daily kline data for all stocks and upserts into PostgreSQL daily_kline table.
Supports incremental update (only fetches data after the latest date in DB).

Usage:
    python scripts/update_daily_baostock.py [--start-date 2025-04-01] [--codes 600519,000001]
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://postgres@localhost:5432/quant_minute"

# BaoStock daily kline fields
DAILY_FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg"


def to_bs_code(code: str) -> str:
    """Convert '600519' -> 'sh.600519'"""
    code = code.strip()
    if "." in code:
        return code
    if code.startswith("6") or code.startswith("9"):
        return f"sh.{code}"
    elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
        return f"sz.{code}"
    elif code.startswith("4") or code.startswith("8"):
        return f"bj.{code}"
    return f"sh.{code}"


def from_bs_code(bs_code: str) -> str:
    """Convert 'sh.600519' -> '600519'"""
    if "." in bs_code:
        return bs_code.split(".")[1]
    return bs_code


def get_codes_from_db(engine) -> list:
    """Get all A-share codes from stock_info."""
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT code FROM stock_info WHERE code ~ '^[036]' ORDER BY code"
        )).fetchall()
        return [row[0] for row in r]


def get_latest_dates(engine, codes: list) -> dict:
    """Get latest date for each code in daily_kline."""
    result = {}
    # Batch query for efficiency
    batch_size = 500
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        with engine.connect() as conn:
            r = conn.execute(text("""
                SELECT code, MAX(date) as max_date
                FROM daily_kline
                WHERE code = ANY(:codes)
                GROUP BY code
            """), {"codes": batch}).fetchall()
            for row in r:
                result[row[0]] = str(row[1])
    return result


def fetch_daily(bs, code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily kline from BaoStock for one stock."""
    bs_code = to_bs_code(code)

    rs = bs.query_history_k_data_plus(
        bs_code,
        DAILY_FIELDS,
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="3",  # 不复权
    )

    if rs.error_code != "0":
        return pd.DataFrame()

    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=rs.fields)

    # Convert types
    for col in ["open", "high", "low", "close", "preclose", "volume", "amount", "turn", "pctChg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Filter out invalid dates
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]

    # Rename 'code' from bs format to plain
    df["code"] = df["code"].apply(from_bs_code)

    return df


def upsert_daily(engine, df: pd.DataFrame) -> int:
    """Upsert daily kline data into PostgreSQL."""
    if df.empty:
        return 0

    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO daily_kline (code, date, open, high, low, close, volume, amount, turnover)
                VALUES (:code, :date, :open, :high, :low, :close, :volume, :amount, :turnover)
                ON CONFLICT (code, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount
            """), {
                "code": row["code"],
                "date": row["date"],
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
                "amount": float(row.get("amount", 0)),
                "turnover": float(row.get("turn", 0)),
            })
            inserted += 1

    return inserted


def update_stock_info(engine, bs, codes: list):
    """Add new stocks from BaoStock to stock_info if not present."""
    with engine.connect() as conn:
        existing = {row[0] for row in conn.execute(text("SELECT code FROM stock_info")).fetchall()}

    new_codes = [c for c in codes if c not in existing]
    if not new_codes:
        return 0

    with engine.begin() as conn:
        for code in new_codes:
            market = "SH" if code.startswith("6") else "SZ" if code.startswith(("0", "3")) else "BJ"
            conn.execute(
                text("INSERT INTO stock_info (code, name, market) VALUES (:code, '', :market) ON CONFLICT (code) DO NOTHING"),
                {"code": code, "market": market},
            )

    logger.info(f"Added {len(new_codes)} new stocks to stock_info")
    return len(new_codes)


def main():
    parser = argparse.ArgumentParser(description="Update daily kline from BaoStock")
    parser.add_argument("--start-date", type=str, default="",
                        help="Override start date (YYYY-MM-DD). Default: auto-detect per stock")
    parser.add_argument("--end-date", type=str, default="",
                        help="End date (YYYY-MM-DD). Default: today")
    parser.add_argument("--codes", type=str, default="",
                        help="Comma-separated codes (default: all from stock_info)")
    parser.add_argument("--max-stocks", type=int, default=0,
                        help="Max stocks to process (0=all)")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Delay between requests (seconds)")
    parser.add_argument("--db-url", type=str, default=DB_URL)
    args = parser.parse_args()

    import baostock as bs

    # Login
    result = bs.login()
    if result.error_code != "0":
        logger.error(f"BaoStock login failed: {result.error_msg}")
        return
    logger.info("BaoStock login successful")

    engine = create_engine(args.db_url)

    # Get stock list
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    else:
        codes = get_codes_from_db(engine)
    logger.info(f"Stock list: {len(codes)} codes")

    if args.max_stocks > 0:
        codes = codes[:args.max_stocks]

    # Get latest dates per stock
    if args.start_date:
        latest_dates = {c: args.start_date for c in codes}
    else:
        latest_dates = get_latest_dates(engine, codes)
        logger.info(f"Got latest dates for {len(latest_dates)} stocks")

    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")

    # Update stock_info with any new codes
    update_stock_info(engine, bs, codes)

    # Process each stock
    total_imported = 0
    success_count = 0
    fail_count = 0
    skip_count = 0
    t0 = time.time()

    for i, code in enumerate(codes):
        # Determine start date (latest date in DB + 1 day, or override)
        if code in latest_dates:
            latest = latest_dates[code]
            # Start from the day after latest
            start = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start = args.start_date or "2025-04-01"

        if start > end_date:
            skip_count += 1
            continue

        try:
            df = fetch_daily(bs, code, start, end_date)
            if not df.empty:
                inserted = upsert_daily(engine, df)
                total_imported += inserted
                success_count += 1
            else:
                success_count += 1  # No new data is still a success

        except Exception as e:
            fail_count += 1
            logger.error(f"Error {code}: {e}")
            # Try re-login on error
            try:
                bs.logout()
                bs.login()
            except Exception:
                pass

        # Progress every 50 stocks
        if (i + 1) % 50 == 0 or i == len(codes) - 1:
            elapsed = time.time() - t0
            avg = elapsed / (i + 1) if (i + 1) > 0 else 1
            remaining = (len(codes) - i - 1) * avg
            logger.info(
                f"  [{i + 1}/{len(codes)}] "
                f"imported: {total_imported:,} | "
                f"ok: {success_count} | fail: {fail_count} | skip: {skip_count} | "
                f"avg: {avg:.2f}s/stock | "
                f"ETA: {remaining / 60:.1f}min"
            )

        if args.delay > 0:
            time.sleep(args.delay)

    # Logout
    bs.logout()

    elapsed = time.time() - t0
    logger.info(f"\n{'=' * 60}")
    logger.info(
        f"Update complete: {total_imported:,} rows | "
        f"{success_count} ok | {fail_count} fail | {skip_count} skip | "
        f"{elapsed:.0f}s ({elapsed / 60:.1f}min)"
    )

    # Verify
    with engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM daily_kline")).fetchone()
        logger.info(f"Total daily_kline rows: {r[0]:,}")
        r = conn.execute(text("SELECT MAX(date) FROM daily_kline")).fetchone()
        logger.info(f"Latest date: {r[0]}")
        r = conn.execute(text(
            "SELECT COUNT(DISTINCT code) FROM daily_kline WHERE date = (SELECT MAX(date) FROM daily_kline)"
        )).fetchone()
        logger.info(f"Stocks on latest date: {r[0]}")

    engine.dispose()


if __name__ == "__main__":
    main()
