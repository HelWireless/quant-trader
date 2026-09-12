# -*- coding: utf-8 -*-
"""R3 替代方案测试：用有经济含义的"市场广度门控"替代纯随机的"3连亏停手"。

用法: python hoshi_r3_test.py <variant>
  r1  h5s9 + 关R3 + 广度门控20(默认)
  r2  h5s9 + 关R3 + 广度门控30
  r3  原版  + 关R3 + 广度门控30
  r4  h5s9 + 开R3 + 广度门控30  (只加广度门控，保留R3)
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

CFG = {
    'r1': dict(score=9.0, stop=5, r3=False, bt=20.0),
    'r2': dict(score=9.0, stop=5, r3=False, bt=30.0),
    'r3': dict(score=8.0, stop=15, r3=False, bt=30.0),
    'r4': dict(score=9.0, stop=5, r3=True, bt=30.0),
}

v = sys.argv[1]
c = CFG[v]
hbe.MIN_SCORE = c['score']
hbe.LOSS_HARD_START_DAY = c['stop']
hbe.USE_R3_GATE = c['r3']
hbe.BREADTH_THRESH = c['bt']
hbe.USE_BREADTH_GATE = True
hbe.SCORE_TIER_SIZING = False
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
