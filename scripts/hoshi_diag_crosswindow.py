# -*- coding: utf-8 -*-
"""闭环验证 score9 的跨窗口 trade-off：
用原版出场(硬止损15天)在 节点1/节点4/节点5 跑 MIN_SCORE=8.0，
把每笔按 score 分桶，看 score∈[8,9) 被 score9 挡掉的批次 在【亏损窗口/其他窗口】的盈亏。

预期：若 节点1/节点4(亏损窗口) 的 [8,9) 批次整体是【亏损】的 → 证明 score9 用"节点2少赚"换来了"节点1/4避损"。
"""
import importlib.util

spec = importlib.util.spec_from_file_location('hbe', 'scripts/hoshi_backtest_exp.py')
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

code_bars, names, all_dates = hbe.load_data('scripts/hoshi_csv_long')

def run(tag, start, end):
    hbe.MAX_BUY_PER_DAY = 0
    hbe.LOSS_START_DAY = 15
    hbe.LOSS_HARD_START_DAY = 15
    hbe.MIN_SCORE = 8.0
    hbe.MAX_SLOTS = 10
    hbe.EXIT_MODE = 'AUTO'
    res = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    closed = res['closed']
    ret = (res['final_capital'] - 500000.0) / 500000.0 * 100.0
    lo = [t for t in closed if 8.0 <= t['score'] < 9.0]
    hi = [t for t in closed if t['score'] >= 9.0]
    total_cost = sum(t['cost'] for t in closed)
    lo_cost = sum(t['cost'] for t in lo)
    print('\n===== %s %s-%s | 出场=原版15 | 门槛8.0 =====' % (tag, start[:4], end[:4]))
    print('总笔=%d 收益=%+.2f%%' % (len(closed), ret))
    print('  [8,9)被挡批次: %3d笔 净%+9.0f (均%+.2f%%) 胜率%3.0f%% | 止损%d笔净%+.0f' %
          (len(lo), sum(t['pnl'] for t in lo),
           sum(t['pnl'] for t in lo)/lo_cost*100 if lo_cost else 0,
           100*sum(1 for t in lo if t['pnl']>0)/len(lo) if lo else 0,
           sum(1 for t in lo if '止损' in t['exit_reason']),
           sum(t['pnl'] for t in lo if '止损' in t['exit_reason'])))
    print('  [9,∞)保留批次: %3d笔 净%+9.0f (均%+.2f%%)' %
          (len(hi), sum(t['pnl'] for t in hi),
           (sum(t['pnl'] for t in hi)/sum(t['cost'] for t in hi)*100 if hi else 0)))

run('节点1(亏损窗口)', '2016-01-01', '2021-12-31')
run('节点4(亏损窗口)', '2024-01-01', '2026-09-01')
run('节点3', '2022-01-01', '2025-12-31')
run('节点5', '2023-01-01', '2026-09-01')
print('\n完成')
