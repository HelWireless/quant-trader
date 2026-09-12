# -*- coding: utf-8 -*-
"""T5 加一法消融：以 h5s9 为基准 V0，逐个加入 T5 的三处改动。

V0 = h5s9            : 评分9 + 止损5 + R3开 + 广度20
A  = V0 + 分档仓位    : 评分8 + 分档(9:1/8.5:.7/8:.45) + 止损5 + R3开 + 广度20
B  = V0 + 关R3       : 评分9 + 止损5 + R3关 + 广度20
C  = V0 + 广度30     : 评分9 + 止损5 + R3开 + 广度30
T5 = 三者全开        : 评分8 + 分档 + 止损5 + R3关 + 广度30

用法: python hoshi_abl.py <v0|a|b|c> [group]   group 默认 1
输出: hoshi_abl<group>_<key>.csv
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

key = sys.argv[1].lower()
group = sys.argv[2] if len(sys.argv) > 2 else '1'
win_file = ('hoshi_time_corr_windows.csv' if group == '1' else 'hoshi_oos2_windows.csv')

WINDOWS = []
with open(os.path.join(HERE, win_file), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        WINDOWS.append((r['start'], r['end'], int(r['len_months'])))

TIERS_A = [(9.0, 1.00), (8.5, 0.70), (8.0, 0.45)]

VAR = {
    'v0': dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
               USE_R3_GATE=True, BREADTH_THRESH=20.0),
    'a': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=True,
              SCORE_TIERS=TIERS_A, USE_R3_GATE=True, BREADTH_THRESH=20.0),
    'b': dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
              USE_R3_GATE=False, BREADTH_THRESH=20.0),
    'c': dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
              USE_R3_GATE=True, BREADTH_THRESH=30.0),
}

for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                 ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                 SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                 MIN_SCORE=8.0, LOSS_HARD_START_DAY=15).items():
    setattr(hbe, k, v)
for k, v in VAR[key].items():
    setattr(hbe, k, v)

out_path = os.path.join(HERE, 'hoshi_abl%s_%s.csv' % (group, key))
done = {}
if os.path.exists(out_path):
    with open(out_path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            done[(r['start'], r['end'])] = (r['pct'], r.get('trades', ''))

fout = open(out_path, 'w', newline='', encoding='utf-8')
wcsv = csv.writer(fout)
wcsv.writerow(['start', 'end', 'len_months', 'pct', 'trades'])
for i, (s, e, m) in enumerate(WINDOWS, 1):
    if (s, e) in done:
        wcsv.writerow([s, e, m, done[(s, e)][0], done[(s, e)][1]])
        continue
    fout.flush()
    r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
    ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
    wcsv.writerow([s, e, m, '%.4f' % ret, len(r['closed'])])
    fout.flush()
    print('[%2d/%d] %s~%s (%2d月) %s %+8.2f%% | 笔数 %d'
          % (i, len(WINDOWS), s[:7], e[:7], m, key.upper(), ret, len(r['closed'])), flush=True)

fout.close()
print('DONE abl group%s %s -> %s' % (group, key, out_path), flush=True)
