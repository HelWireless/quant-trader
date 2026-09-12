# -*- coding: utf-8 -*-
"""对指定窗口跑原版(门槛8.0)，把交易按 score 分桶，量化"被9分门槛过滤掉"的批次盈亏。
这是判断 score9 在某市场是"挡灾"还是"误杀"的直接证据。
同时统计 R3 停手次数（路径/序列风险）。
"""
import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    'hbe', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_backtest_exp.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

code_bars, names, all_dates = hbe.load_data(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_csv_long'))

WINDOWS = [
    ('A 2014-12~2016-11 疯牛+股灾(gap-462)', '2014-12-01', '2016-11-30', -461.9),
    ('B 2019-05~2021-04 核心资产慢牛(-49)', '2019-05-01', '2021-04-30', -49.0),
    ('C 2018-10~2019-09 政策底反弹(-42)', '2018-10-01', '2019-09-30', -42.1),
    ('G 2012-08~2014-07 慢涨(-47.6)', '2012-08-01', '2014-07-31', -47.6),
    ('D 2022-02~2025-01 熊(+40.5)', '2022-02-01', '2025-01-31', 40.5),
    ('E 2016-02~2019-01 熊(+21.3)', '2016-02-01', '2019-01-31', 21.3),
    ('F 2014-06~2015-05 疯牛但原版亏(+62.6)', '2014-06-01', '2015-05-31', 62.6),
]

for tag, s, e, gap in WINDOWS:
    hbe.MAX_BUY_PER_DAY = 0
    hbe.LOSS_START_DAY = 15
    hbe.LOSS_HARD_START_DAY = 15
    hbe.MIN_SCORE = 8.0
    hbe.MAX_SLOTS = 10
    hbe.EXIT_MODE = 'AUTO'
    res = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
    closed = res['closed']
    ret = (res['final_capital'] - 500000.0) / 50000.0 / 10.0
    lo = [t for t in closed if 8.0 <= t['score'] < 9.0]
    hi = [t for t in closed if t['score'] >= 9.0]
    lo_cost = sum(t['cost'] for t in lo) or 1.0
    hi_cost = sum(t['cost'] for t in hi) or 1.0
    print('\n===== %s =====' % tag)
    print('  原版(门槛8) 总笔=%d 收益=%+.2f%% | R3停手=%d段' % (len(closed), ret, len(res['stops'])))
    print('  [8,9)被9分门槛挡掉的批次: %3d笔 净盈亏%+9.0f (占成本%+.2f%%) 胜率%3.0f%% 止损%d笔'
          % (len(lo), sum(t['pnl'] for t in lo), sum(t['pnl'] for t in lo) / lo_cost * 100,
             100 * sum(1 for t in lo if t['pnl'] > 0) / len(lo) if lo else 0,
             sum(1 for t in lo if '止损' in t['exit_reason'])))
    print('  [9,∞)保留批次        : %3d笔 净盈亏%+9.0f (占成本%+.2f%%) 胜率%3.0f%% 止损%d笔'
          % (len(hi), sum(t['pnl'] for t in hi), sum(t['pnl'] for t in hi) / hi_cost * 100,
             100 * sum(1 for t in hi if t['pnl'] > 0) / len(hi) if hi else 0,
             sum(1 for t in hi if '止损' in t['exit_reason'])))
    # 被挡批次若剔除后的近似收益（原版总成本 vs 去掉低分交易后的净额）
    tot_pnl = sum(t['pnl'] for t in closed)
    print('  → 总净盈亏 %+.0f，其中被挡批次贡献 %+.0f（占 %.0f%%）'
          % (tot_pnl, sum(t['pnl'] for t in lo),
             (sum(t['pnl'] for t in lo) / tot_pnl * 100) if tot_pnl else 0))
    print('  → 判定: %s' % ('误杀(挡掉的是赚钱交易)' if sum(t['pnl'] for t in lo) > 0 else '挡灾(挡掉的是亏钱交易)'))

print('\n完成')
