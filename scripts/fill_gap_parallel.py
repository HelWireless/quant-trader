"""Parallel baostock gap fill — streaming version.

Uses imap_unordered for real-time progress. Each worker processes
small batches and results are written to DB as they arrive.

Usage:
  py -3 scripts/fill_gap_parallel.py [--workers 4] [--max-stocks N]
"""

import argparse
import logging
import multiprocessing as mp
import sys
import time
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
BATCH_SIZE = 10  # stocks per worker batch


def worker_fetch_batch(args_tuple):
    """Fetch a small batch of codes from baostock.
    
    Returns list of (code, row_count, error_msg).
    row_count = -1 means error, 0 means no data, >0 means success.
    On success, also returns the DataFrame via a side channel (file).
    """
    codes, batch_id = args_tuple
    
    from core.data.baostock_minute import BaostockMinuteFetcher
    from core.data.pg_storage import MinuteKlineDB
    import pandas as pd
    
    db = MinuteKlineDB()
    fetcher = BaostockMinuteFetcher()
    
    results = []
    for code in codes:
        last_error = None
        for attempt in range(3):
            try:
                df = fetcher.fetch(code, FREQ, start_date=START_DATE, end_date=END_DATE)
                if df.empty and attempt < 2:
                    try:
                        fetcher._logout()
                    except Exception:
                        pass
                    fetcher._login()
                    continue
                
                # Write directly to DB from worker
                if not df.empty:
                    try:
                        inserted = db.bulk_insert_fast(FREQ, df, source=SOURCE)
                        db.log_import(SOURCE, code, FREQ, "done",
                                      rows_imported=len(df),
                                      start_dt=str(df["datetime"].min()),
                                      end_dt=str(df["datetime"].max()))
                        results.append((code, inserted, None))
                    except Exception as e:
                        results.append((code, -1, f"DB error: {e}"))
                else:
                    db.log_import(SOURCE, code, FREQ, "done", rows_imported=0)
                    results.append((code, 0, None))
                
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                try:
                    fetcher._logout()
                except Exception:
                    pass
                try:
                    fetcher._login()
                except Exception:
                    pass
        
        if last_error:
            results.append((code, -1, last_error))
    
    try:
        fetcher._logout()
    except Exception:
        pass
    db.close()
    
    return (batch_id, results)


def main():
    parser = argparse.ArgumentParser(description="Parallel baostock gap fill")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel workers (default: 4)")
    parser.add_argument("--max-stocks", type=int, default=0)
    parser.add_argument("--codes", type=str, default="")
    parser.add_argument("--skip-completed", action="store_true")
    parser.add_argument("--db-url", default="postgresql://postgres@localhost:5432/quant_minute")
    args = parser.parse_args()

    from core.data.pg_storage import MinuteKlineDB
    db = MinuteKlineDB(args.db_url)

    # Get stock list
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    else:
        logger.info("Loading stock list from DB...")
        with db.engine.connect() as conn:
            r = conn.execute(text("SELECT DISTINCT code FROM kline_5min ORDER BY code"))
            codes = [row[0] for row in r]
        logger.info(f"Found {len(codes)} codes")

    if args.max_stocks > 0:
        codes = codes[:args.max_stocks]

    # Skip completed
    if args.skip_completed:
        with db.engine.connect() as conn:
            r = conn.execute(text(
                "SELECT DISTINCT code FROM _minute_import_log "
                "WHERE source = :src AND frequency = :freq AND status = 'done'"
            ), {"src": SOURCE, "freq": FREQ})
            completed = {row[0] for row in r}
        before = len(codes)
        codes = [c for c in codes if c not in completed]
        logger.info(f"Skip-completed: {before - len(codes)} done, {len(codes)} remaining")

    db.ensure_partitions(FREQ, START_DATE, END_DATE)
    db.close()

    n_workers = min(args.workers, len(codes) // BATCH_SIZE + 1)
    n_workers = max(1, n_workers)
    
    # Split into batches
    batches = []
    for i in range(0, len(codes), BATCH_SIZE):
        batch_codes = codes[i:i + BATCH_SIZE]
        batches.append((batch_codes, len(batches)))

    logger.info(f"Gap fill: {START_DATE} ~ {END_DATE}, {len(codes)} stocks, "
                f"{len(batches)} batches, {n_workers} workers")
    logger.info(f"Estimated time: ~{len(codes) * 4.5 / 3600:.1f} hours")

    start_time = time.time()
    total_imported = 0
    success_count = 0
    fail_count = 0
    processed = 0
    total_stocks = len(codes)

    with mp.Pool(n_workers) as pool:
        for batch_id, results in pool.imap_unordered(worker_fetch_batch, batches):
            for code, row_count, error in results:
                processed += 1
                if error or row_count < 0:
                    fail_count += 1
                else:
                    success_count += 1
                    total_imported += max(0, row_count)
            
            # Progress every batch
            elapsed = time.time() - start_time
            avg_per_stock = elapsed / processed if processed > 0 else 1
            remaining = (total_stocks - processed) * avg_per_stock
            logger.info(
                f"  [{processed}/{total_stocks}] "
                f"imported: {total_imported:,} | "
                f"ok: {success_count} | fail: {fail_count} | "
                f"avg: {avg_per_stock:.1f}s/stock | "
                f"ETA: {remaining / 3600:.1f}h"
            )

    total_time = time.time() - start_time
    logger.info(f"\n{'=' * 60}")
    logger.info(
        f"Gap fill complete: {total_imported:,} rows | "
        f"{success_count} success | {fail_count} fail | "
        f"{total_time:.0f}s ({total_time / 3600:.1f}h)"
    )


if __name__ == "__main__":
    main()
