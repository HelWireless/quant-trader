"""用 baostock 补充本地 DuckDB 日线数据（增量、幂等、可重复运行）。

数据链路：baostock（免费在线日线）→ data/tdx.duckdb

为什么要用 baostock：
  - 免费、稳定、在线直连，不依赖 cody_pc 服务器，也不依赖 TDX 行情服务器。
  - baostock 直接返回 preclose / pctChg / amount，数据口径干净。
  - 服务器关机 / TDX 不可用时，这是本地独立拉数据的可靠替代。

写入结构与 refresh_tdx_duckdb.py 完全一致，hoshi 管线无需任何改动：
  - raw_kline_daily (symbol, open, high, low, close, amount, volume, date)
  - raw_basic_daily (date, symbol, close, preclose, change_pct, amplitude, turnover, floatmv, totalmv)
  ⚠️ 两表必须一起写，否则 change_pct 缺失 → hoshi 静默漏信号。

用法：
    python scripts/refresh_baostock_duckdb.py                     # 增量补全到最新交易日
    python scripts/refresh_baostock_duckdb.py --limit 20          # 小样本试跑
    python scripts/refresh_baostock_duckdb.py --dry-run           # 只统计不写库
    python scripts/refresh_baostock_duckdb.py --days 300          # 每只拉最近 300 根日线
"""
import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
from loguru import logger

DB_PATH = str(PROJECT_ROOT / "data" / "tdx.duckdb")

FIELDS = "date,code,open,high,low,close,preclose,volume,amount,pctChg,turn,tradestatus"


def _bs_to_symbol(bs_code: str) -> str:
    """baostock 代码 'sh.600000' → 本地 symbol 'sh600000'"""
    return bs_code.replace(".", "")


def _bs_to_sym_and_name(bs_code: str, bs_name: str):
    """baostock 代码/名称 → (本地 symbol, 6位码, 本地 market 前缀)"""
    market, code = bs_code.split(".")
    return f"{market}{code}", code, market


def get_all_a_stocks():
    """用 baostock 拉全市场 A 股列表（含名称），返回 list[(bs_code, name)]。
    调用前必须已 bs.login()。"""
    import baostock as bs

    today = date.today().strftime("%Y-%m-%d")
    rs = bs.query_all_stock(day=today)
    out = []
    while (rs.error_code == "0") & rs.next():
        row = rs.get_row_data()
        # row: [code, tradeStatus, code_name]
        bs_code, status, name = row[0], row[1], row[2]
        if status != "1":  # 非交易状态跳过
            continue
        # 只要 A 股：sh/sz 全部 + bj 里非北证指数
        if bs_code.startswith(("sh.", "sz.")):
            out.append((bs_code, name))
        elif bs_code.startswith("bj."):
            # bj 里过滤北证指数（如 bj.899xxx）
            sym, code6, market = _bs_to_sym_and_name(bs_code, name)
            if code6.startswith(("4", "8", "9")) and not code6.startswith("899"):
                out.append((bs_code, name))
    return out


def fetch_daily(symbol_bs, start_date, end_date):
    """拉单只 baostock 日线，返回按日期升序的 list[dict]。
    baostock 返回顺序是升序，直接可用。"""
    import baostock as bs
    import socket

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(20)  # 防止单次查询永久挂起
    try:
        rs = bs.query_history_k_data_plus(
            symbol_bs,
            FIELDS,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",  # 不复权 bfq，与 hoshi 的 v_stock_bfq 对齐
        )
        rows = []
        while (rs.error_code == "0") & rs.next():
            rows.append(rs.get_row_data())
    except Exception:
        # 查询异常返回空，由调用方决定是否重连
        return []
    finally:
        socket.setdefaulttimeout(old_timeout)

    out = []
    for r in rows:
        # date,code,open,high,low,close,preclose,volume,amount,pctChg,turn,tradestatus
        try:
            tradestatus = r[11]
            if tradestatus != "1":  # 停牌日跳过
                continue
            d = datetime.strptime(r[0], "%Y-%m-%d").date()
            out.append({
                "date": d,
                "open": float(r[2]),
                "high": float(r[3]),
                "low": float(r[4]),
                "close": float(r[5]),
                "preclose": float(r[6]) if r[6] else None,
                "volume": int(float(r[7])) if r[7] else 0,  # baostock volume 单位是股
                "amount": float(r[8]) if r[8] else 0.0,
                "pctChg": float(r[9]) if r[9] else None,
                "turn": float(r[10]) if r[10] else None,
            })
        except (ValueError, TypeError) as e:
            logger.debug(f"skip row {r}: {e}")
            continue
    return out


