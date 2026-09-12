# -*- coding: utf-8 -*-
"""生成二次验证用的 180 个随机窗口。

规则：
  - 60 个随机起点（精确到天），范围 2005-01-01 ~ 2018-09-11
    上限锁在 2018-09 是为了保证最长 8 年的窗口也不越出数据末端 2026-09-11，
    避免"截断窗口"引入偏差。
  - 每个起点随机 3 个持有期：1~8 年，精确到月（12~96 个月）
  - 合计 180 窗

用法: python gen_windows_180.py [seed]
输出: scripts/windows_180.csv
"""
import calendar
import csv
import os
import random
import sys
from datetime import date

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20260913
N_NODES = 60
N_LEN = 3
START_LO = date(2005, 1, 1)
START_HI = date(2018, 9, 11)
DATA_END = date(2026, 9, 11)
LEN_RANGE = (12, 96)      # 1~8 年，单位月

random.seed(SEED)


def add_months(d, m):
    y = d.year + (d.month - 1 + m) // 12
    mo = (d.month - 1 + m) % 12 + 1
    day = min(d.day, calendar.monthrange(y, mo)[1])
    return date(y, mo, day)


span = (START_HI - START_LO).days
starts = sorted(START_LO.fromordinal(START_LO.toordinal() + random.randint(0, span))
                for _ in range(N_NODES))

rows = []
for s in starts:
    lens = [random.randint(*LEN_RANGE) for _ in range(N_LEN)]
    for m in lens:
        e = add_months(s, m)
        assert e <= DATA_END, '窗口越界: %s + %d月 = %s' % (s, m, e)
        rows.append((s.isoformat(), e.isoformat(), m))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'windows_180.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['start', 'end', 'len_months'])
    for r in rows:
        w.writerow(r)

print('种子 %d，节点 %d 个，窗口 %d 个' % (SEED, N_NODES, len(rows)))
print('输出: %s' % out)

# 分布自检
import collections
buckets = collections.Counter()
for _, _, m in rows:
    y = m // 12
    buckets['%d年' % min(y, 8)] += 1
print('\n持有期分布:')
for k in sorted(buckets, key=lambda x: int(x[0])):
    print('  %-5s %3d 窗' % (k, buckets[k]))
year_buckets = collections.Counter(r[0][:4] for r in rows)
print('\n起点年份分布:')
for y in sorted(year_buckets):
    print('  %s  %3d 窗' % (y, year_buckets[y]))
