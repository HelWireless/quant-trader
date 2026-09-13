# -*- coding: utf-8 -*-
"""三方案 × 双系统模拟对比：检验「真实执行」下结论是否反转。

背景：此前回测结论是 hoshi-cplus > 方案B > 原版。
本脚本把三者放进【同一套带 20% 执行偏差的模拟框架】重跑，看排序是否变化。

用法: python -m sim.compare_presets [start] [end]
"""
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hoshi_cplus.config import PRESETS                       # noqa: E402
from hoshi_cplus.data import load_data, precompute           # noqa: E402
from sim.runner import run_simulation                        # noqa: E402

S = sys.argv[1] if len(sys.argv) > 1 else '2020-01-20'
E = sys.argv[2] if len(sys.argv) > 2 else '2026-09-01'
CAP = 300000.0
SEED = 20260913
ORDER = ['original', 'B', 'cplus']


def summarize(res):
    eq = [r['equity'] for r in res['equity_curve']]
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, (v - peak) / peak * 100.0)
    sells = [t for t in res['A'].trade_log
             if str(t['side']).lower() == 'sell' and t.get('ret') not in ('', None)]
    wins = sum(1 for t in sells if float(t['ret']) > 0)
    return dict(final=res['final_capital'], ret=res['ret'], mdd=mdd,
                n_buy=sum(1 for t in res['A'].trade_log
                          if str(t['side']).lower() == 'buy'),
                n_sell=len(sells),
                win=(100.0 * wins / len(sells)) if sells else 0.0,
                avg=(sum(float(t['ret']) for t in sells) / len(sells)) if sells else 0.0)


print('加载数据...', flush=True)
code_bars, names = load_data('scripts/hoshi_csv_2005')
prepared = precompute(code_bars)

d0, d1 = date.fromisoformat(S), date.fromisoformat(E)
out = {}
for p in ORDER:
    for biased in (True, False):
        tag = '有偏差' if biased else '无偏差'
        print('\n>>> %s × %s ...' % (PRESETS[p].name, tag), flush=True)
        r = run_simulation(prepared, code_bars, names, d0, d1, capital=CAP,
                           biased=biased, seed=SEED, preset=p)
        out[(p, biased)] = summarize(r)
        s = out[(p, biased)]
        print('    期末 %s  收益 %+.2f%%  回撤 %.2f%%  笔 %d  胜率 %.1f%%'
              % (format(int(s['final']), ','), s['ret'], s['mdd'],
                 s['n_sell'], s['win']), flush=True)

# ---------------- 报告 ----------------
L = []
W = L.append
W('# 三方案 × 双系统模拟 —— 真实执行下是否反转')
W('')
W('- 区间：%s ~ %s    本金：%.0f    种子：%d' % (S, E, CAP, SEED))
W('- 偏差模型：20%% 异常（买 8%%追高/4%%买最低/8%%失败；卖 8%%割肉/3%%卖最高/9%%漏卖）+ 涨跌停封板')
W('')
for biased, tag in ((False, '无偏差（理想执行）'), (True, '有偏差（真实模拟）')):
    W('## %s' % tag)
    W('')
    W('| 方案 | 期末资金 | 收益率 | 最大回撤 | 买卖笔数 | 胜率 |')
    W('|---|---:|---:|---:|---:|---:|')
    for p in ORDER:
        s = out[(p, biased)]
        W('| %s | %s | %+.2f%% | %.2f%% | %d | %.1f%% |'
          % (PRESETS[p].name.split(' ')[0], format(int(s['final']), ','),
             s['ret'], s['mdd'], s['n_sell'], s['win']))
    rank = sorted(ORDER, key=lambda p: -out[(p, biased)]['ret'])
    W('')
    W('**排名**：%s' % ' > '.join(PRESETS[p].name.split(' ')[0] for p in rank))
    W('')

W('## 结论')
W('')
rows = {}
for p in ORDER:
    a = out[(p, True)]
    b = out[(p, False)]
    rows[p] = dict(bias=a['ret'], ideal=b['ret'],
                   decay=a['ret'] - b['ret'],
                   loss=a['final'] - b['final'])
    W('- **%s**：理想 %+.2f%% → 有偏差 %+.2f%%（**%+.2f pp**，金额 %s 元）'
      % (PRESETS[p].name.split(' ')[0], b['ret'], a['ret'],
         a['ret'] - b['ret'], format(int(a['final'] - b['final']), ',')))
W('')
r_ideal = sorted(ORDER, key=lambda p: -out[(p, False)]['ret'])
r_bias = sorted(ORDER, key=lambda p: -out[(p, True)]['ret'])
W('排序（理想）：%s' % ' > '.join(r_ideal))
W('')
W('排序（有偏差）：%s' % ' > '.join(r_bias))
W('')
W('**→ %s**' % ('排序未变，结论不反转 ✅' if r_ideal == r_bias
               else '⚠️ 排序发生变化，需要重新审视'))

txt = '\n'.join(L)
print('\n' + txt)
os.makedirs('sim_out_cmp', exist_ok=True)
with open(os.path.join('sim_out_cmp', 'report.md'), 'w', encoding='utf-8') as f:
    f.write(txt + '\n')
with open(os.path.join('sim_out_cmp', 'summary.csv'), 'w', newline='',
          encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['preset', 'biased', 'final', 'ret_pct', 'mdd', 'n_sell', 'win_rate'])
    for p in ORDER:
        for biased in (False, True):
            s = out[(p, biased)]
            w.writerow([p, biased, round(s['final'], 2), round(s['ret'], 4),
                        round(s['mdd'], 4), s['n_sell'], round(s['win'], 2)])
print('\n输出: sim_out_cmp/')
