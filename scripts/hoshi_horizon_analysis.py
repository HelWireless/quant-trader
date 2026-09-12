# -*- coding: utf-8 -*-
"""持有期分析：策略收益是否随持有时间单调上升？

合并两组随机窗口：
  第一组 种子 20260907，长度 1/2/3/5/8 年（30 窗，base/h5s9/t5/s4/t1 全齐）
  第二组 种子 20260911，长度 1/2/4/7 年（30 窗，按完成情况自动纳入）
按窗口长度分组，看 负窗占比 / 最差窗口 / 几何均值 是否随长度改善。
"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMES = ['base', 'h5s9', 't5', 's4', 't1']
NAME = {'base': '原版', 'h5s9': 'h5s9', 't5': 'T5', 's4': 'S4', 't1': 'T1'}

rows = {}   # (start,end) -> dict(months=..., set=..., scheme->ret)
_buf = []


def P(*a):
    _buf.append(' '.join(str(x) for x in a))


def load(path, sk, setname):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if '%s_pct' % sk not in r:
                continue
            k = (r['start'], r['end'])
            d = rows.setdefault(k, {'months': int(r['len_months']), 'set': setname})
            d[sk] = float(r['%s_pct' % sk])
            n += 1
    return n


# ---- 第一组 ----
with open(os.path.join(HERE, 'hoshi_time_corr_windows.csv'), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        k = (r['start'], r['end'])
        d = rows.setdefault(k, {'months': int(r['len_months']), 'set': 1})
        d['base'] = float(r['base_pct'])
        d['h5s9'] = float(r['h5s9_pct'])
for sk in ('t5', 's4', 't1'):
    load(os.path.join(HERE, 'hoshi_oos30_%s.csv' % sk), sk, 1)

# ---- 第二组 ----
for sk in ('base', 'h5s9', 't5'):
    load(os.path.join(HERE, 'hoshi_oos2_%s.csv' % sk), sk, 2)


def geo(v):
    p = 1.0
    for x in v:
        p *= (1 + x / 100.0)
    return (p ** (1.0 / len(v)) - 1) * 100.0


def med(v):
    s = sorted(v)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2


def spearman(xs, ys):
    def rank(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and a[order[j + 1]] == a[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


counts = {sk: sum(1 for d in rows.values() if sk in d) for sk in SCHEMES}
avail = [sk for sk in SCHEMES if counts[sk] >= 24]
P('合并窗口总数 %d（第一组 30 + 第二组 %d 个不同起点）'
  % (len(rows), sum(1 for d in rows.values() if d.get('set') == 2)))
P('各方案可用窗口数: ' + ', '.join('%s=%d' % (NAME[s], counts[s]) for s in SCHEMES))
P('')

P('=' * 96)
P('===== 按持有期分组 =====')
for sk in avail:
    lens = sorted(set(d['months'] for d in rows.values() if sk in d))
    P('')
    P('【%s】  n=%d' % (NAME[sk], counts[sk]))
    P('  %-7s %-4s %11s %11s %11s %11s %10s'
      % ('持有期', 'n', '等权均值', '几何均值', '中位', '最差窗', '负窗占比'))
    P('  ' + '-' * 72)
    allv = []
    for m in lens:
        v = [d[sk] for d in rows.values() if sk in d and d['months'] == m]
        allv.extend((m, x) for x in v)
        lab = ('%d年' % (m // 12)) if m % 12 == 0 else ('%d个月' % m)
        P('  %-7s %-4d %+11.2f %+11.2f %+11.2f %+11.2f %9.0f%%'
          % (lab, len(v), sum(v) / len(v), geo(v), med(v), min(v),
             sum(1 for x in v if x < 0) / len(v) * 100))
    rho = spearman([x[0] for x in allv], [x[1] for x in allv])
    P('  → 持有期 vs 收益 Spearman rho = %+.3f  (n=%d)' % (rho, len(allv)))

P('')
P('=' * 96)
P('===== 短(≤2年) vs 长(≥3年) =====')
P('%-8s %12s %10s %12s %10s %12s' % ('方案', '短-几何', '短-负窗', '长-几何', '长-负窗', '长减短(pp)'))
P('-' * 70)
for sk in avail:
    short = [d[sk] for d in rows.values() if sk in d and d['months'] <= 24]
    long_ = [d[sk] for d in rows.values() if sk in d and d['months'] >= 36]
    if len(short) < 3 or len(long_) < 3:
        continue
    P('%-8s %+12.2f %9.0f%% %+12.2f %9.0f%% %+12.2f' % (
        NAME[sk], geo(short), sum(1 for x in short if x < 0) / len(short) * 100,
        geo(long_), sum(1 for x in long_ if x < 0) / len(long_) * 100,
        geo(long_) - geo(short)))

with open(os.path.join(HERE, '_horizon.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(_buf))
