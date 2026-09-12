# -*- coding: utf-8 -*-
"""诊断 hoshi 5窗口 trades CSV 的出场结构，为设计统一改进方案提供依据。

聚焦：亏损窗口(节点1,节点4) vs 盈利窗口 在「出场原因构成/止损单持有天数/
深亏单共性/止盈单效率」上的差异，找出"统一参数下能改善亏损窗口"的杠杆。
"""
import csv, os, collections

OUT = 'scripts/hoshi_user_diag_out'
FILES = {
    '节点1_2016-21': '节点1_2016-2021_trades.csv',
    '节点2_2012-15': '节点2_2012-2015_trades.csv',
    '节点3_2022-25': '节点3_2022-2025_trades.csv',
    '节点4_2024-26': '节点4_2024-2026_trades.csv',
    '节点5_2023-26': '节点5_2023-2026_trades.csv',
}

def load(p):
    rows = []
    with open(p, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    'code': r['代码'], 'name': r.get('名称', ''),
                    'score': float(r.get('评分', 0)),
                    'mode': r.get('模式', r.get('出场模式', '')),
                    'buy': r['买入日'], 'sell': r['卖出日'],
                    'buy_price': float(r['买入价']), 'sell_price': float(r['卖出价']),
                    'cost': float(r.get('成本', r.get('买入成本', 0))),
                    'pnl': float(r['净盈亏']),
                    'ret': float(r.get('收益率%', r.get('净收益率%', 0))),
                    'hold': int(r['持有天数']),
                    'reason': r['出场原因'],
                })
            except (ValueError, KeyError):
                continue
    return rows

def cat(reason):
    if '止盈' in reason and '超时' not in reason: return '止盈(峰值回落)'
    if '止盈超时' in reason: return '止盈超时'
    if '止损' in reason: return '止损'
    if '强平' in reason: return '回测结束强平'
    if '强制' in reason or '超40' in reason: return '超期强平'
    return reason

print('%-12s %6s %9s | %-16s %6s %10s | %6s %10s | %6s %10s' %
      ('窗口','总笔','总净¥','类别','笔数','净额¥','笔数','净额¥','笔数','净额¥'))
print('-'*130)
for name, fn in FILES.items():
    rows = load(os.path.join(OUT, fn))
    by = collections.defaultdict(list)
    for r in rows:
        by[cat(r['reason'])].append(r)
    line = '%-12s %6d %+9.0f' % (name, len(rows), sum(r['pnl'] for r in rows))
    for k in ['止盈(峰值回落)', '止盈超时', '止损', '回测结束强平', '超期强平']:
        sub = by.get(k, [])
        line += ' | %-16s %6d %+10.0f' % (k, len(sub), sum(r['pnl'] for r in sub))
    print(line)
    stops = by.get('止损', [])
    if stops:
        cnt = collections.Counter(r['hold'] for r in stops)
        print('   止损单持有天数分布: ' + ' '.join('%d天:%d笔' % (h, n) for h, n in sorted(cnt.items())))
        deep = [r for r in stops if r['ret'] <= -25]
        if deep:
            print('   止损深亏(<-25%): ' + ' | '.join('%s %s %+.1f%%(hold%d)' % (r['code'], r['name'], r['ret'], r['hold']) for r in deep))
print()
print('=== 止损单内部子结构（反弹卖出 vs 硬止损）===')
for name, fn in FILES.items():
    rows = [r for r in load(os.path.join(OUT, fn)) if r['reason'].startswith('止损')]
    reb = [r for r in rows if '反弹' in r['reason']]
    hard = [r for r in rows if '硬止损' in r['reason']]
    avg = (sum(r['hold'] for r in rows) / len(rows)) if rows else 0
    print('%-12s 止损共%d笔 | 反弹卖出:%d笔(净%+.0f, 深亏%d) | 硬止损:%d笔(净%+.0f, 深亏%d) | 止损单均hold %.1f天' %
          (name, len(rows), len(reb), sum(r['pnl'] for r in reb), sum(1 for r in reb if r['ret'] <= -25),
           len(hard), sum(r['pnl'] for r in hard), sum(1 for r in hard if r['ret'] <= -25), avg))
