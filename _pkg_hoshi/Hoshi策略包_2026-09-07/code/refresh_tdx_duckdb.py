"""自动补充本地通达信 DuckDB 日线数据（增量、幂等、可重复运行）。

数据链路：TDX 行情服务器(pytdx) → data/tdx.duckdb

背景（重要）：
  - `v_stock_bfq` 视图 = raw_kline_daily JOIN raw_symbol_class
                        LEFT JOIN raw_basic_daily(提供 preclose/change_pct)
    hoshi 依赖 change_pct 判跌。所以"补数据"必须同时补 **raw_kline_daily** 和
    **raw_basic_daily**，否则新数据没有涨跌幅 → 策略静默漏信号。
  - 单位坑：duckdb 的 volume 单位是【股】，pytdx 的 vol 单位是【手】→ 必须 ×100。
  - 市场：sh=1, sz=0, bj=2

特性：
  - 增量：只补 (symbol, date) > 现有最大日期 的 K 线
  - 幂等：先 DELETE 再 INSERT，重复运行不会重复数据
  - 容错：多行情服务器轮转 + 断线自动重连
  - 可测试：--limit N 只处理前 N 只，用小样本验证

用法：
    python scripts/refresh_tdx_duckdb.py                # 全量增量更新
    python scripts/refresh_tdx_duckdb.py --limit 20     # 小样本试跑
    python scripts/refresh_tdx_duckdb.py --dry-run      # 只统计不写库
"""
import argparse
import sys
import time
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))  # 用 append 避免仓库自带 pytdx 覆盖 pip 版

import duckdb
from loguru import logger

from pytdx.hq import TdxHq_API

DB_PATH = str(PROJECT_ROOT / "data" / "tdx.duckdb")

# 已验证可用（2026-09-01 实测可取到当日 15:00 数据）的行情服务器
HOSTS = [
    ("180.153.18.170", 7709),
    ("180.153.18.172", 80),
    ("202.108.253.139", 80),
    ("60.191.117.167", 7709),
]

MARKET_MAP = {"sh": 1, "sz": 0, "bj": 2}
CATEGORY_DAILY = 9
BAR_COUNT = 300  # 拉取最近 300 根日线，足够覆盖 MA60 + 增量窗口


def connect_tdx(host_idx: int = 0):
    """连接 TDX 行情服务器，失败则轮转下一个。"""
    n = len(HOSTS)
    for i in range(n):
        host, port = HOSTS[(host_idx + i) % n]
        api = TdxHq_API(raise_exception=False)
        try:
            if api.connect(host, port, time_out=3):
                logger.info(f"TDX connected: {host}:{port}")
                return api, (host_idx + i) % n
        except Exception as e:
            logger.debug(f"connect {host}:{port} failed: {e}")
        try:
            api.disconnect()
        except Exception:
            pass
    raise RuntimeError("所有 TDX 行情服务器均不可用")


