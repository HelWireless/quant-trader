# -*- coding: utf-8 -*-
"""验证集 #2 结果汇总。

第二组 30 窗是全新抽样（种子 20260911，长度 1/2/4/7 年），
对 T5 而言全部是干净样本外（T5 当初是在第一组的 A~F 六窗上选的）。

额外给一个 STRICT 子集：剔除与 A~F 任一窗口重叠超过 50% 的窗口，
避免"同一段行情换个起止点又算一次"的隐性复用。
"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMES = [('base', '原版 评分8+止损15'),
           ('h5s9', 'h5s9 评分9+止损5'),
           ('t5', 'T5 分档+关R3+广度30')]

# 第一组里用于选方案的 A~F
SELECT = [('2014-12-01', '2016-11-30'), ('2019-05-01', '2021-04-30'),
          ('2018-10-01', '2019-09-30'), ('2022-02-01', '2025-01-31'),
          ('2016-02-01', '2019-01-31'), ('2014-06-01', '2015-05-31')]


def to_m(d):
    y, m, _ = d.split('-')
    return int(y) * 12 + int(m)


SEL = [(to_m(a), to_m(b)) for a, b in SELECT]

rows = {}
for sk, _ in SCHEMES:
    p = os.path.join(HERE, 'hoshi_oos2_%s.csv' % sk)
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            k = (r['start'], r['end'])
            d = rows.setdefault(k, {'months': int(r['len_months']), 'ovl': 0.0})
            d[sk] = float(r['%s_pct' % sk])

# 与 A~F 的最大重叠比例
for k, d in rows.items():
    a, b = to_m(k[0]), to_m(k[1])
    span = b - a + 1
    best = 0.0
    for sa, sb in SEL:
        inter = max(0, min(b, sb) - max(a, sa) + 1)
        best = max(best, inter / float(min(span, sb - sa + 1)))
    d['ovl'] = best

done = [k for k in sorted(rows) if all(sk in rows[k] for sk, _ in SCHEMES)]
strict = [k for k in done if rows[k]['ovl'] <= 0.5]


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
    if n == 0:
        return 0, 0, 1.0
    w = sum(1 for k in keys if rows[k][f1] > rows[k][f2])
    z = (w - n / 2.0) / (math.sqrt(n) / 2.0)
    return w, n, math.erfc(abs(z) / math.sqrt(2))


print('已完成窗口 %d/30，其中 STRICT（与A~F重叠≤50%%）%d 个'
      % (len(done), len(strict)))
if not done:
    raise SystemExit('尚无完成窗口')

for label, keys in (('ALL30 第二组全部', done), ('STRICT 剔除与A~F高重叠', strict)):
    if len(keys) < 3:
        continue
    print()
    print('=' * 94)
    print('===== %s（n=%d）=====' % (label, len(keys)))
    print('%-22s %9s %9s %9s %9s %8s' % ('方案', '等权均值', '几何均值', '中位', '最差', '负窗'))
    print('-' * 72)
    for g, sk, nm in sorted(((geo([rows[k][sk] for k in keys]), sk, nm)
                             for sk, nm in SCHEMES), key=lambda x: -x[0]):
        v = [rows[k][sk] for k in keys]
        print('%-22s %+9.2f %+9.2f %+9.2f %+9.2f %4d/%d' % (
            nm, sum(v) / len(v), g, med(v), min(v),
            sum(1 for x in v if x < 0), len(v)))
    print()
    print('  --- 配对符号检验 ---')
    for sk, nm in [('t5', 'T5')]:
        for ref, rnm in (('base', '原版'), ('h5s9', 'h5s9')):
            w, n, p = signp(keys, sk, ref)
            print('  %-6s vs %-6s 胜 %2d/%-2d (%3.0f%%)  p=%.4f  %s'
                  % (nm, rnm, w, n, w / n * 100, p,
                     '显著' if p < .05 else ('边缘' if p < .1 else '不显著')))
    w, n, p = signp(keys, 'base', 'h5s9')
    print('  %-6s vs %-6s 胜 %2d/%-2d (%3.0f%%)  p=%.4f  %s'
          % ('原版', 'h5s9', w, n, w / n * 100, p,
             '显著' if p < .05 else ('边缘' if p < .1 else '不显著')))

print()
print('=' * 94)
print('===== 按窗口长度拆分（几何均值 %）=====')
lens = sorted(set(rows[k]['months'] for k in done))
print('%-10s %12s %12s %12s %8s' % ('长度', '原版', 'h5s9', 'T5', 'n'))
print('-' * 58)
for m in lens:
    ks = [k for k in done if rows[k]['months'] == m]
    print('%-10s %12s %12s %12s %8d' % (
        '%d年' % (m // 12),
        '%+.2f' % geo([rows[k]['base'] for k in ks]),
        '%+.2f' % geo([rows[k]['h5s9'] for k in ks]),
        '%+.2f' % geo([rows[k]['t5'] for k in ks]), len(ks)))

print()
print('===== 逐窗明细（%）=====')
print('%-24s %5s %10s %10s %10s %8s' % ('窗口', '月', '原版', 'h5s9', 'T5', 'A~F重叠'))
print('-' * 74)
for k in done:
    d = rows[k]
    print('%-24s %5d %+10.2f %+10.2f %+10.2f %7.0f%%%s' % (
        '%s~%s' % (k[0][:7], k[1][:7]), d['months'],
        d['base'], d['h5s9'], d['t5'], d['ovl'] * 100,
        '  <-STRICT剔除' if d['ovl'] > 0.5 else ''))
