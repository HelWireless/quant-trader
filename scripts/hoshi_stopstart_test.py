# -*- coding: utf-8 -*-
"""
方向B: 止损起始日(loss_start_day)敏感性 —— 在最终版基础上做"单一参数诊断"
================================================================
最终版(唯一版本)出场:S3止盈第14/15天才武装, 止损原本"第15天才监控(前14天裸奔)"。
用户痛点: 7月团灭的深套单(可到-56%), 正因前14天无止损裸奔。

本实验把"从第几天开始监控止损"参数化, 在 15.5 年完整周期(2011~2026)上对比:
  loss_start_day = 15(原版) / 10 / 7 / 3 / 1(全程硬止损兜底)
看全程止损能否压掉尾部巨亏、同时保住收益。止盈节奏(S3/S4自适应)保持不变。
"""
import importlib.util, time, statistics as st

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'
START, END = '2011-01-01', '2026-09-01'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None
INIT = 500000.0

def _analyze(res):
    c = res['closed']
    n = len(c)
    wins = [t for t in c if t['pnl'] > 0]
    losses = [t for t in c if t['pnl'] <= 0]
    nat = [t for t in c if t['exit_reason'] != '回测结束强平']
    rets = [t['return_pct'] for t in c]
    return dict(
        final=res['final_capital'],
        ret=(res['final_capital'] - INIT) / INIT * 100.0,
        n=n, n_nat=len(nat),
        winrate=(len(wins) * 100.0 / n) if n else None,
        worst=(min(rets) if rets else None),
        best=(max(rets) if rets else None),
        avg_loss=(st.mean([t['return_pct'] for t in losses]) if losses else None),
        avg_win=(st.mean([t['return_pct'] for t in wins]) if wins else None),
        pnl=sum(t['pnl'] for t in nat),
        stops=len(res['stops']), skip=res['skipped'],
    )

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d'
      % (time.time()-t0, len(code_bars), len(all_dates)), flush=True)

hbl.MAX_SLOTS = 10
hbl.MAX_BUY_PER_DAY = 0   # 原版不限买入(上一轮已证明原版买入上限最优)
results = []
for day in [15, 10, 7, 3, 1]:
    hbl.TOTAL_CAPITAL = INIT
    hbl.LOSS_START_DAY = day
    t1 = time.time()
    res = hbl.run_backtest(code_bars, names, all_dates, start=START, end=END)
    a = _analyze(res)
    tag = '原版(第%d天)' % day
    print('[%s] 终值¥%.0f  收益率%+7.2f%%  笔数%d  胜率%s  最差单笔%s  平均亏损%s  自然盈亏¥%+.0f  用时%.0fs'
          % (tag, a['final'], a['ret'], a['n'],
             ('%.1f%%' % a['winrate']) if a['winrate'] is not None else 'NA',
             ('%.1f%%' % a['worst']) if a['worst'] is not None else 'NA',
             ('%.1f%%' % a['avg_loss']) if a['avg_loss'] is not None else 'NA',
             a['pnl'], time.time()-t1), flush=True)
    results.append((day, a))

print('\n===== 止损起始日敏感性 (2011~2026, 15.5年, 原版不限买入) =====', flush=True)
print('%-14s %12s %8s %6s %8s %9s %9s %9s %8s' % ('止损起始日', '终值¥', '收益率%', '笔数', '胜率%', '最差单笔%', '均亏损%', '均盈利%', 'R3停手'), flush=True)
for day, a in results:
    print('%-14s %12.0f %+8.2f %6d %8s %9s %9s %9s %8d'
          % ('第%d天起' % day, a['final'], a['ret'], a['n'],
             ('%.1f' % a['winrate']) if a['winrate'] is not None else '-',
             ('%.1f' % a['worst']) if a['worst'] is not None else '-',
             ('%.1f' % a['avg_loss']) if a['avg_loss'] is not None else '-',
             ('%.1f' % a['avg_win']) if a['avg_win'] is not None else '-',
             a['stops']), flush=True)
