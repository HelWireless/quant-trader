# -*- coding: utf-8 -*-
"""OOS 阶段性汇总（只汇总已完成的方案）。"""
import csv
import math
import os
import io

HERE = os.path.dirname(os.path.abspath(__file__))
SELECT = {
    ('2014-12-01', '2016-11-30'), ('2019-05-01', '2021-04-30'),
    ('2018-10-01', '2019-09-30'), ('2022-02-01', '2025-01-31'),
    ('2016-02-01', '2019-01-31'), ('2014-06-01', '2015-05-31'),
}
AVAIL = [('s4', 'S4 折中门槛8.5'), ('t1', 'T1 分档仓位')]
for sk, nm in [('t5', 'T5 分档+关R3+广度30')]:
    if os.path.exists(os.path.join(HERE, 'hoshi_oos30_%s.csv' % sk)):
        rows_n = sum(1 for _ in open(os.path.join(HERE, 'hoshi_oos30_%s.csv' % sk), encoding='utf-8')) - 1
        if rows_n >= 30:
            AVAIL.insert(0, (sk, nm))

rows = {}
for sk, _ in AVAIL:
    with open(os.path.join(HERE, 'hoshi_oos30_%s.csv' % sk), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            k = (r['start'], r['end'])
            d = rows.setdefault(k, {'months': int(r['len_months']),
                                    'base': float(r['base_pct']),
                                    'h5s9': float(r['h5s9_pct'])})
            d[sk] = float(r['%s_pct' % sk])

done = [k for k in sorted(rows) if all(sk in rows[k] for sk, _ in AVAIL)]
oos = [k for k in done if k not in SELECT]

buf = io.StringIO()
P = lambda *a: buf.write(' '.join(str(x) for x in a) + '\n')


def geo(v):
    p = 1.0
    for x in v:
        p *= (1 + x / 100.0)
    return (p ** (1.0 / len(v)) - 1) * 100.0


def med(v):
    s = sorted(v)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2


def signp(keys, f1, f2):
    n = len(keys)
    w = sum(1 for k in keys if rows[k][f1] > rows[k][f2])
    z = (w - n / 2.0) / (math.sqrt(n) / 2.0)
    return w, n, math.erfc(abs(z) / math.sqrt(2))


P('已完成窗口 %d，OOS24（剔除A~F）%d，本轮方案: %s'
  % (len(done), len(oos), ', '.join(nm for _, nm in AVAIL)))
for label, keys in (('ALL30', done), ('OOS24', oos)):
    P('')
    P('=' * 92)
    P('===== %s（n=%d）=====' % (label, len(keys)))
    P('%-22s %9s %9s %9s %9s %8s' % ('方案', '等权均值', '几何均值', '中位', '最差', '负窗'))
    P('-' * 70)
    cand = [('base', '原版'), ('h5s9', 'h5s9')] + AVAIL
    for g, sk, nm in sorted(((geo([rows[k][sk] for k in keys]), sk, nm) for sk, nm in cand), key=lambda x: -x[0]):
        v = [rows[k][sk] for k in keys]
        P('%-22s %+9.2f %+9.2f %+9.2f %+9.2f %4d/%d' % (
            nm, sum(v) / len(v), g, med(v), min(v), sum(1 for x in v if x < 0), len(v)))
    P('')
    for sk, nm in AVAIL:
        for ref in ('base', 'h5s9'):
            w, n, p = signp(keys, sk, ref)
            P('  %-20s vs %-5s 胜 %2d/%-2d (%.0f%%)  p=%.4f %s'
              % (nm, ref, w, n, w / n * 100, p, '显著' if p < .05 else ('边缘' if p < .1 else '不显著')))

P('')
P('===== 逐窗明细 % =====')
P('%-22s %5s %9s %9s %11s %11s' % ('窗口', '月', '原版', 'h5s9',
                                    AVAIL[0][1].split()[0], AVAIL[-1][1].split()[0]))
P('-' * 74)
for k in done:
    d = rows[k]
    P('%-22s %5d %+9.2f %+9.2f %s' % (
        '%s~%s%s' % (k[0][:7], k[1][:7], '*' if k in SELECT else ' '),
        d['months'], d['base'], d['h5s9'],
        ' '.join('%+11.2f' % d[sk] for sk, _ in AVAIL)))

with open(os.path.join(HERE, '_oos_partial.txt'), 'w', encoding='utf-8') as f:
    f.write(buf.getvalue())
print('ok')
