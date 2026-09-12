# -*- coding: utf-8 -*-
"""第二组独立随机窗口（验证集 #2）。

与第一组（种子 20260907，长度 1/2/3/5/8 年）的区别：
- 新种子 20260911，完全独立抽样
- 长度换成本轮指定的 1/2/4/7 年 = [12, 24, 48, 84] 个月
- 排除与第一组完全相同的 (start,end) 组合，保证是独立样本
输出 scripts/hoshi_oos2_windows.csv
"""
import calendar
import csv
import os
import random
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260911
LENGTHS = [12, 24, 48, 84]          # 1 / 2 / 4 / 7 年
COUNTS = {12: 8, 24: 8, 48: 7, 84: 7}   # 合计 30
DATA_END_Y, DATA_END_M = 2026, 6    # 数据覆盖到的最后一个月

random.seed(SEED)


def add_months(y, m, n):
    tot = m - 1 + n
    return (y + tot // 12, tot % 12 + 1)


def month_last_day(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


# 第一组的窗口，用于去重
old = set()
p1 = os.path.join(HERE, 'hoshi_time_corr_windows.csv')
if os.path.exists(p1):
    with open(p1, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            old.add((r['start'], r['end']))

wins = []
for length_m in LENGTHS:
    limit_y, limit_m = add_months(DATA_END_Y, DATA_END_M, -length_m + 1)
    opts = []
    y, m = 2010, 1
    while (y, m) <= (limit_y, limit_m):
        opts.append((y, m))
        y, m = add_months(y, m, 1)
    picks = []
    guard = 0
    while len(picks) < COUNTS[length_m] and guard < 10000:
        guard += 1
        sy, sm = random.choice(opts)
        ey, em = add_months(sy, sm, length_m - 1)
        s = date(sy, sm, 1)
        e = month_last_day(ey, em)
        if (s.isoformat(), e.isoformat()) in old:
            continue
        if (s, e) in picks:
            continue
        picks.append((s, e))
    for s, e in picks:
        wins.append({'len_m': length_m, 'start': s, 'end': e})

random.shuffle(wins)

out = os.path.join(HERE, 'hoshi_oos2_windows.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['start', 'end', 'len_months'])
    for x in sorted(wins, key=lambda z: (z['len_m'], z['start'])):
        w.writerow([x['start'].isoformat(), x['end'].isoformat(), x['len_m']])

lines = []
lines.append('种子=%d  长度分布=%s  窗口数=%d' % (SEED, LENGTHS, len(wins)))
lines.append('已排除与第一组重复的 %d 个组合' % len(old))
lines.append('输出: %s' % out)
lines.append('')
lines.append('%-14s %-14s %6s' % ('start', 'end', '月'))
for x in sorted(wins, key=lambda z: (z['len_m'], z['start'])):
    lines.append('%-14s %-14s %6d' % (x['start'], x['end'], x['len_m']))

with open(os.path.join(HERE, '_oos2_windows.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('ok')
