"""CLI tool for minute-level data management.

Commands:
  init-db           Create PostgreSQL tables and partitions
  import-v43        Import 5-min data from local V43 .dat files
  import-baostock   Import minute data from BaoStock API
  update            Incremental update from BaoStock
  aggregate         Run 5→15/30/60-min aggregation
  query             Query and display minute data
  stats             Show import statistics and table sizes
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_db(db_url: str):
    """Get MinuteKlineDB instance."""
    from core.data.pg_storage import MinuteKlineDB
    return MinuteKlineDB(db_url)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_init_db(args):
    """Initialize PostgreSQL schema with monthly partitions."""
    db = _get_db(args.db_url)
    logger.info(f"Initializing schema: {args.db_url}")
    db.init_schema(from_year=args.from_year, to_year=args.to_year)
    logger.info("Schema initialization complete")
    stats = db.get_stats()
    for table, info in stats.items():
        logger.info(f"  {table}: ready")
    db.close()


def cmd_import_v43(args):
    """Import 5-min data from Eastmoney V43 local files."""
    from core.data.v43_minute import V43MinuteReader

    db = _get_db(args.db_url)
    reader = V43MinuteReader(sh_path=args.sh_path, sz_path=args.sz_path)

    stats = reader.get_stats()
    for market, info in stats.items():
        logger.info(f"  {market}: {info['codes']} codes, {info['records']} records")

    all_codes = reader.get_all_codes()
    if args.max_stocks > 0:
        all_codes = all_codes[:args.max_stocks]

    logger.info(f"Importing {len(all_codes)} stocks from V43 5-min files")

    # Ensure partitions for expected date range
    db.ensure_partitions("5", "2020-01-01", "2027-12-31")

    total_imported = 0
    total_codes_with_data = 0
    start_time = time.time()

    for i, code in enumerate(all_codes):
        try:
            df = reader.read_stock(code)
            if not df.empty:
                inserted = db.bulk_insert_fast("5", df, source="v43")
                total_imported += inserted
                total_codes_with_data += 1

                # Log import
                min_dt = df["datetime"].min()
                max_dt = df["datetime"].max()
                db.log_import("v43", code, "5", "done",
                              rows_imported=len(df),
                              start_dt=str(min_dt), end_dt=str(max_dt))

        except Exception as e:
            logger.error(f"Failed to import {code}: {e}")
            db.log_import("v43", code, "5", "error", error_msg=str(e))

        if (i + 1) % 100 == 0 or i == len(all_codes) - 1:
            elapsed = time.time() - start_time
            speed = total_imported / elapsed if elapsed > 0 else 0
            logger.info(f"  V43 progress: {i + 1}/{len(all_codes)} | "
                        f"imported: {total_imported} rows | "
                        f"codes with data: {total_codes_with_data} | "
                        f"speed: {speed:.0f} rows/s")

    elapsed = time.time() - start_time
    logger.info(f"V43 import complete: {total_imported} rows, "
                f"{total_codes_with_data} codes, {elapsed:.1f}s")
    db.close()


def cmd_import_baostock(args):
    """Import minute data from BaoStock API."""
    from core.data.baostock_minute import BaostockMinuteFetcher

    db = _get_db(args.db_url)
    fetcher = BaostockMinuteFetcher()

    # Get stock list
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    else:
        # Try to get codes from V43 or DB
        try:
            from core.data.v43_minute import V43MinuteReader
            reader = V43MinuteReader()
            codes = reader.get_all_codes()
        except Exception:
            logger.error("Cannot determine stock list. Use --codes or import V43 first.")
            return

    # Filter completed codes
    completed = db.get_completed_codes("baostock", args.freq)
    remaining = [c for c in codes if c not in completed]
    logger.info(f"Total: {len(codes)}, completed: {len(completed)}, "
                f"remaining: {len(remaining)}")

    if args.max_stocks > 0:
        remaining = remaining[:args.max_stocks]

    # Ensure partitions
    db.ensure_partitions(args.freq, args.start_date or "2020-01-01",
                         args.end_date or "2027-12-31")

    total_imported = 0
    start_time = time.time()

    def progress_callback(current, total, code, df):
        nonlocal total_imported
        if not df.empty:
            try:
                inserted = db.bulk_insert_fast(args.freq, df, source="baostock")
                total_imported += inserted
                db.log_import("baostock", code, args.freq, "done",
                              rows_imported=len(df),
                              start_dt=str(df["datetime"].min()),
                              end_dt=str(df["datetime"].max()))
            except Exception as e:
                logger.error(f"Insert failed for {code}: {e}")
                db.log_import("baostock", code, args.freq, "error",
                              error_msg=str(e))
        else:
            db.log_import("baostock", code, args.freq, "done", rows_imported=0)

        if current % 20 == 0 or current == total:
            elapsed = time.time() - start_time
            logger.info(f"  BaoStock progress: {current}/{total} | "
                        f"imported: {total_imported} rows | "
                        f"elapsed: {elapsed:.0f}s")

    fetcher.batch_fetch(
        remaining, freq=args.freq,
        start_date=args.start_date or "",
        end_date=args.end_date or "",
        delay=args.delay,
        progress_callback=progress_callback,
    )

    elapsed = time.time() - start_time
    logger.info(f"BaoStock import complete: {total_imported} rows, {elapsed:.1f}s")
    db.close()


def cmd_import_pytdx(args):
    """Import minute data from TDX servers via pytdx (fastest source)."""
    from core.data.pytdx_minute import PytdxMinuteFetcher

    db = _get_db(args.db_url)
    fetcher = PytdxMinuteFetcher()

    if not fetcher.connect():
        logger.error("Cannot connect to TDX servers")
        return

    # Get stock list
    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    elif getattr(args, "from_file", ""):
        # Load codes from text file (one code per line)
        from pathlib import Path as P
        fpath = P(args.from_file)
        if fpath.exists():
            codes = [line.strip() for line in fpath.read_text().splitlines() if line.strip()]
            logger.info(f"Loaded {len(codes)} codes from {fpath}")
        else:
            logger.error(f"File not found: {args.from_file}")
            return
    else:
        # Try: DB existing codes → PostgreSQL stock_info → V43 index
        codes = db.get_all_codes("5")
        if not codes:
            # Try loading from PostgreSQL stock_info
            try:
                from sqlalchemy import create_engine as ce, text as tx
                pg_engine = ce(args.db_url)
                with pg_engine.connect() as conn:
                    result = conn.execute(tx("SELECT code FROM stock_info"))
                    codes = [r[0] for r in result
                             if r[0].startswith(("6", "0", "3"))]
                pg_engine.dispose()
                if codes:
                    logger.info(f"Loaded {len(codes)} A-share codes from stock_info")
            except Exception:
                pass
        if not codes:
            try:
                from core.data.v43_minute import V43MinuteReader
                reader = V43MinuteReader()
                codes = reader.get_all_codes()
            except Exception:
                pass
        if not codes:
            logger.error("No stock list available. Use --codes, --from-file, or import-v43 first.")
            return

    # Filter completed codes if incremental
    if args.skip_completed:
        completed = db.get_completed_codes("pytdx", args.freq)
        codes = [c for c in codes if c not in completed]
        logger.info(f"Skipping {len(completed)} already completed codes, "
                    f"{len(codes)} remaining")

    if args.max_stocks > 0:
        codes = codes[:args.max_stocks]

    logger.info(f"Importing {len(codes)} stocks via pytdx, freq={args.freq}, "
                f"max_bars={args.max_bars or 'all'}")

    # Parse date range
    date_range = None
    if getattr(args, "date_range", ""):
        parts = args.date_range.split(",")
        if len(parts) == 2:
            date_range = (parts[0].strip(), parts[1].strip())
            logger.info(f"Date range filter: {date_range[0]} ~ {date_range[1]}")

    # Ensure partitions
    db.ensure_partitions(args.freq, "2020-01-01", "2027-12-31")

    start_time = time.time()
    total = fetcher.fetch_and_import(
        codes, freq=args.freq, db=db,
        max_bars=args.max_bars, delay=args.delay,
        date_range=date_range,
    )

    elapsed = time.time() - start_time
    logger.info(f"pytdx import complete: {total} rows, {elapsed:.1f}s "
                f"({total/elapsed:.0f} rows/s)")
    fetcher.disconnect()
    db.close()


def cmd_update(args):
    """Incremental update from BaoStock."""
    from core.data.baostock_minute import BaostockMinuteFetcher

    db = _get_db(args.db_url)
    fetcher = BaostockMinuteFetcher()

    codes = db.get_all_codes(args.freq)
    if not codes:
        logger.warning("No codes found in DB, doing full import first")
        logger.info("Run import-baostock or import-v43 first")
        return

    logger.info(f"Incremental update: {len(codes)} codes, freq={args.freq}")
    new_rows = fetcher.fetch_incremental(codes, args.freq, db, delay=args.delay)
    logger.info(f"Incremental update complete: {new_rows} new rows")

    # Re-aggregate for updated data
    if args.aggregate and new_rows > 0:
        from core.data.minute_aggregator import aggregate_in_db
        for freq in [15, 30, 60]:
            logger.info(f"Re-aggregating to {freq}-min...")
            inserted = aggregate_in_db(db, freq, codes)
            logger.info(f"  {freq}-min: {inserted} rows")

    db.close()


def cmd_aggregate(args):
    """Run 5→15/30/60-min aggregation."""
    from core.data.minute_aggregator import aggregate_in_db

    db = _get_db(args.db_url)

    freqs = [int(f.strip()) for f in args.freq.split(",")]

    for freq in freqs:
        logger.info(f"Aggregating 5-min → {freq}-min...")
        start_time = time.time()

        inserted = aggregate_in_db(
            db, freq,
            start_date=args.start_date or "",
            end_date=args.end_date or "",
            batch_size=args.batch_size,
        )

        elapsed = time.time() - start_time
        logger.info(f"  {freq}-min aggregation complete: {inserted} rows, "
                     f"{elapsed:.1f}s")

    db.close()


def cmd_query(args):
    """Query and display minute data."""
    db = _get_db(args.db_url)

    df = db.load(args.code, args.freq)
    if df.empty:
        logger.info(f"No data found for {args.code} at {args.freq}-min")
        db.close()
        return

    # Show last N rows
    n = args.rows or 20
    display_df = df.tail(n)

    print(f"\n{'=' * 80}")
    print(f"  {args.code} | {args.freq}-min | {len(df)} total bars")
    print(f"  Range: {df['datetime'].min()} ~ {df['datetime'].max()}")
    print(f"{'=' * 80}")
    print(display_df.to_string(index=False))
    print()

    # Optional: compute and show indicators
    if args.indicators:
        try:
            from core.data.minute_bridge import MinuteBridge
            bridge = MinuteBridge(db)
            idf = bridge.compute_minute_indicators(args.code, args.freq, days=120)
            if not idf.empty:
                print(f"\nLatest indicators:")
                latest = idf.iloc[-1]
                for col in ["ma5", "ma10", "ma20", "ma60", "macd_dif", "macd_dea",
                            "rsi12", "kdj_k", "kdj_d", "kdj_j"]:
                    if col in idf.columns:
                        print(f"  {col}: {latest[col]:.2f}" if isinstance(latest[col], float) else f"  {col}: {latest[col]}")
        except ImportError:
            logger.warning("Indicator computation not available")

    db.close()


def cmd_stats(args):
    """Show import statistics."""
    db = _get_db(args.db_url)
    stats = db.get_stats()

    print(f"\n{'=' * 60}")
    print(f"  PostgreSQL Minute Kline Database Statistics")
    print(f"  Database: {args.db_url}")
    print(f"{'=' * 60}")

    for table, info in stats.items():
        print(f"\n  {table}:")
        print(f"    Rows:   {info['rows']:,}")
        print(f"    Codes:  {info['codes']}")
        print(f"    Range:  {info['min_date']} ~ {info['max_date']}")
        print(f"    Size:   {info.get('size', 'unknown')}")

    # Import log summary
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COUNT(*), COUNT(DISTINCT code), "
                "SUM(CASE WHEN status='done' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) "
                "FROM _minute_import_log"
            )).fetchone()
            if row:
                print(f"\n  Import Log:")
                print(f"    Total entries:  {row[0]}")
                print(f"    Distinct codes: {row[1]}")
                print(f"    Successful:     {row[2]}")
                print(f"    Errors:         {row[3]}")
    except Exception:
        pass

    print()
    db.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Minute-level data management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")
    parser.add_argument("--db-url", type=str,
                        default="postgresql://postgres@localhost:5432/quant_minute",
                        help="PostgreSQL connection URL")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init-db
    p_init = subparsers.add_parser("init-db", help="Create tables and partitions")
    p_init.add_argument("--from-year", type=int, default=2015,
                        help="Partition start year (default: 2015)")
    p_init.add_argument("--to-year", type=int, default=2027,
                        help="Partition end year (default: 2027)")

    # import-v43
    p_v43 = subparsers.add_parser("import-v43",
                                   help="Import 5-min from V43 files")
    p_v43.add_argument("--sh-path", type=str, default="",
                        help="SH Min5Data file path")
    p_v43.add_argument("--sz-path", type=str, default="",
                        help="SZ Min5Data file path")
    p_v43.add_argument("--max-stocks", type=int, default=0,
                        help="Max stocks to import (0=all)")

    # import-baostock
    p_bs = subparsers.add_parser("import-baostock",
                                  help="Import from BaoStock API")
    p_bs.add_argument("--freq", type=str, default="5",
                       help="Frequency: 5, 15, 30, 60 (default: 5)")
    p_bs.add_argument("--start-date", type=str, default="",
                       help="Start date YYYY-MM-DD")
    p_bs.add_argument("--end-date", type=str, default="",
                       help="End date YYYY-MM-DD")
    p_bs.add_argument("--codes", type=str, default="",
                       help="Comma-separated codes (empty=all)")
    p_bs.add_argument("--delay", type=float, default=0.3,
                       help="Delay between requests (seconds)")
    p_bs.add_argument("--max-stocks", type=int, default=0,
                       help="Max stocks to import (0=all)")

    # import-pytdx
    p_tdx = subparsers.add_parser("import-pytdx",
                                   help="Import from TDX servers via pytdx (fastest)")
    p_tdx.add_argument("--freq", type=str, default="5",
                        help="Frequency: 1, 5, 15, 30, 60 (default: 5)")
    p_tdx.add_argument("--codes", type=str, default="",
                        help="Comma-separated codes (empty=all)")
    p_tdx.add_argument("--from-file", type=str, default="",
                        help="Text file with one code per line")
    p_tdx.add_argument("--max-bars", type=int, default=0,
                        help="Max bars per stock (0=all, ~24000 for 5-min)")
    p_tdx.add_argument("--delay", type=float, default=0.05,
                        help="Delay between requests (seconds)")
    p_tdx.add_argument("--max-stocks", type=int, default=0,
                        help="Max stocks to import (0=all)")
    p_tdx.add_argument("--skip-completed", action="store_true",
                        help="Skip already imported stocks")
    p_tdx.add_argument("--date-range", type=str, default="",
                        help="Filter by date range: 'YYYY-MM-DD,YYYY-MM-DD' "
                             "(e.g. '2023-03-01,2024-02-29')")

    # update
    p_upd = subparsers.add_parser("update", help="Incremental update")
    p_upd.add_argument("--freq", type=str, default="5",
                        help="Frequency: 5, 15, 30, 60")
    p_upd.add_argument("--delay", type=float, default=0.2,
                        help="Delay between requests")
    p_upd.add_argument("--aggregate", action="store_true",
                        help="Re-aggregate after update")

    # aggregate
    p_agg = subparsers.add_parser("aggregate", help="Aggregate 5→15/30/60")
    p_agg.add_argument("--freq", type=str, default="15,30,60",
                        help="Target frequencies (comma-separated)")
    p_agg.add_argument("--start-date", type=str, default="",
                        help="Filter start date")
    p_agg.add_argument("--end-date", type=str, default="",
                        help="Filter end date")
    p_agg.add_argument("--batch-size", type=int, default=100,
                        help="Codes per batch")

    # query
    p_query = subparsers.add_parser("query", help="Query minute data")
    p_query.add_argument("--code", type=str, required=True,
                          help="Stock code")
    p_query.add_argument("--freq", type=str, default="5",
                          help="Frequency")
    p_query.add_argument("--rows", type=int, default=20,
                          help="Number of rows to display")
    p_query.add_argument("--indicators", action="store_true",
                          help="Show technical indicators")

    # stats
    subparsers.add_parser("stats", help="Show statistics")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return

    commands = {
        "init-db": cmd_init_db,
        "import-v43": cmd_import_v43,
        "import-baostock": cmd_import_baostock,
        "import-pytdx": cmd_import_pytdx,
        "update": cmd_update,
        "aggregate": cmd_aggregate,
        "query": cmd_query,
        "stats": cmd_stats,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
