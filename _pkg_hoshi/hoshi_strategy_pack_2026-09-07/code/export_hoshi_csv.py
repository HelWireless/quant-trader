# -*- coding: utf-8 -*-
"""
================================================================================
 从本地 data/tdx.duckdb（baostock 补的数据）导出全市场日线 CSV，
 格式对齐 Hoshi 独立 CSV 回测器 hoshi_backtest_csv.py 的【目录模式】输入：
   每个文件一列 date,open,high,low,close,volume
   文件名：<6位代码>_<name>.csv   （name 用 raw_symbol_name 表，缺失则只留代码）

 用法：
   python scripts/export_hoshi_csv.py --start 2026-07-01 --end 2026-09-01 \
       --out scripts/hoshi_csv

 说明：
   - 默认只导出 2026-06-01 之后有日线的股票（近两月），避免把 6000+ 只全量导成
     海量小文件。--all 可关闭该过滤。
   - 导出结果可用：
     python .workbuddy/hoshi_qmt_kit/Hoshi_QMT_Kit/独立CSV回测器/hoshi_backtest_csv.py \
         --input scripts/hoshi_csv --out scripts/hoshi_live_result \
         --start 2026-07-01 --end 2026-09-01
================================================================================
"""
import argparse
import os
import sys

import duckdb

_WIN_INVALID = set('<>:"/\\|?*')

# 标准 A 股代码段白名单（前缀 -> 市场）。用白名单而非黑名单，
# 因为库里混着指数(sh000xxx/sz399xxx)、基金ETF(sh5xxxxx/sz15xxxx,16xxxx,18xxxx)、
# 债券、国债逆回购(sh204xxx/sz1318xx) —— 这些"价格"不是股价：
# 实测 sh204003(GC003国债逆回购) 的 145.50 是年化利率14.55%，被当成股价
# 会算出 -98.96% 的假暴跌，直接毁掉回测结论。
_STOCK_PREFIX = {
    "sh": ("600", "601", "603", "605", "688", "689"),
    "sz": ("000", "001", "002", "003", "300", "301"),
}


def _is_excluded(symbol, name):
    """是否剔除。白名单：只保留标准 A 股代码段；再剔 ST/退市/N新股。"""
    market = symbol[:2]
    code6 = symbol[2:] if len(symbol) >= 8 else symbol
    # 1) 代码段白名单（自动排除北交所、指数、基金ETF、债券、国债逆回购）
    if market not in _STOCK_PREFIX or not code6[:3].isdigit():
        return True
    if not code6.startswith(_STOCK_PREFIX[market]):
        return True
    # 2) ST / *ST / 退市 / 上市首日N股
    if "ST" in (name or "").upper() or "退" in (name or ""):
        return True
    if (name or "").startswith("N"):
        return True
    return False
    return False


def _safe_fname(code6, name):
    """生成安全的文件名：去掉 Windows 非法字符（含 *ST 等）。保留 6 位代码供回测器识别。"""
    safe = "".join(c for c in name if c not in _WIN_INVALID).strip()
    return f"{code6}_{safe}.csv" if safe else f"{code6}.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/tdx.duckdb", help="DuckDB 路径")
    ap.add_argument("--out", default="scripts/hoshi_csv", help="CSV 输出目录")
    ap.add_argument("--start", default="2026-07-01", help="起始日(默认2026-07-01)")
    ap.add_argument("--end", default="2026-09-01", help="结束日(默认2026-09-01)")
    ap.add_argument("--all", action="store_true", help="导出所有股票(默认只导近两月有日线的)")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已存在的 CSV")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    con = duckdb.connect(args.db, read_only=True)

    # 1) 确定股票范围
    if args.all:
        stocks = con.execute(
            "SELECT symbol, COALESCE(n.name, '') FROM raw_kline_daily k "
            "LEFT JOIN raw_symbol_name n USING (symbol) GROUP BY symbol, n.name"
        ).fetchall()
    else:
        stocks = con.execute(
            "SELECT DISTINCT k.symbol, COALESCE(n.name, '') FROM raw_kline_daily k "
            "LEFT JOIN raw_symbol_name n USING (symbol) "
            "WHERE k.date >= ?",
            [args.start],
        ).fetchall()

    print(f"待导出股票数: {len(stocks)}")

    # 2) 逐只导出
    n_written = n_skip_empty = 0
    n_excluded = 0
    for symbol, name in stocks:
        # --- 标的范围过滤（对齐 hoshi_final_strategy.md：剔除北交所/ST/退市/N新股）---
        # 回测器 hoshi_backtest_csv.py 本身没有这些过滤，只能在导出阶段剔除，
        # 否则北交所(920/430/4/8开头)的大波动票会污染结果（实测 920045 单笔 -49%）。
        if _is_excluded(symbol, name):
            n_excluded += 1
            continue

        # 6 位代码
        code6 = symbol[2:] if len(symbol) >= 8 else symbol

        fname = _safe_fname(code6, name)
        fpath = os.path.join(args.out, fname)
        if os.path.exists(fpath) and not args.overwrite:
            n_written += 1
            continue

        bars = con.execute(
            "SELECT date, open, high, low, close, volume FROM raw_kline_daily "
            "WHERE symbol = ? AND date BETWEEN ? AND ? "
            "ORDER BY date",
            [symbol, args.start, args.end],
        ).fetchall()

        if not bars:
            n_skip_empty += 1
            continue

        with open(fpath, "w", newline="", encoding="utf-8") as f:
            f.write("date,open,high,low,close,volume\n")
            for date, o, h, lo, c, v in bars:
                f.write(
                    f"{date},{o},{h},{lo},{c},{v or 0}\n"
                )
        n_written += 1

    con.close()
    print(f"完成: 写入 {n_written} 个文件, 空跳过 {n_skip_empty}, "
          f"剔除(北交所/ST/退/N股) {n_excluded}")
    print(f"输出目录: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
