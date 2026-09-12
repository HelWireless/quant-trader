# -*- coding: utf-8 -*-
"""
用户指定 5 窗口 × 原版策略（权威口径）回测
原版 = 不限买入(MAX_BUY_PER_DAY=0) + 第15天止损(LOSS_START_DAY=15)，regime 关闭。
数据源 scripts/hoshi_csv_long（2009-06 至今 5262 只白名单）。

窗口：
  节点1: 2016-2021 (5年, 2018熊+2019-20反弹+2021牛顶)
  节点2: 2012-2015 (3年, 含2014-15大牛)
  节点3: 2022-2025 (3年, 熊+震荡)
  节点4: 2024-2026 (2年, 近两年, 截到2026-09)
  节点5: 2023-2026 (3年, 2023-2026)

用法：python scripts/hoshi_user_windows.py > scripts/hoshi_user_windows.log 2>&1
"""
import importlib.util, time, statistics as st

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None
INIT = 500000.0

WINDOWS = [
    ('节点1 2016-2021', '2016-01-01', '2021-12-31'),
    ('节点2 2012-2015', '2012-01-01', '2015-12-31'),
    ('节点3 2022-2025', '2022-01-01', '2025-12-31'),
    ('节点4 2024-2026', '2024-01-01', '2026-09-01'),
    ('节点5 2023-2026', '2023-01-01', '2026-09-01'),
]

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d 区间 %s~%s'
      % (time.time()-t0, len(code_bars), len(all_dates), all_dates[0], all_dates[-1]), flush=True)

# 原版口径
hbl.MAX_SLOTS = 10
hbl.MAX_BUY_PER_DAY = 0        # 不限买入(原版)
hbl.LOSS_START_DAY = 15        # 第15天止损(原版)
hbl.USE_REGIME_LOSS = False    # 关闭 regime 自适应


def run(start, end):
    hbl.TOTAL_CAPITAL = INIT
    res = hbl.run_backtest(code_bars, names, all_dates, start=start, end=end)
    c = res['closed']
    if not c:
        return dict(ret=None, n=0, wr=None, worst=None, nat_pnl=0.0, stops=len(res['stops']),
                    skip=res['skipped'], total_pnl=0.0)
    rets = [t['return_pct'] for t in c]
    wins = sum(1 for t in c if t['pnl'] > 0)
    nat = [t for t in c if t['exit_reason'] != '回测结束强平']
    held = [t for t in c if t['exit_reason'] == '回测结束强平']
    return dict(ret=(res['final_capital']-INIT)/INIT*100.0, n=len(c),
                wr=wins*100.0/len(c), worst=min(rets),
                nat_pnl=sum(t['pnl'] for t in nat),
                held_pnl=sum(t['pnl'] for t in held),
                held_n=len(held),
                stops=len(res['stops']), skip=res['skipped'],
                total_pnl=sum(t['pnl'] for t in c))


print('\n%-24s %10s %6s %8s %9s %10s %10s %6s %6s' %
      ('窗口', '收益%', '笔数', '胜率%', '最差单笔%', '自然盈亏¥', '末仓盈亏¥', '末仓数', 'R3停手'), flush=True)
for label, s, e in WINDOWS:
    a = run(s, e)
    if a['ret'] is None:
        print('%-24s: 无成交' % label, flush=True)
        continue
    print('%-24s %+9.2f %6d %7.1f %+9.1f %+10.0f %+10.0f %6d %6d'
          % (label, a['ret'], a['n'], a['wr'], a['worst'],
             a['nat_pnl'], a['held_pnl'], a['held_n'], a['stops']), flush=True)

print('\n全部完成.', flush=True)
