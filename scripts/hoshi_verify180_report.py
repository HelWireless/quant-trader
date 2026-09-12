# -*- coding: utf-8 -*-
"""二次验证报告：180 窗 × 3 方案（base / B / Bp），数据源 2005 年起。

读 scripts/verify180_raw.csv，输出：
  - 三方案总体对比（几何/等权/中位/最差/负窗/笔数）
  - 两两配对检验（配对 t、符号检验精确双尾 p、胜率）
  - 按持有期分档（1~8 年）
  - 按起点年份分档
  - 逐窗明细 CSV 与 Markdown 报告
"""
import csv
import math
import os
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'verify180_raw.csv')
LABEL = {'base': '原版(8分/止损15/R3开)',
         'B': 'B(9分/止损5/R3关/−8.2%)',
         'Bp': "B'(9分/止损5/R3关/−6.0%)"}
ORDER = ['base', 'B', 'Bp']


def geo(vals):
    p = 1.0
    for v in vals:
        p *= (1.0 + v / 100.0)
    return (p ** (1.0 / len(vals)) - 1.0) * 100.0 if vals else float('nan')


def _mean(v):
    return sum(v) / len(v) if v else float('nan')


def _median(v):
    if not v:
        return float('nan')
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def paired_t(a, b):
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    if n < 2:
        return _mean(d), float('nan')
    m = _mean(d)
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
    if sd == 0:
        return m, float('inf') if m else 0.0
    return m, m / (sd / math.sqrt(n))


def sign_p(w, n):
    if n == 0:
        return 1.0
    k = min(w, n - w)
    return min(2.0 * sum(comb(n, i) for i in range(k + 1)) / (2.0 ** n), 1.0)


def main():
    data = {}
    meta = {}
    with open(SRC, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if not r.get('scheme') or r.get('pct') in (None, ''):
                continue
            key = (r['start'], r['end'])
            meta[key] = int(r['len_months'])
            data.setdefault(r['scheme'], {})[key] = (float(r['pct']),
                                                     int(r.get('trades') or 0))
    keys = sorted(meta.keys())
    print('窗口数 %d，方案 %s' % (len(keys), list(data.keys())))

    L = []
    W = L.append
    W('=' * 92)
    W('二次验证：180 窗 × 3 方案（数据 2005 起，独立重建引擎 hoshi_rebuild_v2）')
    W('=' * 92)
    W('')
    W('%-28s %10s %10s %10s %10s %7s %8s' %
      ('方案', '几何', '等权', '中位', '最差', '负窗', '均笔数'))
    vals = {}
    trs = {}
    for sk in ORDER:
        if sk not in data:
            continue
        v = [data[sk][k][0] for k in keys if k in data[sk]]
        t = [data[sk][k][1] for k in keys if k in data[sk]]
        vals[sk] = v
        trs[sk] = t
        W('%-28s %+9.2f%% %+9.2f%% %+9.2f%% %+9.2f%% %3d/%d %8.0f'
          % (LABEL[sk], geo(v), _mean(v), _median(v), min(v),
             sum(1 for x in v if x < 0), len(v), _mean(t)))

    # ---- 两两配对 ----
    W('')
    W('=== 两两配对检验（逐窗同窗口对比）===')
    for a, b in (('Bp', 'B'), ('Bp', 'base'), ('B', 'base')):
        if a not in vals or b not in vals:
            continue
        ks = [k for k in keys if k in data[a] and k in data[b]]
        va = [data[a][k][0] for k in ks]
        vb = [data[b][k][0] for k in ks]
        w = sum(1 for x, y in zip(va, vb) if x - y > 1e-9)
        lo = sum(1 for x, y in zip(va, vb) if x - y < -1e-9)
        m, tv = paired_t(va, vb)
        pv = sign_p(w, w + lo)
        W('')
        W('  %s  −  %s' % (LABEL[a], LABEL[b]))
        W('    窗口 %d | 均值差 %+.2fpp | 中位差 %+.2fpp | 几何差 %+.2fpp'
          % (len(ks), m, _median([x - y for x, y in zip(va, vb)]), geo(va) - geo(vb)))
        W('    配对 t = %.2f | 胜 %d / 负 %d / 平 %d → 胜率 %.0f%% | 符号检验 p = %.4g'
          % (tv, w, lo, len(ks) - w - lo, 100.0 * w / max(1, w + lo), pv))
        W('    判定：%s' % ('★显著更优' if (pv < 0.05 and m > 0)
                          else ('显著更差' if (pv < 0.05 and m < 0) else '无显著差异')))

    # ---- 按持有期分档 ----
    W('')
    W('=== 按持有期分档（几何收益）===')
    W('  %-8s %5s %12s %12s %12s' % ('长度', '窗数', '原版', 'B', "B'"))
    buckets = {}
    for k in keys:
        y = max(1, min(8, meta[k] // 12))
        buckets.setdefault(y, []).append(k)
    for y in sorted(buckets):
        ks = buckets[y]
        row = []
        for sk in ORDER:
            v = [data[sk][k][0] for k in ks if sk in data and k in data[sk]]
            row.append(geo(v) if v else float('nan'))
        W('  %-8s %5d %+11.2f%% %+11.2f%% %+11.2f%%'
          % ('%d年' % y, len(ks), row[0], row[1], row[2]))

    # ---- 按起点年份分档 ----
    W('')
    W('=== 按起点年份分档（几何收益）===')
    W('  %-8s %5s %12s %12s %12s' % ('起点年', '窗数', '原版', 'B', "B'"))
    yb = {}
    for k in keys:
        yb.setdefault(k[0][:4], []).append(k)
    for y in sorted(yb):
        ks = yb[y]
        row = []
        for sk in ORDER:
            v = [data[sk][k][0] for k in ks if sk in data and k in data[sk]]
            row.append(geo(v) if v else float('nan'))
        W('  %-8s %5d %+11.2f%% %+11.2f%% %+11.2f%%'
          % (y, len(ks), row[0], row[1], row[2]))

    txt = '\n'.join(L)
    print(txt)

    with open(os.path.join(HERE, 'verify180_report.md'), 'w', encoding='utf-8') as f:
        f.write('# 二次验证：180 窗 × 3 方案\n\n```\n' + txt + '\n```\n')

    with open(os.path.join(HERE, 'verify180_detail.csv'), 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['start', 'end', 'len_months', 'base_pct', 'B_pct', 'Bp_pct',
                    'base_tr', 'B_tr', 'Bp_tr', 'Bp_minus_B', 'Bp_minus_base'])
        for k in keys:
            b0 = data.get('base', {}).get(k)
            b1 = data.get('B', {}).get(k)
            b2 = data.get('Bp', {}).get(k)
            w.writerow([k[0], k[1], meta[k],
                        '%.4f' % b0[0] if b0 else '', '%.4f' % b1[0] if b1 else '',
                        '%.4f' % b2[0] if b2 else '',
                        b0[1] if b0 else '', b1[1] if b1 else '', b2[1] if b2 else '',
                        '%.4f' % (b2[0] - b1[0]) if (b1 and b2) else '',
                        '%.4f' % (b2[0] - b0[0]) if (b0 and b2) else ''])
    print('\n写出: verify180_report.md / verify180_detail.csv')


if __name__ == '__main__':
    main()
