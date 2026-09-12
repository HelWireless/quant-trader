"""Update daily kline data from AkShare (东方财富).

Fetches daily kline data for all A-share stocks and upserts into PostgreSQL.
Supports incremental update (only fetches data after the latest date in DB).

Usage:
    python scripts/update_daily_akshare.py [--start-date 2025-04-01] [--codes 600519,000001]
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

# AkShare column positions (encoding-safe)
# 0:日期, 1:股票代码, 2:开盘, 3:收盘, 4:最高, 5:最低, 6:成交量, 7:成交额, 8:振幅, 9:涨跌幅, 10:涨跌额, 11:换手率
COL_MAP = {
    0: "date",
    1: "code",
    2: "open",
    3: "close",
    4: "high",
    5: "low",
    6: "volume",
    7: "amount",
    9: "pctChg",
    11: "turnover",
}


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


def fetch_daily_akshare(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily kline from AkShare for one stock."""
    import akshare as ak

    # Format dates as YYYYMMDD
    start_fmt = start_date.replace("-", "")
    end_fmt = end_date.replace("-", "")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_fmt,
            end_date=end_fmt,
            adjust="",  # 不复权
        )
    except Exception as e:
        logger.debug(f"AkShare error for {code}: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Rename columns by position (Chinese names vary by encoding)
    col_names = list(range(len(df.columns)))
    df.columns = col_names
    df = df.rename(columns=COL_MAP)

    # Keep only needed columns
    keep_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount", "pctChg", "turnover"]
    for col in keep_cols:
        if col not in df.columns:
            df[col] = 0

    df = df[keep_cols].copy()

    # Ensure code is string
    df["code"] = code

    # Convert numeric columns
    for col in ["open", "high", "low", "close", "volume", "amount", "pctChg", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

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
                    amount = EXCLUDED.amount,
                    turnover = EXCLUDED.turnover
            """), {
                "code": str(row["code"]),
                "date": str(row["date"])[:10],
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
                "amount": float(row.get("amount", 0)),
                "turnover": float(row.get("turnover", 0)),
            })
            inserted += 1

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Update daily kline from AkShare")
    parser.add_argument("--start-date", type=str, default="",
                        help="Override start date (YYYY-MM-DD). Default: auto-detect per stock")
    parser.add_argument("--end-date", type=str, default="",
                        help="End date (YYYY-MM-DD). Default: today")
    parser.add_argument("--codes", type=str, default="",
                        help="Comma-separated codes (default: all from stock_info)")
    parser.add_argument("--max-stocks", type=int, default=0,
                        help="Max stocks to process (0=all)")
    parser.add_argument("--delay", type=float, default=0.3,
                        help="Delay between requests (seconds, default: 0.3)")
    parser.add_argument("--db-url", type=str, default=DB_URL)
    args = parser.parse_args()

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
        latest_dates = {}
    else:
        latest_dates = get_latest_dates(engine, codes)
        logger.info(f"Got latest dates for {len(latest_dates)} stocks")

    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")

    # Process each stock
    total_imported = 0
    success_count = 0
    fail_count = 0
    skip_count = 0
    t0 = time.time()

    for i, code in enumerate(codes):
        # Determine start date
        if code in latest_dates:
            latest = latest_dates[code]
            start = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        elif args.start_date:
            start = args.start_date
        else:
            start = "2025-04-01"

        if start > end_date:
            skip_count += 1
            continue

        try:
            df = fetch_daily_akshare(code, start, end_date)
            if not df.empty:
                inserted = upsert_daily(engine, df)
                total_imported += inserted
            success_count += 1

        except Exception as e:
            fail_count += 1
            logger.error(f"Error {code}: {e}")

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
