# -*- coding: utf-8 -*-
"""对齐诊断：把回测引擎与双系统模拟的逐笔交易并排打印，找出第一处分歧。

用法: python sim/diag_align.py [start] [end]
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hoshi_cplus.backtest import run_backtest                 # noqa: E402
from hoshi_cplus.data import load_data, precompute            # noqa: E402
from sim.runner import run_simulation                         # noqa: E402

S = sys.argv[1] if len(sys.argv) > 1 else '2020-01-20'
E = sys.argv[2] if len(sys.argv) > 2 else '2020-03-20'

print('加载数据...', flush=True)
code_bars, names = load_data('scripts/hoshi_csv_2005')
prepared = precompute(code_bars)

print('\n=== 回测引擎 ===', flush=True)
rb = run_backtest(prepared, preset='cplus', start=S, end=E, code_bars=code_bars)
print('  ret=%+.4f%%  trades=%d  buys=%d' % (rb['ret'], rb['n_trades'], rb['n_buys']))

print('\n=== 双系统模拟（无偏差）===', flush=True)
ri = run_simulation(prepared, code_bars, names, date.fromisoformat(S),
                    date.fromisoformat(E), capital=300000.0, biased=False)
tl = ri['A'].trade_log
print('  ret=%+.4f%%  trades=%d' % (ri['ret'], len(tl)))

# ---------------- 汇总：按卖出原因分布 ----------------
import collections
print('\n=== 卖出原因分布 ===')
for tag, items in (('回测', [t for t in rb['trades'] if t['side'].lower() == 'sell']),
                   ('模拟', [t for t in tl if t['side'].lower() == 'sell'])):
    c = collections.Counter(t['reason'] for t in items)
    print('  %s: %s' % (tag, dict(c)))

# ---------------- 出场「持有天数」分布 ----------------
def holding_days(items):
    """从买卖配对算持有天数（按记录顺序近似配对）。"""
    open_pos = {}
    dist = []
    for t in items:
        code = t['code']
        if t['side'].lower() == 'buy':
            open_pos[code] = t['date']
        else:
            bd = open_pos.pop(code, None)
            if bd:
                dist.append((t['date'] - bd).days)
    return dist


print('\n=== 持有自然日分布（均值 / 中位 / 最长）===')
for tag, items in (('回测', rb['trades']), ('模拟', tl)):
    d = holding_days(items)
    if d:
        d2 = sorted(d)
        print('  %s: n=%d  均值%.1f  中位%.1f  最长%d' %
              (tag, len(d), sum(d) / len(d), d2[len(d2) // 2], d2[-1]))

# ---------------- 逐笔并排（卖出） ----------------
print('\n=== 卖出明细并排（前 30 笔，按日期）===')
bs = [t for t in rb['trades'] if t['side'].lower() == 'sell']
ms = [t for t in tl if t['side'].lower() == 'sell']
bs.sort(key=lambda x: (x['date'], x['code']))
ms.sort(key=lambda x: (x['date'], x['code']))

print('  %-3s %-11s %-8s %-9s %-8s %-7s | %-11s %-8s %-9s %-8s %-7s'
      % ('#', '回测日期', '代码', '卖价', '收益%', '原因', '模拟日期', '代码', '卖价', '收益%', '原因'))
n = max(len(bs), len(ms))
for i in range(min(30, n)):
    b = bs[i] if i < len(bs) else None
    m = ms[i] if i < len(ms) else None
    mark = ''
    if b and m and b['code'] != m['code']:
        mark = '  <<< 分歧'
    print('  %-3d %-11s %-8s %-9.3f %+8.2f %-7s | %-11s %-8s %-9.3f %+8.2f %-7s%s'
          % (i + 1,
             b['date'] if b else '-', b['code'] if b else '-',
             b['price'] if b else 0, b['ret'] if b else 0, b['reason'] if b else '-',
             m['date'] if m else '-', m['code'] if m else '-',
             m['price'] if m else 0, float(m['ret'] or 0) if m else 0,
             m['reason'] if m else '-', mark))

# ---------------- 买入明细并排（含 S3/S4 模式） ----------------
print('\n=== 买入明细并排（前 25 笔，含模式）===')
bb = sorted([t for t in rb['buys']], key=lambda x: (x['date'], x['code']))
mb = sorted([t for t in tl if t['side'].lower() == 'buy'],
            key=lambda x: (x['date'], x['code']))
print('  %-3s %-11s %-8s %-9s %-6s %-5s | %-11s %-8s %-9s %-6s'
      % ('#', '回测日期', '代码', '买价', '模式', '评分', '模拟日期', '代码', '买价', '模式'))
for i in range(min(25, max(len(bb), len(mb)))):
    b = bb[i] if i < len(bb) else None
    m = mb[i] if i < len(mb) else None
    mark = '  <<< 分歧' if (b and m and b['code'] != m['code']) else ''
    print('  %-3d %-11s %-8s %-9.3f %-6s %-5s | %-11s %-8s %-9.3f %-6s%s'
          % (i + 1,
             b['date'] if b else '-', b['code'] if b else '-',
             b['price'] if b else 0, b.get('mode', '-') if b else '-',
             b.get('score', '-') if b else '-',
             m['date'] if m else '-', m['code'] if m else '-',
             m['price'] if m else 0,
             (m.get('reason', '') or '-') if m else '-', mark))

# ---------------- 模式分布 ----------------
print('\n=== 买入时的模式分布（S3 / S4）===')
for tag, items in (('回测', rb['buys']),
                   ('模拟', [t for t in tl if t['side'].lower() == 'buy'])):
    c = collections.Counter(str(t.get('mode', '?')) for t in items)
    print('  %s: %s' % (tag, dict(c)))

