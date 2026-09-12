"""对 hoshi_replay_result.json 做归因分析。

关键：**绝对收益没有意义，必须减去市场基准。**
如果这两个月大盘等权平均也在跌 8%，那么 T+5 -7.64% 只是 beta，不是策略失效。

输出：
  1. 市场基准（同期全市场等权平均前瞻收益）→ 超额收益
  2. 按模式拆分（confirmation / stabilization）
  3. 按评分区间拆分 → 检验打分是否有效
  4. 按信号日聚集度 → 检验是否只是"大盘暴跌日"的被动放大
  5. 近期（最后 5 个交易日）信号 = 当下可执行的机会

用法： python scripts/hoshi_replay_analysis.py
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger

from core.data.duckdb_source import TdxDB
from scripts.hoshi_replay import FWD_WINDOWS

PROJECT_ROOT = Path(__file__).parent.parent
RESULT = PROJECT_ROOT / "scripts" / "hoshi_replay_result.json"
DB = str(PROJECT_ROOT / "data" / "tdx.duckdb")
BASELINE_DAYS = 90  # 基准计算加载的交易日数（需 >= 回放窗口 + 最长前瞻窗口）


def market_baseline(tdx: TdxDB, dates: list) -> dict:
    """计算每个日期的全市场等权平均前瞻收益（基准）。

    口径与信号一致：close(T+k)/close(T)-1，只用当日有成交且非 ST 的 A 股。
    """
    logger.info(f"计算 {len(dates)} 个交易日的市场基准 ...")
    syms = tdx.get_all_stock_symbols()
    name_map = tdx.get_symbol_name_map()
    from core.screener.hoshi import is_st_name

    syms = [s for s in syms if not is_st_name(name_map.get(s, ""))]

    # days 必须给具体数值：batch_load_daily 的 days=0 会变成 `rn <= 0`（空集），
    # 不是"全部"。取 60 根足够覆盖 45 天回放窗口 + 最长 10 天前瞻。
    df = tdx.batch_load_daily(symbols=syms, days=BASELINE_DAYS, fq="bfq", min_records=1)
    logger.info(f"  基准样本 {len(df)} 只")
    if not df:
        raise RuntimeError("基准样本为空，无法计算超额收益")

    # 建立 date -> 位置 索引
    pos = {}
    closes = {}
    for s, d in df.items():
        d = d.sort_values("date").reset_index(drop=True)
        pos[s] = {pd.Timestamp(x).date(): i for i, x in enumerate(d["date"])}
        closes[s] = d["close"].to_numpy()

    out = {}
    for dt in dates:
        base = {}
        rets = {k: [] for k in FWD_WINDOWS}
        for s, p in pos.items():
            i = p.get(dt)
            if i is None:
                continue
            c = closes[s]
            b = c[i]
            if b <= 0:
                continue
            for k in FWD_WINDOWS:
                j = i + k
                if j < len(c):
                    rets[k].append((c[j] - b) / b * 100.0)
        for k in FWD_WINDOWS:
            base[k] = sum(rets[k]) / len(rets[k]) if rets[k] else None
        out[dt] = base
    return out


def stats_block(vals: list) -> dict:
    if not vals:
        return {}
    n = len(vals)
    return {
        "n": n,
        "均值%": round(sum(vals) / n, 2),
        "中位%": round(sorted(vals)[n // 2], 2),
        "胜率%": round(sum(1 for v in vals if v > 0) / n * 100, 1),
    }


def main():
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    sigs = payload["signals"]
    meta = payload["meta"]
    dates = sorted({s["date"] for s in sigs})
    logger.info(f"载入 {len(sigs)} 条信号，覆盖 {len(dates)} 个交易日")

    tdx = TdxDB(DB)
    try:
        base = market_baseline(tdx, [pd.Timestamp(d).date() for d in dates])
    finally:
        tdx.close()

    # 给每条信号补上基准与超额
    for s in sigs:
        b = base.get(pd.Timestamp(s["date"]).date(), {})
        s["base"] = {f"T+{k}": b.get(k) for k in FWD_WINDOWS}
        s["excess"] = {}
        for k in FWD_WINDOWS:
            v, bv = s["fwd"].get(f"T+{k}"), b.get(k)
            s["excess"][f"T+{k}"] = None if (v is None or bv is None) else round(v - bv, 2)

    lines = []
    P = lines.append
    P("=" * 78)
    P(f"  Hoshi 归因分析   {meta['start']} ~ {meta['end']}  ({meta['n_days']} 个交易日)")
    P("=" * 78)

    # ---- 1. 总体 vs 基准 ----
    vs_base = []
    for k in FWD_WINDOWS:
        tag = f"T+{k}"
        sv = [s["fwd"][tag] for s in sigs if s["fwd"].get(tag) is not None]
        ev = [s["excess"][tag] for s in sigs if s["excess"].get(tag) is not None]
        bv = [base[pd.Timestamp(s["date"]).date()][k]
              for s in sigs
              if s["fwd"].get(tag) is not None
              and base.get(pd.Timestamp(s["date"]).date(), {}).get(k) is not None]
        if not sv:
            continue
        bs, es = stats_block(bv), stats_block(ev)
        vs_base.append([tag, f"{stats_block(sv)['均值%']:.2f}", f"{bs.get('均值%', 0):.2f}",
                        f"{es.get('均值%', 0):.2f}", f"{stats_block(sv)['胜率%']:.1f}",
                        f"{bs.get('胜率%', 0):.1f}"])
    P("")
    P("【1】总体 vs 市场基准（超额 = 信号收益 - 全市场等权收益）")
    P(f"  {'窗口':<6}{'信号均值%':>10}{'基准均值%':>11}{'超额%':>9}{'信号胜率%':>11}{'基准胜率%':>11}")
    P("  " + "-" * 60)
    for r in vs_base:
        P(f"  {r[0]:<6}{float(r[1]):>10.2f}{float(r[2]):>11.2f}{float(r[3]):>9.2f}"
          f"{float(r[4]):>11.1f}{float(r[5]):>11.1f}")

    def cut(pairs, title, headers, order=None):
        """pairs: [(bucket_label, [信号...])] → 打印并返回表格行"""
        rows = []
        for label, sub in pairs:
            v = [s["fwd"]["T+5"] for s in sub if s["fwd"].get("T+5") is not None]
            e = [s["excess"]["T+5"] for s in sub if s["excess"].get("T+5") is not None]
            st, es = stats_block(v), stats_block(e)
            if st:
                rows.append([label, st["n"], f"{st['均值%']:.2f}",
                             f"{es.get('均值%', 0):.2f}", f"{st['胜率%']:.1f}"])
        P("")
        P(title)
        P(f"  {headers[0]:<14}{'数量':>7}{'均值%':>9}{'超额%':>9}{'胜率%':>9}")
        P("  " + "-" * 52)
        for r in rows:
            P(f"  {r[0]:<14}{r[1]:>7}{float(r[2]):>9.2f}{float(r[3]):>9.2f}{float(r[4]):>9.1f}")
        return rows

    # ---- 2. 按模式 ----
    by_mode = cut(
        [(m, [s for s in sigs if s["mode"] == m]) for m in ("confirmation", "stabilization")],
        "【2】按模式拆分（T+5）", ["模式"],
    )

    # ---- 3. 按评分 ----
    buckets = [(9.0, 10.01, "9.0-10.0"), (8.0, 9.0, "8.0-8.9"),
               (7.0, 8.0, "7.0-7.9"), (6.0, 7.0, "6.0-6.9"), (0, 6.0, "<6.0")]
    by_score = cut(
        [(lb, [s for s in sigs if lo <= s["score"] < hi]) for lo, hi, lb in buckets],
        "【3】按评分区间拆分（检验打分是否有效 / T+5）", ["评分区间"],
    )

    # ---- 4. 拥挤度 ----
    per_day = defaultdict(list)
    for s in sigs:
        per_day[s["date"]].append(s)
    day_cnt = {d: len(v) for d, v in per_day.items()}
    crowd_labels = [
        ("冷清(<10)", lambda n: n < 10),
        ("中性(10~50)", lambda n: 10 <= n <= 50),
        ("拥挤(>50)", lambda n: n > 50),
    ]
    by_crowding = cut(
        [
            (lb, [s for s in sigs if f(day_cnt[s["date"]])])
            for lb, f in crowd_labels
        ],
        "【4】按当日全市场信号拥挤度（T+5）",
        ["拥挤度"],
    )

    # ---- 5. 连跌总跌幅 / 当日涨幅敏感性 ----
    def total_drop(s):
        m = re.search(r"\(([-+0-9.]+)%\)", next((g for g in s["signals"] if g.startswith("连跌")), ""))
        return float(m.group(1)) if m else None

    drop_labels = [(lb, lambda d, lo=lo, hi=hi: lo <= d < hi) for lo, hi, lb in
                   [(-999, -20, "<-20%"), (-20, -15, "-20~-15%"), (-15, -10, "-15~-10%"),
                    (-10, -6, "-10~-6%"), (-6, 999, ">-6%")]]
    by_drop = cut(
        [(lb, [s for s in sigs if total_drop(s) is not None and f(total_drop(s))])
         for lb, f in drop_labels],
        "【5】按连跌总跌幅（T+5，检验评分里的「深跌加分」是否反向）", ["跌幅区间"],
    )

    pct_labels = [(lb, lambda c, lo=lo, hi=hi: lo <= c < hi) for lo, hi, lb in
                  [(-999, 0, "<0%"), (0, 2, "0~2%"), (2, 5, "2~5%"), (5, 9, "5~9%"), (9, 999, ">9%")]]
    by_daypct = cut(
        [(lb, [s for s in sigs if f(s["pct_change"])]) for lb, f in pct_labels],
        "【6】按信号日当天涨幅（T+5，检验评分里的「确认日大涨加分」是否反向）", ["当日涨幅"],
    )

    # ---- 7. 信号日聚集度 ----
    top_days = sorted(per_day.items(), key=lambda x: -len(x[1]))[:8]
    P("")
    P("【7】信号最密集的交易日 Top8（判断是否只是大盘暴跌日的被动放大）")
    P(f"  {'日期':<12}{'信号数':>7}{'T+5均值%':>10}{'T+5超额%':>11}")
    P("  " + "-" * 42)
    for d, ss in top_days:
        v = [x["fwd"]["T+5"] for x in ss if x["fwd"].get("T+5") is not None]
        e = [x["excess"]["T+5"] for x in ss if x["excess"].get("T+5") is not None]
        st, es = stats_block(v), stats_block(e)
        P(f"  {d:<12}{len(ss):>7}{(st or {}).get('均值%', 0):>10.2f}{(es or {}).get('均值%', 0):>11.2f}")

    # ---- 8. 近期机会 ----
    P("")
    last_days = sorted(per_day.keys())[-5:]
    P(f"【8】最近 5 个交易日的信号（{' ~ '.join(last_days)}）= 当下可关注")
    recent = [s for s in sigs if s["date"] in last_days]
    recent.sort(key=lambda x: (-x["score"], x["date"]))
    P(f"  {'日期':<12}{'模式':<6}{'代码':<9}{'名称':<10}{'分':>5}{'价':>8}{'当日%':>8}{'T+5%':>8}")
    P("  " + "-" * 70)
    for s in recent[:25]:
        f5 = s["fwd"].get("T+5")
        f5s = f"{f5:+.2f}" if f5 is not None else "   -  "
        mt = "确认" if s["mode"] == "confirmation" else "企稳"
        P(f"  {s['date']:<12}{mt:<6}{s['code'][2:]:<9}{s['name'][:8]:<10}"
          f"{s['score']:>5.1f}{s['price']:>8.2f}{s['pct_change']:>+8.2f}{f5s:>8}")
    P("")
    P("  注：T+5 为 '-' 表示距今不足 5 个交易日，尚未走完。")

    # ---- 6. 结论 ----
    all_v = [s["fwd"]["T+5"] for s in sigs if s["fwd"].get("T+5") is not None]
    all_e = [s["excess"]["T+5"] for s in sigs if s["excess"].get("T+5") is not None]
    st, es = stats_block(all_v), stats_block(all_e)
    b_all = stats_block(
        [base[pd.Timestamp(s["date"]).date()][5]
         for s in sigs
         if s["fwd"].get("T+5") is not None
         and base.get(pd.Timestamp(s["date"]).date(), {}).get(5) is not None]
    )
    P("")
    P("=" * 78)
    P("  结论")
    P("=" * 78)
    P(f"  T+5 绝对收益 {st.get('均值%', 0):+.2f}%，同期全市场等权基准 {b_all.get('均值%', 0):+.2f}%")
    P(f"  T+5 超额收益 {es.get('均值%', 0):+.2f}%，胜率 {st.get('胜率%', 0)}%")
    if es.get("均值%", 0) > 1.0:
        P("  → 扣除大盘 beta 后仍有正超额，策略逻辑成立，可直接用。")
    elif es["均值%"] > -1.0:
        P("  → 超额接近 0：策略基本等于买大盘，需加过滤条件（如板块/量能/趋势强度）。")
    else:
        P("  → 扣除大盘 beta 后仍为负超额，说明当前参数下策略是在**接下跌中的刀**，")
        P("     不建议直接实盘。建议：提高评分门槛、加量能确认、或只在指数站上 MA20 时开仓。")
    P("=" * 78)

    text = "\n".join(lines)
    print(text)
    out = PROJECT_ROOT / "scripts" / "hoshi_replay_analysis.txt"
    out.write_text(text, encoding="utf-8")
    logger.info(f"分析已写入: {out}")

    # 把归因结果写回 payload，并重新渲染自包含 HTML（含归因区块）
    verdict_text = (
        f"T+5 绝对收益 {st.get('均值%', 0):+.2f}%，同期全市场等权基准 "
        f"{b_all.get('均值%', 0):+.2f}%，T+5 超额 {es.get('均值%', 0):+.2f}%（胜率 "
        f"{st.get('胜率%', 0)}%）→ " + (
            "扣除大盘 beta 后仍为正超额，策略逻辑成立，可直接用。"
            if es.get("均值%", 0) > 1.0 else
            "超额接近 0，策略基本等于买大盘，需加过滤（板块/量能/趋势强度）。"
            if es["均值%"] > -1.0 else
            "扣除大盘 beta 后仍为负超额，当前参数下策略在接下跌中的刀，建议提高评分门槛/加量能确认/指数站上 MA20 再开仓。"
        )
    )
    payload["analysis"] = {
        "vs_baseline": vs_base,
        "by_mode": by_mode,
        "by_score": by_score,
        "by_crowding": by_crowding,
        "by_drop": by_drop,
        "by_daypct": by_daypct,
        "verdict": {"text": verdict_text, "excess": es.get("均值%", 0)},
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 重新渲染 HTML（hoshi_replay.render_html 读取 payload 里的归因）
    from scripts.hoshi_replay import OUT_HTML, render_html
    render_html(payload, OUT_HTML)
    logger.info(f"HTML 报告已更新（含归因）: {OUT_HTML}")


if __name__ == "__main__":
    main()
