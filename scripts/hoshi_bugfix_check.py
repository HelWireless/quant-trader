# -*- coding: utf-8 -*-
"""对比强平 bug 修复前后的收益差异。

用法: python hoshi_bugfix_check.py <engine> <scheme>
  engine = exp4(有bug) | exp5(已修复)
  scheme = base | h5s9 | t5
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
eng, sk = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location(
    'hbe', os.path.join(HERE, 'hoshi_backtest_%s.py' % eng))
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
for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                 ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                 SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                 MIN_SCORE=8.0, LOSS_HARD_START_DAY=15).items():
    setattr(hbe, k, v)
for k, v in SCHEMES[sk].items():
    setattr(hbe, k, v)

WINDOWS = [
    ('F 2014-06~2015-05', '2014-06-01', '2015-05-31'),
    ('A 2014-12~2016-11', '2014-12-01', '2016-11-30'),
    ('E 2016-02~2019-01', '2016-02-01', '2019-01-31'),
    ('近 2025-07~2026-06', '2025-07-01', '2026-06-30'),
]

for tag, s, e in WINDOWS:
    r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
    ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
    nfc = sum(1 for t in r['closed'] if t['exit_reason'] == '回测结束强平')
    print('%s %-5s %-20s %+10.2f%%  笔数=%4d 其中强平=%d'
          % (eng, sk, tag, ret, len(r['closed']), nfc), flush=True)
print('DONE %s %s' % (eng, sk), flush=True)
