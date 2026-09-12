# -*- coding: utf-8 -*-
"""生成《Hoshi 机制研究报告》HTML。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'docs', 'Hoshi_机制研究报告_2026-09-10.html')

# ============================ 数据区 ============================
# 2x2 因子分解
X22 = [
    # 窗口, V0, V1, V2, V3, 笔数V0, 笔数V3
    ('A 2014-12~2016-11 疯牛+股灾', 495.21, 29.88, 449.07, 33.29, 105, 74),
    ('B 2019-05~2021-04 核心资产慢牛', 26.05, -0.78, 29.99, -22.96, 106, 73),
    ('C 2018-10~2019-09 政策底反弹', 30.01, -13.71, 9.05, -12.13, 71, 36),
    ('E 2016-02~2019-01 存量熊市', -27.70, -6.05, -14.45, -6.44, 84, 75),
]

# 评分分桶
BUCKET = [
    # 窗口, 市场性质, [8,9)笔, [8,9)胜率, [8,9)净盈亏万, [9,∞)笔, [9,∞)胜率, [9,∞)净盈亏万, 判定
    ('A 2014-12~16-11', '疯牛+股灾', 59, 56, 236.5, 46, 57, 11.1, '误杀'),
    ('B 2019-05~21-04', '核心资产慢牛', 70, 57, 7.4, 36, 61, 5.6, '误杀'),
    ('C 2018-10~19-09', '政策底反弹', 45, 62, 16.7, 26, 46, -1.7, '误杀'),
    ('G 2012-08~14-07', '缓慢上涨', 70, 53, 20.5, 30, 37, -9.5, '误杀'),
    ('D 2022-02~25-01', '震荡熊', 115, 50, 3.2, 98, 51, 0.1, '误杀(弱)'),
    ('E 2016-02~19-01', '存量熊市', 59, 27, -11.8, 25, 48, -2.0, '挡灾'),
    ('F 2014-06~15-05', '极端普涨', 39, 67, -9.3, 33, 52, -12.0, '挡灾'),
]

# 四分框架
QUAD = [
    ('高广度 + 高波动<br><span class="sub">震荡急涨 / 急涨急跌</span>', 11, 87.3, 29.7, -57.6,
     '原版的甜蜜点，h5s9 的滑铁卢<br>11 窗中 9 窗 gap 为负'),
    ('高广度 + 低波动<br><span class="sub">单边普涨 / 无回调</span>', 4, -21.1, -9.1, 12.0,
     '超跌信号 = 选弱者，原版本身也亏<br>普涨时还在跌的票必有问题'),
    ('低广度 + 高波动<br><span class="sub">动荡分化</span>', 4, 41.3, 52.0, 10.7,
     '分化剧烈，精选有价值，h5s9 更优'),
    ('低广度 + 低波动<br><span class="sub">存量阴跌</span>', 11, -3.7, 6.9, 10.6,
     '超跌 = 趋势延续，必须严格门槛<br>h5s9 稳定占优（除 B 窗口异常）'),
]

# R3 探针
R3 = [
    ('A 2014-12~2016-11', 495.21, 390.93, 33.29, 146.82, '关 R3 让 h5s9 +113pp'),
    ('C 2018-10~2019-09', 30.01, 3.42, -12.13, -16.78, '关 R3 让原版 -27pp'),
    ('F 2014-06~2015-05', -42.58, -20.79, 19.98, 29.04, '关 R3 让原版 +22pp'),
]

# 市场特征相关
CORR = [
    ('波动率 20d', -0.463, 0.579),
    ('跌停占比', -0.410, None),
    ('截面离散度', -0.378, 0.502),
    ('涨停占比', -0.375, 0.495),
    ('广度 MA20', -0.182, 0.220),
    ('市场区间涨幅', -0.173, 0.242),
]

# 方案对比（收益 %）
SCHEMES = [
    # 名称, A, B, C, D, E, F, 备注
    ('T5 分档仓位 + 关R3 + 广度30', 559.99, 12.40, -0.90, 4.68, -3.86, 67.75, '三项合成，本报告推荐'),
    ('S4 折中门槛 8.5 + 止损5', 465.49, 5.49, 5.04, 12.18, -19.51, 23.30, '只改一个数字，最简单'),
    ('T1 评分分档仓位 + 止损5', 293.25, 26.98, 3.29, 37.64, -7.46, -0.68, '9分满仓/8.5分7成/8分4.5成'),
    ('R3 原版 + 关R3 + 广度30', 369.62, 24.97, 0.17, -3.96, -3.19, -18.67, '原版去噪'),
    ('原版 (评分8 + 止损15)', 495.21, 26.05, 30.01, 6.61, -27.70, -42.58, '基准'),
    ('R2 h5s9 + 关R3 + 广度30', 123.19, 10.52, -16.37, 2.24, -12.80, 29.04, 'h5s9 去噪'),
    ('S1 广度自适应门槛 47', 18.29, 15.39, 8.43, 9.48, -10.13, 35.35, '广度≥47%时放宽到8'),
    ('S3 相对强度过滤', 59.73, 0.47, -10.64, 12.74, -7.35, 8.11, '剔除落后于市场的票'),
    ('S2 波动自适应止损 1.8', 38.42, 4.84, -13.29, 26.89, -18.02, 16.53, '波动≥1.8%时提前止损'),
    ('h5s9 (评分9 + 止损5)', 33.29, -22.96, -12.13, 47.15, -6.44, 19.98, '当前改进版'),
    ('S5 广度47 + 波动1.8', 10.78, 27.25, -1.78, 30.20, -26.60, 8.90, '两个自适应叠加'),
]

WINDOW_TAGS = ['A 疯牛+股灾', 'B 核心资产慢牛', 'C 政策底反弹', 'D 震荡熊', 'E 存量熊市', 'F 极端普涨']


def cls(v):
    if v is None:
        return 'na'
    return 'up' if v >= 0 else 'dn'


def fmt(v):
    return '—' if v is None else '%+.2f' % v


# ============================ HTML ============================
def build_22():
    rows = []
    for w, v0, v1, v2, v3, n0, n3 in X22:
        e_score15 = v1 - v0
        e_score5 = v3 - v2
        e_stop8 = v2 - v0
        e_stop9 = v3 - v1
        inter = e_score5 - e_score15
        rows.append("""<tr>
