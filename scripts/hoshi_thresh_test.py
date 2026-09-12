# -*- coding: utf-8 -*-
"""硬止损**阈值**对照：LOSS_HARD_PCT = -6.0% vs -8.2%

背景：实盘 live engine 用 LOSS_HARD_PCT=-6.0%，而此前 60 窗验证用的是引擎默认
-8.2%。两者**从未联合验证**（此前 60 窗只验证了「启用日 = 5」，即 LOSS_HARD_START_DAY，
**不是阈值**）。本脚本把阈值单独定死。

基线 = 方案 B：评分9 + LOSS_START_DAY=15 + LOSS_HARD_START_DAY=5 + R3关 + 广度20

用法: python hoshi_thresh_test.py <group> <tag>
  group = 1 | 2
  tag   = t6 (-6.0%) | t8 (-8.2%，= 方案 B 原样)

输出: hoshi_thr<group>_<tag>.csv

★ 自检锚点: t8 必须与 hoshi_abl<group>_b.csv 逐位相同
  （同为「方案 B + 默认 -8.2%」，两条独立路径得到同一结果才算框架正确）。
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

group = sys.argv[1] if len(sys.argv) > 1 else '1'
tag = sys.argv[2].lower() if len(sys.argv) > 2 else 't8'
win_file = ('hoshi_time_corr_windows.csv' if group == '1' else 'hoshi_oos2_windows.csv')

WINDOWS = []
with open(os.path.join(HERE, win_file), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        WINDOWS.append((r['start'], r['end'], int(r['len_months'])))

# ---- 方案 B 基线（与 hoshi_best_B.SCHEME_B 一致）----
SCHEME_B = dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
                USE_R3_GATE=False, BREADTH_THRESH=20.0)

THRESH = {
    't6': -6.0,   # 实盘 live engine 用的
    't8': -8.2,   # 引擎默认 / 此前 60 窗验证所用
}

# 先铺全局默认，再叠方案 B，最后叠阈值
for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                 ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                 SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                 USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                 MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, LOSS_HARD_PCT=-8.2).items():
    setattr(hbe, k, v)
for k, v in SCHEME_B.items():
    setattr(hbe, k, v)
hbe.LOSS_HARD_PCT = THRESH[tag]

# ---- 生效性断言（防止 setattr 被静默忽略）----
assert hbe.LOSS_HARD_PCT == THRESH[tag], 'LOSS_HARD_PCT 未生效'
assert hbe.MIN_SCORE == 9.0 and hbe.LOSS_HARD_START_DAY == 5, '方案 B 基线未生效'
assert hbe.USE_R3_GATE is False, 'R3 未关闭'

out_path = os.path.join(HERE, 'hoshi_thr%s_%s.csv' % (group, tag))

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
    print('[%2d/%d] %s~%s (%2d月) %s=%+.1f%% %+8.2f%% | 笔数 %d'
          % (i, len(WINDOWS), s[:7], e[:7], m, tag.upper(), THRESH[tag], ret,
             len(r['closed'])), flush=True)

fout.close()
print('DONE thr group%s %s (LOSS_HARD_PCT=%+.1f%%) -> %s' % (group, tag, THRESH[tag], out_path),
      flush=True)
