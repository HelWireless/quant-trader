# -*- coding: utf-8 -*-
"""同窗口三方案对照复盘：原版 / H5S9 / 方案B，指定资金与区间。

用于把「WSL 实盘流水线的结果」与「本地回测引擎的结果」放在同一口径下对账。

用法:
  python hoshi_replay_compare.py [start] [end] [capital]
  默认 2026-09-01 2026-09-11 300000
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False

START = sys.argv[1] if len(sys.argv) > 1 else '2026-09-01'
END = sys.argv[2] if len(sys.argv) > 2 else '2026-09-11'
CAPITAL = float(sys.argv[3]) if len(sys.argv) > 3 else 300000.0

BASE = dict(
    LOSS_START_DAY=15, MAX_SLOTS=10, MAX_BUY_PER_DAY=0, EXIT_MODE='AUTO',
    ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
    SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
    USE_BREADTH_GATE=True, BREADTH_THRESH=20.0, TOTAL_CAPITAL=CAPITAL)

SCHEMES = [
    ('原版(8分/止损15/R3开)', dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, USE_R3_GATE=True)),
    ('H5S9(9分/止损5/R3开)', dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, USE_R3_GATE=True)),
    ('方案B(9分/止损5/R3关)', dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, USE_R3_GATE=False)),
]

hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

import re as _re
for _fn in os.listdir(os.path.join(HERE, 'hoshi_csv_long')):
    _m = _re.match(r'(\d{6})_(.+)\.csv$', _fn)
    if _m and not names.get(_m.group(1)):
        names[_m.group(1)] = _m.group(2)

print('=' * 100)
print('同窗口三方案对照 | %s ~ %s | 初始资金 %.0f 元' % (START, END, CAPITAL))
print('=' * 100)

for label, over in SCHEMES:
    cfg = dict(BASE)
    cfg.update(over)
    for k, v in cfg.items():
        setattr(hbe, k, v)
    r = hbe.run_backtest(code_bars, names, all_dates, start=START, end=END)
    eq = r['equity_curve']
    last = eq[-1] if eq else (END, CAPITAL, 0.0, CAPITAL)
    real_sells = [t for t in r['closed'] if t['exit_reason'] != '回测结束强平']
    holds = [t for t in r['closed'] if t['exit_reason'] == '回测结束强平']

    print('\n■ %s' % label)
    print('  期末权益 %.2f 元 | 区间收益 %+.2f%% | 买入 %d 笔 | 卖出 %d 笔 | 期末持仓 %d 只'
          % (last[3], (last[3] - CAPITAL) / CAPITAL * 100.0,
             len(r['buys']), len(real_sells), len(holds)))
    if r['buys']:
        print('  %-10s %-7s %-8s %5s %8s %7s %10s' % ('买入日', '代码', '名称', '评分', '价格', '股数', '金额'))
        for b in sorted(r['buys'], key=lambda x: (x['date'], -x['score'])):
            print('  %-10s %-7s %-8s %5.1f %8.2f %7d %10.2f'
                  % (b['date'], b['code'], b['name'], b['score'], b['price'], b['shares'], b['cost']))
    else:
        print('  （无买入）')
    for t in sorted(real_sells, key=lambda x: x['sell_date']):
        print('  卖出 %-10s %-7s %-8s %6.2f -> %6.2f  %+7.2f%%  %s'
              % (t['sell_date'], t['code'], t['name'], t['buy_price'],
                 t['sell_price'], t['return_pct'], t['exit_reason']))
    for t in sorted(holds, key=lambda x: x['buy_date']):
        print('  持仓 %-10s %-7s %-8s 买 %6.2f  末 %6.2f  %+7.2f%%'
              % (t['buy_date'], t['code'], t['name'], t['buy_price'],
                 t['sell_price'], t['return_pct']))
