# -*- coding: utf-8 -*-
"""B 方案（h5s9 + 关R3）与 T5 / h5s9 / 原版 的同窗口配对比较（含符号检验）。

用法: python hoshi_abl_summary.py [group]   默认 1
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GROUP = sys.argv[1] if len(sys.argv) > 1 else '1'


def rd(path, col):
    d = {}
    p = os.path.join(HERE, path)
    if not os.path.exists(p):
        return d
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                d[(r['start'], r['end'])] = float(r[col])
            except (KeyError, ValueError, TypeError):
                pass
    return d


def geo(v):
    p = 1.0
    for x in v:
        p *= (1 + x / 100.0)
    return (p ** (1.0 / len(v)) - 1.0) * 100.0 if p > 0 else -100.0


def med(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def binom_tail(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / (2.0 ** n)


def pair(a, b, keys):
    d = [a[k] - b[k] for k in keys]
    n = len(d)
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else float('inf')
    win = sum(1 for x in d if x > 0)
    p2 = min(1.0, 2.0 * binom_tail(max(win, n - win), n))
    return n, m, t, win, p2


D = {
    'base': rd('hoshi_fix%s_base.csv' % GROUP, 'base_pct'),
    'h5s9': rd('hoshi_fix%s_h5s9.csv' % GROUP, 'h5s9_pct'),
    'T5': rd('hoshi_fix%s_t5.csv' % GROUP, 't5_pct'),
    'B': rd('hoshi_abl%s_b.csv' % GROUP, 'pct'),
}

print('=' * 96)
print('第 %s 组：四方案单样本统计' % GROUP)
print('=' * 96)
print('%-6s %4s %10s %10s %10s %10s %8s' % ('方案', 'n', '等权均值', '几何', '中位', '最差', '负窗'))
print('-' * 96)
for k in ('base', 'h5s9', 'B', 'T5'):
    v = list(D[k].values())
    if not v:
        print('%-6s   0          -          -          -          -        -' % k)
        continue
    print('%-6s %4d %9.2f%% %9.2f%% %9.2f%% %9.2f%% %5d/%d'
          % (k, len(v), sum(v) / len(v), geo(v), med(v), min(v),
             sum(1 for x in v if x < 0), len(v)))

print()
print('=' * 96)
print('配对比较（符号检验：精确二项双尾 p）')
print('=' * 96)
print('%-14s %4s %12s %8s %10s %14s' % ('对比', 'n', '平均差', 't 值', '胜/总', '符号检验 p'))
print('-' * 96)
for a, b in (('B', 'base'), ('B', 'h5s9'), ('B', 'T5'), ('T5', 'base'), ('h5s9', 'base')):
    keys = [k for k in D[a] if k in D[b]]
    if not keys:
        continue
    n, m, t, win, p2 = pair(D[a], D[b], keys)
    ps = '<0.0001' if p2 < 0.0001 else '%.4f' % p2
    flag = ' ***' if p2 < 0.05 else ''
    print('%-14s %4d %11.2fpp %8.2f %5d/%-5d %14s%s'
          % ('%s − %s' % (a, b), n, m, t, win, n, ps, flag))

# 交易笔数对比
print()
print('交易笔数（均值）:')
for k in ('base', 'h5s9', 'B', 'T5'):
    p = {'base': 'hoshi_fix%s_base.csv', 'h5s9': 'hoshi_fix%s_h5s9.csv',
         'T5': 'hoshi_fix%s_t5.csv', 'B': 'hoshi_abl%s_b.csv'}[k] % GROUP
    fp = os.path.join(HERE, p)
    if not os.path.exists(fp):
        continue
    tr = []
    with open(fp, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                tr.append(int(float(r['trades'])))
            except (KeyError, ValueError, TypeError):
                pass
    if tr:
        print('  %-6s 均值 %6.1f 笔' % (k, sum(tr) / len(tr)))
print('=' * 96)
