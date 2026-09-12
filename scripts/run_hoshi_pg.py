"""Run Hoshi strategy on PostgreSQL daily kline data.

Scans all stocks in the database for Hoshi pattern (stabilization after decline in uptrend).

Usage:
    python scripts/run_hoshi_pg.py [--mode confirmation|stabilization] [--top 30] [--min-score 4.0]
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.screener.hoshi import HoshiScreener, print_hoshi_results
from core.screener.screener import ScreeningResult


DB_URL = "postgresql://postgres@localhost:5432/quant_minute"


def load_all_daily_data(engine, days: int = 120) -> tuple[dict, dict]:
    """Load daily kline data for all stocks from PostgreSQL.

    Returns:
        (df_dict, name_map): dict of code -> DataFrame, dict of code -> name
    """
    # Get all stock codes with daily kline data
    with engine.connect() as conn:
        codes_result = conn.execute(text(
            "SELECT DISTINCT code FROM daily_kline ORDER BY code"
        )).fetchall()
        codes = [r[0] for r in codes_result]

        # Get stock names
        names_result = conn.execute(text(
            "SELECT code, name FROM stock_info WHERE name != ''"
        )).fetchall()
        name_map = {r[0]: r[1] for r in names_result}

    logger.info(f"Loading {len(codes)} stocks, last {days} days...")

    df_dict = {}
    t0 = time.time()

    for i, code in enumerate(codes):
        query = text("""
            SELECT date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code = :code
            ORDER BY date DESC
            LIMIT :days
        """)
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params={"code": code, "days": days})

        if len(df) < 65:  # Need at least 60 for MA60
            continue

        # Reverse to chronological order
        df = df.iloc[::-1].reset_index(drop=True)

        # Compute change_pct
        df["change_pct"] = df["close"].pct_change() * 100

        df_dict[code] = df

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - t0
            logger.info(f"  Loaded {i+1}/{len(codes)} stocks in {elapsed:.1f}s")

    elapsed = time.time() - t0
    logger.info(f"Loaded {len(df_dict)} stocks with sufficient data in {elapsed:.1f}s")

    return df_dict, name_map


def main():
    parser = argparse.ArgumentParser(description="Run Hoshi strategy on PostgreSQL data")
    parser.add_argument("--mode", type=str, default="confirmation",
                        choices=["confirmation", "stabilization"],
                        help="Hoshi mode: 'confirmation' (稳健) or 'stabilization' (激进)")
    parser.add_argument("--top", type=int, default=30,
                        help="Return top N results (default: 30)")
    parser.add_argument("--min-score", type=float, default=4.0,
                        help="Minimum score threshold (default: 4.0)")
    parser.add_argument("--days", type=int, default=120,
                        help="Load last N days of data (default: 120)")
    parser.add_argument("--db-url", type=str, default=DB_URL,
                        help="PostgreSQL connection URL")
    args = parser.parse_args()

    logger.info(f"Hoshi strategy scan: mode={args.mode}, top={args.top}, "
                f"min_score={args.min_score}, days={args.days}")

    engine = create_engine(args.db_url)

    # Load data
    df_dict, name_map = load_all_daily_data(engine, days=args.days)

    # Run Hoshi screener
    screener = HoshiScreener(mode=args.mode, min_score=args.min_score)
    t0 = time.time()
    results = screener.screen_batch(df_dict, name_map, top_n=args.top)
    elapsed = time.time() - t0

    # Print results
    print_hoshi_results(results)
    logger.info(f"Scan complete: {len(results)} hits in {elapsed:.1f}s")

    engine.dispose()


if __name__ == "__main__":
    main()
