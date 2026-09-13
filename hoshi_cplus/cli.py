# -*- coding: utf-8 -*-
"""hoshi-cplus 命令行入口。

单窗口回测：
    python -m hoshi_cplus --data scripts/hoshi_csv_2005 --preset cplus \
        --start 2011-03-01 --end 2016-02-29

批量回测：
    python -m hoshi_cplus --data scripts/hoshi_csv_2005 \
        --windows scripts/windows_180.csv \
        --schemes cplus,B,original --out out.csv

实盘信号扫描（输出买入指令单）：
    python -m hoshi_cplus --data scripts/hoshi_csv_2005 --scan 2026-09-11
    python -m hoshi_cplus --data scripts/hoshi_csv_2005 --scan-last 15
"""
import argparse
import csv
import sys

from .backtest import run_backtest
from .config import TOTAL_CAPITAL, get_preset
from .data import load_data, precompute
from .orders import build_plan, render_plan, scan_signals


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


def _run_scan(args, prepared, code_bars, names, days):
    """信号扫描：输出可直接照做的买入指令单。"""
    dates = prepared[0]
    p = get_preset(args.preset)
    total = 0
    for day in days:
        res = scan_signals(prepared, code_bars, names, day, p,
                           equity=args.capital, held=(), max_slots=10)
        if res is None:
            continue
        bv = ('%.1f%%' % res['breadth']) if res['breadth'] is not None else '样本不足'
        print()
        print('=' * 70)
        print('信号扫描   %s    方案 %s' % (day, p.name))
        print('市场广度   %s   → 门控 %s（阈值 20%%）'
              % (bv, '通过' if res['breadth_pass'] else '未通过 (不开新仓)'))
        print('=' * 70)
        if not res['candidates']:
            print('（当日无合格买入信号）')
            continue
        print('候选 %d 只：\n' % len(res['candidates']))
        for c in res['candidates']:
            print(render_plan(build_plan(c, dates, p)))
            total += 1
    print('\n共 %d 条买入指令单' % total)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hoshi-cplus', description='hoshi-cplus 策略')
    ap.add_argument('--data', default='scripts/hoshi_csv_2005', help='日线 CSV 目录')
    ap.add_argument('--preset', default='cplus', help='方案（cplus / B / original）')
    ap.add_argument('--start', help='回测起始日 YYYY-MM-DD')
    ap.add_argument('--end', help='回测结束日 YYYY-MM-DD')
    ap.add_argument('--capital', type=float, default=TOTAL_CAPITAL)
    ap.add_argument('--windows', help='批量模式：窗口 CSV')
    ap.add_argument('--schemes', default='cplus', help='批量模式：逗号分隔方案名')
    ap.add_argument('--out', default='hoshi_cplus_out.csv', help='批量模式输出')
    ap.add_argument('--scan', help='信号扫描：信号日 YYYY-MM-DD')
    ap.add_argument('--scan-last', type=int, help='信号扫描：最近 N 个交易日')
    args = ap.parse_args(argv)

    print('加载数据: %s' % args.data)
    code_bars, names = load_data(args.data)
    print('  标的数 %d' % len(code_bars))
    prepared = precompute(code_bars)

    if args.windows:
        _run_batch(args, prepared, code_bars)
        return 0

    if args.scan or args.scan_last:
        # 注意：dates 里是 datetime.date 对象，字符串比不进去
        from datetime import date as _date
        dates = prepared[0]
        days = ([_date.fromisoformat(args.scan)] if args.scan
                else dates[-args.scan_last:])
        _run_scan(args, prepared, code_bars, names, days)
        return 0

    if not (args.start and args.end):
        ap.error('需要 --start/--end（回测）或 --scan / --scan-last（信号扫描）')

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
