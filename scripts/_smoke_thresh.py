# -*- coding: utf-8 -*-
"""冒烟自检（临时）：确认 LOSS_HARD_PCT 的 setattr 真正生效，且 t8 与 abl1_b 锚点吻合。

判据（三条全过才开大规模跑批）：
  1) t8 必须与 hoshi_abl1_b.csv 锚点逐位相同      -> 基线对齐正确
  2) t6 必须与 t8 有差异                            -> 阈值真的生效
  3) trades 数应与锚点一致
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0
print('loading market features + csv ...', flush=True)
hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))
print('loaded: %d codes, %d dates' % (len(code_bars), len(all_dates)), flush=True)

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
            ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
            SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
            USE_R3_GATE=False, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
            MIN_SCORE=9.0, LOSS_HARD_START_DAY=5)

# (start, end, abl1_b 锚点 pct, 锚点 trades)
CASES = [('2025-07-01', '2026-06-30', 141.1568, 188),
         ('2023-01-01', '2023-12-31', -3.8671, 101)]

res = {}
for thr in (-8.2, -6.0):
    for k, v in BASE.items():
        setattr(hbe, k, v)
    hbe.LOSS_HARD_PCT = thr
    assert hbe.LOSS_HARD_PCT == thr
    for s, e, exp_pct, exp_tr in CASES:
        r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
        ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
        n = len(r['closed'])
        res[(thr, s)] = ret
        if thr == -8.2:
            ok = 'ANCHOR-OK' if abs(ret - exp_pct) < 0.001 else 'ANCHOR-DIFF %+.4f' % (ret - exp_pct)
        else:
            ok = ''
        print('thr=%+.1f%%  %s~%s  %+10.4f%%  笔%3d  | 锚点 %+10.4f%%/%3d笔  %s'
              % (thr, s, e, ret, n, exp_pct, exp_tr, ok), flush=True)

print('\n--- 判据 ---', flush=True)
d6 = res[(-6.0, '2025-07-01')] - res[(-8.2, '2025-07-01')]
d23 = res[(-6.0, '2023-01-01')] - res[(-8.2, '2023-01-01')]
print('阈值生效? 2025-07 窗口 (-6.0) - (-8.2) = %+.4f pp  -> %s' % (d6, 'YES' if abs(d6) > 1e-6 else 'NO!!'))
print('阈值生效? 2023   窗口 (-6.0) - (-8.2) = %+.4f pp  -> %s' % (d23, 'YES' if abs(d23) > 1e-6 else 'NO!!'))
