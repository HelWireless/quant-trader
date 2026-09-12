# -*- coding: utf-8 -*-
"""评分分档仓位测试：用"仓位"替代"二值门槛"，看能否同时解决误杀与挡灾。

用法: python hoshi_tier_test.py <variant>
  t1  tiersA(9:1.0/8.5:0.7/8:0.45) + stop5
  t2  tiersA + stop15
  t3  tiersB(9:1.0/8.5:0.6/8:0.30) + stop5
  t4  tiersB + stop15
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp4.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0
hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

WINDOWS = [
    ('A 2014-12~16-11', '2014-12-01', '2016-11-30'),
    ('B 2019-05~21-04', '2019-05-01', '2021-04-30'),
    ('C 2018-10~19-09', '2018-10-01', '2019-09-30'),
    ('D 2022-02~25-01', '2022-02-01', '2025-01-31'),
    ('E 2016-02~19-01', '2016-02-01', '2019-01-31'),
    ('F 2014-06~15-05', '2014-06-01', '2015-05-31'),
]

TIERS_A = [(9.0, 1.00), (8.5, 0.70), (8.0, 0.45)]
TIERS_B = [(9.0, 1.00), (8.5, 0.60), (8.0, 0.30)]

CFG = {
    't1': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, T=TIERS_A),
    't2': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, T=TIERS_A),
    't3': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, T=TIERS_B),
    't4': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, T=TIERS_B),
}

v = sys.argv[1]
c = CFG[v]
hbe.MIN_SCORE = c['MIN_SCORE']
hbe.LOSS_HARD_START_DAY = c['LOSS_HARD_START_DAY']
hbe.SCORE_TIER_SIZING = True
hbe.SCORE_TIERS = c['T']
hbe.SCORE_TIER_ADAPTIVE = False
hbe.ADAPTIVE_SCORE = False
hbe.ADAPTIVE_STOP = False
hbe.RS_FILTER = False
hbe.MAX_BUY_PER_DAY = 0
hbe.LOSS_START_DAY = 15
hbe.MAX_SLOTS = 10
hbe.EXIT_MODE = 'AUTO'

out = []
for tag, s, e in WINDOWS:
    r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
    ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
    out.append('%s %+8.2f%% 笔数=%3d R3停手=%d' % (tag, ret, len(r['closed']), len(r['stops'])))
    print('%s | %s' % (v, out[-1]), flush=True)

print('RESULT %s | %s' % (v, ' | '.join(o.split()[1] for o in out)), flush=True)
