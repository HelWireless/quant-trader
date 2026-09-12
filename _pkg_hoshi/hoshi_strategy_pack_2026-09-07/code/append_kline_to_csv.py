# -*- coding: utf-8 -*-
"""把 duckdb 里新增交易日的K线增量追加到 scripts/hoshi_csv_long 的按股CSV。
只追加 > 文件内最后日期 的行；新上市股(无文件)按白名单创建。
用法: python scripts/append_kline_to_csv.py --start 2026-09-02 --end 2026-09-04
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from export_hoshi_csv import _is_excluded, _safe_fname  # noqa: E402

import duckdb  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='data/tdx.duckdb')
    ap.add_argument('--out', default='scripts/hoshi_csv_long')
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    rows = con.execute(
        "SELECT k.symbol, k.date, k.open, k.high, k.low, k.close, k.volume, "
        "COALESCE(n.name,'') FROM raw_kline_daily k "
        "LEFT JOIN raw_symbol_name n USING (symbol) "
        "WHERE k.date BETWEEN ? AND ? ORDER BY k.symbol, k.date",
        [args.start, args.end],
    ).fetchall()
    con.close()

    by_sym = defaultdict(list)
    names = {}
    for symbol, d, o, h, lo, c, v, name in rows:
        if _is_excluded(symbol, name):
            continue
        code6 = symbol[2:] if len(symbol) >= 8 else symbol
        by_sym[code6].append((d, o, h, lo, c, v or 0))
        if name:
            names[code6] = name

    print('白名单内待处理标的: %d' % len(by_sym))
    # 一次性建文件索引（避免逐股 listdir 的 O(n²)）
    all_files = os.listdir(args.out)
    file_index = {}
    for fn in all_files:
        if not fn.endswith('.csv'):
            continue
        code6 = fn.split('_')[0].replace('.csv', '')
        file_index.setdefault(code6, os.path.join(args.out, fn))

    n_append = n_skip = n_new = 0
    for code6, bars in by_sym.items():
        fpath = file_index.get(code6)
        if fpath is None:
            name = names.get(code6, '')
            fname = _safe_fname(code6, name)
            fpath = os.path.join(args.out, fname)
            file_index[code6] = fpath
            last_date = None
            n_new += 1
        else:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.read().strip().splitlines()
            last_date = lines[-1].split(',')[0] if len(lines) > 1 else None

        new_rows = [b for b in bars if last_date is None or str(b[0]) > last_date]
        if not new_rows:
            n_skip += 1
            continue
        with open(fpath, 'a', encoding='utf-8', newline='') as f:
            for d, o, h, lo, c, v in new_rows:
                f.write('%s,%s,%s,%s,%s,%s\n' % (d, o, h, lo, c, v))
        n_append += 1

    print('完成: 追加 %d 只, 无新增跳过 %d 只, 新建 %d 只' % (n_append, n_skip, n_new))


if __name__ == '__main__':
    main()