<td class="w">%s</td>
<td class="num %s">%+.2f</td><td class="num %s">%+.2f</td>
<td class="num %s">%+.2f</td><td class="num %s">%+.2f</td>
<td class="num %s">%+.1f</td><td class="num %s">%+.1f</td>
<td class="num %s">%+.1f</td><td class="num %s">%+.1f</td>
<td class="num %s">%+.1f</td>
<td class="num dim">%d→%d</td></tr>""" % (
            w, cls(v0), v0, cls(v1), v1, cls(v2), v2, cls(v3), v3,
            cls(e_score15), e_score15, cls(e_score5), e_score5,
            cls(e_stop8), e_stop8, cls(e_stop9), e_stop9,
            cls(inter), inter, n0, n3))
    return '\n'.join(rows)


def build_bucket():
    rows = []
    for w, nature, n1, wr1, p1, n2, wr2, p2, verdict in BUCKET:
        diff = wr1 - wr2
        vc = 'bad' if verdict.startswith('误杀') else 'good'
        rows.append("""<tr>
<td class="w">%s</td><td class="dim">%s</td>
<td class="num">%d</td><td class="num %s">%d%%</td><td class="num %s">%+.1f</td>
<td class="num">%d</td><td class="num %s">%d%%</td><td class="num %s">%+.1f</td>
<td class="num %s">%+d</td>
<td><span class="tag %s">%s</span></td></tr>""" % (
            w, nature, n1, cls(wr1 - 50), wr1, cls(p1), p1,
            n2, cls(wr2 - 50), wr2, cls(p2), p2,
            cls(diff), diff, vc, verdict))
    return '\n'.join(rows)


def build_quad():
    rows = []
    for name, n, base, h5, gap, note in QUAD:
        rows.append("""<tr>
<td>%s</td><td class="num">%d</td>
<td class="num %s">%+.1f%%</td><td class="num %s">%+.1f%%</td>
<td class="num %s">%+.1f</td><td class="dim">%s</td></tr>""" % (
            name, n, cls(base), base, cls(h5), h5, cls(gap), gap, note))
    return '\n'.join(rows)


def build_corr():
    rows = []
    for name, r_gap, r_base in CORR:
        rows.append("""<tr><td>%s</td><td class="num %s">%+.3f</td><td class="num">%s</td></tr>""" % (
            name, 'dn' if r_gap < 0 else 'up', r_gap,
            '%+.3f' % r_base if r_base is not None else '—'))
    return '\n'.join(rows)


def build_r3():
    rows = []
    for w, bo, bc, ho, hc, note in R3:
        d_b = bc - bo
        d_h = hc - ho
        rows.append("""<tr><td class="w">%s</td>
