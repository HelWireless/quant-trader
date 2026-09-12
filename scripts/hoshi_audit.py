# -*- coding: utf-8 -*-
"""核查 hard5_score9(328万,全正候选) 各节点交易合理性, 特别防'峰值回落止盈虚高'失真。
方法: 看单日涨幅>20%(创业板/科创板20cm)或>10%(主板)的卖出是否大量由'峰值回落止盈'贡献,
判断是否存在未建模涨跌停导致的高估。同时导出 baseline 对照。
"""
import importlib.util
from collections import Counter

spec = importlib.util.spec_from_file_location('hbe', 'scripts/hoshi_backtest_exp.py')
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
code_bars, names, all_dates = hbe.load_data('scripts/hoshi_csv_long')
INIT = 500000.0
# 用于判断板块(主板10%/创科20%)
def board(code):
    return 'CREATIVE' if str(code).startswith(('300','301','688','689')) else 'MAIN'

def run_and_audit(cfg, start, end, tag):
    hbe.TOTAL_CAPITAL = INIT
    for k, v in cfg.items():
        setattr(hbe, k, v)
    res = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    closed = res['closed']
    ret = (res['final_capital'] - INIT) / INIT * 100.0
    # 分类每笔: 按买入-卖出日 与 各自价格算单日理论可成交上限
    # 峰值回落止盈假设可在当日high附近卖。统计止盈单里 ret>单日涨停上限的笔(buy open->sell price)
    # 简化: 看 单日(买入日到卖出日仅1个交易区间持有) 且 ret 超板块单日上限(需更细), 这里做粗略红牌检测:
    # 若某笔 buy->sell 跨 N 个交易日, ret 超过 N*板块单日上限 即高度可疑(涨跌停未建模导致可买在低点卖在连续涨停高点)
    from datetime import date
    MAXRET = {'MAIN': 1.10, 'CREATIVE': 1.20}  # 单日复利上限(粗略)
    sus = []
    for t in closed:
        if t['return_pct'] <= 0:
            continue
        # 估算最多连续涨幅: 若持有期间含涨停连板,ret可超; 用天数粗略
        n = max(t['hold_days'], 1)
        # 理论上若每天涨停买入时点完美(n个涨停=复利), 上限为 (1.1^n或1.2^n)
        cap = MAXRET[board(t['code'])] ** n
        if t['return_pct'] / 100.0 + 1 > cap * 1.0:  # 实际很难每天吃满涨停
            sus.append((t['code'], t['return_pct'], t['hold_days'], t['exit_reason'], board(t['code']), cap))
    print('\n===== %s %s-%s =====' % (tag, start, end))
    print('总笔=%d 收益=%+.2f%%' % (len(closed), ret))
    print('止盈峰值回落笔数:', sum(1 for t in closed if '止盈(峰值回落' in t['exit_reason']))
    print('疑似超单日涨停上限的可疑盈利单: %d笔' % len(sus))
    for s in sus[:8]:
        print('  %s %+.1f%% hold%d天 %s 板块%s 理论上限%.1f倍' % (s[0], s[1], s[2], s[3], s[4], s[5]))
    # 盈利单的买入板块与持有天数分布
    wins = [t for t in closed if t['pnl'] > 0]
    main_w = sum(1 for t in wins if board(t['code']) == 'MAIN')
    print('盈利单 %d笔 | 主板%d | 创科%d | 盈利单均hold %.1f天' %
          (len(wins), main_w, len(wins)-main_w, sum(t['hold_days'] for t in wins)/len(wins) if wins else 0))

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15, MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO')
H5S9 = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5, MIN_SCORE=9.0, MAX_SLOTS=10, EXIT_MODE='AUTO')
run_and_audit(BASE, '2024-01-01', '2026-09-01', 'baseline 节点4')
run_and_audit(H5S9, '2024-01-01', '2026-09-01', 'hard5_score9 节点4')
run_and_audit(H5S9, '2016-01-01', '2021-12-31', 'hard5_score9 节点1')
print('\n完成')
