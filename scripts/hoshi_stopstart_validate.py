# -*- coding: utf-8 -*-
"""
方向B 稳健性验证: 在多个代表性 regime 窗口上, 对比止损起始日 15(原版)/10/7。
确认"提前止损到第7~10天"改善收益是跨窗口稳健的, 而非 15.5 年单路径的过拟合。
"""
import importlib.util, time

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None
INIT = 500000.0

# (标签, start, end) 各 regime 窗口
WINDOWS = [
    ('2012~2015 大牛',   '2012-01-01', '2015-12-31'),
    ('2014~2018 牛转熊', '2014-01-01', '2018-12-31'),
    ('2020~2023 震荡',   '2020-01-01', '2023-12-31'),
    ('2022~2025 熊修复', '2022-01-01', '2025-12-31'),
    ('2023~2026 反弹',   '2023-01-01', '2026-09-01'),
]
DAYS = [15, 10, 7]

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d' % (time.time()-t0, len(code_bars), len(all_dates)), flush=True)
hbl.MAX_SLOTS = 10
hbl.MAX_BUY_PER_DAY = 0

# 先记录各窗口原版第15天，再对比
print('\n===== 多窗口: 止损起始日 15 vs 10 vs 7 收益率% =====', flush=True)
print('%-14s %10s %10s %10s %14s' % ('窗口', '第15天(原版)', '第10天', '第7天', '最差值差异'), flush=True)
rows = []
for label, s, e in WINDOWS:
    per = {}
    for day in DAYS:
        hbl.TOTAL_CAPITAL = INIT
        hbl.LOSS_START_DAY = day
        res = hbl.run_backtest(code_bars, names, all_dates, start=s, end=e)
        ret = (res['final_capital'] - INIT) / INIT * 100.0
        per[day] = ret
    best = max(per[10], per[7])
    worst_improve = min(per[10], per[7]) - per[15]
    rows.append((label, per[15], per[10], per[7]))
    print('%-14s %10.2f %10.2f %10.2f   (10/7较原版最低改善 %+.2fpp)'
          % (label, per[15], per[10], per[7], worst_improve), flush=True)

print('\n===== 汇总: 每窗口 10/7天 vs 原版15天 =====', flush=True)
n_better = sum(1 for r in rows if min(r[2], r[3]) > r[1])
n_worse = sum(1 for r in rows if min(r[2], r[3]) < r[1])
print('提前止损(取10/7中较劣者)优于原版的窗口: %d/%d' % (n_better, len(rows)))
print('提前止损(取10/7中较劣者)劣于原版的窗口: %d/%d' % (n_worse, len(rows)))