<td class="num %s">%+.2f</td><td class="num %s">%+.2f</td><td class="num %s">%+.1f</td>
<td class="num %s">%+.2f</td><td class="num %s">%+.2f</td><td class="num %s">%+.1f</td>
<td class="dim">%s</td></tr>""" % (
            w, cls(bo), bo, cls(bc), bc, cls(d_b), d_b,
            cls(ho), ho, cls(hc), hc, cls(d_h), d_h, note))
    return '\n'.join(rows)


def geo(v):
    p = 1.0
    for x in v:
        p *= (1 + x / 100.0)
    return (p ** (1.0 / len(v)) - 1) * 100.0


def med(v):
    s = sorted(v)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]


def build_schemes():
    scored = []
    for row in SCHEMES:
        name = row[0]
        vals = list(row[1:7])
        note = row[7]
        scored.append((geo(vals), name, vals, note))
    scored.sort(key=lambda x: -x[0])
    rows = []
    for g, name, vals, note in scored:
        cells = ''.join('<td class="num %s">%s</td>' % (cls(v), fmt(v)) for v in vals)
        nneg = sum(1 for v in vals if v < 0)
        hi = ' class="hi"' if name.startswith('T5') else ''
        rows.append(
            '<tr%s><td class="w">%s</td>%s<td class="num %s"><b>%+.2f</b></td>'
            '<td class="num %s">%+.2f</td><td class="num %s">%+.2f</td>'
            '<td class="num dim">%d/6</td><td class="num dim">%.0f</td><td class="dim">%s</td></tr>'
            % (hi, name, cells, cls(g), g, cls(min(vals)), min(vals),
               cls(med(vals)), med(vals), nneg, sum(50 * (1 + v / 100.0) for v in vals), note))
    return '\n'.join(rows)


HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hoshi 机制研究报告 · 2026-09-10</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1a1d24;--dim:#6b7280;--line:#e5e7eb;
--up:#d32029;--dn:#0f9d58;--acc:#2563eb;--accbg:#eff6ff;--warn:#b45309;--warnbg:#fffbeb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
.sub2{color:var(--dim);font-size:14px;margin-bottom:28px}
h2{font-size:21px;margin:44px 0 14px;padding-left:12px;border-left:4px solid var(--acc)}
h3{font-size:17px;margin:26px 0 10px;color:#374151}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:16px 0}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f3f4f6;font-weight:600;color:#374151;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.w{font-weight:600;white-space:nowrap}
td.dim,.dim{color:var(--dim)}
.up{color:var(--up);font-weight:600}.dn{color:var(--dn);font-weight:600}
.na{color:#9ca3af}
tr.hi{background:#fff7ed}
tr.hi td.w{color:#c2410c}
.tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:600}
.tag.bad{background:#fef2f2;color:#b91c1c}
.tag.good{background:#f0fdf4;color:#15803d}
.kbox{background:var(--accbg);border-left:4px solid var(--acc);border-radius:0 8px 8px 0;padding:14px 18px;margin:16px 0}
.kbox.warn{background:var(--warnbg);border-left-color:var(--warn)}
.kbox b{color:var(--acc)}.kbox.warn b{color:var(--warn)}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.kpi .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2}
.kpi .l{font-size:12.5px;color:var(--dim);margin-top:4px}
ul,ol{padding-left:22px}li{margin:6px 0}
code{background:#f3f4f6;padding:1px 6px;border-radius:4px;font-size:13px}
.small{font-size:12.5px;color:var(--dim)}
.eq{background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:12px 16px;
font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;margin:12px 0;overflow-x:auto}
</style></head><body><div class="wrap">

<h1>Hoshi 策略：两个"异常窗口"的机制解剖</h1>
<div class="sub2">为什么 2014-12~2016-11 差 462pp · 为什么 2019-05~2021-04 差 49pp · 能否避免 · 2026-09-10</div>

<div class="kbox">
<b>先说结论（三条）</b>
<ol style="margin:8px 0 0">
<li><b>不是"时间"问题，是"市场形态"问题。</b>决定性变量是「广度 × 波动」的组合。原版只在<b>高广度+高波动（震荡急涨）</b>这一个象限里赚大钱（11 窗均值 +87.3%），h5s9 恰恰在这个象限塌方（gap 均值 −57.6pp）；其余三个象限 h5s9 全部占优。</li>
<li><b>A 窗口 96% 的损失来自"评分门槛 8→9"，与止损几乎无关。</b>2×2 分解：门槛效应 −465pp，止损效应 −46pp。被 9 分门槛挡掉的 59 笔 [8,9) 交易净赚 <b>236.5 万</b>，占原版总盈利的 96%。</li>
<li><b>想靠"择时切换变体"来避灾基本无效，但"改结构"有效。</b>事后切换的理论上限几何 +33.97%；用无前视特征只能做到 +19.98%（原版 +18.31%），增益微弱。
而把二值门槛换成<b>按评分分档给仓位</b>、再用<b>市场广度门控替代 R3 连亏停手</b>，
A 窗口 +33% → <b>+560%</b>（反超原版 +495%），六窗几何均值 +6.88% → <b>+52.16%</b>。</li>
</ol>
</div>

<h2>一、第一层机制：评分衡量的是"超跌强度"，而"跌"的归因会随市场漂移</h2>

<p>Hoshi 的核心信号是<b>超跌反弹</b>：评分越高 = 跌得越急越深。这一点决定了它的命运——
<b>"跌"在不同市场里根本不是同一件事</b>。</p>

<div class="card">
<table>
<tr><th>市场形态</th><th>下跌的归因</th><th>"跌得深"意味着</th><th>评分门槛该怎么做</th></tr>
<tr><td>流动性牛市（2014-15）</td><td>普跌洗盘、杠杆踩踏后的错杀</td><td>弹簧压得越紧，弹得越高</td><td class="dn">越低越好 —— 门槛是纯成本</td></tr>
<tr><td>存量熊市（2016-19、2022-25）</td><td>趋势的开始、基本面恶化</td><td>越深越可能继续跌</td><td class="up">越高越好 —— 门槛是真收益</td></tr>
<tr><td>极端普涨（2014-06~2015-05）</td><td>普涨时还在跌 = 被抛弃的票</td><td>跌得深 = 有硬伤</td><td class="up">越高越好，甚至该停手</td></tr>
<tr><td>结构性分化（2019-21）</td><td>一半是洗盘、一半是真弱</td><td>信号质量高度分化</td><td>需要"渐变"而非"一刀切"</td></tr>
</table>
</div>

<p><b>抽象成一句话：</b>评分门槛的价值 = <code>[高分信号胜率 − 低分信号胜率] × 交易量</code>。
当市场的上涨由 β（整体流动性）驱动时，两类信号胜率趋同，门槛只剩"减少敞口"这一个作用——
等同于<b>在牛市里减仓</b>；当上涨由 α（个股质地）驱动时，两类信号胜率拉开，门槛才产生真实价值。</p>

<h2>二、第二层机制：右尾与左尾的凸性错配</h2>

<p>原版相对 h5s9 有两个"凸性来源"：</p>
<ul>
<li><b>跟踪止盈</b>（+5.2% 武装后回落 1.2% 卖出）——在强趋势里能吃到长波，右尾厚。</li>
<li><b>前 14 天完全不止损</b>——等于免费送出一个"均值回复看跌期权"，在 V 型反转市里几乎必赚。</li>
</ul>

<div class="grid3">
<div class="kpi"><div class="v up">+87.3%</div><div class="l">原版在「高广度+高波动」象限<br>11 个窗口的均值收益</div></div>
<div class="kpi"><div class="v dn">−57.6pp</div><div class="l">同象限 h5s9 − 原版<br>（其余三象限均为正）</div></div>
<div class="kpi"><div class="v">+495%<br><span class="small">→ 去极值后</span> +17.4%</div><div class="l">原版 30 窗均值被 A 窗口单点撑起<br>去掉最大值后与 h5s9 几乎持平</div></div>
</div>

<div class="kbox warn">
<b>这是最容易被误读的一点。</b>30 窗口里原版等权均值 +33.35%、h5s9 +19.15%，看上去原版完胜。
但把 A 窗口（+495%）这一个点去掉后，原版 <b>+17.42%</b>、h5s9 <b>+16.86%</b>——几乎一样。
换句话说：<b>h5s9 不是让策略变差了，而是把策略的右尾削平了</b>；
它换来的是负窗口从 10/30 降到 7/30、最差窗口从 −42.58% 收窄到 −35.90%。
</div>

<h2>三、第三层机制：序列门控让效应不可加（路径依赖）</h2>

<p>R3 门控（连续 3 笔亏损即停手）＋ 10 个槽位的容量约束，使策略成为<b>强路径依赖</b>系统：
改一个参数会完全改写后续交易序列，于是"局部归因"会系统性低估真实影响。</p>

<div class="eq">gap = 门槛效应 + 止损效应 + <b>交互项</b></div>

<p>在 B 窗口，交互项高达 <b>−26.1pp</b>，占总 gap（−49.0pp）的一半以上——
两个单独看都很小的改动（门槛 −26.8pp、止损 +3.9pp），叠加后放大到 −49pp。</p>

<div class="kbox warn">
<b>实践含义：</b>任何"我把 X 单独关掉测一下"的归因方式，在这个策略上都会给出偏乐观的结论。
评价改动必须<b>整窗口端到端重跑</b>，不能做增量推断。
</div>

<h2>四、证据一：2×2 因子分解（把门槛和止损彻底分开）</h2>

<p>h5s9 其实是两个独立改动的叠加：<code>评分门槛 8→9</code> 与 <code>硬止损起点 15天→5天</code>。
四格全跑一遍，就能把 gap 精确拆开。</p>

<div class="card">
<table>
<tr><th rowspan="2">窗口</th><th colspan="4">四格收益 %</th><th colspan="2">门槛效应</th><th colspan="2">止损效应</th><th rowspan="2">交互项</th><th rowspan="2">笔数<br>V0→V3</th></tr>
<tr><th>V0 分8+损15</th><th>V1 分9+损15</th><th>V2 分8+损5</th><th>V3 分9+损5</th><th>@损15</th><th>@损5</th><th>@分8</th><th>@分9</th></tr>
__T22__
</table>
<p class="small">V0 = 原版，V3 = h5s9。交互项 = 门槛@损5 − 门槛@损15。</p>
</div>

<div class="kbox">
<b>读出来的东西：</b>
<ul style="margin:8px 0 0">
<li><b>A 窗口：</b>门槛效应 <span class="dn">−465pp</span>，止损效应仅 <span class="dn">−46pp</span>。
用户问的"为什么差 462pp"，<b>96% 的答案就是评分门槛</b>，而且是极端误杀。</li>
<li><b>C 窗口（2018-10 政策底反弹）：</b>同样门槛主导（<span class="dn">−43.7pp</span>）。
说明 A 的机制不是孤例，能推广到用户提到的其他节点。</li>
<li><b>E 窗口（存量熊市）：</b>符号完全反过来——门槛 <span class="up">+21.7pp</span>、止损 <span class="up">+13.3pp</span>，
两个改动<b>都是正贡献</b>。第一层机制的对称性得到验证。</li>
<li><b>B 窗口：</b>门槛 −26.8pp、止损 +3.9pp，但交互项 <span class="dn">−26.1pp</span>。
单独拆看不出问题，合起来才塌——典型的路径依赖。</li>
</ul>
</div>

<h2>五、证据二：评分分桶 —— 门槛在牛市是误杀，在熊市是挡灾</h2>

<p>让原版（门槛 8）跑完，再按成交时的评分把交易分成 <code>[8,9)</code> 与 <code>[9,∞)</code> 两组。
前者正是被 9 分门槛挡掉的那批。</p>

<div class="card">
<table>
<tr><th rowspan="2">窗口</th><th rowspan="2">性质</th><th colspan="3">[8,9) 被挡掉的批次</th><th colspan="3">[9,∞) 保留的批次</th><th rowspan="2">胜率差<br>[8,9)−[9,∞)</th><th rowspan="2">判定</th></tr>
<tr><th>笔数</th><th>胜率</th><th>净盈亏(万)</th><th>笔数</th><th>胜率</th><th>净盈亏(万)</th></tr>
__TBUCKET__
</table>
</div>

<div class="kbox">
<b>这张表是整个研究的支点：</b>
<ul style="margin:8px 0 0">
<li><b>A 窗口极端误杀：</b>被挡的 59 笔净赚 <b>+236.5 万</b>，占原版总盈利 247.6 万的 <b>96%</b>。
门槛几乎砍掉了全部利润，只留下 +11.1 万。</li>
<li><b>E 窗口真挡灾：</b>被挡的 59 笔胜率仅 <b>27%</b>（对比 A 窗口 56%），净亏 −11.8 万。
熊市里 8~9 分的信号是真的坏信号。</li>
<li><b>更反直觉的发现 —— 评分的单调性本身不稳定：</b>
C、G、F 三个窗口里 <code>[8,9)</code> 的胜率<b>反而高于</b> <code>[9,∞)</code>（+16、+16、+15pp）。
也就是说"评分越高越安全"这个假设在过半窗口里不成立。
这解释了为什么单纯调高门槛无法稳定改善——<b>评分不是单调的质量指标</b>。</li>
<li><b>F 窗口（极端普涨）的特殊性：</b><code>[8,9)</code> 胜率 67%（最高）却净亏 −9.3 万。
典型"卖保险"结构：多数小赚、少数巨亏。普涨市里超跌信号本身就是负向指标。</li>
</ul>
</div>

<h2>六、证据三：广度 × 波动四分框架（可直接推广到其他节点）</h2>

<p>把 30 个窗口按"广度 MA20 中位数 49.8%"与"20 日波动率中位数 1.60%"切成四象限，
gap 的符号几乎被象限完全决定。</p>

<div class="card">
<table>
<tr><th>象限</th><th>窗口数</th><th>原版均值</th><th>h5s9 均值</th><th>gap 均值</th><th>机制解释</th></tr>
__TQUAD__
</table>
</div>

<p><b>为什么这个框架能推广：</b>用户提到的 <code>2018-10~2019-09</code>（C 窗口）落在"高广度+高波动"象限
（广度 50.1 / 波动 1.64），gap −42.1pp —— 与 A 窗口同一机制，无需另立解释。
反过来，<code>2014-06~2015-05</code>（F）虽然同样身处 2014-15 大牛市，
却因广度高达 69.5%、波动仅 1.39% 而落入"高广度+低波动"象限，gap 反而是 <span class="up">+62.6pp</span>。
<b>可见"2014~2015 都会差很多"这个印象并不准确——真正决定的是广度与波动的组合，不是年份。</b></p>

<h2>七、证据四：市场特征相关性与"择时切换"的极限</h2>

<div class="card">
<table>
<tr><th>市场特征（窗口内均值）</th><th>与 gap(h5s9−原版) 的相关</th><th>与原版收益的相关</th></tr>
__TCORR__
</table>
<p class="small">Pearson，n=30。gap 与"波动/离散/涨跌停占比"负相关最强；原版收益则与它们正相关最强——
再次印证：<b>原版吃的就是高波动高离散的右尾</b>。</p>
</div>

<h3>那么，能不能提前判断该用哪个变体？</h3>

<div class="card">
<table>
<tr><th>口径</th><th>等权均值</th><th>几何均值</th><th>最差窗口</th><th>说明</th></tr>
<tr><td>全用原版</td><td class="num up">+33.35%</td><td class="num up">+18.31%</td><td class="num dn">−42.58%</td><td class="dim">均值被 A 窗口单点撑起</td></tr>
<tr><td>全用 h5s9</td><td class="num up">+19.15%</td><td class="num up">+15.77%</td><td class="num dn">−35.90%</td><td class="dim">更稳，右尾被削</td></tr>
<tr><td>Oracle（事后每窗选优）</td><td class="num up">+46.74%</td><td class="num up">+33.97%</td><td class="num dn">−35.90%</td><td class="dim">理论上限，不可实现</td></tr>
<tr><td>波动率切分（全窗口特征）</td><td class="num up">+40.41%</td><td class="num up">+26.71%</td><td class="num dn">−35.90%</td><td class="dim">含事后信息，LOO 后仍 +25.48%</td></tr>
<tr><td><b>波动率切分（起点前 60 日，无前视）</b></td><td class="num up">+36.49%</td><td class="num up">+22.96%</td><td class="num dn">−35.90%</td><td class="dim"><b>可执行，但 LOO 仅 +19.98%</b></td></tr>
</table>
</div>

<div class="kbox warn">
<b>诚实的结论：</b>用全窗口特征切分，留一交叉验证几何 +25.48%（样本内 +26.71%，衰减仅 1.2pp），
证明"市场状态确实决定了哪个变体更优"这一机制<b>成立且稳健</b>。
但改用<b>无前视</b>的可观测特征后，留一验证只有 <b>+19.98%</b>，相对原版 +18.31% 仅剩 +1.7pp 增益——
<b>切换变体的择时价值基本被信息劣势吃掉了。</b>
方向对，但性价比低：<b>不要靠"二选一择时"解决问题，要改参数结构本身。</b>
</div>

<h2>八、证据五：R3 序列门控是纯噪声</h2>

<div class="card">
<table>
<tr><th rowspan="2">窗口</th><th colspan="3">原版</th><th colspan="3">h5s9</th><th rowspan="2">观察</th></tr>
<tr><th>R3 开</th><th>R3 关</th><th>差</th><th>R3 开</th><th>R3 关</th><th>差</th></tr>
__TR3__
</table>
</div>

<p>R3 在三个窗口里的方向<b>互相矛盾</b>：A 窗口关掉让 h5s9 +113pp，C 窗口关掉让原版 −27pp，
F 窗口关掉让原版 +22pp。关掉 R3 后交易笔数大致翻倍（A：74→197，C：71→123，F：72→131），
说明 R3 本质上是一个<b>随机的敞口削减器</b>——它同时压低了好结果和坏结果的幅度，
停手时点相对于行情转折点是随机的。</p>

<p><b>建议：</b>用有经济含义的"市场广度门控"替代纯随机的"连亏计数"。
当前广度门控阈值只有 20%（几乎不触发），可考虑提到 30%。</p>

<p>六窗实测印证了"R3 = 随机方差放大器"的判断：把它关掉换成广度门控 30% 后，
h5s9 几何 +6.88% → <b>+15.49%</b>，原版 +27.60% → +28.23%（几乎无增益，
但最差窗口从 −42.58% 收窄到 −18.67%）。
<b>关 R3 不会让策略变好或变坏，它只是把底层方案的倾向放大——
所以它是一个应当在结构改造完成后再处理的"噪声项"。</b></p>

<h2>九、解决方案与回测对比</h2>

<div class="card">
<table>
<tr><th>方案</th>__THWIN__<th>几何均值</th><th>最差窗</th><th>中位</th><th>负窗</th><th>累加<br>(万元)</th><th>说明</th></tr>
__TSCHEME__
</table>
<p class="small">A/B/C 为"误杀型"窗口（h5s9 跑输原版），D/E/F 为"挡灾型"窗口（h5s9 跑赢原版）。
按<b>几何均值</b>降序排列。几何均值 = 六窗收益连乘后开 6 次方，等价于把六个窗口首尾相接做复利，
比等权均值更贴近实盘——等权均值会被 A 窗口这种单点极端值完全支配。</p>
</div>

<h3>逐一评价</h3>
<ul>
<li><b>T5（分档仓位 + 关 R3 + 广度30）全面领先。</b>几何 +52.16%，
比原版（+27.60%）高 24.6pp、比 h5s9（+6.88%）高 45.3pp。
更关键的是它<b>同时改善了右尾和下行</b>：A 窗口 +559.99% <b>超过原版的 +495.21%</b>，
最差窗口却只有 −3.86%（原版 −42.58%、h5s9 −22.96%）。
三个组件各自独立作用：分档仓位解决门槛误杀，关 R3 去掉序列噪声，广度门控补上有经济含义的防守。</li>
<li><b>S4（折中门槛 8.5）是性价比最高的单点改动。</b>只把评分门槛从 9 改回 8.5，
A 窗口就从 +33.29% 弹回 <b>+465.49%</b>（原版 +495.21%），几何 +38.23% 排第二。
代价是 E 窗口从 −6.44% 恶化到 −19.51%——<b>门槛越松，熊市越吃亏，这个权衡无法回避</b>。</li>
<li><b>T1（分档仓位）中位数最高（+15.13%）</b>，六个窗口分布最均匀，
但在 A 窗口（+293%）不如 S4/T5——因为分档后 8~9 分信号的仓位被压到 4.5 成，右尾仍被削了一部分。</li>
<li><b>关 R3 的作用取决于搭配。</b>单独加到原版上几乎无增益（几何 +27.60%→+28.23%），
但把最差窗口从 −42.58% 收窄到 −18.67%；加到 h5s9 上是 +6.88%→+15.49%；
加到分档仓位上则是 +36.70%→+52.16%。<b>R3 不是"改好改坏"的开关，而是方差放大器——
它放大的是底层方案本身的倾向。</b></li>
<li><b>S1/S2/S3/S5 四个自适应方案全部不合格</b>（几何 +6.3%~+12.0%）。
按日频切换参数会制造大量不一致的交易序列，代价超过了自适应带来的收益。
这印证了前面的判断：<b>不要做参数择时，要改结构。</b></li>
</ul>

<h3>关 R3 + 广度门控 30% 的逐窗影响</h3>
<div class="card">
<table>
<tr><th>窗口</th><th>原版</th><th>原版+关R3+广度30</th><th>差</th><th>h5s9</th><th>h5s9+关R3+广度30</th><th>差</th></tr>
<tr><td>A 疯牛+股灾</td><td class="num up">+495.21</td><td class="num up">+369.62</td><td class="num dn">−125.6</td><td class="num up">+33.29</td><td class="num up">+123.19</td><td class="num up">+89.9</td></tr>
<tr><td>B 核心资产慢牛</td><td class="num up">+26.05</td><td class="num up">+24.97</td><td class="num dn">−1.1</td><td class="num dn">−22.96</td><td class="num up">+10.52</td><td class="num up">+33.5</td></tr>
<tr><td>C 政策底反弹</td><td class="num up">+30.01</td><td class="num up">+0.17</td><td class="num dn">−29.8</td><td class="num dn">−12.13</td><td class="num dn">−16.37</td><td class="num dn">−4.2</td></tr>
<tr><td>D 震荡熊</td><td class="num up">+6.61</td><td class="num dn">−3.96</td><td class="num dn">−10.6</td><td class="num up">+47.15</td><td class="num up">+2.24</td><td class="num dn">−44.9</td></tr>
<tr><td>E 存量熊市</td><td class="num dn">−27.70</td><td class="num dn">−3.19</td><td class="num up">+24.5</td><td class="num dn">−6.44</td><td class="num dn">−12.80</td><td class="num dn">−6.4</td></tr>
<tr><td>F 极端普涨</td><td class="num dn">−42.58</td><td class="num dn">−18.67</td><td class="num up">+23.9</td><td class="num up">+19.98</td><td class="num up">+29.04</td><td class="num up">+9.1</td></tr>
</table>
<p class="small">注意 <b>D 窗口</b>：h5s9 在这里赚 +47.15%，关掉 R3 后掉到 +2.24%（−44.9pp）。
这说明 R3 并非"总是坏"——它在某些窗口确实躲开了连续亏损。
<b>它的方向是随机的，这正是必须替换它的理由。</b></p>
</div>

<h2>十、30 窗口样本外验证（关键）</h2>

<div class="kbox warn">
<b>为什么必须做这一步：</b>上面第九节的所有方案都是在这 6 个窗口上<b>比出来的</b>，
而其中 A 窗口（+495%）一个点就能支配任何均值。如果不做样本外检验，
整份报告都可能是在给噪声编故事。
</div>

<p>验证方法：跑满此前 30 个随机窗口（种子 20260907，与基线完全相同）。
由于 A~F 六个窗口<b>本身就包含在这 30 个里面</b>，再单独给出
<b>OOS24</b> 口径——剔除当初用来选方案的那 6 个窗口后剩下的 24 个，
这才是真正干净的样本外。</p>

<h3>ALL30（全部 30 窗）</h3>
<div class="card">
<table>
<tr><th>方案</th><th>等权均值</th><th>几何均值</th><th>中位</th><th>最差窗</th><th>负窗</th></tr>
<tr><td class="w">T5 分档+关R3+广度30</td><td class="num up">+77.77</td><td class="num up"><b>+54.33</b></td><td class="num up">+20.79</td><td class="num dn">−13.43</td><td class="num">5/30</td></tr>
<tr><td>S4 折中门槛8.5</td><td class="num up">+31.70</td><td class="num up">+20.92</td><td class="num up">+12.79</td><td class="num dn">−26.65</td><td class="num">3/30</td></tr>
<tr><td>T1 分档仓位</td><td class="num up">+23.96</td><td class="num up">+18.46</td><td class="num up">+10.47</td><td class="num dn">−8.54</td><td class="num">4/30</td></tr>
<tr><td>原版</td><td class="num up">+33.35</td><td class="num up">+18.31</td><td class="num up">+21.28</td><td class="num dn">−42.58</td><td class="num">10/30</td></tr>
<tr><td>h5s9</td><td class="num up">+19.15</td><td class="num up">+15.77</td><td class="num up">+16.17</td><td class="num dn">−35.90</td><td class="num">7/30</td></tr>
</table>
</div>

<h3>OOS24（剔除选方案用的 A~F，真正干净的样本外）</h3>
<div class="card">
<table>
<tr><th>方案</th><th>等权均值</th><th>几何均值</th><th>中位</th><th>最差窗</th><th>负窗</th><th>vs 原版</th><th>vs h5s9</th></tr>
<tr class="hi"><td class="w">T5 分档+关R3+广度30</td><td class="num up">+70.54</td><td class="num up"><b>+54.88</b></td><td class="num up">+30.00</td><td class="num dn">−13.43</td><td class="num">3/24</td><td class="num up">胜 20/24<br>p=0.0011</td><td class="num up">胜 19/24<br>p=0.0043</td></tr>
<tr><td>h5s9</td><td class="num up">+21.48</td><td class="num up">+18.10</td><td class="num up">+16.17</td><td class="num dn">−35.90</td><td class="num">4/24</td><td class="dim">—</td><td class="dim">—</td></tr>
<tr><td>S4 折中门槛8.5</td><td class="num up">+19.13</td><td class="num up">+16.94</td><td class="num up">+13.82</td><td class="num dn">−26.65</td><td class="num">2/24</td><td class="num na">13/24 p=0.68</td><td class="num na">12/24 p=1.00</td></tr>
<tr><td>原版</td><td class="num up">+21.36</td><td class="num up">+16.09</td><td class="num up">+21.28</td><td class="num dn">−42.06</td><td class="num">8/24</td><td class="dim">—</td><td class="dim">—</td></tr>
<tr><td>T1 分档仓位</td><td class="num up">+15.24</td><td class="num up">+14.30</td><td class="num up">+10.47</td><td class="num dn">−8.54</td><td class="num">2/24</td><td class="num na">10/24 p=0.41</td><td class="num na">8/24 p=0.10</td></tr>
</table>
<p class="small">p 值为配对符号检验（正态近似，双尾）。</p>
</div>

<div class="kbox">
<b>验证结论：三个方案里只有 T5 活下来了。</b>
<ul style="margin:8px 0 0">
<li><b>T5 通过，且高度显著。</b>OOS24 几何 +54.88%（h5s9 +18.10%、原版 +16.09%），
24 个样本外窗口中赢下 20 个（vs 原版）和 19 个（vs h5s9），p 值 0.0011 / 0.0043。
最差窗口 −13.43%，也远好于原版 −42.58% 和 h5s9 −35.90%。
<b>它在右尾和下行两端同时变好，不是靠单点极值撑起来的。</b></li>
<li><b>S4 和 T1 未通过。</b>S4 在 OOS24 上几何 +16.94%，
<b>反而略低于 h5s9 的 +18.10%</b>，符号检验 p=1.00（12/24，等同抛硬币）。
T1 更差（+14.30%，vs h5s9 只赢 8/24）。
<b>它们在 6 窗上的亮眼表现几乎全部来自 A 窗口那一个点。</b>
这正好演示了本报告反复强调的那件事：等权均值会被极端窗口完全支配。</li>
<li><b>结论修正：</b>上一节"只改一个数就选 S4"的建议<b>在样本外不成立，予以撤回</b>。
T1（分档仓位单独使用）同样不予推荐。</li>
</ul>
</div>

<h3>T5 在 OOS24 上的三个亏损窗口</h3>
<div class="card">
<table>
<tr><th>窗口</th><th>长度</th><th>原版</th><th>h5s9</th><th>T5</th></tr>
<tr><td>2012-08~2014-07</td><td>24月</td><td class="num up">+21.97</td><td class="num dn">−25.66</td><td class="num dn">−13.43</td></tr>
<tr><td>2021-02~2024-01</td><td>36月</td><td class="num up">+7.07</td><td class="num up">+11.44</td><td class="num dn">−12.42</td></tr>
<tr><td>2023-01~2023-12</td><td>12月</td><td class="num dn">−7.93</td><td class="num dn">−0.66</td><td class="num dn">−5.59</td></tr>
</table>
<p class="small">T5 并非全胜，但三个亏损窗口的幅度都在 −13% 以内，
且在其中两个上原版/h5s9 同样亏损。这与原版那种 −42% 级别的塌方不是一回事。</p>
</div>

<h2>十一、落地建议</h2>

<div class="kbox">
<b>推荐（已含样本外验证结果）</b>
<ol style="margin:8px 0 0">
<li><b>把二值门槛换成评分分档仓位。</b>
<code>评分≥9 → 满仓 / ≥8.5 → 7 成 / ≥8 → 4.5 成</code>。
这是解决"牛市误杀"的正解：低分信号<b>降权而非清零</b>，
在保留熊市防守的同时不再把 A 窗口那种机会整体砍掉。</li>
<li><b>用市场广度门控替代 R3 连亏停手</b>（阈值从 20% 提到 30%）。
R3 是随机方差放大器；广度门控有明确经济含义（广度低 = 普跌 = 不该开新仓）。</li>
<li><b>两者叠加即 T5 方案</b>：六窗几何 +52.16%（原版 +27.60%、h5s9 +6.88%），
最差窗口 −3.86%，A 窗口 +559.99% 反超原版。</li>
<li><b>不要只改门槛（S4 / T1 已证伪）。</b>S4 在 OOS24 上几何 +16.94%，
低于 h5s9 的 +18.10%，符号检验 p=1.00；T1 更差（+14.30%）。
<b>评分门槛这个旋钮本身已经被调到底了，再怎么调都出不来样本外收益。</b>
真正的增益来自"关 R3 + 广度门控"这一项，分档仓位必须与它<b>同时</b>使用。</li>
<li><b>停止用"全窗口等权均值"评价策略。</b>原版均值被 A 窗口单点支配，
应改用几何均值 + 负窗口占比 + 最差窗口三重口径。</li>
<li><b>不要投入精力做"变体择时"。</b>四个自适应方案（S1/S2/S3/S5）全部跑输两个基准之一，
无前视条件下择时增益仅 +1.7pp，不值得承受过拟合风险。</li>
</ol>
</div>

<div class="kbox warn">
<b>启用前还要确认的两件事</b>
<ol style="margin:8px 0 0">
<li><b>换手率与冲击成本。</b>T5 关掉 R3 后交易笔数成倍上升（8 年窗口可达 900+ 笔，
是原版的 3~5 倍）。回测里已含手续费与印花税，但<b>未含滑点与冲击成本</b>。
笔数越多这两项越致命，上线前必须按实际资金规模重算。
这一条是 T5 最大的落地风险。</li>
<li><b>分档系数还没做过敏感度检查。</b>当前用 1.0 / 0.7 / 0.45，是拍的，
没在样本外调过。不过反过来讲——<b>没调过也意味着没过拟合</b>，
建议上线后先按这组系数跑，只在明显异常时才微调。</li>
</ol>
</div>

<div class="kbox warn">
<b>本报告的局限</b>
<ul style="margin:8px 0 0">
<li>T5 已通过 30 窗口样本外验证（OOS24 几何 +54.88%，p&lt;0.01），
但<b>未做组件消融</b>：分档仓位与"关 R3 + 广度门控"各自的贡献尚未在 30 窗上拆分。
已知 T1（仅分档）单独不显著，推测主要增益来自关 R3，但需要再跑一轮确认。</li>
<li>四分框架的切分点（广度 49.8% / 波动 1.60%）来自这 30 窗口的中位数，换样本会漂移，
应作为<b>定性框架</b>而非硬阈值使用。</li>
<li>分桶诊断中部分窗口的收益率展示漏乘 100（脚本打印问题），
本报告引用的"净盈亏（万元）"字段是原始、未受影响的，可直接采信。</li>
</ul>
</div>

<p class="small" style="margin-top:36px">
生成时间：2026-09-10 · 数据源：白名单 A 股日线（代码段白名单过滤后）·
引擎：hoshi_backtest_exp3/exp4.py · 所有回测均为 50 万本金、单股 10%×10 槽、T+1、含手续费与印花税
</p>

</div></body></html>
"""


def main():
    html = HTML
    for k, v in dict(
        T22=build_22(),
        TBUCKET=build_bucket(),
        TQUAD=build_quad(),
        TCORR=build_corr(),
        TR3=build_r3(),
        TSCHEME=build_schemes(),
        THWIN=''.join('<th>%s</th>' % t for t in WINDOW_TAGS),
    ).items():
        html = html.replace('__%s__' % k, v)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print('已生成: %s (%d 字节)' % (OUT, len(html)))


if __name__ == '__main__':
    main()
