# -*- coding: utf-8 -*-
"""时间关联性检验：盈利结果是否与时间有关？

设计（用户指定：随机取30个时间点，2010年至今，窗口 1/2/3/5/8 年）：
- 种子 20260907 固定可复现；按月粒度取起点。
- 分层抽样：每种窗口长度(12/24/36/60/96个月)各 6 个窗口 = 30 个，保证每种长度有足够样本做分组分析。
  每种长度的起点在 [2010-01, 2026-09 - 长度] 内均匀随机（保证窗口完整不截断）。
- 两方案：baseline原版(MIN_SCORE=8, LOSS_HARD_START_DAY=15) vs hard5_score9(MIN_SCORE=9, LOSS_HARD_START_DAY=5)。
- 输出：scripts/hoshi_time_corr_windows.csv + 控制台汇总（含Pearson相关系数）。
"""
import importlib.util
import os
import random
import calendar
from datetime import date

random.seed(20260907)

spec = importlib.util.spec_from_file_location(
    'hbe', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_backtest_exp.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_csv_long')
code_bars, names, all_dates = hbe.load_data(CSV_DIR)
INIT = 500000.0


def add_months(y, m, n):
    tot = m - 1 + n
    return (y + tot // 12, tot % 12 + 1)


def month_last_day(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def make_windows():
    """分层：长度[12,24,36,60,96]个月各6个；起点均匀取自 [2010-01, 2026-09-长度] 内的某月1日。"""
    wins = []
    for length_m in [12, 24, 36, 60, 96]:
        # 允许起点上限：窗口结束 <= 2026-09
        limit_y, limit_m = add_months(2026, 9, -length_m)
        opts = []
        y, m = 2010, 1
        while (y, m) <= (limit_y, limit_m):
            opts.append((y, m))
            y, m = add_months(y, m, 1)
        picks = [random.choice(opts) for _ in range(6)]
        for (sy, sm) in picks:
            ey, em = add_months(sy, sm, length_m - 1)
            e = month_last_day(ey, em)
            wins.append({'len_m': length_m, 'start': date(sy, sm, 1), 'end': e})
    random.shuffle(wins)  # 打乱执行顺序，避免长度聚集影响进度观测
    return wins


WINDOWS = make_windows()

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15,
            MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO')
H5S9 = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=5,
            MIN_SCORE=9.0, MAX_SLOTS=10, EXIT_MODE='AUTO')


def run(cfg, s, e):
    hbe.TOTAL_CAPITAL = INIT
    for k, v in cfg.items():
        setattr(hbe, k, v)
    res = hbe.run_backtest(code_bars, names, all_dates,
                           start=s.isoformat(), end=e.isoformat())
    ret = (res['final_capital'] - INIT) / INIT * 100.0
    return ret, len(res['closed'])


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float('nan')
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return float('nan')
    return cov / (vx * vy) ** 0.5


rows = []
print('%-4s %-11s %-11s %5s %9s %9s %7s %7s' %
      ('#', 'start', 'end', '年限', '原版%', 'h5s9%', '原版笔', 'h5s9笔'), flush=True)
for i, w in enumerate(WINDOWS, 1):
    s, e = w['start'], w['end']
    rb, nb = run(BASE, s, e)
    rh, nh = run(H5S9, s, e)
    years = w['len_m'] / 12.0
    rows.append(dict(start=s, end=e, len_m=w['len_m'], base=rb, h5s9=rh))
    print('%-4d %-11s %-11s %5.1f %+9.2f %+9.2f %7d %7d  (累计%d/%d)' %
          (i, s.isoformat(), e.isoformat(), years, rb, rh, nb, nh, i, len(WINDOWS)), flush=True)

# ---- 写CSV ----
csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_time_corr_windows.csv')
with open(csv_path, 'w', encoding='utf-8') as f:
    f.write('start,end,len_months,base_pct,h5s9_pct\n')
    for r in rows:
        f.write('%s,%s,%d,%.4f,%.4f\n' % (r['start'], r['end'], r['len_m'], r['base'], r['h5s9']))

# ---- 统计 ----
print('\n===== 汇总统计 =====', flush=True)
for key, label in [('base', '原版'), ('h5s9', 'hard5_score9')]:
    rets = [r[key] for r in rows]
    pos = sum(1 for v in rets if v > 0)
    print('%-14s 均值%+7.2f%% 中位%+7.2f%% 最差%+7.2f%% 最好%+7.2f%% 正收益%d/30' %
          (label, sum(rets) / len(rets), sorted(rets)[15], min(rets), max(rets), pos))

print('\n--- 盈利 vs 起点年代 (Pearson r) ---', flush=True)
for key, label in [('base', '原版'), ('h5s9', 'hard5_score9')]:
    xs = [r['start'].year + (r['start'].month - 1) / 12.0 for r in rows]
    ys = [r[key] for r in rows]
    print('%-14s r = %+.3f' % (label, pearson(xs, ys)))

print('\n--- 盈利 vs 窗口长度 (Pearson r, 用月数) ---', flush=True)
for key, label in [('base', '原版'), ('h5s9', 'hard5_score9')]:
    xs = [r['len_m'] for r in rows]
    ys = [r[key] for r in rows]
    print('%-14s r = %+.3f' % (label, pearson(xs, ys)))

print('\n--- 按窗口长度分组 ---', flush=True)
for lm in [12, 24, 36, 60, 96]:
    sub = [r for r in rows if r['len_m'] == lm]
    b = [r['base'] for r in sub]
    h = [r['h5s9'] for r in sub]
    print('%2d年窗口(%d个): 原版 均值%+7.2f%% 正%d/%d | h5s9 均值%+7.2f%% 正%d/%d' %
          (lm // 12, len(sub), sum(b) / len(b), sum(1 for v in b if v > 0), len(b),
           sum(h) / len(h), sum(1 for v in h if v > 0), len(h)))

print('\n完成. CSV: %s' % csv_path, flush=True)
