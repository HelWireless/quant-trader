# -*- coding: utf-8 -*-
"""修正 hoshi CSV 目录尾部被"盘中快照"污染的行（truncate + 重追加）。

背景（2026-09-21 发现的数据 bug）
--------------------------------
`refresh_tdx_duckdb.py` 的 `upsert_symbol` 只写入 `date > 现有最大日期` 的 bar：

    new_bars = [b for b in bars if (max_date is None or b["date"] > max_date)]
    if not new_bars:
        return 0          # 已有当日行 -> 直接跳过，永不修正

于是**任何在盘中跑过的刷新，都会把当天那根 K 线永久冻结成盘中快照**
（O/H/L 是当时的极值、C 是当时的现价），收盘后重跑刷新也**不会**覆盖。
`append_new_bars.py` 同样是 append-only（`r[0] > cur_last`），所以失真值会一路进 CSV。

本脚本做的事：
  1) 从 CSV 尾部**删掉** date >= --from 的行；
  2) 用 duckdb 里（已修正过的）同区间行**重新追加**回去。

只动尾部，前面的历史一个字节都不碰。默认 --dry-run 先报告影响面。

用法
----
  python scripts/repair_csv_tail.py --dir scripts/hoshi_csv_long --from 2026-09-18 --dry-run
  python scripts/repair_csv_tail.py --dir scripts/hoshi_csv_long --from 2026-09-18
"""
import argparse
import os
import re

import duckdb

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tdx.duckdb")

# 只处理白名单股票（与非白名单噪音无关）
_WL = (
    "(symbol LIKE 'sh600%' OR symbol LIKE 'sh601%' OR symbol LIKE 'sh603%' OR symbol LIKE 'sh605%'"
    " OR symbol LIKE 'sh688%' OR symbol LIKE 'sh689%'"
    " OR symbol LIKE 'sz000%' OR symbol LIKE 'sz001%' OR symbol LIKE 'sz002%' OR symbol LIKE 'sz003%'"
    " OR symbol LIKE 'sz300%' OR symbol LIKE 'sz301%')"
)


def market_of(code6):
    return "sh" if code6[0] == "6" else "sz"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--from", dest="from_date", required=True, help="从该日期起（含）删掉并重追加")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(DB, read_only=True)
    dbmax = con.execute("SELECT max(date) FROM raw_kline_daily").fetchone()[0]
    print("duckdb 最新日期 =", dbmax)
    print("重挂区间 =", args.from_date, "~", dbmax)

    rows = con.execute(
        f"SELECT symbol, date, open, high, low, close, volume "
        f"FROM raw_kline_daily WHERE {_WL} AND date >= DATE '{args.from_date}' "
        f"ORDER BY symbol, date"
    ).fetchall()
    by_sym = {}
    for sym, d, o, h, l, c, v in rows:
        by_sym.setdefault(sym, []).append((str(d), o, h, l, c, v))
    print("库内待重挂行数 =", len(rows))

    files = [f for f in os.listdir(args.dir) if f.endswith(".csv")]
    n_touched = n_dropped = n_added = 0
    missing = []

    for fn in sorted(files):
        m = re.match(r"(\d{6})_.*\.csv$|(\d{6})\.csv$", fn)
        if not m:
            continue
        code6 = m.group(1) or m.group(2)
        sym = market_of(code6) + code6
        path = os.path.join(args.dir, fn)

        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        lines = text.splitlines()
        if not lines or not lines[0].startswith("date"):
            continue
        header, body = lines[0], lines[1:]

        keep = []
        dropped = 0
        for ln in body:
            if ln and ln.split(",")[0] >= args.from_date:
                dropped += 1
            else:
                keep.append(ln)

        # 重追加：date > keep 里最后一根
        last_kept = keep[-1].split(",")[0] if keep else ""
        new = [r for r in by_sym.get(sym, []) if r[0] > last_kept]
        if dropped == 0 and not new:
            continue

        n_touched += 1
        n_dropped += dropped
        n_added += len(new)
        if not new and dropped:
            missing.append(fn)

        if args.dry_run:
            continue

        out = "\n".join([header] + keep + [",".join([str(x) for x in r]) for r in new]) + "\n"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(out)

    print(("【dry-run】" if args.dry_run else "已写入") + f" 目录 = {args.dir}")
    print("  受影响文件数 =", n_touched)
    print("  删除尾部行数 =", n_dropped)
    print("  重追加行数   =", n_added)
    if missing:
        print(f"  ⚠ 删了但库里没得补的文件数 = {len(missing)}（例如 {missing[:5]}）")
    con.close()


if __name__ == "__main__":
    main()
