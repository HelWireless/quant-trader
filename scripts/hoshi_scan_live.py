# -*- coding: utf-8 -*-
"""hoshi-cplus 实盘信号扫描（live 模式）。

为什么不能用 `python -m hoshi_cplus --scan D`：
  包内 precompute() 把信号挂在 sig_by_date[d] 上，用的却是 bars[:k]（截止 d 的**前一根**）。
  即「确认日 = d 的前一交易日、执行日 = d」。所以 --scan 的 D 是**执行日**，
  而执行日当天还没有 K 线 → 用它扫"明天"永远拿不到结果（days 里没有 D）。
  实盘要的是：用**最新一根收盘**当确认日，执行日 = 下一个交易日。

本脚本直接对每只票的最后一根 K 线跑 detect_signal（closes[-1] = 最新收盘 = 确认日），
与回测口径一致：确认日收盘出信号 → 次日开盘买入。

用法
----
  python scripts/hoshi_scan_live.py                          # 默认 scripts/hoshi_csv_2005
  python scripts/hoshi_scan_live.py --data scripts/hoshi_csv_long
  python scripts/hoshi_scan_live.py --day 2026-09-15         # 指定确认日（默认取最新）
  python scripts/hoshi_scan_live.py --held 002365,300901     # 已持有的不再重复买
  python scripts/hoshi_scan_live.py --equity 298545.93       # 用于算建议股数
  python scripts/hoshi_scan_live.py --json out.json
"""
import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.config import (LOT_SIZE, MAX_POSITION_R, MAX_SLOTS, MA_SLOW,
                                MIN_BARS, BREADTH_THRESH, BREADTH_MIN_SAMPLE,
                                get_preset)
from hoshi_cplus.data import load_data
from hoshi_cplus.signals import detect_signal


def limit_pct(code):
    """涨跌停幅度（%）：创业板 30x / 科创板 68x = 20%，其余 10%。"""
    return 20.0 if code[:2] in ('30', '68') else 10.0


def scan(dirpath, confirm_day, preset_key, held, equity):
    p = get_preset(preset_key)
    code_bars, names = load_data(dirpath)
    if confirm_day is None:
        confirm_day = max(b[-1].date for b in code_bars.values() if b)

    n_above = n_valid = 0
    hits = []
    for code, bars in code_bars.items():
        if not bars or bars[-1].date != confirm_day:
            continue                              # 当日无数据（停牌/退市/未更新）
        k = len(bars) - 1
        seg = bars[max(0, k - (MIN_BARS - 1)):k + 1]
        if len(seg) < MIN_BARS - 1:
            continue
        if len(seg) >= MA_SLOW + 1:
            ma60 = sum(b.close for b in seg[-MA_SLOW - 1:-1]) / float(MA_SLOW)
            if ma60 > 0:
                n_valid += 1
                if seg[-1].close > ma60:
                    n_above += 1

        s = detect_signal([b.open for b in seg], [b.high for b in seg],
                          [b.low for b in seg], [b.close for b in seg])
        if s is None or s < p.min_score or code in held:
            continue
        prev = bars[k - 1].close if k >= 1 else None
        chg = ((bars[k].close / prev - 1) * 100.0) if prev else 0.0
        hits.append(dict(
            code=code, name=names.get(code, ''), score=s,
            close=bars[k].close, chg=chg,
            at_high=abs(bars[k].close - bars[k].high) < 1e-9,
            limit_up=(chg >= limit_pct(code) - 0.05 and
                      abs(bars[k].close - bars[k].high) < 1e-9),
        ))

    breadth = (100.0 * n_above / n_valid) if n_valid >= BREADTH_MIN_SAMPLE else None
    breadth_pass = breadth is not None and breadth >= BREADTH_THRESH
    hits.sort(key=lambda x: (-x['score'], x['code']))

    cands = []
    if breadth_pass:
        free = max(0, MAX_SLOTS - len(held))
        for h in hits[:free]:
            h = dict(h)
            h['shares'] = int(equity * MAX_POSITION_R // h['close'] // LOT_SIZE) * LOT_SIZE
            h['est_amount'] = h['shares'] * h['close']
            cands.append(h)
    return dict(dir=dirpath, confirm_day=str(confirm_day), n_valid=n_valid,
                n_above=n_above, breadth=breadth, breadth_pass=breadth_pass,
                all_hits=hits, candidates=cands)


def main():
    ap = argparse.ArgumentParser(description='hoshi-cplus 实盘信号扫描（live）')
    ap.add_argument('--data', default='scripts/hoshi_csv_2005')
    ap.add_argument('--day', help='确认日 YYYY-MM-DD（默认取数据里最新）')
    ap.add_argument('--preset', default='cplus')
    ap.add_argument('--held', default='', help='已持有代码，逗号分隔')
    ap.add_argument('--equity', type=float, default=300000.0)
    ap.add_argument('--json', help='把结果写成 JSON')
    args = ap.parse_args()

    from datetime import date as _date
    held = tuple(x.strip() for x in args.held.split(',') if x.strip())
    r = scan(args.data, _date.fromisoformat(args.day) if args.day else None,
             args.preset, held, args.equity)

    print('=' * 72)
    print('hoshi-cplus 实盘扫描（live 模式）')
    print('  数据目录 : %s' % r['dir'])
    print('  确认日   : %s（用该日收盘算信号）' % r['confirm_day'])
    pname = get_preset(args.preset).name
    print('  方案     : %s（预设名 %s）' % (pname, args.preset))
    bv = '样本不足' if r['breadth'] is None else '%.1f%%' % r['breadth']
    print('  市场广度 : %s（%d/%d）→ 门控 %s（阈值 %.0f%%）'
          % (bv, r['n_above'], r['n_valid'],
             '通过' if r['breadth_pass'] else '未通过，不开新仓', BREADTH_THRESH))
    print('=' * 72)

    if r['all_hits']:
        print('\n全部合格信号（评分≥9，共 %d 只）：\n' % len(r['all_hits']))
        for h in r['all_hits']:
            flag = ' ⚠确认日涨停' if h['limit_up'] else ''
            print('  %s %-8s 评分%4.1f  确认日收%.3f (%+.2f%%)%s'
                  % (h['code'], h['name'], h['score'], h['close'], h['chg'], flag))
    else:
        print('\n（当日无合格信号）')

    print('\n建议买入（受 %d 个仓位上限约束，已剔除已持有）：\n' % MAX_SLOTS)
    if not r['candidates']:
        print('  （无）')
    for h in r['candidates']:
        print('  %s %-8s 评分%4.1f  %d 股  约 %.0f 元'
              % (h['code'], h['name'], h['score'], h['shares'], h['est_amount']))
    print()

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=2, default=str)
        print('已写入 %s' % args.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
