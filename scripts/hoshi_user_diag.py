# -*- coding: utf-8 -*-
"""
用户指定窗口的逐笔诊断：聚焦 节点1(2016-21,亏损) 与 节点5(2023-26,+51%大赚)。
对每个窗口：导出完整 trades CSV，并按"买入年/出场原因"分解盈亏，看钱从哪来/亏在哪。
用法：python scripts/hoshi_user_diag.py > scripts/hoshi_user_diag.log 2>&1
"""
import importlib.util, time, csv, os
import collections

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'
OUT_DIR = 'scripts/hoshi_user_diag_out'
os.makedirs(OUT_DIR, exist_ok=True)

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None
INIT = 500000.0

WINDOWS = [
    ('节点1_2016-2021', '2016-01-01', '2021-12-31'),
    ('节点2_2012-2015', '2012-01-01', '2015-12-31'),
    ('节点3_2022-2025', '2022-01-01', '2025-12-31'),
    ('节点4_2024-2026', '2024-01-01', '2026-09-01'),
    ('节点5_2023-2026', '2023-01-01', '2026-09-01'),
]

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load %.1fs' % (time.time()-t0), flush=True)
hbl.MAX_SLOTS = 10
hbl.MAX_BUY_PER_DAY = 0
hbl.LOSS_START_DAY = 15
hbl.USE_REGIME_LOSS = False


def run(start, end):
    hbl.TOTAL_CAPITAL = INIT
    return hbl.run_backtest(code_bars, names, all_dates, start=start, end=end)


for tag, s, e in WINDOWS:
    res = run(s, e)
    c = res['closed']
    print('\n========== %s (%s ~ %s) ==========' % (tag, s, e), flush=True)
    print('总收益 %+.2f%% | 笔 %d | R3停手 %d | 跳过信号 %d'
          % ((res['final_capital']-INIT)/INIT*100, len(c), len(res['stops']), res['skipped']), flush=True)

    # 导出 trades CSV
    real = [t for t in c if t['exit_reason'] != '回测结束强平']
    path = os.path.join(OUT_DIR, tag + '_trades.csv')
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['代码','名称','评分','模式','买入日','卖出日','买入价','卖出价','股数',
                    '成本','卖出所得','费用','净盈亏','收益率%','持有天数','出场原因'])
        for t in sorted(c, key=lambda x: x['buy_date']):
            w.writerow([t['code'], t['name'], '%.1f'%t['score'], t['mode'],
                        t['buy_date'], t['sell_date'], '%.2f'%t['buy_price'], '%.2f'%t['sell_price'],
                        t['shares'], '%.2f'%t['cost'], '%.2f'%t['proceeds'], '%.2f'%t['fees'],
                        '%.2f'%t['pnl'], '%.2f'%t['return_pct'], t['hold_days'], t['exit_reason']])
    print('逐笔明细 -> %s (%d笔)' % (path, len(c)), flush=True)

    # 按买入年分解自然盈亏
    byyear = collections.defaultdict(lambda: [0.0, 0, 0.0])  # pnl, n, sumret_pp
    byreason = collections.defaultdict(lambda: [0.0, 0])
    for t in real:
        y = int(str(t['buy_date'])[:4])
        byyear[y][0] += t['pnl']; byyear[y][1] += 1; byyear[y][2] += t['return_pct']
        byreason[t['exit_reason']][0] += t['pnl']; byreason[t['exit_reason']][1] += 1
    print('按买入年 (真实已出场):', flush=True)
    for y in sorted(byyear):
        pnl, n, rp = byyear[y]
        print('  %d: 笔%-3d 净盈亏%+10.0f  均单笔%+.1f%%' % (y, n, pnl, rp/n if n else 0), flush=True)
    print('按出场原因:', flush=True)
    for r, (pnl, n) in sorted(byreason.items(), key=lambda x: -x[1][0]):
        print('  %-22s 笔%-3d 净盈亏%+10.0f' % (r, n, pnl), flush=True)

    # 展示单笔盈亏分布前几大
    prof = sorted(real, key=lambda x: -x['pnl'])[:5]
    loss = sorted(real, key=lambda x: x['pnl'])[:5]
    print('  Top5盈利:', flush=True)
    for t in prof:
        print('    %s %s 买%s→卖%s %+.1f%% (持%d天, %s)' % (t['code'], t['name'], t['buy_date'], t['sell_date'], t['return_pct'], t['hold_days'], t['exit_reason']), flush=True)
    print('  Top5亏损:', flush=True)
    for t in loss:
        print('    %s %s 买%s→卖%s %+.1f%% (持%d天, %s)' % (t['code'], t['name'], t['buy_date'], t['sell_date'], t['return_pct'], t['hold_days'], t['exit_reason']), flush=True)

print('\n全部完成.', flush=True)
