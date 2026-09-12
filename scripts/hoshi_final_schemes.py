# -*- coding: utf-8 -*-
"""最终方案回测（一个进程内跑多个方案，复用已加载数据，节省内存）。

用法: python hoshi_final_schemes.py <group>
  g1 = 分档仓位 t1/t2
  g2 = R3 替代 r2/r3
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

SCHEMES = {
    't1': dict(desc='t1 分档仓位A(9:1/8.5:.7/8:.45)+stop5',
               MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=True,
               SCORE_TIERS=TIERS_A, USE_R3_GATE=True, BREADTH_THRESH=20.0),
    't2': dict(desc='t2 分档仓位A+stop15',
               MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, SCORE_TIER_SIZING=True,
               SCORE_TIERS=TIERS_A, USE_R3_GATE=True, BREADTH_THRESH=20.0),
    'r2': dict(desc='r2 h5s9+关R3+广度30',
               MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
               USE_R3_GATE=False, BREADTH_THRESH=30.0),
    'r3': dict(desc='r3 原版+关R3+广度30',
               MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, SCORE_TIER_SIZING=False,
               USE_R3_GATE=False, BREADTH_THRESH=30.0),
    't5': dict(desc='t5 分档仓位A+stop5+关R3+广度30',
               MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=True,
               SCORE_TIERS=TIERS_A, USE_R3_GATE=False, BREADTH_THRESH=30.0),
}

GROUPS = {'g1': ['t1', 't2'], 'g2': ['r2', 'r3'], 'g3': ['t5']}

g = sys.argv[1]
for sk in GROUPS[g]:
    cfg = dict(SCHEMES[sk])
    desc = cfg.pop('desc')
    for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                     ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                     SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                     USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                     MIN_SCORE=8.0, LOSS_HARD_START_DAY=15).items():
        setattr(hbe, k, v)
    for k, v in cfg.items():
        setattr(hbe, k, v)
    out = []
    for tag, s, e in WINDOWS:
        r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
        ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
        out.append((tag, ret, len(r['closed']), len(r['stops'])))
        print('%s | %-36s | %-16s %+8.2f%% 笔数=%3d R3停手=%d'
              % (g, desc, tag, ret, len(r['closed']), len(r['stops'])), flush=True)
    print('RESULT %s | %s | %s' % (g, sk, ' | '.join('%s %+.2f' % (t[0][0], t[1]) for t in out)), flush=True)
