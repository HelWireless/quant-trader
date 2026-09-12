# -*- coding: utf-8 -*-
"""
读 hoshi_user_diag_out/ 下 5 个窗口的 trades CSV，聚合出统一结构对比：
  每窗口: 总收益/笔数/止盈总额vs止损总额/两者净值/止盈单数/止损单数/大牛贡献(单笔>+20%)/深亏(<-25%)
输出到 stdout，供综合总结用。
用法：python scripts/hoshi_user_aggregate.py
"""
import csv, os, glob

OUT = 'scripts/hoshi_user_diag_out'

NODES = [
    ('节点1_2016-2021', '2016-01-01', '2021-12-31'),
    ('节点2_2012-2015', '2012-01-01', '2015-12-31'),
    ('节点3_2022-2025', '2022-01-01', '2025-12-31'),
    ('节点4_2024-2026', '2024-01-01', '2026-09-01'),
    ('节点5_2023-2026', '2023-01-01', '2026-09-01'),
]

def load(path):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({
                'code': row['代码'], 'name': row['名称'],
                'buy': row['买入日'], 'sell': row['卖出日'],
                'ret': float(row['收益率%']), 'pnl': float(row['净盈亏']),
                'days': int(row['持有天数']), 'reason': row['出场原因'],
            })
    return rows

print('%-18s %12s %6s | %12s %12s | %12s | %12s %10s | %8s %8s' %
      ('窗口','真实净盈亏¥','笔数','止盈总额¥','止损总额¥','止盈/止损净值¥','大牛单(+20%)','深亏单(<-25%)','止损单均%','大牛贡献¥'))
print('-'*130)
for tag, s, e in NODES:
    path = os.path.join(OUT, tag + '_trades.csv')
    if not os.path.exists(path):
        print('%-18s 缺失 %s' % (tag, path))
        continue
    rows = load(path)
    # 去掉"回测结束强平"伪平仓
    real = [r for r in rows if r['reason'] != '回测结束强平']
    tp = sum(r['pnl'] for r in real if r['pnl'] > 0)
    sl = sum(r['pnl'] for r in real if r['pnl'] <= 0)
    ntp = sum(1 for r in real if r['pnl'] > 0)
    nsl = sum(1 for r in real if r['pnl'] <= 0)
    big = [r for r in real if r['ret'] >= 20]
    deep = [r for r in real if r['ret'] <= -25]
    big_pnl = sum(r['pnl'] for r in big)
    big_n = len(big)
    avg_sl = sum(r['ret'] for r in real if r['pnl'] <= 0)/nsl if nsl else 0
    total_pnl = sum(r['pnl'] for r in real)
    # 收益% 用净值近似(总投入是50万动态), 取真实 pnl/实际参考——改用原始总净盈亏占初始本金近似不好，直接给总净盈亏
    print('%-18s %+11.0f %6d | %+11.0f %+11.0f | %+12.0f | %12d(%+.0f¥) %12d | %+7.1f%% %+8.0f' %
          (tag, total_pnl, len(real), tp, sl, tp+sl,
           big_n, big_pnl, len(deep), avg_sl, big_pnl))
print('\n注: 净值为真实已出场(剔除伪平仓)。大牛单=单笔收益>=+20%; 深亏单=<=-25%。')
