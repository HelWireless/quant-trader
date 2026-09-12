"""Hoshi 策略逐日复盘（walk-forward 回放）。

用途：回答"过去两个月，如果每天都跑 hoshi，会看到哪些机会、事后看表现如何"。

设计要点（量化纪律）：
  1. **无未来数据**：每个回放日 d 只用 date <= d 的 K 线（batch_load_daily(end_date=d) 语义），
     并通过 HoshiScreener(as_of=d) 双重保险：最新一根不是 d 的直接丢弃。
  2. **只在真实交易日回放**：日期取自数据库实际成交日期，周末/节假日不会空转报警。
  3. **性能**：全量数据只加载一次，之后在内存里按日切片，避免 N 次全市场查询。
  4. **事后评估**：信号产生后，用 T+1 / T+3 / T+5 / T+10 的真实涨幅评估（这是回看，
     不是交易 —— 实际下单还要考虑 T+1 开盘价与是否一字板）。

用法：
    python scripts/hoshi_replay.py                          # 默认近 2 个月
    python scripts/hoshi_replay.py --start 2026-07-01 --end 2026-09-01
    python scripts/hoshi_replay.py --mode both --min-amount 5e7
    python scripts/hoshi_replay.py --symbols sh600367,sz000001   # 单票调试
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from loguru import logger

from core.data.duckdb_source import TdxDB
from core.screener.hoshi import HoshiScreener

DB_PATH = str(PROJECT_ROOT / "data" / "tdx.duckdb")
OUT_JSON = PROJECT_ROOT / "scripts" / "hoshi_replay_result.json"
OUT_HTML = PROJECT_ROOT / "scripts" / "hoshi_replay_report.html"

LOOKBACK = 90          # 每个回放日向前取多少根 K 线（>= 65 才能算 MA60）
FWD_WINDOWS = [1, 3, 5, 10]  # 事后评估窗口（交易日）


def load_all(tdx: TdxDB, symbols, end_date: str, warmup_days: int):
    """一次性加载回放窗口 + 预热区间的全部数据。"""
    logger.info(f"加载全量数据 (end={end_date}, days={warmup_days}) ...")
    df_dict = tdx.batch_load_daily(
        symbols=symbols, days=warmup_days, fq="bfq", min_records=1, end_date=end_date
    )
    logger.info(f"已加载 {len(df_dict)} 只股票")
    return df_dict


def build_index(df_dict):
    """为每个 symbol 建立 date -> 位置 的索引，用于事后收益计算。"""
    idx = {}
    for sym, df in df_dict.items():
        d = df.sort_values("date").reset_index(drop=True)
        pos = {pd.Timestamp(x).date(): i for i, x in enumerate(d["date"])}
        idx[sym] = (d, pos)
    return idx


def fwd_returns(idx, symbol, sig_date, n_max):
    """计算信号日之后第 k 个交易日的累计涨幅 %%（k in FWD_WINDOWS）。

    返回 dict {1: x, 3: y, ...}，数据不足则为 None。
    """
    if symbol not in idx:
        return {}
    d, pos = idx[symbol]
    i = pos.get(sig_date)
    if i is None:
        return {}
    base = float(d["close"].iloc[i])
    out = {}
    for k in FWD_WINDOWS:
        j = i + k
        out[k] = (
            (float(d["close"].iloc[j]) - base) / base * 100.0 if j < len(d) and base > 0 else None
        )
    return out


def replay(df_dict, idx, dates, mode, min_score, min_amount, name_map, exclude_st=True, max_daily_signals=None):
    """逐日回放，返回 [(signal_dict, ...)]"""
    # MA 只算一次：在完整序列上算好后随切片复用。
    # 否则每个回放日每只票都要重算 sma（5500 票 × 45 天 = 25 万次滚动），慢 5~10 倍。
    # sma 是滚动窗口，只用历史值，提前算不会引入未来数据。
    from core.analysis.indicators import sma

    with_ma = {}
    for sym, df in df_dict.items():
        d = df.copy()
        d["ma20"] = sma(d["close"], 20)
        d["ma60"] = sma(d["close"], 60)
        with_ma[sym] = d

    signals = []
    per_day = []
    day_stats = []

    for d in dates:
        d_ts = pd.Timestamp(d)
        screener = HoshiScreener(
            mode=mode,
            min_score=min_score,
            exclude_st=exclude_st,
            exclude_suspended=True,
            min_amount=min_amount,
            as_of=d,
            max_daily_signals=max_daily_signals,
        )
        hits = []
        for sym, df in with_ma.items():
            # 只看 <= d 的部分（无未来数据）
            sub = df[df["date"] <= d_ts]
            if len(sub) < 65:
                continue
            sub = sub.tail(LOOKBACK)
            r = screener.screen_one(sym, name_map.get(sym, ""), sub)
            if r is not None:
                hits.append(r)

        hits.sort(key=lambda x: x.score, reverse=True)

        # 注意：拥挤度门控在 main() 层按【当日全市场（确认+企稳合计）】统一应用，
        # 因为"当日拥挤度"衡量的是当天整体有多少信号（跨模式），逐模式门控会漏掉
        # 确认、企稳各自 <30 但合计 >30 的普跌日。

        for r in hits:
            fwd = fwd_returns(idx, r.code, d, max(FWD_WINDOWS))
            signals.append(
                {
                    "date": str(d),
                    "code": r.code,
                    "name": r.name,
                    "score": r.score,
                    "price": round(r.price, 2),
                    "pct_change": round(r.pct_change, 2),
                    "signals": r.signals,
                    "mode": mode,
                    "fwd": {f"T+{k}": (round(v, 2) if v is not None else None) for k, v in fwd.items()},
                }
            )
        per_day.append({"date": str(d), "count": len(hits), "codes": [h.code for h in hits]})
        day_stats.append(
            {"date": str(d), "n": len(hits), "stat": dict(screener.stats)}
        )
        if len(hits):
            logger.info(f"  {d}  {mode:<13} 命中 {len(hits)} 只")

    return signals, per_day, day_stats


def summarize(signals):
    """汇总统计：窗口胜率、平均收益、高频标的。"""
    summary = {}
    for k in FWD_WINDOWS:
        vals = [s["fwd"][f"T+{k}"] for s in signals if s["fwd"].get(f"T+{k}") is not None]
        if not vals:
            summary[f"T+{k}"] = None
            continue
        wins = sum(1 for v in vals if v > 0)
        summary[f"T+{k}"] = {
            "样本": len(vals),
            "胜率%": round(wins / len(vals) * 100, 1),
            "平均%": round(sum(vals) / len(vals), 2),
            "中位%": round(sorted(vals)[len(vals) // 2], 2),
            "最好%": round(max(vals), 2),
            "最差%": round(min(vals), 2),
        }

    freq = defaultdict(lambda: {"count": 0, "name": "", "scores": [], "fwd5": []})
    for s in signals:
        e = freq[s["code"]]
        e["count"] += 1
        e["name"] = s["name"]
        e["scores"].append(s["score"])
        v = s["fwd"].get("T+5")
        if v is not None:
            e["fwd5"].append(v)
    top = sorted(
        (
            {
                "code": c,
                "name": v["name"],
                "次数": v["count"],
                "最高分": max(v["scores"]),
                "T+5平均%": round(sum(v["fwd5"]) / len(v["fwd5"]), 2) if v["fwd5"] else None,
            }
            for c, v in freq.items()
        ),
        key=lambda x: (-x["次数"], -(x["最高分"] or 0)),
    )[:30]
    return summary, top


def render_html(payload, out_path):
    """生成自包含 HTML 报告。"""
    import html as _h

    meta = payload["meta"]
    sigs = payload["signals"]
    per_day = payload["per_day"]
    per_day_all = payload.get("per_day_all", {})
    summary = payload["summary"]
    top = payload["top_stocks"]

    # 逐日命中柱状图（内联 SVG，不引外部依赖）
    # 单模式运行时 confirmation 可能不存在，需回退到 stabilization 的日期轴
    dates = [d["date"] for d in per_day_all.get("confirmation", [])] or [
        d["date"] for d in per_day_all.get("stabilization", [])
    ]
    maxn = max(
        [d["n"] for d in per_day_all.get("confirmation", [])]
        + [d["n"] for d in per_day_all.get("stabilization", [])]
        + [1]
    )

    def bars(mode, color):
        data = {d["date"]: d["n"] for d in per_day_all.get(mode, [])}
        out = []
        step = max(1, len(dates) // 45)
        w = 880 / max(len(dates), 1)
        for i, dt in enumerate(dates):
            n = data.get(dt, 0)
            h = n / maxn * 130
            out.append(
                f'<rect x="{i*w:.2f}" y="{140-h:.2f}" width="{max(w-1,1):.2f}" '
                f'height="{h:.2f}" fill="{color}" opacity="0.85"><title>{dt}: {n} 只</title></rect>'
            )
        return "".join(out)

    # 汇总卡片
    cards = []
    for k, v in summary.items():
        if not v:
            continue
        cls = "pos" if v["平均%"] > 0 else "neg"
        cards.append(
            f'<div class="card"><div class="k">{k}</div>'
            f'<div class="v {cls}">{v["平均%"]:+.2f}%</div>'
            f'<div class="s">胜率 {v["胜率%"]}% · 中位 {v["中位%"]:+.2f}% · n={v["样本"]}</div></div>'
        )

    has_excess = any(s.get("excess") for s in sigs)

    # 归因区块（由 hoshi_replay_analysis.py 写入 payload["analysis"]）
    an = payload.get("analysis")

    def an_table(rows, title, headers):
        if not rows:
            return ""
        body = "".join(
            "<tr>" + "".join(f"<td class=num>{c}</td>" if i else f"<td>{c}</td>"
                             for i, c in enumerate(r)) + "</tr>"
            for r in rows
        )
        return (
            f"<h3>{title}</h3><table><thead><tr>"
            + "".join(f"<th class=num>{h}</th>" if i else f"<th>{h}</th>"
                      for i, h in enumerate(headers))
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )

    rows = []
    for s in sigs[:400]:
        f = s["fwd"]
        ex = s.get("excess") or {}

        def cell(v):
            if v is None:
                return '<td class="na">-</td>'
            c = "pos" if v > 0 else ("neg" if v < 0 else "")
            return f'<td class="{c}">{v:+.2f}%</td>'
        mode_tag = '<span class="tag c">确认</span>' if s["mode"] == "confirmation" else '<span class="tag s">企稳</span>'
        ex_cells = "".join(cell(ex.get(f"T+{k}")) for k in (1, 5)) if has_excess else ""
        rows.append(
            f"<tr><td>{s['date']}</td><td>{mode_tag}</td><td class=code>{s['code'][2:]}</td>"
            f"<td>{_h.escape(s['name'])}</td><td class=num>{s['score']}</td>"
            f"<td class=num>{s['price']}</td><td class=num>{s['pct_change']:+.2f}%</td>"
            + "".join(cell(f.get(f"T+{k}")) for k in FWD_WINDOWS)
            + ex_cells
            + "</tr>"
        )

    top_rows = "".join(
        f"<tr><td class=code>{t['code'][2:]}</td><td>{_h.escape(t['name'])}</td>"
        f"<td class=num>{t['次数']}</td><td class=num>{t['最高分']}</td>"
        f"<td class=num>{('%+.2f%%' % t['T+5平均%']) if t['T+5平均%'] is not None else '-'}</td></tr>"
        for t in top
    )

    ex_th = "<th class=num>超额T+1</th><th class=num>超额T+5</th>" if has_excess else ""
    verdict = ""
    if an and an.get("verdict"):
        v = an["verdict"]
        cls = "pos" if v["excess"] > 0 else "neg"
        verdict = (
            f'<div class="verdict {cls}"><b>结论：</b>{_h.escape(v["text"])}</div>'
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Hoshi 策略逐日复盘 {meta['start']} ~ {meta['end']}</title>
<style>
:root{{--bg:#0f1216;--panel:#171b21;--line:#252b33;--fg:#e6edf3;--dim:#8b949e;
--up:#f6465d;--down:#2ebd85;--accent:#58a6ff;}}
*{{box-sizing:border-box}}
body{{margin:0;padding:28px;background:var(--bg);color:var(--fg);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}}
h1{{font-size:22px;margin:0 0 6px}} h2{{font-size:16px;margin:28px 0 12px;color:var(--accent)}}
.meta{{color:var(--dim);font-size:13px;margin-bottom:20px;line-height:1.7}}
.meta code{{background:#1f2530;padding:1px 6px;border-radius:4px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 18px;min-width:172px}}
.card .k{{color:var(--dim);font-size:12px;letter-spacing:.5px}}
.card .v{{font-size:26px;font-weight:600;margin:4px 0}}
.card .s{{color:var(--dim);font-size:12px}}
.pos{{color:var(--up)}} .neg{{color:var(--down)}} .na{{color:#4b535d}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel);
border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th{{background:#1c222a;padding:9px 10px;text-align:left;color:var(--dim);font-weight:500;
position:sticky;top:0}}
td{{padding:7px 10px;border-top:1px solid var(--line)}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
td.code{{font-family:ui-monospace,Consolas,monospace;color:var(--accent)}}
tr:hover td{{background:#1b2129}}
.tag{{padding:1px 7px;border-radius:4px;font-size:11px}}
.tag.c{{background:#12304d;color:#58a6ff}} .tag.s{{background:#3d2a12;color:#e3a008}}
.wrap{{max-height:620px;overflow:auto;border-radius:10px}}
.note{{color:var(--dim);font-size:12px;margin-top:8px;line-height:1.7}}
.verdict{{margin-top:14px;padding:12px 16px;border-radius:8px;font-size:13px;line-height:1.8;
border:1px solid var(--line);background:var(--panel)}}
.verdict.pos{{border-left:3px solid var(--up)}} .verdict.neg{{border-left:3px solid var(--down)}}
h3{{font-size:13px;color:var(--dim);margin:18px 0 6px;font-weight:600}}
.legend{{display:flex;gap:18px;color:var(--dim);font-size:12px;margin:8px 0}}
.sw{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}}
</style></head><body>
<h1>Hoshi 策略逐日复盘</h1>
<div class="meta">
  区间 <code>{meta['start']} ~ {meta['end']}</code> · 交易日 <code>{meta['n_days']}</code> 天 ·
  标的池 <code>{meta['n_symbols']}</code> 只 · 最低评分 <code>{meta['min_score']}</code> ·
  最低成交额 <code>{meta['min_amount_yi']} 亿</code><br>
  信号总数 <code>{len(sigs)}</code>（确认模式 {meta['n_conf']} · 企稳模式 {meta['n_stab']}）·
  数据截止 <code>{meta['db_max_date']}</code>
</div>

<h2>事后表现（相对信号日收盘价）</h2>
<div class="cards">{''.join(cards)}</div>
<div class="note">口径：T+k = 信号日之后第 k 个<b>交易日</b>收盘价相对信号日收盘价的涨幅。
样本不足（区间末尾）的不计入。此表是<b>回看</b>，未扣交易成本，也未考虑 T+1 一字板无法买入的情形。</div>
{verdict}

{('<h2>归因分析</h2>' + an_table(an.get('vs_baseline'), '总体 vs 全市场等权基准',
   ['窗口', '信号均值%', '基准均值%', '超额%', '信号胜率%', '基准胜率%'])
  + an_table(an.get('by_mode'), '按模式（T+5）', ['模式', '数量', '均值%', '超额%', '胜率%'])
  + an_table(an.get('by_score'), '按评分区间（T+5）', ['评分区间', '数量', '均值%', '超额%', '胜率%'])
  + an_table(an.get('by_crowding'), '按当日信号拥挤度（T+5）', ['拥挤度', '数量', '均值%', '超额%', '胜率%'])
  + an_table(an.get('by_drop'), '按连跌总跌幅（T+5）', ['跌幅区间', '数量', '均值%', '超额%', '胜率%'])
  + an_table(an.get('by_daypct'), '按信号日当天涨幅（T+5）', ['当日涨幅', '数量', '均值%', '超额%', '胜率%'])
  ) if an else ''}

<h2>逐日信号分布</h2>
<div class="legend">
  <span><i class="sw" style="background:#58a6ff"></i>确认模式 (confirmation)</span>
  <span><i class="sw" style="background:#e3a008"></i>企稳模式 (stabilization)</span>
</div>
<svg viewBox="0 0 880 170" style="width:100%;height:170px;background:var(--panel);
border:1px solid var(--line);border-radius:10px">
  <line x1="0" y1="140" x2="880" y2="140" stroke="#2b323b"/>
  <line x1="0" y1="10" x2="880" y2="10" stroke="#2b323b" stroke-dasharray="3 3"/>
  <text x="6" y="24" fill="#8b949e" font-size="11">峰值 {maxn}</text>
  {bars('confirmation', '#58a6ff')}
  {bars('stabilization', '#e3a008')}
</svg>

<h2>高频标的（出现次数 Top {len(top)}）</h2>
<table><thead><tr><th>代码</th><th>名称</th><th class=num>次数</th><th class=num>最高分</th>
<th class=num>T+5 平均</th></tr></thead><tbody>{top_rows}</tbody></table>

<h2>信号明细（按得分排序，最多 400 行）</h2>
<div class="wrap"><table>
<thead><tr><th>日期</th><th>模式</th><th>代码</th><th>名称</th><th class=num>得分</th>
<th class=num>价格</th><th class=num>当日</th>
{"".join(f'<th class=num>T+{k}</th>' for k in FWD_WINDOWS)}{ex_th}
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<div class="note">生成时间 {meta['generated_at']}</div>
</body></html>"""
    Path(out_path).write_text(html_doc, encoding="utf-8")
    logger.info(f"HTML 报告已写入: {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=(date.today() - timedelta(days=60)).isoformat())
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--mode", default="both", choices=["both", "confirmation", "stabilization"])
    ap.add_argument("--min-score", type=float, default=5.0)
    ap.add_argument("--min-amount", type=float, default=5e7, help="最低当日成交额（元）")
    ap.add_argument("--symbols", default="", help="只回放指定标的，逗号分隔（调试用）")
    ap.add_argument("--no-exclude-st", action="store_true")
    ap.add_argument("--max-per-day", type=int, default=None,
                    help="每日信号拥挤度上限：当日命中数超过该值则整日放弃（避免市场普跌日接刀）")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    tdx = TdxDB(args.db)
    try:
        name_map = tdx.get_symbol_name_map()
        all_dates = tdx.get_trading_dates(args.start, args.end)
        if not all_dates:
            logger.error("回放区间内无交易日，检查 --start/--end 与数据库日期范围")
            return
        logger.info(f"回放交易日 {len(all_dates)} 天: {all_dates[0]} ~ {all_dates[-1]}")

        if args.symbols.strip():
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        else:
            symbols = tdx.get_all_stock_symbols()

        # 预热：回放起始日之前需要 LOOKBACK 根 K 线
        warmup_start = (pd.Timestamp(all_dates[0]) - pd.Timedelta(days=170)).date()
        n_warm = len(tdx.get_trading_dates(str(warmup_start), all_dates[-1]))
        df_dict = load_all(tdx, symbols, str(all_dates[-1]), n_warm + len(all_dates) + 5)
        idx = build_index(df_dict)

        # 过滤掉预热不足的标的
        warm_set = set(tdx.get_trading_dates(str(warmup_start), str(all_dates[0])))
        enough = {
            s: df for s, df in df_dict.items()
            if sum(1 for x in df["date"] if pd.Timestamp(x).date() in warm_set) >= 65
        }
        logger.info(f"预热后可用于回放: {len(enough)} / {len(df_dict)} 只")

        modes = ["confirmation", "stabilization"] if args.mode == "both" else [args.mode]
        all_sigs, per_day_all = [], {}
        for m in modes:
            logger.info(f"=== 回放模式: {m} ===")
            sigs, per_day, _ = replay(
                enough, idx, all_dates, m, args.min_score, args.min_amount,
                name_map, exclude_st=not args.no_exclude_st,
            )
            all_sigs.extend(sigs)
            per_day_all[m] = [{"date": d["date"], "n": d["count"]} for d in per_day]

        # 每日拥挤度门控（统一按当日全市场合计命中数）：当日总信号 > 上限 → 整日放弃。
        # 实证：拥挤日(>50) T+5 -9.14%/20%，冷清日(<10) +0.91%/49%。
        if args.max_per_day is not None:
            from collections import Counter
            day_total = Counter(s["date"] for s in all_sigs)
            before = len(all_sigs)
            all_sigs = [
                s for s in all_sigs if day_total[s["date"]] <= args.max_per_day
            ]
            dropped_days = sorted(d for d, c in day_total.items() if c > args.max_per_day)
            if dropped_days:
                logger.info(
                    f"拥挤度门控: 丢弃 {len(dropped_days)} 个普跌日 "
                    f"{dropped_days}（合计 {before} → {len(all_sigs)} 信号）"
                )

        all_sigs.sort(key=lambda x: (-x["score"], x["date"]))
        summary, top = summarize(all_sigs)

        db_max = tdx.conn.execute("SELECT MAX(date) FROM raw_kline_daily").fetchone()[0]
        payload = {
            "meta": {
                "start": str(all_dates[0]),
                "end": str(all_dates[-1]),
                "n_days": len(all_dates),
                "n_symbols": len(enough),
                "min_score": args.min_score,
                "min_amount_yi": round(args.min_amount / 1e8, 2),
                "n_conf": sum(1 for s in all_sigs if s["mode"] == "confirmation"),
                "n_stab": sum(1 for s in all_sigs if s["mode"] == "stabilization"),
                "max_per_day": args.max_per_day,
                "db_max_date": str(db_max),
                "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "summary": summary,
            "top_stocks": top,
            "signals": all_sigs,
            "per_day": per_day_all.get(modes[0], []),
            "per_day_all": per_day_all,
        }
        OUT_JSON.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"JSON 已写入: {OUT_JSON}")

        print("\n" + "=" * 72)
        print(f"  Hoshi 逐日复盘  {all_dates[0]} ~ {all_dates[-1]}  ({len(all_dates)} 个交易日)")
        print("=" * 72)
        print(f"  信号总数 : {len(all_sigs)}   (确认 {payload['meta']['n_conf']} / 企稳 {payload['meta']['n_stab']})")
        print(f"  覆盖标的 : {len(set(s['code'] for s in all_sigs))} 只")
        print("-" * 72)
        for k, v in summary.items():
            if v:
                print(f"  {k:<5} 平均 {v['平均%']:+.2f}%  中位 {v['中位%']:+.2f}%  "
                      f"胜率 {v['胜率%']:>5.1f}%  最好 {v['最好%']:+.2f}%  最差 {v['最差%']:+.2f}%  n={v['样本']}")
        print("-" * 72)
        print("  高频标的 Top10:")
        for t in top[:10]:
            f = f"{t['T+5平均%']:+.2f}%" if t["T+5平均%"] is not None else "-"
            print(f"    {t['code'][2:]:<8}{t['name']:<10} {t['次数']:>3} 次  最高分 {t['最高分']:.1f}  T+5均值 {f}")
        print("=" * 72)

        render_html(payload, OUT_HTML)
    finally:
        tdx.close()


if __name__ == "__main__":
    main()
