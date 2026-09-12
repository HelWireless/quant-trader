# -*- coding: utf-8 -*-
"""消融汇总：以 h5s9(V0) 为基准，逐个加回 T5 的三处改动，同窗口配对比较。"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUP = '1'


def rd(path, col):
    d = {}
    if not os.path.exists(path):
        return d
    with open(path, encoding='utf-8') as f:
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


V0 = rd(os.path.join(HERE, 'hoshi_fix%s_h5s9.csv' % GROUP), 'h5s9_pct')
T5 = rd(os.path.join(HERE, 'hoshi_fix%s_t5.csv' % GROUP), 't5_pct')
VARS = [
    ('A  仅+分档仓位', rd(os.path.join(HERE, 'hoshi_abl%s_a.csv' % GROUP), 'pct')),
    ('B  仅+关R3', rd(os.path.join(HERE, 'hoshi_abl%s_b.csv' % GROUP), 'pct')),
    ('C  仅+广度30', rd(os.path.join(HERE, 'hoshi_abl%s_c.csv' % GROUP), 'pct')),
]

print('=' * 92)
print('消融（第一组 %d 窗，以 h5s9 为 V0 基准，逐项加回 T5 的改动）' % len(V0))
print('=' * 92)
print('%-16s %4s %10s %10s %10s %10s' % ('方案', 'n', '几何(全窗)', '几何(同窗V0)', '增益pp', '胜/总'))
print('-' * 92)
print('%-16s %4d %9.2f%% %9.2f%% %10s %10s'
      % ('V0 h5s9 基准', len(V0), geo(list(V0.values())), geo(list(V0.values())), '-', '-'))
for name, d in VARS:
    if not d:
        print('%-16s   0        -           -           -          -' % name)
        continue
    keys = [k for k in d if k in V0]
    g_all = geo(list(d.values()))
    g_pair = geo([d[k] for k in keys])
    g_v0 = geo([V0[k] for k in keys])
    win = sum(1 for k in keys if d[k] > V0[k])
    print('%-16s %4d %9.2f%% %9.2f%% %9.2fpp %6d/%d'
          % (name, len(d), g_all, g_pair, g_pair - g_v0, win, len(keys)))
if T5:
    keys = [k for k in T5 if k in V0]
    g_all = geo(list(T5.values()))
    g_pair = geo([T5[k] for k in keys])
    g_v0 = geo([V0[k] for k in keys])
    win = sum(1 for k in keys if T5[k] > V0[k])
    print('%-16s %4d %9.2f%% %9.2f%% %9.2fpp %6d/%d'
          % ('T5  三项全开', len(T5), g_all, g_pair, g_pair - g_v0, win, len(keys)))
print('=' * 92)
print('注：几何(同窗V0) 只取该方案已跑完的窗口，与 V0 的同批窗口对比，增益pp 才是公平口径。')
