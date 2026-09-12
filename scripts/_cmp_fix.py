# -*- coding: utf-8 -*-
"""对比污染版 vs 修复版（第一组 30 窗）。"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

old = {}
with open(os.path.join(HERE, 'hoshi_time_corr_windows.csv'), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        old[(r['start'], r['end'])] = (int(r['len_months']),
                                       float(r['base_pct']), float(r['h5s9_pct']))
new = {}
p = os.path.join(HERE, 'hoshi_fix30_base.csv')
if os.path.exists(p):
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            new[(r['start'], r['end'])] = float(r['base_pct'])


def geo(v):
    q = 1.0
    for x in v:
        q *= (1 + x / 100.0)
    return (q ** (1.0 / len(v)) - 1) * 100.0


def med(v):
    s = sorted(v)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2


out = []
out.append('修复版已完成 %d/30 窗' % len(new))
out.append('')
out.append('===== 原版：污染版 vs 修复版 =====')
ov = [old[k][1] for k in old]
nv = [new.get(k, old[k][1]) for k in old]
out.append('%-12s %10s %10s %10s %10s %8s' % ('', '等权均值', '几何均值', '中位', '最差', '负窗'))
out.append('-' * 64)
out.append('%-12s %+10.2f %+10.2f %+10.2f %+10.2f %5d/30'
           % ('污染版', sum(ov) / len(ov), geo(ov), med(ov), min(ov),
              sum(1 for x in ov if x < 0)))
out.append('%-12s %+10.2f %+10.2f %+10.2f %+10.2f %5d/30'
           % ('修复版', sum(nv) / len(nv), geo(nv), med(nv), min(nv),
              sum(1 for x in nv if x < 0)))

out.append('')
out.append('===== 变化幅度 >1pp 的窗口 =====')
out.append('%-24s %6s %11s %11s %10s' % ('窗口', '月', '污染版', '修复版', '差(pp)'))
out.append('-' * 66)
chg = []
for k in sorted(new):
    o = old[k][1]
    n = new[k]
    if abs(n - o) > 1.0:
        chg.append((abs(n - o), k, o, n))
for _, k, o, n in sorted(chg, key=lambda x: -x[0]):
    out.append('%-24s %6d %+11.2f %+11.2f %+10.1f'
               % ('%s~%s' % (k[0][:7], k[1][:7]), old[k][0], o, n, n - o))
out.append('  变化窗口 %d/30，未变 %d/30（未变的期末强平数=0）'
           % (len(chg), 30 - len(chg)))

# 按长度分组（修复版）
out.append('')
out.append('===== 修复版 原版 按持有期分组 =====')
out.append('%-8s %5s %11s %11s %11s %10s' % ('长度', 'n', '等权均值', '几何均值', '中位', '负窗占比'))
out.append('-' * 60)
bym = {}
for k in old:
    bym.setdefault(old[k][0], []).append(new.get(k, old[k][1]))
for m in sorted(bym):
    v = bym[m]
    out.append('%-8s %5d %+11.2f %+11.2f %+11.2f %9.0f%%'
               % ('%d年' % (m // 12), len(v), sum(v) / len(v), geo(v), med(v),
                  sum(1 for x in v if x < 0) / len(v) * 100))

with open(os.path.join(HERE, '_cmp_fix.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
