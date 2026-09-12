# -*- coding: utf-8 -*-
"""核查 hard5_S4 / S4 方案的异常高收益是否真实（防数据/引擎 bug）。"""
import importlib.util
from collections import Counter

spec = importlib.util.spec_from_file_location('hbe', 'scripts/hoshi_backtest_exp.py')
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
code_bars, names, all_dates = hbe.load_data('scripts/hoshi_csv_long')
INIT = 500000.0

def run_one(cfg, start, end, tag):
    hbe.TOTAL_CAPITAL = INIT
    for k, v in cfg.items():
        setattr(hbe, k, v)
    res = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    closed = res['closed']
    ret = (res['final_capital'] - INIT) / INIT * 100.0
    same_day = sum(1 for t in closed if t['buy_date'] == t['sell_date'])
    buy_sell_le1 = sum(1 for t in closed if t['hold_days'] <= 1)
    best = sorted(closed, key=lambda t: -t['return_pct'])[:3]
    worst = sorted(closed, key=lambda t: t['return_pct'])[:3]
    reasons = dict(Counter(t['exit_reason'] for t in closed))
    # 检查卖出价是否超出当日合理区间(hard5卖出价应贴近某日价格; 粗略看有无极端值)
    big_ret = [t for t in closed if t['return_pct'] > 50]
    print('\n===== %s %s =====' % (tag, '->'.join([start, end])))
    print('总笔=%d 收益=%+.2f%% 最终权益=%.0f' % (len(closed), ret, res['final_capital']))
    print('买入日==卖出日:%d (T1违规应0) | hold<=1天:%d' % (same_day, buy_sell_le1))
    print('单笔>+50%%: %d笔' % len(big_ret))
    print('Top3盈利:')
    for t in best:
        print('  %s 买%s@%.2f 卖%s@%.2f %+.1f%% hold%d %s' % (t['code'], t['buy_date'], t['buy_price'], t['sell_date'], t['sell_price'], t['return_pct'], t['hold_days'], t['exit_reason']))
    print('Top3亏损:')
    for t in worst:
        print('  %s 买%s@%.2f 卖%s@%.2f %+.1f%% hold%d %s' % (t['code'], t['buy_date'], t['buy_price'], t['sell_date'], t['sell_price'], t['return_pct'], t['hold_days'], t['exit_reason']))
    print('出场原因:', reasons)
    # 复权/价格合理性: 检查卖出价是否=某日开盘或按百分比算
    return ret

# 核查最可疑的: S4在节点4(2024-26,+26.7%) 和 节点5(+249%) 以及 hard5_S4 节点4
S4 = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15, MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='S4')
H5S4 = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5, MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='S4')
run_one(H5S4, '2024-01-01', '2026-09-01', 'hard5_S4 节点4(近两年)')
print('\n完成')
