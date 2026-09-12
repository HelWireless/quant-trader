# -*- coding: utf-8 -*-
"""
2026 真实 regime 窗口: 原版(第15天止损) vs 全程硬止损(第1天) 对比
用于决定实盘在近期窗口该用哪个。逐笔保留, 同时给止损起始日敏感度(15/7/3/1)。
窗口: 6-1至今 / 4-1至今 / 今年至今 / 近一年。
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
    ('6-1至今(2026)',   '2026-06-01', '2026-09-01'),
    ('4-1至今(2026)',   '2026-04-01', '2026-09-01'),
    ('今年(2026)',      '2026-01-01', '2026-09-01'),
    ('近一年',          '2025-09-01', '2026-09-01'),
]
DAYS = [15, 7, 3, 1]

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d' % (time.time()-t0, len(code_bars), len(all_dates)), flush=True)
hbl.MAX_SLOTS = 10
hbl.MAX_BUY_PER_DAY = 0

def run(start, end, day):
    hbl.TOTAL_CAPITAL = INIT; hbl.LOSS_START_DAY = day
    res = hbl.run_backtest(code_bars, names, all_dates, start=start, end=end)
    c = res['closed']
    rets = [t['return_pct'] for t in c]
    wins = sum(1 for t in c if t['pnl'] > 0)
    losses = [t['return_pct'] for t in c if t['pnl'] <= 0]
    nat = [t for t in c if t['exit_reason'] != '回测结束强平']
    return dict(ret=(res['final_capital']-INIT)/INIT*100.0, n=len(c),
                wr=(wins*100.0/len(c)) if c else None,
                worst=(min(rets) if rets else None),
                avg_loss=(st.mean(losses) if losses else None),
                nat_pnl=sum(t['pnl'] for t in nat),
                stops=len(res['stops']), skip=res['skipped'])

for label, s, e in WINDOWS:
    print('\n========== %s (%s ~ %s) ==========' % (label, s, e), flush=True)
    print('%-14s %10s %6s %8s %9s %9s %10s %6s' % ('止损起始日','收益率%','笔数','胜率%','最差单笔%','均亏损%','自然盈亏¥','R3停手'), flush=True)
    per = {}
    for day in DAYS:
        a = run(s, e, day)
        per[day] = a
        tag = '第%d天(原版)' % day if day == 15 else ('全程' if day == 1 else '第%d天' % day)
        print('%-14s %+10.2f %6d %8s %9s %9s %+10.0f %6d'
              % (tag, a['ret'], a['n'], ('%.1f'%a['wr']) if a['wr'] is not None else '-',
                 ('%.1f'%a['worst']) if a['worst'] is not None else '-',
                 ('%.1f'%a['avg_loss']) if a['avg_loss'] is not None else '-',
                 a['nat_pnl'], a['stops']), flush=True)
    print('  结论: 原版收益%+.2f vs 全程%+.2f | 全程胜出: %s | 全程最差单笔收敛: %.1f%%→%.1f%%'
          % (per[15]['ret'], per[1]['ret'], '是' if per[1]['ret'] > per[15]['ret'] else '否',
             per[15]['worst'] or 0, per[1]['worst'] or 0), flush=True)
