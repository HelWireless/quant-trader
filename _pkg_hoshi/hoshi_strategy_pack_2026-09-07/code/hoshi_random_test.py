# -*- coding: utf-8 -*-
"""二次稳健性测试：对可信策略 hard5_score9 做 out-of-sample 随机窗口检验。

方法（用户指定）：
- 随机挑选 2010 年后 5 个节点（按月粒度），每节点随机 1~5 年，时间可重叠（种子 20260903 固定，可复现）。
- 对比方案：baseline_原版(LOSS_HARD_START_DAY=15, MIN_SCORE=8) vs hard5_score9(LOSS_HARD_START_DAY=5, MIN_SCORE=9)。
- 判定"是否反转"：hard5_score9 在某随机窗口是否 ①由正转负 ②跑输 baseline。

窗口清单（_gen_random_windows.py, seed=20260903）:
W1 2019-12 ~ 2022-04 (29月)
W2 2013-04 ~ 2017-08 (53月)
W3 2014-12 ~ 2018-05 (42月)
W4 2017-05 ~ 2019-07 (27月)
W5 2019-06 ~ 2022-02 (33月)
"""
import importlib.util

spec = importlib.util.spec_from_file_location('hbe', 'scripts/hoshi_backtest_exp.py')
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

code_bars, names, all_dates = hbe.load_data('scripts/hoshi_csv_long')
INIT = 500000.0

WINDOWS = [
    ('W1', '2019-12-01', '2022-04-30'),
    ('W2', '2013-04-01', '2017-08-31'),
    ('W3', '2014-12-01', '2018-05-31'),
    ('W4', '2017-05-01', '2019-07-31'),
    ('W5', '2019-06-01', '2022-02-28'),
]

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15,
            MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO')
H5S9 = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5,
            MIN_SCORE=9.0, MAX_SLOTS=10, EXIT_MODE='AUTO')

def run(cfg, start, end):
    hbe.TOTAL_CAPITAL = INIT
    for k, v in cfg.items():
        setattr(hbe, k, v)
    res = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    closed = res['closed']
    ret = (res['final_capital'] - INIT) / INIT * 100.0
    wins = sum(1 for t in closed if t['pnl'] > 0)
    return ret, len(closed), wins

print('\n===== 二次稳健性测试: 5个随机窗口 out-of-sample =====')
print('%-5s %-20s %-10s %10s %10s %10s %10s' %
      ('窗口', '区间', 'base%', 'h5s9%', 'base笔', 'h5s9笔', 'h5s9跑赢?'))
print('-' * 90)
all_base_ret = 0.0
all_h5s9_ret = 0.0
all_base_eq = 0.0
all_h5s9_eq = 0.0
neg_h5s9 = 0
outperf = 0
for tag, s, e in WINDOWS:
    rb, nb, wb = run(BASE, s, e)
    rh, nh, wh = run(H5S9, s, e)
    all_base_ret += rb
    all_h5s9_ret += rh
    all_base_eq += INIT * (1 + rb / 100.0)
    all_h5s9_eq += INIT * (1 + rh / 100.0)
    if rh < 0:
        neg_h5s9 += 1
    win_flag = 'YES' if rh > rb else 'no'
    if rh > rb:
        outperf += 1
    print('%-5s %-20s %10.2f %10.2f %10d %10d %10s' %
          (tag, '%s~%s' % (s[:7], e[:7]), rb, rh, nb, nh, win_flag))

print('-' * 90)
print('5窗口 hard5_score9 收益加总: %+.2f%% (baseline %+.2f%%)' % (all_h5s9_ret, all_base_ret))
print('5窗口 hard5_score9 累加权益: %.0f (baseline %.0f)' % (all_h5s9_eq, all_base_eq))
print('hard5_score9 跑赢 baseline 窗口数: %d/5 | 由正转负(反转)窗口数: %d/5' % (outperf, neg_h5s9))
print('\n完成')
