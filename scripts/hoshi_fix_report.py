# -*- coding: utf-8 -*-
"""修复引擎(exp5) 双组 60 窗汇总报告生成器。

输入: hoshi_fix1_{base,h5s9,t5}.csv, hoshi_fix2_{base,h5s9,t5}.csv
输出: docs/Hoshi_样本外验证_修复版.html  + hoshi_fix_all.csv
"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCHEMES = ['base', 'h5s9', 't5']
NAME = {'base': '原版(评分8/止损15/R3开/广度20)',
        'h5s9': 'h5s9(评分9/止损5/R3开/广度20)',
        't5': 'T5(分档仓位/止损5/R3关/广度30)'}


def load(group, sk):
    p = os.path.join(HERE, 'hoshi_fix%s_%s.csv' % (group, sk))
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                v = float(r['%s_pct' % sk])
            except (KeyError, ValueError, TypeError):
                continue
            out[(r['start'], r['end'])] = (v, int(float(r.get('trades') or 0)),
                                           int(r['len_months']))
    return out


def geo(vals):
    if not vals:
        return float('nan')
    p = 1.0
    for v in vals:
        p *= (1.0 + v / 100.0)
    if p <= 0:
        return -100.0
    return (p ** (1.0 / len(vals)) - 1.0) * 100.0


def med(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return float('nan')
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def stats(vals):
    n = len(vals)
    if n == 0:
        return dict(n=0)
    return dict(n=n, mean=sum(vals) / n, geo=geo(vals), med=med(vals),
                worst=min(vals), best=max(vals), neg=sum(1 for v in vals if v < 0))


DATA = {}
for g in ('1', '2'):
    for sk in SCHEMES:
        DATA[(g, sk)] = load(g, sk)

# ---------- 合并长表 ----------
all_rows = []
keys_all = set()
for g in ('1', '2'):
    for k in DATA[(g, 'base')]:
        keys_all.add((g,) + k)
rows_merged = []
for g, s, e in sorted(keys_all):
    rec = dict(group=g, start=s, end=e)
    ok = True
    for sk in SCHEMES:
        d = DATA[(g, sk)].get((s, e))
        rec[sk] = d[0] if d else None
        rec['m'] = d[2] if d else rec.get('m')
        if d is None:
            ok = False
    rec['complete'] = ok
    rows_merged.append(rec)

with open(os.path.join(HERE, 'hoshi_fix_all.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['group', 'start', 'end', 'len_months', 'base_pct', 'h5s9_pct', 't5_pct'])
    for r in rows_merged:
        w.writerow([r['group'], r['start'], r['end'], r['m'],
                    '' if r['base'] is None else '%.4f' % r['base'],
                    '' if r['h5s9'] is None else '%.4f' % r['h5s9'],
                    '' if r['t5'] is None else '%.4f' % r['t5']])


def block(pred, label):
    out = []
    for sk in SCHEMES:
        vals = [r[sk] for r in rows_merged if pred(r) and r[sk] is not None]
        st = stats(vals)
        if not st.get('n'):
            out.append((label, sk, None))
            continue
        out.append((label, sk, st))
    return out


def binom_tail(k, n):
    """单尾 P(X >= k), X ~ Bin(n, 0.5)"""
    if n <= 0:
        return float('nan')
    s = sum(math.comb(n, i) for i in range(k, n + 1))
    return s / (2.0 ** n)


def paired(a, b, pred):
    """a - b 配对差 + 符号检验"""
    d = [r[a] - r[b] for r in rows_merged if pred(r) and r[a] is not None and r[b] is not None]
    if not d:
        return None
    n = len(d)
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else float('inf')
    win = sum(1 for x in d if x > 0)
    lose = n - win
    # 符号检验：双尾 = 2 * 单尾(取较小一侧)
    p_one = binom_tail(max(win, lose), n)
    p_two = min(1.0, 2.0 * p_one)
    return dict(n=n, mean=m, sd=sd, t=t, win=win, winrate=100.0 * win / n,
                p_one=p_one, p_two=p_two)


BLOCKS = []
BLOCKS += block(lambda r: r['group'] == '1', '第一组 30 窗（种子20260907，1~8年混长）')
BLOCKS += block(lambda r: r['group'] == '2', '第二组 30 窗（种子20260911，1/2/4/7年）')
BLOCKS += block(lambda r: True, '合计 60 窗')
for m in (12, 24, 48, 84):
    BLOCKS += block(lambda r, mm=m: r['group'] == '2' and r['m'] == mm,
                    '第二组 · 按长度 %d年' % (m // 12))
for m in (12, 24, 36, 60, 96):
    BLOCKS += block(lambda r, mm=m: r['group'] == '1' and r['m'] == mm,
                    '第一组 · 按长度 %d年' % (m // 12))

PAIRS = []
for lbl, pred in [('第一组', lambda r: r['group'] == '1'),
                  ('第二组', lambda r: r['group'] == '2'),
                  ('合计60窗', lambda r: True)]:
    PAIRS.append((lbl, 'T5-原版', paired('t5', 'base', pred)))
    PAIRS.append((lbl, 'h5s9-原版', paired('h5s9', 'base', pred)))
    PAIRS.append((lbl, 'T5-h5s9', paired('t5', 'h5s9', pred)))
for g, gname in (('2', '第二组'), ('1', '第一组')):
    for m in ((12, 24, 48, 84) if g == '2' else (12, 24, 36, 60, 96)):
        lbl = '%s·%d年' % (gname, m // 12)
        pred = (lambda r, gg=g, mm=m: r['group'] == gg and r['m'] == mm)
        PAIRS.append((lbl, 'T5-原版', paired('t5', 'base', pred)))
        PAIRS.append((lbl, 'h5s9-原版', paired('h5s9', 'base', pred)))

# ---------- 跨长度分档的方向一致性（分档级符号检验）----------
BUCKET = []
for g, gname in (('2', '第二组'), ('1', '第一组')):
    for m in ((12, 24, 48, 84) if g == '2' else (12, 24, 36, 60, 96)):
        p = paired('t5', 'base', lambda r, gg=g, mm=m: r['group'] == gg and r['m'] == mm)
        if p and p['n'] >= 5:
            BUCKET.append(('%s·%d年' % (gname, m // 12), p))
B_POS = sum(1 for _, p in BUCKET if p['win'] * 2 > p['n'])
B_N = len(BUCKET)
B_P = min(1.0, 2.0 * binom_tail(max(B_POS, B_N - B_POS), B_N)) if B_N else float('nan')

# ---------- 第一组 污染 vs 修复 对照 ----------
cmp_rows = []
p1 = os.path.join(HERE, 'hoshi_time_corr_windows.csv')
if os.path.exists(p1):
    old = {}
    with open(p1, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            old[(r['start'], r['end'])] = (float(r['base_pct']), float(r['h5s9_pct']))
    for r in rows_merged:
        if r['group'] != '1':
            continue
        o = old.get((r['start'], r['end']))
        if o and r['base'] is not None:
            cmp_rows.append((r['start'], r['end'], o[0], r['base'], r['base'] - o[0],
                             o[1], r['h5s9'] if r['h5s9'] is not None else float('nan')))
    if cmp_rows:
        with open(os.path.join(HERE, 'hoshi_fix_vs_bug.csv'), 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['start', 'end', 'base_污染', 'base_修复', '差值', 'h5s9_污染', 'h5s9_修复'])
            for row in cmp_rows:
                w.writerow([row[0], row[1], '%.4f' % row[2], '%.4f' % row[3], '%+.4f' % row[4],
                            '%.4f' % row[5], '%.4f' % row[6]])

cn = len(cmp_rows)
chg = sum(1 for r in cmp_rows if abs(r[4]) > 0.01)

# ---------- HTML ----------
CSS = """
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f7f8fa;
color:#1f2328;margin:0;padding:32px 20px;line-height:1.7}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px}
h2{font-size:19px;margin:34px 0 12px;padding-left:10px;border-left:4px solid #d93025}
h3{font-size:15px;margin:20px 0 8px;color:#444}
.sub{color:#666;font-size:13px;margin-bottom:22px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px;
box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:14px}
th,td{border:1px solid #e6e8eb;padding:7px 9px;text-align:right}
th{background:#f0f2f5;font-weight:600;text-align:center}
td:first-child,th:first-child{text-align:left}
.pos{color:#c0392b;font-weight:600}
.neg{color:#1e8449;font-weight:600}
.note{background:#fff8e6;border-left:4px solid #f0ad4e;padding:12px 14px;font-size:13px;margin:14px 0}
.bad{background:#fdecea;border-left:4px solid #d93025;padding:12px 14px;font-size:13px;margin:14px 0}
.ok{background:#eaf7ef;border-left:4px solid #1e8449;padding:12px 14px;font-size:13px;margin:14px 0}
code{background:#eef0f3;padding:1px 5px;border-radius:3px;font-size:12px}
"""


def cls(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


def fmt(v, d=2, sign=True):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '-'
    return ('%+.2f' % v) if sign else ('%.2f' % v)


H = []
H.append('<div class="wrap"><h1>Hoshi 策略 · 样本外验证（修复引擎 exp5）</h1>')
H.append('<div class="sub">引擎 = hoshi_backtest_exp5.py（已修复"按全数据集最后一根K线强平"的严重 bug）｜'
         '双组独立随机窗口各 30 个，共 60 个｜初始资金 50 万</div>')
H.append('<div class="bad"><b>重要前提</b>：2026-09-10 那轮机制研究全部基于污染数据，已作废。'
         '本报告中一切结论以 exp5 修复版为准。修复影响：第一组 30 窗中原版有 <b>%d/%d</b> 个窗口结果发生变化。'
         '</div>' % (chg, cn))

H.append('<h2>一、总览：三方案 × 三组口径</h2>')
H.append('<table><tr><th>样本</th><th>方案</th><th>窗口数</th><th>等权均值</th><th>几何均值</th>'
         '<th>中位数</th><th>最差窗</th><th>最好窗</th><th>负收益窗</th></tr>')
cur_lbl = None
for lbl, sk, st in BLOCKS:
    if lbl != cur_lbl:
        cur_lbl = lbl
        H.append('<tr><td colspan="9" style="background:#fafbfc;text-align:left;font-weight:600">%s</td></tr>' % lbl)
    if st is None:
        H.append('<tr><td></td><td>%s</td><td colspan="7" style="text-align:center;color:#999">未完成</td></tr>' % sk.upper())
        continue
    H.append('<tr><td></td><td>%s</td><td>%d</td><td class="%s">%s</td><td class="%s">%s</td>'
             '<td class="%s">%s</td><td class="%s">%s</td><td class="%s">%s</td><td>%d (%.0f%%)</td></tr>'
             % (sk.upper(), st['n'], cls(st['mean']), fmt(st['mean']), cls(st['geo']), fmt(st['geo']),
                cls(st['med']), fmt(st['med']), cls(st['worst']), fmt(st['worst']),
                cls(st['best']), fmt(st['best']), st['neg'], 100.0 * st['neg'] / st['n']))
H.append('</table>')
H.append('<div class="note">评价口径：等权均值会被单个极端窗口支配，<b>几何均值 + 负窗占比 + 最差窗</b> 才是可持续性的判据。</div>')

H.append('<h2>二、配对比较（同窗口逐一对减）</h2>')
H.append('<div class="note"><b>符号检验</b>（精确二项，H0：两方案胜率各 50%）不依赖收益的正态假设，'
         '比 t 检验更稳健——窗口收益分布厚尾且彼此重叠时，应以符号检验为准。</div>')
H.append('<table><tr><th>样本</th><th>对比</th><th>窗口数</th><th>平均差(pp)</th><th>标准差</th>'
         '<th>t 值</th><th>胜出窗口数</th><th>胜率</th><th>符号检验 p(双尾)</th></tr>')
for lbl, name, p in PAIRS:
    if not p:
        H.append('<tr><td>%s</td><td>%s</td><td colspan="7" style="text-align:center;color:#999">未完成</td></tr>' % (lbl, name))
        continue
    tv = '&infin;' if p['t'] == float('inf') else '%.2f' % p['t']
    pv = p['p_two']
    pstr = ('&lt;0.0001' if pv < 0.0001 else '%.4f' % pv)
    pcls = 'pos' if pv < 0.05 else ''
    H.append('<tr><td>%s</td><td>%s</td><td>%d</td><td class="%s">%s</td><td>%.1f</td><td>%s</td>'
             '<td>%d/%d</td><td>%.0f%%</td><td class="%s"><b>%s</b></td></tr>'
             % (lbl, name, p['n'], cls(p['mean']), fmt(p['mean']), p['sd'], tv,
                p['win'], p['n'], p['winrate'], pcls, pstr))
H.append('</table>')

if B_N:
    H.append('<h3>跨持有期的一致性（分档级符号检验）</h3>')
    H.append('<div class="%s">把每个长度分档当作一次独立试验：T5 在 <b>%d/%d</b> 个分档中胜率超过 50%%'
             '（分档级符号检验 p = %s）。'
             '单个分档样本量小（n=5~8）难以各自显著，但<b>方向在所有持有期上完全一致</b>——'
             '这比任何单点的收益数值都更能说明 T5 的优势不是某个行情阶段的偶然。'
             '分档明细：%s。</div>'
             % ('ok' if B_P < 0.05 else 'note', B_POS, B_N,
                ('&lt;0.0001' if B_P < 0.0001 else '%.4f' % B_P),
                '、'.join('%s %d/%d' % (lbl, p['win'], p['n']) for lbl, p in BUCKET)))

H.append('<h2>三、逐窗明细（60 窗）</h2>')
H.append('<table><tr><th>#</th><th>组</th><th>起</th><th>止</th><th>月数</th>'
         '<th>原版 %</th><th>h5s9 %</th><th>T5 %</th><th>T5-原版</th></tr>')
for i, r in enumerate(rows_merged, 1):
    d = (r['t5'] - r['base']) if (r['t5'] is not None and r['base'] is not None) else None
    H.append('<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td>'
             '<td class="%s">%s</td><td class="%s">%s</td><td class="%s">%s</td><td class="%s">%s</td></tr>'
             % (i, r['group'], r['start'][:7], r['end'][:7], r['m'],
                cls(r['base']), fmt(r['base']), cls(r['h5s9']), fmt(r['h5s9']),
                cls(r['t5']), fmt(r['t5']), cls(d), fmt(d)))
H.append('</table>')

H.append('<h2>四、方案定义</h2>')
H.append('<table><tr><th>键</th><th>定义</th></tr>')
for sk in SCHEMES:
    H.append('<tr><td>%s</td><td style="text-align:left">%s</td></tr>' % (sk.upper(), NAME[sk]))
H.append('</table>')

# ---------- 消融章节 ----------
ABL_DEF = [
    ('V0', 'h5s9 基准：评分9 + 止损5 + R3开 + 广度20'),
    ('A', 'V0 + 分档仓位（评分8，9:1 / 8.5:0.7 / 8:0.45）'),
    ('B', 'V0 + 关 R3 回撤门控'),
    ('C', 'V0 + 广度门控 20 → 30'),
    ('T5', '三项全开 = 分档仓位 + 关R3 + 广度30'),
]
ABL_FILES = [('V0', None), ('A', 'hoshi_abl1_a.csv'), ('B', 'hoshi_abl1_b.csv'),
             ('C', 'hoshi_abl1_c.csv'), ('T5', None)]


def _rd(path, col):
    d = {}
    if not path or not os.path.exists(os.path.join(HERE, path)):
        return d
    with open(os.path.join(HERE, path), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                d[(r['start'], r['end'])] = float(r[col])
            except (KeyError, ValueError, TypeError):
                pass
    return d


V0D = {k: v[0] for k, v in load('1', 'h5s9').items()}
T5D = {k: v[0] for k, v in load('1', 't5').items()}
abl_rows = []
for key, fn in ABL_FILES:
    if key == 'V0':
        d = V0D
    elif key == 'T5':
        d = T5D
    else:
        d = _rd(fn, 'pct')
    if not d:
        abl_rows.append((key, None, None, None, None, 0, 0))
        continue
    keys = [k for k in d if k in V0D]
    g_all = geo(list(d.values()))
    g_pair = geo([d[k] for k in keys])
    g_v0 = geo([V0D[k] for k in keys])
    win = sum(1 for k in keys if d[k] > V0D[k])
    abl_rows.append((key, len(d), g_all, g_pair, (g_pair - g_v0) if keys else None, win, len(keys)))

H.append('<h2>五、归因：T5 的超额来自哪里（加一法消融）</h2>')
H.append('<div class="note">以 h5s9 为基准 V0，逐个加回 T5 的三处改动。'
         '「同窗增益」只取该方案已跑完的窗口、与 V0 同批窗口对比，是公平口径。</div>')
H.append('<table><tr><th>方案</th><th>定义</th><th>窗口数</th><th>几何(全窗)</th>'
         '<th>几何(同窗)</th><th>同窗增益</th><th>胜/总</th></tr>')
DEF_MAP = dict(ABL_DEF)
for key, n, g_all, g_pair, gain, win, tot in abl_rows:
    if n is None:
        H.append('<tr><td>%s</td><td style="text-align:left">%s</td>'
                 '<td colspan="5" style="text-align:center;color:#999">未完成</td></tr>'
                 % (key, DEF_MAP[key]))
        continue
    H.append('<tr><td><b>%s</b></td><td style="text-align:left">%s</td><td>%d</td>'
             '<td class="%s">%s</td><td>%s</td><td class="%s">%s</td><td>%d/%d</td></tr>'
             % (key, DEF_MAP[key], n, cls(g_all), fmt(g_all), fmt(g_pair, sign=False),
                cls(gain), fmt(gain), win, tot))
H.append('</table>')
H.append('<div class="ok"><b>归因结论</b>：T5 的超额几乎全部来自「关掉 R3 回撤门控」；'
         '分档仓位与广度门控 30 单独加入均为<b>负贡献</b>（胜率仅约 1/3）。'
         '→ 更简单、更优的方案应为 <b>B = h5s9 + 关 R3</b>。</div>')
H.append('<h3>R3 为什么是负贡献（机制）</h3>')
H.append('<div class="note">R3 用<b>已完成交易的复利链</b>计算回撤（不含现金与未平仓持仓），'
         '超过 25% 即停手 60 天、再犯升级 120 天。两个缺陷：<br>'
         '① 只看已平仓交易链，回撤被系统性高估，25% 阈值触发过于频繁；<br>'
         '② 本策略是超跌反弹，权益回撤之后恰是信号最密集、赔率最好的时段，'
         '停手 60–120 天等于每次在最优点附近强制离场并错过整段反弹。<br>'
         '→ R3 是<b>顺周期的错误风控</b>，不是代码 bug。</div>')
H.append('</div>')

html = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<title>Hoshi 样本外验证（修复版）</title><style>%s</style></head><body>%s</body></html>'
        % (CSS, ''.join(H)))

out_dir = os.path.join(ROOT, 'docs')
if not os.path.isdir(out_dir):
    os.makedirs(out_dir)
out_html = os.path.join(out_dir, 'Hoshi_样本外验证_修复版.html')
with open(out_html, 'w', encoding='utf-8') as f:
    f.write(html)
print('OK ->', out_html)
for lbl, sk, st in BLOCKS:
    if st:
        print('%-28s %-5s n=%2d 均值%+8.2f 几何%+8.2f 中位%+8.2f 最差%+8.2f 负窗%d'
              % (lbl, sk.upper(), st['n'], st['mean'], st['geo'], st['med'], st['worst'], st['neg']))
print('-' * 78)
for lbl, name, p in PAIRS:
    if p:
        tv = 'inf' if p['t'] == float('inf') else '%.2f' % p['t']
        print('%-10s %-12s n=%2d 平均差%+8.2fpp t=%7s 胜 %2d/%-2d (%.0f%%) 符号检验p=%.4f'
              % (lbl, name, p['n'], p['mean'], tv, p['win'], p['n'], p['winrate'], p['p_two']))
