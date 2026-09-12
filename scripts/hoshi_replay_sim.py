# -*- coding: utf-8 -*-
"""Hoshi 逐日模拟盘：每天按信号买入，统计到现在的盈亏。

回答：每天跑 hoshi 会选出多少只可行股，持有到卖出这些股票整体赚/亏多少。

口径（透明、不隐藏假设）：
  - 买入：每个交易日收盘价，当日所有 hoshi 信号股**等权**各买入一份（每份相同本金）。
  - 卖出：hoshi 本身没有定义卖出规则（它只负责"选买点"）。这里按固定持有期模拟：
        主口径 = 持有 5 个交易日(T+5) 收盘卖出；同时给出 T+1 / T+10 情景对比。
  - 资金：等权，未复利（每笔独立一份本金），不扣佣金印花税（保守起见净值偏乐观，见注）。
  - 覆盖：只有"信号日 + 持有期"都落在数据范围内(<=2026-09-01)的才算已了结；未走完的
        单列"当前持仓"参考。

用法： python scripts/hoshi_replay_sim.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

RESULT = Path(__file__).parent / "hoshi_replay_result.json"


def main():
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    sigs = payload["signals"]
    meta = payload["meta"]
    print("=" * 78)
    print("  Hoshi 逐日模拟盘   {} ~ {}   ({} 个交易日, {} 信号)".format(
        meta["start"], meta["end"], meta["n_days"], len(sigs)))
    print("  最低分 {} · 最低成交额 {}亿 · 每日拥挤度上限 {}".format(
        meta["min_score"], meta["min_amount_yi"], meta.get("max_per_day", "不限")))
    print("=" * 78)

    # ---- 1. 每天选出多少只 ----
    per_day = defaultdict(list)
    for s in sigs:
        per_day[s["date"]].append(s)
    days = sorted(per_day.keys())
    print("\n【1】每天运行的可行股数量（已过拥挤度门控）")
    print("  日期         信号数")
    for d in days:
        print("  {}   {:>4}".format(d, len(per_day[d])))
    print("  ----")
    n_trade_days = len(days)
    print("  有信号交易日 {} 天，共 {} 信号，日均 {:.1f} 只/交易日".format(
        n_trade_days, len(sigs), len(sigs) / max(n_trade_days, 1)))

    # ---- 2. 固定持有期盈亏（等权，每笔一份本金）----
    print("\n【2】等权买入、固定持有 N 个交易日卖出（已了结交易）")
    for hold in (1, 5, 10):
        tag = "T+{}".format(hold)
        closed = [s for s in sigs if s["fwd"].get(tag) is not None]
        if not closed:
            continue
        rets = [s["fwd"][tag] for s in closed]
        wins = sum(1 for r in rets if r > 0)
        total = sum(rets)
        # 等权组合收益 = 每笔一笔本金，组合收益率 = 各笔收益均值（无复利）
        eq_ret = total / len(rets)
        # 若有基准 excess，算超额
        excs = [s.get("excess", {}).get(tag) for s in closed]
        excs = [e for e in excs if e is not None]
        print("  {}: 已了结 {:<4} 笔  合计{} 胜率 {:>5.1f}%  平均{:+.2f}%".format(
            tag, len(rets),
            "{:+.1f}%".format(total) if abs(total) >= 100 else "{:+.2f}%".format(total),
            wins / len(rets) * 100, eq_ret))
        if excs:
            print("      超额(扣大盘beta): 平均 {:+.2f}%".format(sum(excs) / len(excs)))

    # ---- 3. 主口径 T+5 按日拆分（每天买入那批，5日后卖，看每天贡献）----
    hold = 5
    tag = "T+{}".format(hold)
    print("\n【3】主口径 持有{}个交易日：每天那批的收益与贡献".format(hold))
    print("  日期         当日信号  已了结  当日批均值%   累计组合收益率%")
    # 等权组合：每天给当日信号各投一份本金 → 组合收益率 = 已了结单笔收益的等权平均。
    all_closed = []
    day_rows = []
    for d in days:
        ss = [s for s in per_day[d] if s["fwd"].get(tag) is not None]
        if not ss:
            continue
        batch_avg = sum(s["fwd"][tag] for s in ss) / len(ss)
        all_closed.extend(s["fwd"][tag] for s in ss)
        cum = sum(all_closed) / len(all_closed)
        day_rows.append((d, len(per_day[d]), len(ss), batch_avg, cum))
    for d, n_all, n_closed, avg, cum in day_rows:
        print("  {}  {:>6}   {:>4}    {:>+8.2f}     {:>+10.2f}".format(d, n_all, n_closed, avg, cum))
    if day_rows:
        print("  ----")
        print("  T+5 等权组合累计收益率（已了结 {} 笔，等权平均，未扣费）: {:+.2f}%".format(
            len(all_closed), sum(all_closed) / len(all_closed)))

    # ---- 4. 当前持仓（最后未走满持有期的信号）----
    last_date = days[-1] if days else None
    open_pos = [s for s in sigs if s["fwd"].get(tag) is None]
    print("\n【4】当前仍持有（未走满{}个交易日，截至 {})：{} 笔".format(hold, last_date, len(open_pos)))
    print("  日期         代码     名称      分   信号日价   当日%")
    for s in sorted(open_pos, key=lambda x: (-x["score"], x["date"])):
        print("  {}  {}  {:<8}  {:>4.1f}  {:>7.2f}  {:>+6.2f}".format(
            s["date"], s["code"][2:], s["name"][:8], s["score"], s["price"], s["pct_change"]))

    # ---- 5. 结论 ----
    print("\n" + "=" * 78)
    print("  说明")
    print("=" * 78)
    print("  - hoshi 策略只定义『买点』，无卖出规则；本模拟按固定持有期 T+{} 卖出。".format(hold))
    print("  - 等权、每笔一份本金、未复利、未扣佣金/印花税 → 真实成本下收益会略低。")
    print("  - 数据只到 {}，最后 ~{} 个交易日的信号尚未走满持有期，属'当前持仓'，未计入已了结盈亏。".format(
        last_date, hold))
    print("  - 如需『有止盈止损的持仓管理』（该卖就卖、该留就留），需补充明确的退出规则。")


if __name__ == "__main__":
    main()
