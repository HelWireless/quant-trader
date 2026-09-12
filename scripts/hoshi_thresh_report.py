# -*- coding: utf-8 -*-
"""阈值对照报告：LOSS_HARD_PCT -6.0% vs -8.2%（基座 = 方案 B）

数据源：
  组1 (30窗, 种子20260907): hoshi_thr1_t6.csv   vs  hoshi_abl1_b.csv  (= 方案B + -8.2%)
  组2 (30窗, 种子20260911): hoshi_thr2_t6.csv   vs  hoshi_abl2_b.csv
  交叉校验：hoshi_thr1_t8.csv / hoshi_thr2_t8.csv（本次复核跑的 t8 窗口，
           必须与 abl*_b.csv 逐位相同）

用法: python hoshi_thresh_report.py
输出: 控制台报告 + hoshi_thresh_result.csv + hoshi_thresh_result.md
"""
import csv
import math
import os
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))


def geo(vals):
    p = 1.0
    for v in vals:
        p *= (1.0 + v / 100.0)
    return (p ** (1.0 / len(vals)) - 1.0) * 100.0 if vals else float('nan')


def mean(vals):
    return sum(vals) / len(vals) if vals else float('nan')


def median(vals):
    if not vals:
        return float('nan')
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def paired_t(a, b):
    """返回 (均值差, t 值)。a、b 为逐窗配对序列。"""
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    if n < 2:
        return (mean(d), float('nan'))
    m = mean(d)
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
    if sd == 0:
        return (m, float('inf') if m > 0 else (float('-inf') if m < 0 else 0.0))
    return (m, m / (sd / math.sqrt(n)))


def sign_p(w, n):
    """精确二项双尾 p（p=0.5）。w=胜数, n=非平局数。"""
    if n == 0:
        return 1.0
    k = min(w, n - w)
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2.0 ** n) * 2.0
    return min(p, 1.0)


def load(path):
    d = {}
    if not os.path.exists(path):
        return d
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r.get('start') and r.get('pct') not in (None, ''):
                try:
                    d[(r['start'], r['end'])] = (float(r['pct']), int(r.get('trades') or 0),
                                                 int(r.get('len_months') or 0))
                except ValueError:
                    pass
    return d


