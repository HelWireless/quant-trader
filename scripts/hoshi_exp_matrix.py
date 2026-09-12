# -*- coding: utf-8 -*-
"""
Hoshi 统一改进方案 —— 5 节点批量实验驱动器
=========================================
目标：找一套【统一参数】跑 5 个用户窗口，尽量 5 节点都正 + 50万累加权益最高。
baseline = 原版(hoshi_backtest_exp.py: MAX_BUY_PER_DAY=0, LOSS_START_DAY=15,
          LOSS_HARD_START_DAY=15, MIN_SCORE=8, S3/S4 AUTO, R3+广度 ON)。
数据源 scripts/hoshi_csv_long(5262只白名单)。

用法: python scripts/hoshi_exp_matrix.py 2>&1 | tee scripts/hoshi_exp_matrix.log
"""
import importlib.util, time, sys

SPEC_PATH = 'scripts/hoshi_backtest_exp.py'
DATA_DIR = 'scripts/hoshi_csv_long'
INIT = 500000.0

spec = importlib.util.spec_from_file_location('hbe', SPEC_PATH)
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False

WINDOWS = [
    ('节点1 2016-21', '2016-01-01', '2021-12-31'),
    ('节点2 2012-15', '2012-01-01', '2015-12-31'),
    ('节点3 2022-25', '2022-01-01', '2025-12-31'),
    ('节点4 2024-26', '2024-01-01', '2026-09-01'),
    ('节点5 2023-26', '2023-01-01', '2026-09-01'),
]

# 方案矩阵: 每个方案 = {名字: 参数字典}
SCHEMES = {
    'baseline_原版': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15,
                          MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO'),
    'hard5_硬止损第5天': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5,
                          MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO'),
    'hard3_硬止损第3天': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=3,
                          MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO'),
    'score9_提高评分': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15,
                          MIN_SCORE=9.0, MAX_SLOTS=10, EXIT_MODE='AUTO'),
    'hard5_score9': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5,
                          MIN_SCORE=9.0, MAX_SLOTS=10, EXIT_MODE='AUTO'),
    'S4_立即武装': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15,
                          MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='S4'),
    'hard5_S4': dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5,
                          MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='S4'),
}

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbe.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d' % (time.time()-t0, len(code_bars), len(all_dates)), flush=True)

def run_one(cfg, start, end):
    hbe.TOTAL_CAPITAL = INIT
    for k, v in cfg.items():
        setattr(hbe, k, v)
    res = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    ret = (res['final_capital'] - INIT) / INIT * 100.0
    return ret, res['final_capital'], len(res['closed']), len(res['stops']), res['skipped']

def scheme_table(cfg):
    row = []
    for _, s, e in WINDOWS:
        r = run_one(cfg, s, e)
        row.append(r)
    return row

# 表头
print('\n方案统一参数跑 5 节点:', flush=True)
header = '%-20s' % '方案'
for label, _, _ in WINDOWS:
    header += ' %9s' % label.split(' ')[1]
header += ' %9s %10s' % ('累加权益', '全正?')
print(header, flush=True)
print('-' * len(header), flush=True)

# 先跑 baseline 校准
print('运行中...', flush=True)
results = {}
for name, cfg in SCHEMES.items():
    t1 = time.time()
    rows = scheme_table(cfg)
    # 每节点 ret% 及 final_capital
    sum_equity = sum(r[1] for r in rows)
    all_pos = all(r[0] > 0 for r in rows)
    results[name] = rows
    line = '%-20s' % name
    for r in rows:
        line += ' %+8.2f%%' % r[0]
    line += ' %9.0f %s' % (sum_equity, 'YES' if all_pos else 'no')
    print(line, flush=True)
    print('  (%.0fs) 笔数=%s  R3停手=%s' % (time.time()-t1,
          ','.join(str(r[2]) for r in rows), ','.join(str(r[3]) for r in rows)), flush=True)

print('\n=== 汇总: 累加权益排序 ===', flush=True)
for name in sorted(results, key=lambda n: -sum(r[1] for r in results[n])):
    rows = results[name]
    print('%-20s 累加权益 %10.0f | 各节点 %s | 全正:%s' %
          (name, sum(r[1] for r in rows),
           ','.join('%+.1f%%' % r[0] for r in rows),
           'YES' if all(r[0] > 0 for r in rows) else 'no'), flush=True)
print('\n全部完成.', flush=True)
