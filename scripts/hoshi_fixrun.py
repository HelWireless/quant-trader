# -*- coding: utf-8 -*-
"""统一回测跑批（引擎 = hoshi_backtest_exp5，强平 bug 已修复）。

用法: python hoshi_fixrun.py <group> <scheme>
  group = 1  第一组 30 窗（种子 20260907，窗口文件 hoshi_time_corr_windows.csv）
  group = 2  第二组 30 窗（种子 20260911，长度 1/2/4/7 年，hoshi_oos2_windows.csv）
  scheme = base | h5s9 | t5

支持断点续跑：已存在的 (start,end) 结果行会跳过。
输出: hoshi_fix<group>_<scheme>.csv
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

group = sys.argv[1]
sk = sys.argv[2]

if group == '1':
    win_path = os.path.join(HERE, 'hoshi_time_corr_windows.csv')
else:
    win_path = os.path.join(HERE, 'hoshi_oos2_windows.csv')

WINDOWS = []
with open(win_path, encoding='utf-8') as f:
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

for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                 ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                 SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                 MIN_SCORE=8.0, LOSS_HARD_START_DAY=15).items():
    setattr(hbe, k, v)
for k, v in SCHEMES[sk].items():
    setattr(hbe, k, v)

out_path = os.path.join(HERE, 'hoshi_fix%s_%s.csv' % (group, sk))
col = '%s_pct' % sk

# 断点续跑：读入已有结果
done = {}
if os.path.exists(out_path):
    with open(out_path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                done[(r['start'], r['end'])] = (r[col], r.get('trades', ''))
            except KeyError:
                pass

fout = open(out_path, 'w', newline='', encoding='utf-8')
wcsv = csv.writer(fout)
wcsv.writerow(['start', 'end', 'len_months', col, 'trades'])
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
          % (i, len(WINDOWS), s[:7], e[:7], m, sk.upper(), ret, len(r['closed'])), flush=True)

fout.close()
print('DONE group%s %s -> %s' % (group, sk, out_path), flush=True)