def existing_max_dates(con):
    rows = con.execute(
        "SELECT symbol, MAX(date) FROM raw_kline_daily GROUP BY symbol"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def upsert_symbol(con, symbol, bars, max_date_map):
    """只写新于现有最大日期的数据到两表。返回新增条数。"""
    max_date = max_date_map.get(symbol)
    new_bars = [b for b in bars if (max_date is None or b["date"] > max_date)]
    if not new_bars:
        return 0

    # preclose 用 baostock 自己的，change_pct 也用 baostock 的 pctChg
    kline_rows, basic_rows = [], []
    for b in new_bars:
        kline_rows.append(
            (symbol, b["open"], b["high"], b["low"], b["close"], b["amount"], b["volume"], b["date"])
        )
        if b["preclose"] is not None and b["preclose"] > 0:
            preclose = b["preclose"]
            change_pct = b["pctChg"]
            amplitude = (b["high"] - b["low"]) / preclose * 100.0 if b["high"] and b["low"] else None
        else:
            preclose, change_pct, amplitude = None, None, None
        basic_rows.append(
            (b["date"], symbol, b["close"], preclose, change_pct, amplitude,
             b["turn"], None, None)
        )

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


def ensure_symbol_meta(con, sym_info: dict):
    """确保 raw_symbol_class / raw_symbol_name 里有该标的（股票）。"""
    for symbol, code6, market, name in sym_info.values():
        con.execute(
            "INSERT INTO raw_symbol_class (symbol, class) "
            "SELECT ?, 'stock' WHERE NOT EXISTS "
            "(SELECT 1 FROM raw_symbol_class WHERE symbol = ? AND class = 'stock')",
            [symbol, symbol],
        )
        con.execute(
            "INSERT INTO raw_symbol_name (symbol, name, class) "
            "SELECT ?, ?, 'stock' WHERE NOT EXISTS "
            "(SELECT 1 FROM raw_symbol_name WHERE symbol = ?)",
            [symbol, name, symbol],
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（小样本试跑）")
    ap.add_argument("--symbols", default="", help="只处理指定标的，逗号分隔，如 sh600367,sz000001")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    ap.add_argument("--days", type=int, default=120, help="每只拉最近 N 根日线（默认120，覆盖MA60+增量）")
    ap.add_argument("--start-date", default="", help="强制从该日期开始拉（回填用），默认自动按 days 推算")
    args = ap.parse_args()

    end_date = date.today().strftime("%Y-%m-%d")
    if args.start_date:
        start_date = args.start_date
    else:
        start_date = (date.today() - timedelta(days=int(args.days * 1.6))).strftime("%Y-%m-%d")

    logger.info("baostock login...")
    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        logger.error(f"baostock login failed: {lg.error_msg}")
        sys.exit(1)

    con = duckdb.connect(DB_PATH)

    # 1) 确定 symbol 列表
    if args.symbols.strip():
        sym_list = [s.strip() for s in args.symbols.split(",") if s.strip()]
        sym_info = {}
        for s in sym_list:
            market = s[:2]
            code6 = s[2:]
            sym_info[s] = (s, code6, market, s)
        logger.info(f"使用指定标的: {len(sym_info)} 只")
    else:
        stocks = get_all_a_stocks()  # list[(bs_code, name)]
        sym_info = {}
        for bs_code, name in stocks:
            symbol, code6, market = _bs_to_sym_and_name(bs_code, name)
            sym_info[symbol] = (symbol, code6, market, name)
        logger.info(f"全市场 A 股: {len(sym_info)} 只")
        if args.limit:
            sym_info = dict(list(sym_info.items())[: args.limit])

    # 2) 确保元数据存在
    if not args.dry_run:
        ensure_symbol_meta(con, sym_info)

    # 3) 增量拉取写入（按批次重连 baostock，防止单连接大量查询后挂起）
    max_date_map = existing_max_dates(con)
    t0 = time.time()
    added_total, failed, done, empty = 0, [], 0, 0

    BATCH = 100  # 每 100 只重新 login 一次

    def _relogin():
        import baostock as _bs
        try:
            _bs.logout()
        except Exception:
            pass
        lg = _bs.login()
        return _bs, lg

    try:
        for i, (symbol, (sym, code6, market, name)) in enumerate(sym_info.items(), 1):
            if i == 1 or (i - 1) % BATCH == 0:
                bs, lg = _relogin()
                if lg.error_code != "0":
                    raise RuntimeError(f"baostock batch relogin failed: {lg.error_msg}")

            bs_code = f"{market}.{code6}"
            try:
                bars = fetch_daily(bs_code, start_date, end_date)
            except Exception as e:
                failed.append((symbol, f"fetch: {e}"))
                continue
            if not bars:
                # 可能连接断了，重连一次再试
                bs, lg = _relogin()
                try:
                    bars = fetch_daily(bs_code, start_date, end_date)
                except Exception as e2:
                    failed.append((symbol, f"fetch-retry: {e2}"))
                    continue
                if not bars:
                    empty += 1
                    continue
            n = upsert_symbol(con, symbol, bars, max_date_map) if not args.dry_run else len(
                [b for b in bars if b["date"] > (max_date_map.get(symbol) or date.min)]
            )
            added_total += n
            done += 1
            if i % 200 == 0:
                logger.info(f"  进度 {i}/{len(sym_info)}  新增={added_total}  无数据={empty}  失败={len(failed)}")
    finally:
        try:
            bs.logout()
        except Exception:
            pass

    if not args.dry_run:
        con.commit()
    rng = con.execute("SELECT MIN(date), MAX(date) FROM raw_kline_daily").fetchone()
    chk = con.execute(
        "SELECT COUNT(*) FROM raw_basic_daily WHERE date >= DATE '2026-06-27' "
        "AND change_pct IS NOT NULL"
    ).fetchone()[0]
    con.close()

    print("\n" + "=" * 60)
    print("  baostock 数据补充完成")
    print("=" * 60)
    print(f"  处理股票数 : {done}/{len(sym_info)}")
    print(f"  新增 K 线行: {added_total}")
    print(f"  无数据     : {empty}")
    print(f"  失败       : {len(failed)}")
    if failed[:5]:
        print("  失败样例   :", failed[:5])
    print(f"  库日期范围 : {rng[0]} ~ {rng[1]}")
    print(f"  basic 新增(含 change_pct): {chk}")
    print(f"  耗时       : {time.time() - t0:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
