# -*- coding: utf-8 -*-
"""读取 hoshi_time_corr_windows.csv，生成时间关联性自包含 HTML 报告（内嵌SVG，离线可开）。
用法: python scripts/hoshi_time_corr_report.py
"""
import csv
import math
import os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, 'hoshi_time_corr_windows.csv')
OUT = os.path.join(HERE, '..', 'docs', 'Hoshi_时间关联性报告_2026-09-08.html')

rows = []
with open(CSV_PATH, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        rows.append({
            'start': date.fromisoformat(r['start']), 'end': date.fromisoformat(r['end']),
            'len': int(r['len_months']),
            'base': float(r['base_pct']), 'h5s9': float(r['h5s9_pct']),
        })
rows.sort(key=lambda r: r['start'])


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    return cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else float('nan')


def linreg(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    k = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
    return k, my - k * mx


POS, NEG = '#E24B4A', '#3B8E4B'   # 涨红跌绿
GRAY, H5 = '#888780', '#534AB7'


def scatter_svg():
    W, H, mL, mR, mT, mB = 660, 330, 52, 16, 18, 44
    pw, ph = W - mL - mR, H - mT - mB
    xs = [r['start'].year + (r['start'].month - 1) / 12.0 for r in rows]
    ymin = min(min(r['base'] for r in rows), min(r['h5s9'] for r in rows))
    ymax = max(max(r['base'] for r in rows), max(r['h5s9'] for r in rows))
    pad = (ymax - ymin) * 0.12 + 1
    y0, y1 = ymin - pad, ymax + pad

    def X(v): return mL + (v - 2009.8) / (2026.9 - 2009.8) * pw
    def Y(v): return mT + (y1 - v) / (y1 - y0) * ph

    s = ['<svg viewBox="0 0 %d %d" style="width:100%%;font-family:sans-serif">' % (W, H)]
    for gv in range(int(math.floor(y0 / 20) * 20), int(y1) + 1, 20):
        yy = Y(gv)
        s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e3da" stroke-width="1"/>'
                 % (mL, yy, W - mR, yy))
        s.append('<text x="%d" y="%.1f" font-size="11" fill="#888" text-anchor="end">%+d%%</text>'
                 % (mL - 6, yy + 4, gv))
    for gy in range(2010, 2027, 2):
        s.append('<text x="%.1f" y="%d" font-size="11" fill="#888" text-anchor="middle">%d</text>'
                 % (X(gy), H - mB + 16, gy))
    zy = Y(0)
    s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#999" stroke-width="1.2" stroke-dasharray="4 3"/>'
             % (mL, zy, W - mR, zy))
    for key, marker in [('base', 'circle'), ('h5s9', 'square')]:
        k, b = linreg(xs, [r[key] for r in rows])
        col = GRAY if key == 'base' else H5
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.85"/>'
                 % (X(2010), Y(k * 2010 + b), X(2026), Y(k * 2026 + b), col))
        for r, xv in zip(rows, xs):
            v = r[key]
            c = POS if v > 0 else NEG
            if marker == 'circle':
                s.append('<circle cx="%.1f" cy="%.1f" r="4.5" fill="%s" stroke="%s" stroke-width="1" opacity="0.9"/>'
                         % (X(xv), Y(v), c, col))
            else:
                s.append('<rect x="%.1f" y="%.1f" width="8" height="8" fill="%s" stroke="%s" stroke-width="1" opacity="0.9"/>'
                         % (X(xv) - 4, Y(v) - 4, c, col))
    s.append('</svg>')
    return ''.join(s), pearson(xs, [r['base'] for r in rows]), pearson(xs, [r['h5s9'] for r in rows])


