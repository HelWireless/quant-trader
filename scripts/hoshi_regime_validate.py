# -*- coding: utf-8 -*-
"""
regime 条件式止损 多窗口稳健性验证
窗口与方向B验证(hoshi_stopstart_validate.py)相同，外加 2026 真实窗口。
对比：原版(恒15) / regime自适应(bull15,weak7) / 全程恒7 / 全程恒1。

用法：
  python scripts/hoshi_regime_validate.py > scripts/hoshi_regime_validate.log 2>&1
"""
import importlib.util, time, statistics as st, os

SPEC_PATH = 'scripts/hoshi_regime_backtest.py'
DATA_DIR = 'scripts/hoshi_csv_long'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None
INIT = 500000.0

WINDOWS = [
    ('2012~15 大牛',   '2012-01-01', '2015-12-31'),
    ('2014~18 牛转熊', '2014-01-01', '2018-12-31'),
    ('2020~23 震荡',   '2020-01-01', '2023-12-31'),
    ('2022~25 熊修复', '2022-01-01', '2025-06-30'),
    ('2023~26 反弹',   '2023-06-01', '2026-09-01'),
    ('近一年',         '2025-09-01', '2026-09-01'),
    ('今年2026',       '2026-01-01', '2026-09-01'),
    ('4-1至今2026',    '2026-04-01', '2026-09-01'),
    ('6-1至今2026',    '2026-06-01', '2026-09-01'),
]

MODE_LABEL = {
    'orig':   '原版(恒15)',
    'regime': 'regime(15/7)',
    'day7':   '恒第7天',
    'day1':   '全程(第1天)',
}

print('加载数据 ...', flush=True)
t0 = time.time()
code_bars, names, all_dates = hbl.load_data(DATA_DIR)
print('load_data %.1fs | 标的%d 交易日%d' % (time.time()-t0, len(code_bars), len(all_dates)), flush=True)
hbl.MAX_SLOTS = 10
hbl.MAX_BUY_PER_DAY = 0


def run(start, end, mode):
    hbl.TOTAL_CAPITAL = INIT
    if mode == 'orig':
        hbl.USE_REGIME_LOSS = False
        hbl.LOSS_START_DAY = 15
    elif mode == 'regime':
        hbl.USE_REGIME_LOSS = True
        hbl.REGIME_LOSS_BULL = 15
        hbl.REGIME_LOSS_WEAK = 7
    elif mode == 'day7':
        hbl.USE_REGIME_LOSS = False
        hbl.LOSS_START_DAY = 7
    elif mode == 'day1':
        hbl.USE_REGIME_LOSS = False
        hbl.LOSS_START_DAY = 1
    res = hbl.run_backtest(code_bars, names, all_dates, start=start, end=end)
    c = res['closed']
    if not c:
        return None
    rets = [t['return_pct'] for t in c]
    wins = sum(1 for t in c if t['pnl'] > 0)
    nat = [t for t in c if t['exit_reason'] != '回测结束强平']
    return dict(ret=(res['final_capital']-INIT)/INIT*100.0, n=len(c),
                wr=wins*100.0/len(c),
                worst=min(rets),
                nat_pnl=sum(t['pnl'] for t in nat),
                stops=len(res['stops']))


# ---- 计算阶段：逐窗口 × 逐模式，结果存 perw ----
perw = {}
for label, s, e in WINDOWS:
    print('\n========== %s (%s ~ %s) ==========' % (label, s, e), flush=True)
    perw[label] = {}
    for mode in MODE_LABEL:
        a = run(s, e, mode)
        perw[label][mode] = a
        if a is None:
            print('  %-14s: 无成交' % MODE_LABEL[mode], flush=True)
            continue
        print('  %-14s: 收益%+8.2f%% | 笔%3d | 胜率%5.1f%% | 最差%6.1f%% | 自然盈亏%+10.0f | R3停手%d'
              % (MODE_LABEL[mode], a['ret'], a['n'], a['wr'], a['worst'], a['nat_pnl'], a['stops']), flush=True)
    if perw[label].get('orig') and perw[label].get('regime'):
        d = perw[label]['regime']['ret'] - perw[label]['orig']['ret']
        print('  >>> regime vs 原版: %+6.2f pp (%s)' % (d, '胜' if d > 0 else '劣'), flush=True)

# ---- 汇总阶段（只读 perw，不再重跑） ----
print('\n\n========== 汇总 ==========', flush=True)

# 独立 regime 验证窗口(前5个, 互不重叠覆盖多牛熊), 用于跨窗口稳健性判断
INDEP = ['2012~15 大牛', '2014~18 牛转熊', '2020~23 震荡', '2022~25 熊修复', '2023~26 反弹']
# 2026 真实窗口(第6-9个), regime ON 是否能改善近期实盘
REAL26 = ['近一年', '今年2026', '4-1至今2026', '6-1至今2026']

def avg(x):
    x = [v for v in x if v is not None]
    return (sum(x)/len(x)) if x else float('nan')

# 全部窗口收益率%对比表
def _ret(label, mode):
    a = perw.get(label, {}).get(mode)
    return a['ret'] if a else None

print('\n【全部窗口收益率%对比表】:')
print('  %-16s' % '窗口' + ''.join('%14s' % v for v in MODE_LABEL.values()))
for label, s, e in WINDOWS:
    cells = []
    for mode in MODE_LABEL:
        v = _ret(label, mode)
        cells.append('%+13.2f' % v if v is not None else '%14s' % '-')
    print('  %-16s' % label + ''.join(cells))

for grpname, grp in [('独立 regime 窗口', INDEP), ('2026 真实窗口', REAL26)]:
    print('\n【%s 平均收益率】' % grpname)
    print('  %-16s' % '模式' + ''.join('%14s' % w for w in grp) + '%14s' % '平均')
    for mode in MODE_LABEL:
        vals = [_ret(w, mode) for w in grp if _ret(w, mode) is not None]
        cells = []
        for w in grp:
            v = _ret(w, mode)
            cells.append('%+13.2f' % v if v is not None else '%14s' % '-')
        print('  %-16s' % MODE_LABEL[mode] + ''.join(cells) + '%+13.2f' % avg(vals))
    # regime vs 原版
    o = avg([_ret(w, 'orig') for w in grp if _ret(w, 'orig') is not None])
    rg = avg([_ret(w, 'regime') for w in grp if _ret(w, 'regime') is not None])
    print('  >>> regime-vs-原版 平均差: %+.2f pp  (%s)' % (rg - o, 'regime更优' if rg > o else '原版更优'))

