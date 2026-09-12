# -*- coding: utf-8 -*-
"""独立复核外部 agent 的 90 窗对照报告（p6 vs 方案B）。

原则：不采信报告里的任何汇总数字，全部从 windows_full.csv 原始逐窗数据重算，
逐项与报告结论对拍。凡对不上的地方逐条列出。

用法: python verify_external_90w.py <windows_full.csv 路径>
"""
import csv
import math
import os
import sys
from math import comb

SRC = sys.argv[1] if len(sys.argv) > 1 else \
    r'C:\Users\cody\xwechat_files\wxid_4567lmhfs91g11_a910\temp\RWTemp\2026-09\690746ce0e0d3494fc4293a16b9d0523\windows_full.csv'


def geo(vals):
    p = 1.0
    for v in vals:
        p *= (1.0 + v / 100.0)
    return (p ** (1.0 / len(vals)) - 1.0) * 100.0


def _mean(vals):
    return sum(vals) / len(vals)


def _median(vals):
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    m = _mean(d)
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
    return m, m / (sd / math.sqrt(n))


def sign_p(w, n):
    if n == 0:
        return 1.0
    k = min(w, n - w)
    return min(2.0 * sum(comb(n, i) for i in range(k + 1)) / (2.0 ** n), 1.0)


rows = []
with open(SRC, encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if not r.get('idx'):
            continue
        rows.append(r)

print('读入 %d 个窗口\n' % len(rows))
OK, BAD = [], []


def chk(name, got, exp, tol=0.02, fmt='%s'):
    hit = (abs(got - exp) <= tol) if isinstance(exp, float) else (got == exp)
    (OK if hit else BAD).append(name)
    print('  %-34s 复算=%s  报告=%s  %s'
          % (name, fmt % got, fmt % exp, 'OK' if hit else '★不符'))


p6 = [float(r['p6_ret_pct']) for r in rows]
B = [float(r['B_ret_pct']) for r in rows]
p6_dd = [float(r['p6_max_dd_pct']) for r in rows]
B_dd = [float(r['B_max_dd_pct']) for r in rows]
p6_tr = [int(r['p6_n_trades']) for r in rows]
B_tr = [int(r['B_n_trades']) for r in rows]
wins = sum(1 for a, b in zip(p6, B) if b > a)
p6wins = sum(1 for a, b in zip(p6, B) if a > b)
tie = len(rows) - wins - p6wins

print('=== 一、90窗总账（第二节）===')
chk('逐窗对决 B 胜', wins, 69)
chk('逐窗对决 p6 胜', p6wins, 21)
print('     （平局 %d）' % tie)
chk('等权平均 p6', _mean(p6), 24.44, fmt='%+.2f%%')
chk('等权平均 B', _mean(B), 58.73, fmt='%+.2f%%')
chk('几何平均 p6', geo(p6), 22.27, fmt='%+.2f%%')
chk('几何平均 B', geo(B), 50.39, fmt='%+.2f%%')
chk('中位 p6', _median(p6), 16.48, fmt='%+.2f%%')
chk('中位 B', _median(B), 59.61, fmt='%+.2f%%')
chk('最好窗 p6', max(p6), 103.05, fmt='%+.2f%%')
chk('最好窗 B', max(B), 180.55, fmt='%+.2f%%')
chk('最差窗 p6', min(p6), -6.38, fmt='%+.2f%%')
chk('最差窗 B', min(B), -6.85, fmt='%+.2f%%')
chk('负收益窗 p6', sum(1 for v in p6 if v < 0), 12)
chk('负收益窗 B', sum(1 for v in B if v < 0), 13)

cap_p6 = sum(float(r['p6_final_capital']) for r in rows)
cap_B = sum(float(r['B_final_capital']) for r in rows)
chk('期末资金合计 p6(万)', cap_p6 / 10000.0, 3359.8531, tol=0.01, fmt='%.1f万')
chk('期末资金合计 B(万)', cap_B / 10000.0, 4285.8280, tol=0.01, fmt='%.1f万')
chk('平均每窗期末 p6', _mean([float(r['p6_final_capital']) for r in rows]), 373317.0,
    tol=1.0, fmt='%.0f')
chk('平均每窗期末 B', _mean([float(r['B_final_capital']) for r in rows]), 476203.0,
    tol=1.0, fmt='%.0f')
chk('净赚合计(万) 差', (cap_B - cap_p6) / 10000.0, 925.9749, tol=0.01, fmt='%.1f万')

print()
print('=== 三、回撤（报告未给全部，这里补全）===')
chk('平均最大回撤 p6', _mean(p6_dd), -10.97, tol=0.02, fmt='%+.2f%%')
chk('平均最大回撤 B', _mean(B_dd), -17.49, tol=0.02, fmt='%+.2f%%')
chk('中位最大回撤 p6', _median(p6_dd), -10.73, tol=0.02, fmt='%+.2f%%')
chk('中位最大回撤 B', _median(B_dd), -16.75, tol=0.02, fmt='%+.2f%%')
chk('最坏回撤 p6', min(p6_dd), -19.08, tol=0.02, fmt='%+.2f%%')
chk('最坏回撤 B', min(B_dd), -23.42, tol=0.02, fmt='%+.2f%%')
dd_p6_win = sum(1 for a, b in zip(p6_dd, B_dd) if a > b)   # 回撤更浅
chk('回撤更浅的窗口 p6', dd_p6_win, 86)

print()
print('=== 换手 / 胜率 ===')
chk('总笔数 p6', sum(p6_tr), 9380)
chk('总笔数 B', sum(B_tr), 26349)
chk('平均笔数 p6', _mean(p6_tr), 104.0, tol=0.6, fmt='%.1f')
chk('平均笔数 B', _mean(B_tr), 293.0, tol=0.6, fmt='%.1f')
chk('换手倍数', sum(B_tr) / sum(p6_tr), 2.81, tol=0.01, fmt='%.2f')
chk('单笔胜率 p6', _mean([float(r['p6_win_rate']) for r in rows]), 41.38, tol=0.02, fmt='%.2f%%')
chk('单笔胜率 B', _mean([float(r['B_win_rate']) for r in rows]), 47.58, tol=0.02, fmt='%.2f%%')
chk('平均持有 p6', _mean([float(r['p6_avg_hold']) for r in rows]), 8.3, tol=0.05, fmt='%.1f')
chk('平均持有 B', _mean([float(r['B_avg_hold']) for r in rows]), 8.7, tol=0.05, fmt='%.1f')

print()
print('=== 统计检验（配对 B-p6）===')
m, tv = paired_t(B, p6)
chk('配对均值差', m, 34.30, tol=0.02, fmt='%+.2fpp')
chk('配对 t', tv, 9.68, tol=0.02, fmt='%.2f')
chk('中位差', _median([b - a for a, b in zip(p6, B)]), 39.80, tol=0.02, fmt='%+.2fpp')
pv = sign_p(wins, wins + p6wins)
print('  符号检验 69胜21负 精确双尾 p = %.2e  （报告 3.9e-07）' % pv)

print()
print('=== 四、R3 触发（报告称 p6 90/90、总 532 次）===')
s6 = [int(r['p6_r3_stops']) for r in rows]
sB = [int(r['B_r3_stops']) for r in rows]
chk('R3 有停手的窗口数 p6', sum(1 for v in s6 if v > 0), 90)
chk('R3 总停手次数 p6', sum(s6), 532)
chk('R3 总停手次数 B', sum(sB), 0)
print('     p6 每窗平均停手 %.2f 次，最多 %d 次，最少 %d 次'
      % (_mean(s6), max(s6), min(s6)))

print()
print('=== 三、按持有期分档（表内数字）===')
buckets = {}
for r in rows:
    m_ = int(r['months'])
    k = '1~2年' if m_ <= 24 else ('2~3年' if m_ <= 36 else ('3~4年' if m_ <= 48 else '4~5年'))
    buckets.setdefault(k, []).append(r)
exp_geo = {'1~2年': (8.08, 19.71), '2~3年': (17.27, 40.91),
           '3~4年': (28.85, 68.61), '4~5年': (49.19, 109.98)}
exp_n = {'1~2年': 29, '2~3年': 24, '3~4年': 19, '4~5年': 18}
exp_dd = {'1~2年': (-9.89, -14.71), '2~3年': (-11.69, -16.66),
          '3~4年': (-11.72, -19.22), '4~5年': (-10.93, -21.26)}
for k in ('1~2年', '2~3年', '3~4年', '4~5年'):
    bk = buckets.get(k, [])
    if not bk:
        continue
    g6 = geo([float(r['p6_ret_pct']) for r in bk])
    gB = geo([float(r['B_ret_pct']) for r in bk])
    d6 = _mean([float(r['p6_max_dd_pct']) for r in bk])
    dB = _mean([float(r['B_max_dd_pct']) for r in bk])
    bw = sum(1 for r in bk if float(r['B_ret_pct']) > float(r['p6_ret_pct']))
    print('  %-6s 窗%2d(报告%2d)  p6几何%+8.2f%%(报%+7.2f%%)  B几何%+8.2f%%(报%+7.2f%%)  '
          'p6回撤%+7.2f%%(报%+7.2f%%)  B回撤%+7.2f%%(报%+7.2f%%)  B胜%d'
          % (k, len(bk), exp_n[k], g6, exp_geo[k][0], gB, exp_geo[k][1],
             d6, exp_dd[k][0], dB, exp_dd[k][1], bw))

print()
print('=' * 70)
print('复核结果：%d 项相符，%d 项不符' % (len(OK), len(BAD)))
if BAD:
    print('不符项：')
    for n in BAD:
        print('  - %s' % n)
else:
    print('★ 报告第二节全部数字与原始数据一致 —— 该部分可直接采信。')
print()
print('※ 注意：2×2 消融里的 A / C 两个配置的逐窗数据**不在本 CSV 内**，')
print('   故「止损 -6.0%% 优于 -8.2%%」这一核心结论无法用本文件复核，')
print('   需用本机引擎独立跑同口径对照来验证。')
