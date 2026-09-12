"""Hoshi 策略日常运行入口（一条命令搞定：补数据 → 体检 → 出信号）。

这是"下次运行"的标准入口。日常只需要：

    python scripts/run_hoshi_local.py --refresh

它会：
  1. 增量补充 TDX 日线到最新交易日（幂等，可重复运行）
  2. 做数据体检（新鲜度 / change_pct 覆盖）
  3. 跑 confirmation + stabilization 两种模式，输出今日信号

其他用法：
    python scripts/run_hoshi_local.py                # 不补数据，直接跑（离线）
    python scripts/run_hoshi_local.py --as-of 2026-08-25   # 复盘指定日期
    python scripts/run_hoshi_local.py --top 50 --min-score 6.0 --min-amount 1e8

注意（量化纪律）：
  - 数据过期（距今天数 > 5）会拒绝出信号，避免用旧数据冒充"今日信号"。
  - 默认过滤 ST / 停牌 / 一字板 / 成交额低于 min-amount 的僵尸股。
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from loguru import logger

from core.data.duckdb_source import TdxDB
from core.screener.hoshi import print_hoshi_results, run_hoshi_on_tdx

DB_PATH = str(PROJECT_ROOT / "data" / "tdx.duckdb")
REFRESH_SCRIPT = PROJECT_ROOT / "scripts" / "refresh_tdx_duckdb.py"
OUT_PATH = PROJECT_ROOT / "scripts" / "hoshi_local_result.json"

STALE_DAYS = 5  # 库内最新交易日距今超过 N 天则视为过期


def do_refresh(extra_args: list) -> bool:
    """调用增量补数据脚本（幂等）。"""
    cmd = [sys.executable, str(REFRESH_SCRIPT)] + extra_args
    logger.info(f"执行数据补充: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if r.returncode != 0:
        logger.error(f"数据补充失败 (exit={r.returncode})")
        return False
    return True


def inspect_db(db: TdxDB) -> dict:
    """数据体检，返回 {最新交易日, 距今天数, 活跃股数, change_pct缺失数}"""
    print("\n" + "=" * 70)
    print("  数据体检")
    print("=" * 70)

    info = {}
    try:
        stats = db.get_stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print("  get_stats 失败:", e)

    r = db.conn.execute(
        "SELECT MAX(date) FROM raw_kline_daily k "
        "JOIN raw_symbol_class c ON c.symbol = k.symbol AND c.class = 'stock'"
    ).fetchone()
    max_date = r[0]
    if isinstance(max_date, datetime):
        max_date = max_date.date()
    info["max_date"] = str(max_date)
    lag = (date.today() - max_date).days if max_date else 9999
    info["lag_days"] = lag
    print(f"  最新交易日 : {max_date}  (距今 {lag} 天)")

    n_active = db.conn.execute(
        "SELECT COUNT(*) FROM (SELECT k.symbol FROM raw_kline_daily k "
        "JOIN raw_symbol_class c ON c.symbol=k.symbol AND c.class='stock' "
        "GROUP BY k.symbol HAVING MAX(k.date) = ?)",
        [max_date],
    ).fetchone()[0]
    info["n_active"] = n_active
    print(f"  当日有成交 : {n_active} 只")

    miss = db.conn.execute(
        "SELECT COUNT(*) FROM raw_basic_daily b "
        "JOIN raw_symbol_class c ON c.symbol=b.symbol AND c.class='stock' "
        "WHERE b.date = ? AND b.change_pct IS NULL",
        [max_date],
    ).fetchone()[0]
    info["missing_change_pct"] = miss
    flag = "✓" if miss == 0 else "✗ 会导致 hoshi 漏信号，请重跑补数据"
    print(f"  change_pct 缺失 : {miss}  {flag}")

    info["stale"] = lag > STALE_DAYS
    if info["stale"]:
        print(f"  ⚠ 数据已过期（>{STALE_DAYS} 天），请加 --refresh 补数据")
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="先增量补数据再跑策略")
    ap.add_argument("--refresh-args", default="", help="透传给补数据脚本的额外参数")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--mode", default="both", choices=["both", "confirmation", "stabilization"],
                    help="默认 both（每日只跑 confirmation 更稳健，见 hoshi_replay 归因）")
    ap.add_argument("--min-score", type=float, default=5.0)
    ap.add_argument("--min-amount", type=float, default=5e7, help="最低当日成交额（元）")
    ap.add_argument("--as-of", default=None, help="信号截止日，默认用库内最新交易日")
    ap.add_argument("--no-exclude-st", action="store_true")
    ap.add_argument("--max-per-day", type=int, default=30,
                    help="每日信号拥挤度上限：当日命中数超过该值则整日放弃（默认 30，避免市场普跌日接刀）")
    ap.add_argument("--allow-stale", action="store_true", help="数据过期时仍继续（仅调试用）")
    args = ap.parse_args()

    if args.refresh:
        extra = args.refresh_args.split() if args.refresh_args else []
        if not do_refresh(extra):
            sys.exit(1)
    else:
        # 子进程结束后必须重新 import，避免复用旧的 duckdb 连接状态
        pass

    db = TdxDB(DB_PATH)
    try:
        info = inspect_db(db)
    finally:
        db.close()

    if info["stale"] and not args.allow_stale:
        print("\n" + "=" * 70)
        print("  已终止：数据过期。")
        print("  请运行: python scripts/run_hoshi_local.py --refresh")
        print("  （加 --allow-stale 可强制继续，但结果不可用于交易决策）")
        print("=" * 70)
        sys.exit(2)

    as_of = args.as_of or info["max_date"]
    out = {}
    modes = ["confirmation", "stabilization"] if args.mode == "both" else [args.mode]
    for mode in modes:
        print("\n" + "=" * 70)
        print(
            f"  Hoshi · {mode}   (as_of={as_of}, top={args.top}, "
            f"min_score={args.min_score}, min_amount={args.min_amount:.0f})"
        )
        print("=" * 70)
        results = run_hoshi_on_tdx(
            db_path=DB_PATH,
            mode=mode,
            top_n=args.top,
            days=args.days,
            min_score=args.min_score,
            min_amount=args.min_amount,
            as_of=as_of,
            exclude_st=not args.no_exclude_st,
            max_daily_signals=args.max_per_day,
        )
        print_hoshi_results(results)
        out[mode] = [
            {
                "code": r.code,
                "name": r.name,
                "score": r.score,
                "price": r.price,
                "pct_change": r.pct_change,
                "signals": r.signals,
            }
            for r in results
        ]

    payload = {
        "as_of": str(as_of),
        "data": info,
        "params": {
            "min_score": args.min_score,
            "min_amount": args.min_amount,
            "days": args.days,
            "max_per_day": args.max_per_day,
        },
        "results": out,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"  结果已写入: {OUT_PATH}")
    print(f"  as_of = {as_of}")
    for m in modes:
        print(f"  {m:<14}: {len(out[m])} 只")
    print("=" * 70)


if __name__ == "__main__":
    main()
