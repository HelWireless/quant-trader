# -*- coding: utf-8 -*-
"""30 窗口样本外验证结果汇总。

关键：A~F 六个窗口是当初"选方案"用的，它们本身也在这 30 窗里。
因此同时给出两套口径：
  ALL30 —— 全部 30 窗
  OOS24 —— 剔除 A~F 后的 24 窗（真正干净的样本外）
"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# 当初用于选方案的 6 个窗口
SELECT = {
    ('2014-12-01', '2016-11-30'),  # A
    ('2019-05-01', '2021-04-30'),  # B
    ('2018-10-01', '2019-09-30'),  # C
    ('2022-02-01', '2025-01-31'),  # D
    ('2016-02-01', '2019-01-31'),  # E
    ('2014-06-01', '2015-05-31'),  # F
}

SCHEMES = [('t5', 'T5 分档仓位+关R3+广度30'),
           ('s4', 'S4 折中门槛8.5'),
           ('t1', 'T1 分档仓位')]

rows = {}
base_months = None
for sk, _ in SCHEMES:
    p = os.path.join(HERE, 'hoshi_oos30_%s.csv' % sk)
    if not os.path.exists(p):
        print('缺少 %s' % p)
        continue
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r['start'], r['end'])
            d = rows.setdefault(key, {'months': int(r['len_months']),
                                      'base': float(r['base_pct']),
                                      'h5s9': float(r['h5s9_pct'])})
            d[sk] = float(r['%s_pct' % sk])

allkeys = sorted(rows.keys())
done = [k for k in allkeys if all(sk in rows[k] for sk, _ in SCHEMES)]
oos = [k for k in done if k not in SELECT]
print('已完成窗口 %d/%d，其中 OOS24（剔除A~F）%d 个' % (len(done), len(allkeys), len(oos)))
if not done:
    raise SystemExit('尚无完成窗口')


def geo(v):
    p = 1.0
    for x in v:
        p *= (1 + x / 100.0)
    return (p ** (1.0 / len(v)) - 1) * 100.0


def med(v):
    s = sorted(v)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]


def stat(keys, field):
    v = [rows[k][field] for k in keys]
    return v


def sign_test(keys, f1, f2):
    """配对符号检验：f1 相对 f2 赢的窗口数 + 二项 p 值（双尾，近似正态）"""
    d = [rows[k][f1] - rows[k][f2] for k in keys]
    n = len(d)
    win = sum(1 for x in d if x > 0)
    # 正态近似
    if n == 0:
        return 0, 0, 1.0
    mu = n / 2.0
    sd = math.sqrt(n) / 2.0
    z = (win - mu) / sd
    p = math.erfc(abs(z) / math.sqrt(2))
    return win, n, p


for label, keys in (('ALL30 全部窗口', done), ('OOS24 剔除选方案的A~F', oos)):
    if len(keys) < 5:
        continue
    print()
    print('=' * 96)
    print('===== %s（n=%d）=====' % (label, len(keys)))
    print('%-24s %9s %9s %9s %9s %8s %10s' %
          ('方案', '等权均值', '几何均值', '中位', '最差', '负窗', '累加(万)'))
    print('-' * 84)
    cand = [('base', '原版 评分8+止损15'), ('h5s9', 'h5s9 评分9+止损5')] + SCHEMES
    ranked = sorted(((geo(stat(keys, sk)), sk, nm) for sk, nm in cand), key=lambda x: -x[0])
    for g, sk, nm in ranked:
        v = stat(keys, sk)
        print('%-24s %+9.2f %+9.2f %+9.2f %+9.2f %4d/%d %10.0f' % (
            nm, sum(v) / len(v), g, med(v), min(v),
            sum(1 for x in v if x < 0), len(v),
            sum(50 * (1 + x / 100.0) for x in v)))

    print()
    print('--- 配对比较（候选方案 vs 基准）---')
    print('%-24s %-18s %10s %10s %12s' % ('对比', '', '胜出窗数', '胜率', '符号检验p'))
    for sk, nm in SCHEMES:
        for ref, rnm in (('base', '原版'), ('h5s9', 'h5s9')):
            w, n, p = sign_test(keys, sk, ref)
            flag = '显著' if p < 0.05 else ('边缘' if p < 0.10 else '不显著')
            print('%-24s %-18s %6d/%-4d %9.1f%% %9.3f %s' % (
                nm, 'vs ' + rnm, w, n, w / n * 100.0, p, flag))

print()
print('=' * 96)
print('===== 按窗口长度拆分（几何均值 %）=====')
lens = sorted(set(rows[k]['months'] for k in done))
hdr = '%-10s' % '窗口长度'
for _, nm in [('base', '原版'), ('h5s9', 'h5s9')] + SCHEMES:
    hdr += '%14s' % nm.split()[0]
print(hdr + '%8s' % 'n')
print('-' * (10 + 14 * (2 + len(SCHEMES)) + 8))
for m in lens:
    ks = [k for k in done if rows[k]['months'] == m]
    line = '%-10s' % ('%d年' % (m // 12))
    for sk, _ in [('base', ''), ('h5s9', '')] + SCHEMES:
        line += '%14s' % ('%+.2f' % geo(stat(ks, sk)))
    print(line + '%8d' % len(ks))

print()
print('===== 逐窗明细（%）=====')
print('%-24s %6s %10s %10s %12s %12s %12s' %
      ('窗口', '长度', '原版', 'h5s9', 'T5', 'S4', 'T1'))
print('-' * 90)
for k in done:
    d = rows[k]
    mark = ' *' if k in SELECT else '  '
    print('%-24s %4d月 %+10.2f %+10.2f %+12.2f %+12.2f %+12.2f' % (
        '%s~%s%s' % (k[0][:7], k[1][:7], mark),
        d['months'], d['base'], d['h5s9'], d['t5'], d['s4'], d['t1']))
print('  （* 标记的是当初用于选方案的 A~F 窗口，OOS24 口径下被剔除）')
