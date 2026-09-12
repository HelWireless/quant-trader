# -*- coding: utf-8 -*-
"""
hoshi 完整周期长跑对比 (2011-01-01 ~ 2026-09-01, ~15.5年)
一次性加载 csv_long(5262只, 2009-06至今), 对每档"每日买入上限"跑全周期,
输出最终权益/收益率/笔数/胜率/R3停手。用于把多窗口结论收敛到一个完整牛熊周期。
"""
import importlib.util, time

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'
START, END = '2011-01-01', '2026-09-01'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None

INIT = 500000.0

def _analyze(res):
    closed = res['closed']
    n = len(closed)
    wins = sum(1 for t in closed if t['pnl'] > 0)
    nat = [t for t in closed if t['exit_reason'] != '回测结束强平']
    return (res['final_capital'],
            (res['final_capital'] - INIT) / INIT * 100.0,
            n, (wins * 100.0 / n) if n else None,
            sum(t['pnl'] for t in nat), len(nat), len(res['stops']), res['skipped'])

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d 区间%s~%s'
      % (time.time()-t0, len(code_bars), len(all_dates), all_dates[0], all_dates[-1]), flush=True)

hbl.MAX_SLOTS = 10
results = []
for cap in [0, 5, 8, 3]:
    hbl.TOTAL_CAPITAL = INIT
    hbl.MAX_BUY_PER_DAY = cap
    t1 = time.time()
    res = hbl.run_backtest(code_bars, names, all_dates, start=START, end=END)
    final, ret, n, wr, nat_pnl, n_nat, stops, skip = _analyze(res)
    tag = '原版(不限)' if cap == 0 else '限买%d只' % cap
    print('[%s] 终值¥%.0f  收益率%+7.2f%%  笔数%d(自然%d)  胜率%s  自然盈亏¥%+.0f  R3停手%d  skip%d  用时%.0fs'
          % (tag, final, ret, n, n_nat, ('%.1f%%' % wr) if wr is not None else 'NA',
             nat_pnl, stops, skip, time.time()-t1), flush=True)
    results.append((cap, tag, final, ret, n, wr, nat_pnl, stops))

print('\n===== 完整周期 %s ~ %s 对比 =====' % (START, END), flush=True)
print('%-12s %12s %10s %6s %8s %12s %8s' % ('买入上限', '终值¥', '收益率%', '笔数', '胜率%', '自然盈亏¥', 'R3停手'), flush=True)
for cap, tag, final, ret, n, wr, nat_pnl, stops in results:
    print('%-12s %12.0f %+10.2f %6d %8s %12.0f %8d'
          % (tag, final, ret, n, ('%.1f' % wr) if wr is not None else 'NA', nat_pnl, stops), flush=True)