def bars_svg():
    W, H, mL, mR, mT, mB = 660, 300, 52, 16, 18, 60
    pw, ph = W - mL - mR, H - mT - mB
    groups = [12, 24, 36, 60, 96]
    stats = {}
    allv = []
    for lm in groups:
        sub = [r for r in rows if r['len'] == lm]
        stats[lm] = {
            'base': sum(r['base'] for r in sub) / len(sub),
            'h5s9': sum(r['h5s9'] for r in sub) / len(sub),
            'base_pos': sum(1 for r in sub if r['base'] > 0), 'h5s9_pos': sum(1 for r in sub if r['h5s9'] > 0),
            'n': len(sub)}
        allv += [stats[lm]['base'], stats[lm]['h5s9']]
    ymin = min(0, min(allv)) - 5
    ymax = max(allv) + 8

    def Y(v): return mT + (ymax - v) / (ymax - ymin) * ph
    gw = pw / len(groups)
    s = ['<svg viewBox="0 0 %d %d" style="width:100%%;font-family:sans-serif">' % (W, H)]
    for gv in range(int(math.floor(ymin / 10) * 10), int(ymax) + 1, 10):
        yy = Y(gv)
        s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e3da"/>'
                 % (mL, yy, W - mR, yy))
        s.append('<text x="%d" y="%.1f" font-size="11" fill="#888" text-anchor="end">%+d%%</text>'
                 % (mL - 6, yy + 4, gv))
    zy = Y(0)
    s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#999"/>' % (mL, zy, W - mR, zy))
    for gi, lm in enumerate(groups):
        gx = mL + gi * gw
        st = stats[lm]
        bw = 34
        for bi, (key, col, lab) in enumerate([('base', GRAY, '原版'), ('h5s9', H5, 'h5s9')]):
            v = st[key]
            x = gx + gw / 2 - bw - 4 + bi * (bw + 8)
            ytop, hgt = (Y(v), Y(0) - Y(v)) if v >= 0 else (Y(0), Y(v) - Y(0))
            s.append('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" fill="%s" rx="2"/>'
                     % (x, ytop, bw, max(hgt, 1), col))
            ty = ytop - 5 if v >= 0 else ytop + hgt + 13
            s.append('<text x="%.1f" y="%.1f" font-size="11" fill="#555" text-anchor="middle">%+.1f%%</text>'
                     % (x + bw / 2, ty, v))
        s.append('<text x="%.1f" y="%d" font-size="12" fill="#444" text-anchor="middle">%d年窗口</text>'
                 % (gx + gw / 2, H - mB + 18, lm // 12))
        s.append('<text x="%.1f" y="%d" font-size="11" fill="#888" text-anchor="middle">正收益 原%d/%d · 改%d/%d</text>'
                 % (gx + gw / 2, H - mB + 34, st['base_pos'], st['n'], st['h5s9_pos'], st['n']))
    s.append('</svg>')
    return ''.join(s), stats


def interp(r):
    a = abs(r)
    if a < 0.2: return '基本无关（|r|<0.2）'
    if a < 0.4: return '弱相关'
    if a < 0.6: return '中等相关'
    return '强相关'


svg1, r_base_year, r_h5_year = scatter_svg()
svg2, stats = bars_svg()
xs_len = [r['len'] for r in rows]
r_base_len = pearson(xs_len, [r['base'] for r in rows])
r_h5_len = pearson(xs_len, [r['h5s9'] for r in rows])

b_rets = [r['base'] for r in rows]
h_rets = [r['h5s9'] for r in rows]

def table_rows():
    out = []
    for r in rows:
        c1 = POS if r['base'] > 0 else NEG
        c2 = POS if r['h5s9'] > 0 else NEG
        out.append('<tr><td>%s</td><td>%s</td><td>%d年</td>'
                   '<td style="color:%s">%+.2f%%</td><td style="color:%s">%+.2f%%</td><td>%+.1fpp</td></tr>'
                   % (r['start'].isoformat(), r['end'].isoformat(), r['len'] // 12,
                      c1, r['base'], c2, r['h5s9'], r['h5s9'] - r['base']))
    return ''.join(out)

html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>Hoshi 盈利-时间关联性报告</title>
<style>
body{{font-family:-apple-system,'Segoe UI',sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#222;background:#fff;line-height:1.65}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:32px;border-bottom:1px solid #eee;padding-bottom:6px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #e3e1d8;padding:5px 9px;text-align:right}} th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3){{text-align:center}}
th{{background:#f5f4ee}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}}
.card{{background:#f7f6f1;border-radius:10px;padding:12px 14px}}
.card .v{{font-size:22px;font-weight:600}} .card .l{{font-size:12px;color:#777}}
.legend{{font-size:12px;color:#777;margin:4px 0 8px}} .legend span{{margin-right:14px}}
</style></head><body>
<h1>Hoshi 盈利-时间关联性检验报告</h1>
<p><b>设计</b>：随机种子 20260907，2010-01 ~ 2026-08 按月粒度随机取 30 个起点，窗口长度 1/2/3/5/8 年分层各 6 个。
两方案统一口径：每窗口独立 50 万、白名单 5262 只、R3+广度门控、T+1、实盘费率。
方案：<b>原版</b>（评分8/第15天止损） vs <b>hard5_score9</b>（评分9/第5天硬止损）。</p>

<div class="cards">
<div class="card"><div class="l">原版 正收益窗口</div><div class="v">{bp}/30</div><div class="l">均值 {bm:+.2f}%  最差 {bw:+.2f}%</div></div>
<div class="card"><div class="l">h5s9 正收益窗口</div><div class="v">{hp}/30</div><div class="l">均值 {hm:+.2f}%  最差 {hw:+.2f}%</div></div>
<div class="card"><div class="l">h5s9 跑赢原版</div><div class="v">{out}/30</div><div class="l">平均差 {od:+.2f}pp</div></div>
<div class="card"><div class="l">起点年代相关 r</div><div class="v">{r1b:+.2f} / {r1h:+.2f}</div><div class="l">原版 / h5s9 —— {i1} / {i1h}</div></div>
<div class="card"><div class="l">窗口长度相关 r</div><div class="v">{r2b:+.2f} / {r2h:+.2f}</div><div class="l">原版 / h5s9 —— {i2} / {i2h}</div></div>
</div>

<h2>一、收益 vs 起点年代（30 个窗口散点 + 线性回归）</h2>
<div class="legend">
<span><span style="color:{POS}">●</span> 盈利</span>
<span><span style="color:{NEG}">●</span> 亏损</span>
<span><b>圆形 = 原版</b>（灰虚线回归）</span>
<span><b>方块 = hard5_score9</b>（紫虚线回归）</span>
</div>
{SVG1}

<h2>二、收益 vs 窗口长度（分组均值 + 各组正收益率）</h2>
{SVG2}

<h2>三、结论</h2>
{CONCLUSION}

<h2>四、30 窗口明细（按起点排序）</h2>
<table><tr><th>起点</th><th>结束</th><th>长度</th><th>原版</th><th>h5s9</th><th>差</th></tr>
{TABLE}
</table>
<p style="color:#888;font-size:12px">生成：scripts/hoshi_time_corr_report.py ｜ 数据：scripts/hoshi_time_corr_windows.csv ｜ 引擎：scripts/hoshi_backtest_exp.py（与权威 hoshi_backtest_csv.py 口径一致）</p>
</body></html>"""

bp = sum(1 for v in b_rets if v > 0)
hp = sum(1 for v in h_rets if v > 0)
out = sum(1 for r in rows if r['h5s9'] > r['base'])
od = sum(r['h5s9'] - r['base'] for r in rows) / len(rows)

conclusion = []
conclusion.append('<p><b>1. 起点年代</b>：原版 r=%+.2f（%s），h5s9 r=%+.2f（%s）。'
                  % (r_base_year, interp(r_base_year), r_h5_year, interp(r_h5_year)))
conclusion.append('<b>2. 窗口长度</b>：原版 r=%+.2f（%s），h5s9 r=%+.2f（%s）。'
                  % (r_base_len, interp(r_base_len), r_h5_len, interp(r_h5_len)))
conclusion.append('<b>3. 方案对比</b>：30 窗口中 h5s9 正收益 %d/30、原版 %d/30；h5s9 跑赢 %d/30，平均每窗口差 %+.2fpp。'
                  % (hp, bp, out, od))
conclusion.append('<b>4. 分组</b>：' + '；'.join(
    '%d年: 原%+.1f%%(正%d/%d) vs 改%+.1f%%(正%d/%d)'
    % (lm // 12, stats[lm]['base'], stats[lm]['base_pos'], stats[lm]['n'],
       stats[lm]['h5s9'], stats[lm]['h5s9_pos'], stats[lm]['n'])
    for lm in [12, 24, 36, 60, 96]) + '。</p>')

html = html.format(
    SVG1=svg1, SVG2=svg2, TABLE=table_rows(), POS=POS, NEG=NEG,
    bp=bp, hp=hp, out=out, od=od,
    bm=sum(b_rets) / 30, hm=sum(h_rets) / 30,
    bw=min(b_rets), hw=min(h_rets),
    r1b=r_base_year, r1h=r_h5_year, r2b=r_base_len, r2h=r_h5_len,
    i1=interp(r_base_year), i1h=interp(r_h5_year), i2=interp(r_base_len), i2h=interp(r_h5_len),
    CONCLUSION=''.join(conclusion))

with open(os.path.abspath(OUT), 'w', encoding='utf-8') as f:
    f.write(html)
print('报告已生成: %s' % os.path.abspath(OUT))
print('r(原版,起点年代)=%+.3f  r(h5s9,起点年代)=%+.3f' % (r_base_year, r_h5_year))
print('r(原版,窗口长度)=%+.3f  r(h5s9,窗口长度)=%+.3f' % (r_base_len, r_h5_len))
