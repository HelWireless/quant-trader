"""Fill the 2023-03 ~ 2024-02 data gap using BaoStock.

Fetches 5-min data for all stocks and inserts into PostgreSQL.
After completion, run aggregation for 15/30/60-min.

Usage:
  py -3 scripts/fill_gap_baostock.py [--max-stocks N] [--codes 600519,000001]
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.baostock_minute import BaostockMinuteFetcher
from core.data.pg_storage import MinuteKlineDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

START_DATE = "2023-03-01"
END_DATE = "2024-02-29"
FREQ = "5"
SOURCE = "bs_gap"


def get_codes_from_db(db):
    """Get all stock codes from existing 5min data."""
    with db.engine.connect() as conn:
        r = conn.execute(text(
            "SELECT DISTINCT code FROM kline_5min ORDER BY code"
        ))
        return [row[0] for row in r]


def main():
    parser = argparse.ArgumentParser(description="Fill data gap via BaoStock")
    parser.add_argument("--max-stocks", type=int, default=0,
                        help="Max stocks (0=all)")
    parser.add_argument("--codes", type=str, default="",
                        help="Comma-separated codes")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Delay between requests (seconds)")
    parser.add_argument("--skip-completed", action="store_true",
                        help="Skip stocks already in import log for this source")
    parser.add_argument("--db-url", default="postgresql://postgres@localhost:5432/quant_minute")
    args = parser.parse_args()

    db = MinuteKlineDB(args.db_url)
    fetcher = BaostockMinuteFetcher()

    # Get stock list
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    else:
        logger.info("Loading stock list from DB...")
        codes = get_codes_from_db(db)
        logger.info(f"Found {len(codes)} codes in DB")

    if args.max_stocks > 0:
        codes = codes[:args.max_stocks]

    # Skip already completed codes
    if args.skip_completed:
        with db.engine.connect() as conn:
            r = conn.execute(text(
                "SELECT DISTINCT code FROM _minute_import_log "
                "WHERE source = :src AND frequency = :freq AND status = 'done'"
            ), {"src": SOURCE, "freq": FREQ})
            completed = {row[0] for row in r}
        before = len(codes)
        codes = [c for c in codes if c not in completed]
        logger.info(f"Skip-completed: {before - len(codes)} already done, {len(codes)} remaining")

    # Ensure partitions for gap period
    db.ensure_partitions(FREQ, START_DATE, END_DATE)

    logger.info(f"Gap fill: {START_DATE} ~ {END_DATE}, {len(codes)} stocks, freq={FREQ}")
    logger.info(f"Estimated time: ~{len(codes) * 17 / 3600:.1f} hours")

    total_imported = 0
    success_count = 0
    fail_count = 0
    start_time = time.time()

    for i, code in enumerate(codes):
        t0 = time.time()
        try:
            df = fetcher.fetch(code, FREQ, start_date=START_DATE, end_date=END_DATE)
            if not df.empty:
                inserted = db.bulk_insert_fast(FREQ, df, source=SOURCE)
                total_imported += inserted
                success_count += 1
                db.log_import(SOURCE, code, FREQ, "done",
                              rows_imported=len(df),
                              start_dt=str(df["datetime"].min()),
                              end_dt=str(df["datetime"].max()))
            else:
                success_count += 1
                db.log_import(SOURCE, code, FREQ, "done", rows_imported=0)

        except Exception as e:
            fail_count += 1
            logger.error(f"Error {code}: {e}")
            db.log_import(SOURCE, code, FREQ, "error", error_msg=str(e))

        elapsed_stock = time.time() - t0

        # Progress every 10 stocks
        if (i + 1) % 10 == 0 or i == len(codes) - 1:
            total_elapsed = time.time() - start_time
            avg = total_elapsed / (i + 1)
            remaining = (len(codes) - i - 1) * avg
            logger.info(
                f"  [{i + 1}/{len(codes)}] "
                f"imported: {total_imported:,} | "
                f"success: {success_count} | fail: {fail_count} | "
                f"avg: {avg:.1f}s/stock | "
                f"ETA: {remaining / 3600:.1f}h | "
                f"last: {elapsed_stock:.1f}s"
            )

        if args.delay > 0 and i < len(codes) - 1:
            time.sleep(args.delay)

    total_time = time.time() - start_time
    logger.info(f"\n{'=' * 60}")
    logger.info(
        f"Gap fill complete: {total_imported:,} rows | "
        f"{success_count} success | {fail_count} fail | "
        f"{total_time:.0f}s ({total_time / 3600:.1f}h)"
    )


if __name__ == "__main__":
    main()
