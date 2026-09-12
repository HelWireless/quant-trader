# -*- coding: utf-8 -*-
"""
近一年逐笔诊断(2025-09-01 ~ 2026-09-01): 定位 2026-07 团灭亏损来源
============================================
输出原版(第15天止损, 不限买入)该窗口每笔: 买入日/代码/价/卖出日/价/收益率/出场原因,
并对每笔计算"买入后到卖出前的最深浮亏%"。
重点: 找出 7月买入的持仓, 看"前14天无止损裸奔"使它们最深跌到哪, 再对比若第7/全程止损能切成多少。
"""
import importlib.util, time

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'
START, END = '2025-09-01', '2026-09-01'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None
INIT = 500000.0

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d' % (time.time()-t0, len(code_bars), len(all_dates)), flush=True)
idx = {code: {b.date: i for i, b in enumerate(bars)} for code, bars in code_bars.items()}

def deepest_dd(code, buy_date, sell_date):
    """买入日之后(含次日)到卖出日之间, 相对买入价的最深收盘/最低浮亏%"""
    bars = code_bars[code]
    i = idx[code].get(buy_date)
    if i is None: return None, None
    entry = bars[i].open
    j = idx[code].get(sell_date) if sell_date else None
    end_i = (j if j is not None else len(bars)) + 1
    seg = bars[i+1:min(end_i, len(bars))]
    if not seg: return None, None
    min_low = min(b.low for b in seg)
    max_hi = max(b.high for b in seg)
    return (min_low - entry) / entry * 100.0, (max_hi - entry) / entry * 100.0

def run(start, end, day):
    hbl.TOTAL_CAPITAL = INIT; hbl.MAX_SLOTS = 10; hbl.MAX_BUY_PER_DAY = 0; hbl.LOSS_START_DAY = day
    res = hbl.run_backtest(code_bars, names, all_dates, start=start, end=end)
    ret = (res['final_capital'] - INIT) / INIT * 100.0
    return res, ret

res, ret = run(START, END, 15)
closed = sorted(res['closed'], key=lambda t: t['buy_date'])
print('\n===== 原版(第15天止损) %s~%s  总收益 %+.2f%% | %d笔 =====' % (START, END, ret, len(closed)), flush=True)
print('%-9s %-6s %8s %-10s %8s %-10s %9s %9s %-22s' % ('买入日','代码','买价','卖出日','卖价','收益率%','最深浮亏%','最高浮盈%','出场原因'), flush=True)
jul_trades = []
for t in closed:
    dd, hi = deepest_dd(t['code'], t['buy_date'], t['sell_date'])
    flag = ' ★7月' if str(t['buy_date'])[:7] == '2026-07' else ''
    print('%-9s %-6s %8.2f %-10s %8.2f %+8.2f %9s %9s %-22s%s'
          % (t['buy_date'], t['code'], t['buy_price'], t['sell_date'], t['sell_price'],
             t['return_pct'], ('%.1f' % dd) if dd is not None else '-',
             ('%.1f' % hi) if hi is not None else '-', t['exit_reason'], flag), flush=True)
    if str(t['buy_date'])[:7] == '2026-07':
        jul_trades.append(t)

print('\n===== 2026-07 买入的持仓（团灭源） =====', flush=True)
print('7月共买入 %d 笔:' % len(jul_trades), flush=True)
for t in jul_trades:
    dd, hi = deepest_dd(t['code'], t['buy_date'], t['sell_date'])
    print('  %s %s  买%.2f  卖%s@%.2f  %+.2f%%  最深浮亏~%s%%  出场:%s'
          % (t['buy_date'], t['code'], t['buy_price'], t['sell_date'], t['sell_price'],
             t['return_pct'], ('%.1f' % dd) if dd is not None else '?', t['exit_reason']), flush=True)

# 对比: 若第7天止损/全程止损, 同一窗口结果
print('\n===== 同窗口不同止损起始日对比 =====', flush=True)
for day in [15, 7, 1]:
    r, rr = run(START, END, day)
    worst = min((t['return_pct'] for t in r['closed']), default=None)
    wins = sum(1 for t in r['closed'] if t['pnl'] > 0)
    n = len(r['closed'])
    print('止损第%d天起: 总收益%+7.2f%%  笔数%d  胜率%s  最差单笔%s'
          % (day, rr, n, ('%.1f%%'%(wins*100.0/n)) if n else '-',
             ('%.1f%%'%worst) if worst is not None else '-'), flush=True)
