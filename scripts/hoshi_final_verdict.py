# -*- coding: utf-8 -*-
"""终局对比：原版 / h5s9 / B(关R3) / T5，双组 60 窗合并 + 分组 + 按持有期。

输出控制台摘要，并写入 hoshi_final_verdict.csv。
"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMES = ['base', 'h5s9', 'B', 'T5']
NAME = {'base': '原版', 'h5s9': 'h5s9', 'B': 'B(关R3)', 'T5': 'T5'}


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


FILES = {
    '1': {'base': ('hoshi_fix1_base.csv', 'base_pct'),
          'h5s9': ('hoshi_fix1_h5s9.csv', 'h5s9_pct'),
          'T5': ('hoshi_fix1_t5.csv', 't5_pct'),
          'B': ('hoshi_abl1_b.csv', 'pct')},
    '2': {'base': ('hoshi_fix2_base.csv', 'base_pct'),
          'h5s9': ('hoshi_fix2_h5s9.csv', 'h5s9_pct'),
          'T5': ('hoshi_fix2_t5.csv', 't5_pct'),
          'B': ('hoshi_abl2_b.csv', 'pct')},
}

LEN = {}
for g in ('1', '2'):
    with open(os.path.join(HERE, FILES[g]['base'][0]), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            LEN[(r['start'], r['end'])] = int(r['len_months'])

D = {}
for sk in SCHEMES:
    d = {}
    for g in ('1', '2'):
        d.update(rd(*FILES[g][sk]))
    D[sk] = d


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
    return n, m, t, win, min(1.0, 2.0 * binom_tail(max(win, n - win), n))


def stat_block(keys, title):
    print('  %-24s %4s %10s %10s %10s %10s %9s' % (title, 'n', '等权均值', '几何', '中位', '最差', '负窗'))
    for sk in SCHEMES:
        v = [D[sk][k] for k in keys if k in D[sk]]
        if not v:
            continue
        print('  %-24s %4d %9.2f%% %9.2f%% %9.2f%% %9.2f%% %5d/%d'
              % (NAME[sk], len(v), sum(v) / len(v), geo(v), med(v), min(v),
                 sum(1 for x in v if x < 0), len(v)))


ALL = sorted(set(D['base']) & set(D['h5s9']) & set(D['B']) & set(D['T5']))
OUT = []
print('=' * 100)
print('终局对比（双组 %d 个窗口，引擎 exp5 已修复强平 bug）' % len(ALL))
print('=' * 100)
stat_block(ALL, '合计 %d 窗' % len(ALL))
G1 = [k for k in ALL if LEN.get(k, 0) and k in D['base'] and k in rd(FILES['1']['base'][0], 'base_pct')]
G2 = [k for k in ALL if k in rd(FILES['2']['base'][0], 'base_pct')]
print()
stat_block(G1, '第一组 %d 窗' % len(G1))
print()
stat_block(G2, '第二组 %d 窗' % len(G2))

print()
print('=' * 100)
print('配对比较（符号检验双尾 p，*** = p<0.05）')
print('=' * 100)
print('  %-16s %16s %12s %8s %10s %12s' % ('对比', '样本', '平均差', 't 值', '胜/总', '符号检验 p'))
print('  ' + '-' * 78)
SETS = [('合计', ALL), ('第一组', G1), ('第二组', G2)]
for gl, keys in SETS:
    for a, b in (('B', 'base'), ('B', 'h5s9'), ('B', 'T5'), ('T5', 'base'), ('h5s9', 'base')):
        ks = [k for k in keys if k in D[a] and k in D[b]]
        if not ks:
            continue
        n, m, t, win, p2 = pair(D[a], D[b], ks)
        ps = '<0.0001' if p2 < 0.0001 else '%.4f' % p2
        flag = ' ***' if p2 < 0.05 else ''
        print('  %-16s %16s %11.2fpp %8.2f %5d/%-5d %12s%s'
              % ('%s − %s' % (NAME[a], NAME[b]), gl, m, t, win, n, ps, flag))
        OUT.append([gl, '%s-%s' % (a, b), n, round(m, 2), round(t, 2), win, round(p2, 5)])
    print()

print('=' * 100)
print('按持有期拆分（第二组窗口，长度固定为 1/2/4/7 年）')
print('=' * 100)
for m in (12, 24, 48, 84):
    ks = [k for k in G2 if LEN.get(k) == m]
    if not ks:
        continue
    stat_block(ks, '%d 年（%d 窗）' % (m // 12, len(ks)))
    for a, b in (('B', 'base'), ('B', 'T5'), ('T5', 'base')):
        kk = [k for k in ks if k in D[a] and k in D[b]]
        if not kk:
            continue
        n, mm, t, win, p2 = pair(D[a], D[b], kk)
        ps = '<0.0001' if p2 < 0.0001 else '%.4f' % p2
        print('      %-14s vs %-8s 平均差%+9.2fpp  胜 %d/%d  p=%s' % (NAME[a], NAME[b], mm, win, n, ps))
    print()

with open(os.path.join(HERE, 'hoshi_final_verdict.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['group', 'pair', 'n', 'mean_diff_pp', 't', 'win', 'p_two_sided'])
    w.writerows(OUT)
print('配对明细已写入 hoshi_final_verdict.csv')
