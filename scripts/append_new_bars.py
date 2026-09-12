# -*- coding: utf-8 -*-
"""把 duckdb 里新增的日线追加到 hoshi_csv_long/*.csv（只增不改，保护已有内容）。

背景：
  回测/复盘吃的是 scripts/hoshi_csv_long 目录下的每票一个 CSV。
  直接重跑 export_hoshi_csv.py --overwrite 会重写全部文件，一旦导出起点与
  历史不同就会改变 MA 预热，导致 hoshi_best_B.py --verify 的锚点对不上。
  本脚本只把「各文件最后日期之后的 K 线」追加进去，历史内容逐字节不动。

用法:
  python scripts/append_new_bars.py            # 追加到所有 CSV
  python scripts/append_new_bars.py --dry-run  # 只统计不写
"""
import argparse
import os
import re
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(HERE, 'hoshi_csv_long')
DB = os.path.abspath(os.path.join(HERE, '..', 'data', 'tdx.duckdb'))

_WL = ("(symbol LIKE 'sh600%' OR symbol LIKE 'sh601%' OR symbol LIKE 'sh603%' "
       "OR symbol LIKE 'sh605%' OR symbol LIKE 'sh688%' OR symbol LIKE 'sh689%' "
       "OR symbol LIKE 'sz000%' OR symbol LIKE 'sz001%' OR symbol LIKE 'sz002%' "
       "OR symbol LIKE 'sz003%' OR symbol LIKE 'sz300%' OR symbol LIKE 'sz301%')")


def market_of(code6):
    return 'sh' if code6[0] == '6' else 'sz'


def last_date_of(path):
    """读文件最后一行拿最后日期（不把整个文件读进内存的方式）。"""
    with open(path, 'rb') as f:
        try:
            f.seek(-2, os.SEEK_END)
        except OSError:
            return None
        while f.read(1) != b'\n':
            try:
                f.seek(-2, os.SEEK_CUR)
            except OSError:
                f.seek(0)
                break
        last = f.readline().decode('utf-8', 'ignore').strip()
    if not last or last.startswith('date'):
        return None
    return last.split(',')[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--dir', default=CSV_DIR)
    args = ap.parse_args()

    con = duckdb.connect(DB, read_only=True)
    dbmax = con.execute('SELECT max(date) FROM raw_kline_daily').fetchone()[0]
    print('duckdb 最新日期 =', dbmax)

    files = [f for f in os.listdir(args.dir) if f.endswith('.csv')]
    print('CSV 文件数 =', len(files))

    # 每个文件当前最后日期
    targets = {}
    for fn in files:
        m = re.match(r'(\d{6})_.*\.csv$', fn)
        if not m:
            continue
        d = last_date_of(os.path.join(args.dir, fn))
        if d:
            targets[fn] = (m.group(1), d)
    print('可追加文件数 =', len(targets))

    # 一次性把「库里最新日往前 20 个交易日内」的行捞出来，够用且快
    rows = con.execute(f"""
        SELECT symbol, date, open, high, low, close, volume
        FROM raw_kline_daily
        WHERE {_WL} AND date > '2026-08-01'
        ORDER BY symbol, date
    """).fetchall()
    print('库内 2026-08-01 之后的行数 =', len(rows))

    by_sym = {}
    for sym, d, o, h, l, c, v in rows:
        by_sym.setdefault(sym, []).append((str(d), o, h, l, c, v))

    added_files = 0
    added_rows = 0
    for fn, (code6, cur_last) in sorted(targets.items()):
        sym = market_of(code6) + code6
        new = [r for r in by_sym.get(sym, []) if r[0] > cur_last]
        if not new:
            continue
        added_files += 1
        added_rows += len(new)
        if args.dry_run:
            if added_files <= 5:
                print('  [dry] %s  %s -> %s  (+%d)' % (fn, cur_last, new[-1][0], len(new)))
            continue
        p = os.path.join(args.dir, fn)
        with open(p, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            need_nl = f.read(1) != b'\n'
        with open(p, 'a', encoding='utf-8', newline='') as f:
            if need_nl:
                f.write('\n')
            for d, o, h, l, c, v in new:
                f.write('%s,%.2f,%.2f,%.2f,%.2f,%d\n' % (d, o, h, l, c, int(v)))
    con.close()

    print('=' * 60)
    print('追加文件数 : %d' % added_files)
    print('追加 K 线行: %d' % added_rows)
    print('模式       : %s' % ('DRY-RUN（未写入）' if args.dry_run else '已写入'))
    print('=' * 60)


if __name__ == '__main__':
    main()
