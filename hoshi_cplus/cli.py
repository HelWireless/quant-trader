# -*- coding: utf-8 -*-
"""hoshi-cplus 命令行入口。

单窗口：
    python -m hoshi_cplus --data scripts/hoshi_csv_2005 --preset cplus \
        --start 2011-03-01 --end 2016-02-29

批量（多方案 × 多窗口）：
    python -m hoshi_cplus --data scripts/hoshi_csv_2005 \
        --windows scripts/windows_180.csv \
        --schemes cplus,B,original --out out.csv
"""
import argparse
import csv
import sys

from .backtest import run_backtest
from .config import PRESETS, TOTAL_CAPITAL, get_preset
from .data import load_data, precompute


def _run_batch(args, prepared, code_bars):
    windows = []
    with open(args.windows, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            windows.append((r['start'], r['end'], int(r['len_months'])))
    schemes = [s.strip() for s in args.schemes.split(',') if s.strip()]

    fout = open(args.out, 'w', newline='', encoding='utf-8')
    w = csv.writer(fout)
    w.writerow(['scheme', 'start', 'end', 'len_months', 'pct', 'trades'])
    n = 0
    for sk in schemes:
        for (s, e, m) in windows:
            r = run_backtest(prepared, preset=sk, start=s, end=e,
                             capital=TOTAL_CAPITAL, code_bars=code_bars)
            n += 1
            if r is None:
                w.writerow([sk, s, e, m, '', ''])
                continue
            w.writerow([sk, s, e, m, '%.4f' % r['ret'], r['n_trades']])
            fout.flush()
            print('  %-10s %s~%s (%2d月) %+9.2f%% 笔%d'
                  % (sk, s[:7], e[:7], m, r['ret'], r['n_trades']), flush=True)
    fout.close()
    print('\n共 %d 窗次 -> %s' % (n, args.out))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hoshi-cplus', description='hoshi-cplus 策略回测')
    ap.add_argument('--data', default='scripts/hoshi_csv_2005', help='日线 CSV 目录')
    ap.add_argument('--preset', default='cplus', help='方案名（cplus / B / original）')
    ap.add_argument('--start', help='窗口起始日 YYYY-MM-DD')
    ap.add_argument('--end', help='窗口结束日 YYYY-MM-DD')
    ap.add_argument('--capital', type=float, default=TOTAL_CAPITAL)
    ap.add_argument('--windows', help='批量模式：窗口 CSV（start,end,len_months）')
    ap.add_argument('--schemes', default='cplus', help='批量模式：逗号分隔的方案名')
    ap.add_argument('--out', default='hoshi_cplus_out.csv', help='批量模式输出')
    args = ap.parse_args(argv)

    print('加载数据: %s' % args.data)
    code_bars, names = load_data(args.data)
    print('  标的数 %d' % len(code_bars))
    prepared = precompute(code_bars)

    if args.windows:
        _run_batch(args, prepared, code_bars)
        return 0

    if not (args.start and args.end):
        ap.error('单窗口模式需要 --start 与 --end')

    p = get_preset(args.preset)
    r = run_backtest(prepared, preset=args.preset, start=args.start, end=args.end,
                     capital=args.capital, code_bars=code_bars)
    if r is None:
        print('窗口内无交易日')
        return 1
    print('\n方案        : %s' % p.name)
    print('窗口        : %s ~ %s' % (r['start'], r['end']))
    print('初始本金    : %.0f' % args.capital)
    print('期末资金    : %.0f' % r['final_capital'])
    print('收益率      : %+.2f%%' % r['ret'])
    print('交易笔数    : %d（买入 %d）' % (r['n_trades'], r['n_buys']))
    if r['closed']:
        wins = sum(1 for x in r['closed'] if x > 0)
        print('胜率        : %.1f%%（%d/%d）' % (100.0 * wins / len(r['closed']),
                                                wins, len(r['closed'])))
        print('平均单笔    : %+.2f%%' % (sum(r['closed']) / len(r['closed'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
