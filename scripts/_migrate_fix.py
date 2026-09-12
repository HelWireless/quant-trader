# -*- coding: utf-8 -*-
"""把已跑完的 exp5 结果迁移到统一命名 hoshi_fix<group>_<scheme>.csv。

hoshi_fix30_base.csv : start,end,len_months,base_pct(污染),h5s9_pct(污染),base_pct(修复),trades
                       -> DictReader 取最后一个 base_pct = 修复值
hoshi_fix30_t5.csv   : start,end,len_months,base_pct(污染),h5s9_pct(污染),t5_pct(修复),trades
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))

JOBS = [
    ('hoshi_fix30_base.csv', 'hoshi_fix1_base.csv', 'base_pct'),
    ('hoshi_fix30_t5.csv', 'hoshi_fix1_t5.csv', 't5_pct'),
]

for src, dst, col in JOBS:
    src_p = os.path.join(HERE, src)
    dst_p = os.path.join(HERE, dst)
    if not os.path.exists(src_p):
        print('SKIP (missing) %s' % src)
        continue
    rows = []
    with open(src_p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append([r['start'], r['end'], r['len_months'], r[col], r.get('trades', '')])
    with open(dst_p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['start', 'end', 'len_months', col, 'trades'])
        w.writerows(rows)
    print('OK %-24s -> %-22s rows=%d' % (src, dst, len(rows)))
