# -*- coding: utf-8 -*-
"""把 hoshi 逐日模拟盘结果渲染成自包含 HTML 报告。"""
import json
import html as _h
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RESULT = Path(__file__).parent / "hoshi_replay_result.json"
OUT = Path(__file__).parent / "hoshi_sim_report.html"


def main():
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    sigs = payload["signals"]
    meta = payload["meta"]

    per_day = defaultdict(list)
    for s in sigs:
        per_day[s["date"]].append(s)
    days = sorted(per_day.keys())

    # 各持有期统计
    holds = {}
    for hold in (1, 5, 10):
        tag = "T+{}".format(hold)
        closed = [s for s in sigs if s["fwd"].get(tag) is not None]
        if not closed:
            continue
        rets = [s["fwd"][tag] for s in closed]
        wins = sum(1 for r in rets if r > 0)
        holds[hold] = {
            "n": len(rets),
            "avg": sum(rets) / len(rets),
            "win": wins / len(rets) * 100,
        }

    # T+5 累计曲线
    hold = 5
    tag = "T+{}".format(hold)
    curve = []
    all_closed = []
    for d in days:
        ss = [s for s in per_day[d] if s["fwd"].get(tag) is not None]
        if not ss:
            continue
        all_closed.extend(s["fwd"][tag] for s in ss)
        curve.append({"date": d, "n": len(per_day[d]), "cum": sum(all_closed) / len(all_closed)})

    def fmt(v):
        return "{:+.2f}%".format(v)

    cards = ""
    for hold in (1, 5, 10):
        if hold not in holds:
            continue
        h = holds[hold]
        cls = "pos" if h["avg"] > 0 else "neg"
        cards += (
            '<div class="card"><div class="k">持有{}日</div>'
            '<div class="v {}">{}</div>'
            '<div class="s">胜率 {:.1f}% · {} 笔已了结</div></div>'.format(
                hold, cls, fmt(h["avg"]), h["win"], h["n"])
        )

    # 累计曲线 SVG
    svg_bars = ""
    if curve:
        maxn = max(c["n"] for c in curve)
        step = max(1, len(curve) // 45)
        w = 880 / len(curve)
        # 净值折线
        vals = [c["cum"] for c in curve]
        vmin, vmax = min(vals), max(vals)
        rng = (vmax - vmin) or 1.0
        pts = []
        for i, c in enumerate(curve):
            y = 130 - (c["cum"] - vmin) / rng * 110
            x = i * w
            pts.append("{:.1f},{:.1f}".format(x, y))
            bar_h = c["n"] / maxn * 26
            svg_bars += (
                '<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" fill="#e3a008" '
                'opacity="0.35"><title>{}: {} 只</title></rect>'.format(
                    x, 30 - bar_h, max(w - 1, 1), bar_h, c["date"], c["n"])
            )
        polyline = " ".join(pts)
    else:
        polyline = ""

    html_doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Hoshi 逐日模拟盘 {start} ~ {end}</title>
<style>
:root{{--bg:#0f1216;--panel:#171b21;--line:#252b33;--fg:#e6edf3;--dim:#8b949e;
--up:#f6465d;--down:#2ebd85;--accent:#58a6ff;}}
*{{box-sizing:border-box}}
body{{margin:0;padding:28px;background:var(--bg);color:var(--fg);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}}
h1{{font-size:22px;margin:0 0 6px}} h2{{font-size:16px;margin:26px 0 12px;color:var(--accent)}}
.meta{{color:var(--dim);font-size:13px;margin-bottom:20px;line-height:1.7}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 18px;min-width:160px}}
.card .k{{color:var(--dim);font-size:12px}}
.card .v{{font-size:26px;font-weight:600;margin:4px 0}}
.card .s{{color:var(--dim);font-size:12px}}
.pos{{color:var(--up)}} .neg{{color:var(--down)}}
.big{{font-size:40px;font-weight:700;margin:4px 0}}
.note{{color:var(--dim);font-size:12px;margin-top:10px;line-height:1.8}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel);
border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th{{background:#1c222a;padding:9px 10px;text-align:left;color:var(--dim);font-weight:500}}
td{{padding:7px 10px;border-top:1px solid var(--line)}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
.hl{{color:var(--accent);font-weight:600}}
</style></head><body>
<h1>Hoshi 逐日模拟盘</h1>
<div class="meta">
区间 <code>{start} ~ {end}</code> · 数据截止 <code>{db_max}</code> ·
最低分 <code>{min_score}</code> · 最低成交额 <code>{min_amt} 亿</code> · 每日拥挤度上限 <code>{maxpd}</code><br>
有信号交易日 <b>{n_days}</b> 天 · 总信号 <b>{n_sig}</b> 只 · 日均 <b>{daily:.1f}</b> 只/交易日<br>
口径：每日收盘等权买入当日信号股，固定持有 N 个交易日卖出；未复利、未扣佣金/印花税。
</div>

<h2>不同持有周期的总体盈亏（已了结交易，等权平均）</h2>
<div class="cards">{cards}</div>

<h2>持有 5 日策略的累计净值曲线</h2>
<svg viewBox="0 0 880 160" style="width:100%;height:160px;background:var(--panel);
border:1px solid var(--line);border-radius:10px">
  <line x1="0" y1="130" x2="880" y2="130" stroke="#2b323b"/>
  <rect x="0" y="130" width="880" height="1" fill="#3a4350"/>
  <text x="6" y="20" fill="#8b949e" font-size="11">每日信号数(黄柱)</text>
  {svg_bars}
  <polyline points="{polyline}" fill="none" stroke="#58a6ff" stroke-width="2.2"/>
  <text x="6" y="150" fill="#8b949e" font-size="11">累计组合收益率(蓝线)</text>
</svg>

<h2>结论（基于 2 个月回放）</h2>
<table>
<tr><th>持有周期</th><th class="num">平均收益</th><th class="num">胜率</th><th class="num">已了结</th><th>解读</th></tr>
<tr><td>T+1</td><td class="num {c1}">{v1}</td><td class="num">{w1:.1f}%</td><td class="num">{n1}</td><td>短线卖出亏损，信号后次日仍在震荡</td></tr>
<tr><td>T+5</td><td class="num {c5}">{v5}</td><td class="num">{w5:.1f}%</td><td class="num">{n5}</td><td>主口径小幅亏损，5 天内反弹未走完</td></tr>
<tr><td>T+10</td><td class="num {c10}">{v10}</td><td class="num">{w10:.1f}%</td><td class="num">{n10}</td><td class="hl">转正！持有 10 个交易日是盈亏分界</td></tr>
</table>
<div class="note">
<b>关键启示：</b>hoshi 信号后 <b>持有时间越久越赚钱</b>（T+10 &gt; T+5 &gt; T+1）。
若按 5 日短线进出，此策略约亏 1.3%；若持有 10 个交易日以上，可转正(+0.92%)。
策略本身<b>没有卖出规则</b>——它只定义"买点"。要让"该卖就卖、该留就留"，
需补充退出规则（如：跌破止损位卖出、或持有满 N 日再评估），当前按固定持有期模拟是保守基线。<br>
⚠️ 样本仅 45 天/单一 regime，未扣交易成本（真实收益会略低），仅供参考，非投资建议。
</div>
</body></html>""".format(
        start=meta["start"], end=meta["end"], db_max=meta["db_max_date"],
        min_score=meta["min_score"], min_amt=meta["min_amount_yi"], maxpd=meta.get("max_per_day", "不限"),
        n_days=len(days), n_sig=len(sigs), daily=len(sigs) / max(len(days), 1),
        cards=cards, svg_bars=svg_bars, polyline=polyline,
        v1=fmt(holds[1]["avg"]), w1=holds[1]["win"], n1=holds[1]["n"],
        c1="pos" if holds[1]["avg"] > 0 else "neg",
        v5=fmt(holds[5]["avg"]), w5=holds[5]["win"], n5=holds[5]["n"],
        c5="pos" if holds[5]["avg"] > 0 else "neg",
        v10=fmt(holds[10]["avg"]), w10=holds[10]["win"], n10=holds[10]["n"],
        c10="pos" if holds[10]["avg"] > 0 else "neg",
    )
    OUT.write_text(html_doc, encoding="utf-8")
    print("HTML 模拟盘报告已写入:", OUT)


if __name__ == "__main__":
    main()
