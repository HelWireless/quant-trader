# -*- coding: utf-8 -*-
"""验证集 #2：第二组独立随机窗口（种子 20260911，长度 1/2/4/7 年）。

用法: python hoshi_oos2.py <scheme>
  base  原版   评分8 + 止损15 + 开R3 + 广度20
  h5s9  h5s9   评分9 + 止损5  + 开R3 + 广度20
  t5    T5     分档仓位(9:1/8.5:.7/8:.45) + 止损5 + 关R3 + 广度30
"""
import csv
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0
hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

WINDOWS = []
with open(os.path.join(HERE, 'hoshi_oos2_windows.csv'), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        WINDOWS.append((r['start'], r['end'], int(r['len_months'])))

TIERS_A = [(9.0, 1.00), (8.5, 0.70), (8.0, 0.45)]

SCHEMES = {
    'base': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, SCORE_TIER_SIZING=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0),
    'h5s9': dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0),
    't5': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=True,
               SCORE_TIERS=TIERS_A, USE_R3_GATE=False, BREADTH_THRESH=30.0),
}

sk = sys.argv[1]
for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                 ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                 SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                 MIN_SCORE=8.0, LOSS_HARD_START_DAY=15).items():
    setattr(hbe, k, v)
for k, v in SCHEMES[sk].items():
    setattr(hbe, k, v)

out_path = os.path.join(HERE, 'hoshi_fix2_%s.csv' % sk)
fout = open(out_path, 'w', newline='', encoding='utf-8')
wcsv = csv.writer(fout)
wcsv.writerow(['start', 'end', 'len_months', '%s_pct' % sk, 'trades'])

print('方案 %s 开始，共 %d 个窗口' % (sk, len(WINDOWS)), flush=True)
for i, (s, e, m) in enumerate(WINDOWS, 1):
    r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
    ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
    wcsv.writerow([s, e, m, '%.4f' % ret, len(r['closed'])])
    fout.flush()
    print('[%2d/%d] %s~%s (%2d月) %s %+8.2f%% | 笔数 %d'
          % (i, len(WINDOWS), s[:7], e[:7], m, sk.upper(), ret, len(r['closed'])), flush=True)

fout.close()
print('DONE %s -> %s' % (sk, out_path), flush=True)
