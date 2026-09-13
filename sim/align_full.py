# -*- coding: utf-8 -*-
"""三方案 × 三种口径 同区间对拍：回测 / 双系统模拟(无偏差) / 双系统模拟(有偏差)。

对齐锚点：**「无偏差」必须复现「回测」**（同一区间同参数）。这是检验
订单驱动框架是否写对的唯一硬标准。三者跑在同一份数据、同一种子上。

用法: python -m sim.align_full [start] [end]
"""
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hoshi_cplus.backtest import run_backtest                 # noqa: E402
from hoshi_cplus.config import PRESETS                        # noqa: E402
from hoshi_cplus.data import load_data, precompute            # noqa: E402
from sim.runner import run_simulation                         # noqa: E402

S = sys.argv[1] if len(sys.argv) > 1 else '2020-01-20'
E = sys.argv[2] if len(sys.argv) > 2 else '2020-03-20'
CAP = 300000.0
SEED = 20260913
ORDER = ['original', 'B', 'cplus']
MODES = [('bt', '回测'), ('ideal', '无偏差'), ('bias', '有偏差')]


def summarize(r):
    eq = [x['equity'] for x in r['equity_curve']]
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, (v - peak) / peak * 100.0)
    sells = [t for t in r['A'].trade_log
             if str(t['side']).lower() == 'sell' and t.get('ret') not in ('', None)]
    wins = sum(1 for t in sells if float(t['ret']) > 0)
    return dict(final=r['final_capital'], ret=r['ret'], mdd=mdd,
                n_sell=len(sells),
                win=(100.0 * wins / len(sells)) if sells else 0.0)


print('加载数据...', flush=True)
code_bars, names = load_data('scripts/hoshi_csv_2005')
prepared = precompute(code_bars)

d0, d1 = date.fromisoformat(S), date.fromisoformat(E)
out = {}
for p in ORDER:
    print('\n>>> %s' % PRESETS[p].name, flush=True)
    rb = run_backtest(prepared, preset=p, start=S, end=E,
                      capital=CAP, code_bars=code_bars)
    out[(p, 'bt')] = dict(final=rb['final_capital'], ret=rb['ret'],
                          mdd=0.0, n_sell=rb['n_trades'], win=0.0)
    print('    回测    期末 %s  %+.2f%%  笔 %d'
          % (format(int(rb['final_capital']), ','), rb['ret'], rb['n_trades']),
          flush=True)
    for biased, key in ((False, 'ideal'), (True, 'bias')):
        r = run_simulation(prepared, code_bars, names, d0, d1, capital=CAP,
                           biased=biased, seed=SEED, preset=p)
        out[(p, key)] = summarize(r)
        s = out[(p, key)]
        print('    %s 期末 %s  %+.2f%%  笔 %d'
              % ('无偏差' if not biased else '有偏差',
                 format(int(s['final']), ','), s['ret'], s['n_sell']), flush=True)

L = []
W = L.append
W('# 三方案 × 三种口径 同区间对拍')
W('')
W('- 区间：%s ~ %s   本金：%.0f   种子：%d' % (S, E, CAP, SEED))
W('- 对齐锚点：**无偏差应复现回测**；这是检验订单驱动框架的唯一硬标准')
W('')
W('| 方案 | 回测收益 | 无偏差 | 有偏差 | 无偏差−回测 | 笔数(回测/无偏差) |')
W('|---|---:|---:|---:|---:|---:|')
for p in ORDER:
    a, b, c = out[(p, 'bt')], out[(p, 'ideal')], out[(p, 'bias')]
    gap = b['ret'] - a['ret']
    W('| %s | %+.2f%% | %+.2f%% | %+.2f%% | **%+7.2f pp** | %d / %d |'
      % (PRESETS[p].name.split(' ')[0], a['ret'], b['ret'], c['ret'],
         gap, a['n_sell'], b['n_sell']))
W('')
for key, tag in MODES:
    rank = sorted(ORDER, key=lambda p: -out[(p, key)]['ret'])
    W('- 排序(%s)：%s' % (tag, ' > '.join(PRESETS[p].name.split(' ')[0] for p in rank)))
W('')
r_bt = sorted(ORDER, key=lambda p: -out[(p, 'bt')]['ret'])
r_id = sorted(ORDER, key=lambda p: -out[(p, 'ideal')]['ret'])
W('**对齐校验**：%s' % ('✅ 无偏差复现了回测排序' if r_bt == r_id
                    else '❌ 排序不一致，框架未对齐（此时「有偏差」的结论不可信）'))

txt = '\n'.join(L)
print('\n' + txt)
os.makedirs('sim_out_align', exist_ok=True)
with open(os.path.join('sim_out_align', 'report_%s_%s.md' % (S, E)), 'w',
          encoding='utf-8') as f:
    f.write(txt + '\n')
with open(os.path.join('sim_out_align', 'summary_%s_%s.csv' % (S, E)), 'w',
          newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['preset', 'mode', 'final', 'ret_pct', 'n_sell'])
    for p in ORDER:
        for key, _ in MODES:
            s = out[(p, key)]
            w.writerow([p, key, round(s['final'], 2), round(s['ret'], 4), s['n_sell']])
print('\n输出: sim_out_align/')