def ordered(path):
    """按窗口文件顺序返回 [(s,e,m,pct,trades)]"""
    out = []
    for fn, g in (('hoshi_time_corr_windows.csv', '1'), ('hoshi_oos2_windows.csv', '2')):
        if not path.startswith('hoshi_thr%s' % g) and not path.startswith('hoshi_abl%s' % g):
            continue
        with open(os.path.join(HERE, fn), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                out.append((r['start'], r['end'], int(r['len_months'])))
    return out


def collect(group):
    """返回 (windows, t6_dict, t8_dict)。"""
    ab = load(os.path.join(HERE, 'hoshi_abl%s_b.csv' % group))
    t6 = load(os.path.join(HERE, 'hoshi_thr%s_t6.csv' % group))
    t8 = dict(ab)
    t8.update(load(os.path.join(HERE, 'hoshi_thr%s_t8.csv' % group)))
    win_path = 'hoshi_time_corr_windows.csv' if group == '1' else 'hoshi_oos2_windows.csv'
    windows = []
    with open(os.path.join(HERE, win_path), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            windows.append((r['start'], r['end'], int(r['len_months'])))
    return windows, t6, t8


def stats(vals, trades):
    return dict(n=len(vals), geo=geo(vals), mean=mean(vals), med=median(vals),
                worst=min(vals) if vals else float('nan'),
                neg=sum(1 for v in vals if v < 0),
                avg_tr=mean(trades) if trades else float('nan'))


def main():
    groups = {}
    for g in ('1', '2'):
        windows, t6, t8 = collect(g)
        pairs = []
        for (s, e, m) in windows:
            a = t6.get((s, e))
            b = t8.get((s, e))
            if a and b:
                pairs.append((s, e, m, a[0], b[0], a[1], b[1]))
        groups[g] = pairs

    lines = []
    W = lines.append
    W('=' * 96)
    W('硬止损阈值对照：LOSS_HARD_PCT -6.0% vs -8.2%   基座 = 方案B（9分/启用日5/R3关/广度20）')
    W('=' * 96)

    all_pairs = []
    for g in ('1', '2'):
        all_pairs += groups[g]

    # ---- 单组 + 合并 ----
    for g in ('1', '2', 'ALL'):
        pairs = all_pairs if g == 'ALL' else groups[g]
        if not pairs:
            continue
        v6 = [p[3] for p in pairs]
        v8 = [p[4] for p in pairs]
        tr6 = [p[5] for p in pairs]
        tr8 = [p[6] for p in pairs]
        s6 = stats(v6, tr6)
        s8 = stats(v8, tr8)
        W('')
        W('### %s  （%d/%d 窗有配对结果）'
          % ('两组合并' if g == 'ALL' else '第%s组' % g,
             len(pairs), 30))
        W('  %-16s %10s %10s %10s %10s %6s %8s' %
          ('方案', '几何', '等权', '中位', '最差', '负窗', '均笔数'))
        for name, s in (('-6.0% (实盘)', s6), ('-8.2% (基线B)', s8)):
            W('  %-16s %+9.2f%% %+9.2f%% %+9.2f%% %+9.2f%% %4d/%d %8.0f'
              % (name, s['geo'], s['mean'], s['med'], s['worst'], s['neg'], s['n'], s['avg_tr']))

        d = [p[3] - p[4] for p in pairs]
        wins = sum(1 for x in d if x > 1e-9)
        losses = sum(1 for x in d if x < -1e-9)
        ties = len(d) - wins - losses
        mt, tv = paired_t(v6, v8)
        pv = sign_p(wins, wins + losses)
        W('')
        W('  配对差分 (-6.0%) − (-8.2%)：')
        W('    均值 %+.2f pp   中位 %+.2f pp   几何差 %+.2f pp'
          % (mean(d), median(d), geo(v6) - geo(v8)))
        W('    配对 t = %.2f   （|t|>2 视为显著）' % tv)
        W('    胜 %d / 负 %d / 平 %d  → 胜率 %.0f%%   符号检验精确双尾 p = %.4f'
          % (wins, losses, ties, 100.0 * wins / max(1, wins + losses), pv))
        W('    结论：%s' % ('-6.0% 显著更优' if (pv < 0.05 and mt > 0)
                          else ('-8.2% 显著更优' if (pv < 0.05 and mt < 0)
                                else '两者无统计显著差异')))

        # 按持有期分档
        W('')
        W('  按持有期分档（-6.0% 视角）：')
        W('    %-10s %4s %10s %10s %10s %8s %10s' %
          ('长度', '窗数', '几何-6.0', '几何-8.2', '均差pp', '胜/负', 'p'))
        buckets = {}
        for p in pairs:
            buckets.setdefault(p[2], []).append(p)
        for m in sorted(buckets):
            bk = buckets[m]
            b6 = [x[3] for x in bk]
            b8 = [x[4] for x in bk]
            bd = [x[3] - x[4] for x in bk]
            bw = sum(1 for x in bd if x > 1e-9)
            bl = sum(1 for x in bd if x < -1e-9)
            W('    %-10s %4d %+9.2f%% %+9.2f%% %+9.2f %6d/%-3d %10.4f'
              % ('%d月' % m, len(bk), geo(b6), geo(b8), mean(bd), bw, bl,
                 sign_p(bw, bw + bl)))

        # 差异最大的窗口
        W('')
        W('  差异最大的 5 窗（-6.0% 减 -8.2%）：')
        for p in sorted(pairs, key=lambda x: -(x[3] - x[4]))[:5]:
            W('    %s~%s (%2d月)  -6.0%% %+9.2f%%  -8.2%% %+9.2f%%  差 %+9.2f pp'
              % (p[0][:7], p[1][:7], p[2], p[3], p[4], p[3] - p[4]))
        W('  ...')
        for p in sorted(pairs, key=lambda x: (x[3] - x[4]))[:5]:
            W('    %s~%s (%2d月)  -6.0%% %+9.2f%%  -8.2%% %+9.2f%%  差 %+9.2f pp'
              % (p[0][:7], p[1][:7], p[2], p[3], p[4], p[3] - p[4]))

    # ---- 锚点交叉校验 ----
    W('')
    W('=' * 96)
    W('锚点交叉校验（本次跑的 t8 窗口 vs abl*_b.csv，应逐位相同）')
    W('=' * 96)
    bad = 0
    for g in ('1', '2'):
        ab = load(os.path.join(HERE, 'hoshi_abl%s_b.csv' % g))
        t8c = load(os.path.join(HERE, 'hoshi_thr%s_t8.csv' % g))
        if not t8c:
            W('  第%s组: 未跑复核窗口' % g)
            continue
        for k, v in sorted(t8c.items()):
            ref = ab.get(k)
            if ref is None:
                W('  第%s组 %s~%s: 锚点缺失' % (g, k[0], k[1]))
                bad += 1
                continue
            ok = abs(v[0] - ref[0]) < 1e-4 and v[1] == ref[1]
            if not ok:
                bad += 1
            W('  第%s组 %s~%s  %+10.4f%%/笔%-4d  vs 锚点 %+10.4f%%/笔%-4d  %s'
              % (g, k[0][:7], k[1][:7], v[0], v[1], ref[0], ref[1],
                 'OK' if ok else '★不一致'))
    W('')
    W('锚点校验：%s' % ('全部通过 ✓' if bad == 0 else '有 %d 处不一致 ✗' % bad))

    txt = '\n'.join(lines)
    print(txt, flush=True)

    with open(os.path.join(HERE, 'hoshi_thresh_result.md'), 'w', encoding='utf-8') as f:
        f.write('# 硬止损阈值对照：-6.0% vs -8.2%\n\n```\n' + txt + '\n```\n')

    with open(os.path.join(HERE, 'hoshi_thresh_result.csv'), 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['group', 'start', 'end', 'len_months', 'pct_m6', 'trades_m6',
                    'pct_m82', 'trades_m82', 'diff_pp'])
        for g in ('1', '2'):
            for p in groups[g]:
                w.writerow([g, p[0], p[1], p[2], '%.4f' % p[3], p[5],
                            '%.4f' % p[4], p[6], '%.4f' % (p[3] - p[4])])
    print('\n写出: hoshi_thresh_result.md / hoshi_thresh_result.csv', flush=True)


if __name__ == '__main__':
    main()
