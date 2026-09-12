# -*- coding: utf-8 -*-
"""最差入场专项：从最糟糕的起点入场，多久能回到正收益？是否越久越高？

起点（两类"最差"）：
  A 类 市场顶部入场（买完市场就崩）
    2015-06-01  股灾顶
    2018-01-01  蓝筹顶
    2021-02-01  核心资产顶
  B 类 策略史上最差起点（原版 1 年窗口 -42.58%）
    2014-06-01

持有期：6 / 12 / 24 / 36 / 60 个月

用法: python hoshi_worst_entry.py <base|h5s9|t5>
"""
import csv
import importlib.util
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp4.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0
hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

TIERS_A = [(9.0, 1.00), (8.5, 0.70), (8.0, 0.45)]
SCHEMES = {
    'base': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, SCORE_TIER_SIZING=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0),
    'h5s9': dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0),
    't5': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=True,
               SCORE_TIERS=TIERS_A, USE_R3_GATE=False, BREADTH_THRESH=30.0),
}

STARTS = [
    ('2014-06-01', 'B类 策略最差起点'),
    ('2015-06-01', 'A类 股灾顶'),
    ('2018-01-01', 'A类 蓝筹顶'),
    ('2021-02-01', 'A类 核心资产顶'),
]
HORIZONS = [6, 12, 24, 36, 60]


def add_months(d, n):
    y, m = d.year, d.month
    tot = m - 1 + n
    return date(y + tot // 12, tot % 12 + 1, 1)


sk = sys.argv[1]
for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                 ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                 SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                 MIN_SCORE=8.0, LOSS_HARD_START_DAY=15).items():
    setattr(hbe, k, v)
for k, v in SCHEMES[sk].items():
    setattr(hbe, k, v)

out_path = os.path.join(HERE, 'hoshi_worst_entry_%s.csv' % sk)
fout = open(out_path, 'w', newline='', encoding='utf-8')
w = csv.writer(fout)
w.writerow(['start', 'tag', 'months', 'end', 'ret_pct', 'trades'])

print('%s 开始' % sk, flush=True)
for s, tag in STARTS:
    sd = date(*[int(x) for x in s.split('-')])
    for m in HORIZONS:
        # 窗口 = [sd, sd + m 个月)
        ey, em = (sd.year + (sd.month - 1 + m) // 12, (sd.month - 1 + m) % 12 + 1)
        import calendar
        e = date(ey, em, calendar.monthrange(ey, em)[1])
        r = hbe.run_backtest(code_bars, names, all_dates,
                             start=sd.isoformat(), end=e.isoformat())
        ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
        w.writerow([s, tag, m, e.isoformat(), '%.4f' % ret, len(r['closed'])])
        fout.flush()
        print('%s | %s | %2d月 (%s~%s) %+8.2f%%  笔数=%d'
              % (sk, s, m, s[:7], e.isoformat()[:7], ret, len(r['closed'])), flush=True)

fout.close()
print('DONE %s -> %s' % (sk, out_path), flush=True)
