# -*- coding: utf-8 -*-
"""合并最差入场两个方案的结果为一张表。"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
rows = {}
for sk in ('base', 't5'):
    p = os.path.join(HERE, 'hoshi_worstfix_%s.csv' % sk)
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            k = (r['start'], int(r['months']))
            d = rows.setdefault(k, {'end': r['end'], 'tag': r['tag']})
            d[sk] = float(r['ret_pct'])
            d[sk + '_n'] = int(r['trades'])

out = os.path.join(HERE, 'hoshi_worst_entry_compare.csv')
order = {'2014-06-01': 0, '2015-06-01': 1, '2018-01-01': 2, '2021-02-01': 3}
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['入场点', '类型', '持有月', '截止', '原版收益%', 'T5收益%', 'T5-原版', '原版笔数', 'T5笔数'])
    for k in sorted(rows, key=lambda x: (order.get(x[0], 9), x[1])):
        d = rows[k]
        b = d.get('base')
        t = d.get('t5')
        w.writerow([k[0], d['tag'], k[1], d['end'],
                    '' if b is None else '%.2f' % b,
                    '' if t is None else '%.2f' % t,
                    '' if (b is None or t is None) else '%.2f' % (t - b),
                    d.get('base_n', ''), d.get('t5_n', '')])
with open(os.path.join(HERE, '_merge_worst.txt'), 'w', encoding='utf-8') as f:
    f.write('written %s' % out)