def get_target_symbols(con, only: str = "stock", active_since=None):
    """取需要更新的 symbol 列表（默认只要 A 股）。

    active_since: 只保留库内最新日期 >= 该日期的标的，用于过滤
                  退市/长期停牌股（这些股 TDX 也取不到数据，纯属浪费请求）。
    """
    sql = "SELECT symbol FROM raw_symbol_class WHERE class = ?"
    params: list = [only]
    if active_since:
        sql = (
            "SELECT c.symbol FROM raw_symbol_class c "
            "JOIN (SELECT k.symbol AS sym, MAX(k.date) AS maxd FROM raw_kline_daily k "
            "GROUP BY k.symbol) m "
            "ON m.sym = c.symbol "
            "WHERE c.class = ? AND m.maxd >= ?"
        )
        params.append(active_since)
    sql += " ORDER BY symbol"
    rows = con.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def existing_max_dates(con):
    """每只股票的现有最新日期。"""
    rows = con.execute(
        "SELECT symbol, MAX(date) FROM raw_kline_daily GROUP BY symbol"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def fetch_bars(api, symbol: str):
    """拉取单只股票最近 BAR_COUNT 根日线，按日期升序返回。"""
    market = MARKET_MAP.get(symbol[:2])
    code = symbol[2:]
    if market is None:
        return []
    bars = api.get_security_bars(CATEGORY_DAILY, market, code, 0, BAR_COUNT)
    if not bars:
        return []
    out = []
    for b in bars:
        y, m, d = b["year"], b["month"], b["day"]
        try:
            dt = date(y, m, d)
        except Exception:
            continue
        out.append(
            {
                "date": dt,
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                # pytdx vol 单位是【手】，duckdb volume 单位是【股】→ ×100
                "volume": int(round(float(b["vol"]) * 100)),
                "amount": float(b["amount"]),
            }
        )
    out.sort(key=lambda x: x["date"])
    return out


def upsert_symbol(con, symbol: str, bars, max_date_map, dry_run=False):
    """把新于现有最大日期的 K 线写入两张表。返回新增条数。"""
    max_date = max_date_map.get(symbol)
    # 只保留新数据（> 现有最大日期）
    new_bars = [b for b in bars if (max_date is None or b["date"] > max_date)]
    if not new_bars:
        return 0

    # 为计算 preclose，需要新数据段之前那根 K 线的收盘价
    if max_date is not None:
        prev = [b for b in bars if b["date"] <= max_date]
        prev_close = prev[-1]["close"] if prev else None
    else:
        prev_close = None

    kline_rows, basic_rows = [], []
    prev_c = prev_close
    for b in new_bars:
        dt = b["date"]
        kline_rows.append(
            (symbol, b["open"], b["high"], b["low"], b["close"], b["amount"], b["volume"], dt)
        )
        if prev_c is not None and prev_c > 0:
            preclose = prev_c
            change_pct = (b["close"] - preclose) / preclose * 100.0
            amplitude = (b["high"] - b["low"]) / preclose * 100.0
        else:
            preclose, change_pct, amplitude = None, None, None
        basic_rows.append(
            (dt, symbol, b["close"], preclose, change_pct, amplitude, None, None, None)
        )
        prev_c = b["close"]

    if dry_run:
        return len(kline_rows)

    start_date = new_bars[0]["date"]
    # 幂等：先删再插
    con.execute(
        "DELETE FROM raw_kline_daily WHERE symbol = ? AND date >= ?", [symbol, start_date]
    )
    con.execute(
        "DELETE FROM raw_basic_daily WHERE symbol = ? AND date >= ?", [symbol, start_date]
    )
    con.executemany(
        "INSERT INTO raw_kline_daily (symbol, open, high, low, close, amount, volume, date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        kline_rows,
    )
    con.executemany(
        "INSERT INTO raw_basic_daily (date, symbol, close, preclose, change_pct, amplitude, "
        "turnover, floatmv, totalmv) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        basic_rows,
    )
    return len(kline_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（小样本试跑）")
    ap.add_argument("--symbols", default="", help="只处理指定标的，逗号分隔，如 sh600367,sz000001")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    ap.add_argument("--class", dest="cls", default="stock", help="symbol class, 默认 stock")
    ap.add_argument(
        "--active-since",
        default="2026-01-01",
        help="只处理库内最新日期 >= 该日期的标的（过滤退市/长停牌），空字符串表示不过滤",
    )
    ap.add_argument("--verbose", action="store_true", help="打印每只标的的明细")
    ap.add_argument("--max-date", default="", dest="max_date",
                    help="只保留 <= 该日期的K线（盘前/盘中刷新时排除当日未完成bar），如 2026-09-04")
    args = ap.parse_args()
    cutoff = date.fromisoformat(args.max_date) if args.max_date else None

    con = duckdb.connect(DB_PATH)  # 读写模式
    if args.symbols.strip():
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = get_target_symbols(con, args.cls, args.active_since or None)
        if args.limit:
            symbols = symbols[: args.limit]
    logger.info(f"待更新: {len(symbols)} 只 ({args.cls})  dry_run={args.dry_run}")

    max_date_map = existing_max_dates(con)
    api, host_idx = connect_tdx(0)

    t0 = time.time()
    added_total, failed, done = 0, [], 0
    empty_syms = []
    for i, sym in enumerate(symbols, 1):
        try:
            bars = fetch_bars(api, sym)
        except Exception as e:
            # 断线重连后重试一次
            logger.debug(f"{sym} fetch 失败({e})，重连重试")
            try:
                api.disconnect()
            except Exception:
                pass
            host_idx = (host_idx + 1) % len(HOSTS)
            api, host_idx = connect_tdx(host_idx)
            try:
                bars = fetch_bars(api, sym)
            except Exception as e2:
                failed.append((sym, str(e2)))
                continue

        if not bars:
            # TDX 无数据：退市 / 长期停牌 / 代码已变更，跳过即可
            empty_syms.append(sym)
            continue
        if cutoff is not None:
            bars = [b for b in bars if b["date"] <= cutoff]

        try:
            n = upsert_symbol(con, sym, bars, max_date_map, dry_run=args.dry_run)
            added_total += n
            done += 1
            if args.verbose:
                dbmax = max_date_map.get(sym)
                print(
                    f"  {sym}: DB_max={dbmax}  fetched={bars[-1]['date']} "
                    f"({len(bars)}根)  新增={n}"
                )
        except Exception as e:
            failed.append((sym, f"upsert: {e}"))

        if i % 500 == 0:
            elapsed = time.time() - t0
            logger.info(
                f"  进度 {i}/{len(symbols)}  新增行={added_total}  "
                f"无数据={len(empty_syms)}  耗时={elapsed:.0f}s  失败={len(failed)}"
            )

    try:
        api.disconnect()
    except Exception:
        pass

    if not args.dry_run:
        con.commit()
    rng = con.execute("SELECT MIN(date), MAX(date) FROM raw_kline_daily").fetchone()
    # 抽样校验：确认 basic 表也有新数据（否则 hoshi 拿不到 change_pct）
    chk = con.execute(
        "SELECT COUNT(*) FROM raw_basic_daily WHERE date >= DATE '2026-06-27' "
        "AND change_pct IS NOT NULL"
    ).fetchone()[0]
    con.close()

    print("\n" + "=" * 60)
    print("  数据补充完成")
    print("=" * 60)
    print(f"  处理股票数 : {done}/{len(symbols)}")
    print(f"  新增 K 线行: {added_total}")
    print(f"  TDX 无数据 : {len(empty_syms)}")
    print(f"  失败       : {len(failed)}")
    if failed[:5]:
        print("  失败样例   :", failed[:5])
    if empty_syms[:5]:
        print("  无数据样例 :", empty_syms[:5])
    print(f"  库日期范围 : {rng[0]} ~ {rng[1]}")
    print(f"  basic 新增(含 change_pct): {chk}")
    print(f"  耗时       : {time.time() - t0:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
