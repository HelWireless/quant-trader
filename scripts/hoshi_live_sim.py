# -*- coding: utf-8 -*-
"""Hoshi 真实持仓管理模拟器：买入 → 持有 → 止盈/止损卖出。

回答：每天跑 hoshi 选出多少只，按真实交易规则（止盈/止损/最长持有）买卖，到现在赚/亏多少。

与 hoshi_replay_sim.py（固定持有期）不同，本脚本实现**真实的持仓管理**：
  - 买入：信号日收盘价买入（每笔一份本金，等权）。
  - 卖出：逐日盯盘，任一条件先触发即卖——
      止盈：收盘价 >= 买入价 * (1 + take_profit)
      止损：收盘价 <= 买入价 * (1 - stop_loss)
      最长持有：持有 max_hold 个交易日后收盘强制卖出（兜底）。
  - 若到数据期末仍未触发，计为"当前持仓"，按最新收盘价浮动估值（未了结，不计入已实现盈亏）。

参数全部可配置（默认一组合理值，用户确认后可覆盖）：
  python scripts/hoshi_live_sim.py --take-profit 0.10 --stop-loss 0.07 --max-hold 20

数据：从 data/tdx.duckdb 取每只信号股在信号日之后的逐日收盘价。
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
RESULT = PROJECT_ROOT / "scripts" / "hoshi_replay_result.json"
DB = PROJECT_ROOT / "data" / "tdx.duckdb"
OUT = PROJECT_ROOT / "scripts" / "hoshi_live_sim_result.json"


def load_closes(db_path, symbols, start_date, end_date):
    """取若干股票在 [start, end] 的逐日收盘价，返回 {code: [(date, close), ...]}"""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        sym_str = ", ".join(f"'{s}'" for s in symbols)
        rows = con.execute(
            f"SELECT symbol, date, close FROM raw_kline_daily "
            f"WHERE symbol IN ({sym_str}) AND date >= DATE '{start_date}' "
            f"AND date <= DATE '{end_date}' ORDER BY symbol, date"
        ).fetchall()
    finally:
        con.close()
    out = defaultdict(list)
    for sym, d, c in rows:
        out[sym].append((d, float(c)))
    return dict(out)


def simulate(sig, closes, take_profit, stop_loss, max_hold):
    """单笔信号按规则模拟，返回 dict 或 None(无法模拟)。

    sig: {date, code, name, score, price, ...}
    closes: 该股票从 signal_date 起的 [(date, close)]（升序）
    返回 {signal_date, code, name, score, buy_date, buy_price, sell_date, sell_price,
          hold_days, ret_pct, exit_reason, status}
    """
    buy_price = sig["price"]
    if not closes:
        return None
    # closes 里第一根 >= 信号日的才算买入后第一个交易日
    seq = [c for c in closes if c[0] >= pd.Timestamp(sig["date"]).date()]
    if not seq:
        return None
    # 买入在信号日收盘，持有从下一交易日开始盯盘
    held = 0
    for d, close in seq:
        if d == pd.Timestamp(sig["date"]).date():
            continue  # 信号日当天不卖
        held += 1
        ret = close / buy_price - 1.0
        if ret >= take_profit:
            return {"status": "closed", "sell_date": str(d), "sell_price": close,
                    "hold_days": held, "ret_pct": round(ret * 100, 2),
                    "exit_reason": "take_profit"}
        if ret <= -stop_loss:
            return {"status": "closed", "sell_date": str(d), "sell_price": close,
                    "hold_days": held, "ret_pct": round(ret * 100, 2),
                    "exit_reason": "stop_loss"}
        if held >= max_hold:
            return {"status": "closed", "sell_date": str(d), "sell_price": close,
                    "hold_days": held, "ret_pct": round(ret * 100, 2),
                    "exit_reason": "max_hold"}
    # 数据结束仍未触发 → 当前持仓
    last_d, last_c = seq[-1]
    return {"status": "open", "sell_date": str(last_d), "sell_price": last_c,
            "hold_days": held, "ret_pct": round(last_c / buy_price - 1, 4) * 100,
            "exit_reason": "open"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--take-profit", type=float, default=0.10, help="止盈幅度（默认10%）")
    ap.add_argument("--stop-loss", type=float, default=0.07, help="止损幅度（默认7%）")
    ap.add_argument("--max-hold", type=int, default=20, help="最长持有交易日数（兜底卖出）")
    ap.add_argument("--end", default="2026-09-01", help="数据截止日")
    args = ap.parse_args()

    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    sigs = payload["signals"]
    meta = payload["meta"]

    # 取所有信号股在信号日之后的收盘价
    symbols = sorted({s["code"] for s in sigs})
    closes_all = load_closes(DB, symbols, meta["start"], args.end)

    results = []
    for s in sigs:
        r = simulate(s, closes_all.get(s["code"], []), args.take_profit,
                     args.stop_loss, args.max_hold)
        if r:
            r.update({"signal_date": s["date"], "code": s["code"],
                      "name": s["name"], "score": s["score"],
                      "buy_price": s["price"], "mode": s.get("mode", "")})
            results.append(r)

    # ---- 统计 ----
    closed = [r for r in results if r["status"] == "closed"]
    open_pos = [r for r in results if r["status"] == "open"]
    print("=" * 78)
    print("  Hoshi 真实持仓管理模拟   {} ~ {}  ({} 信号)".format(
        meta["start"], args.end, len(sigs)))
    print("  止盈 {:.0%} · 止损 {:.0%} · 最长持有 {} 交易日".format(
        args.take_profit, args.stop_loss, args.max_hold))
    print("=" * 78)

    # 每天选出多少只
    per_day = defaultdict(list)
    for s in sigs:
        per_day[s["date"]].append(s)
    days = sorted(per_day.keys())
    print("\n【1】每天运行选出的可行股数")
    for d in days:
        print("  {}   {:>4} 只".format(d, len(per_day[d])))
    print("  ----")
    print("  有信号 {} 天，共 {} 信号，日均 {:.1f} 只/交易日".format(
        len(days), len(sigs), len(sigs) / max(len(days), 1)))

    # 已了结交易盈亏
    print("\n【2】已了结交易（触发止盈/止损/最长持有）")
    print("  已了结 {} 笔 · 仍持有 {} 笔".format(len(closed), len(open_pos)))
    if closed:
        rets = [r["ret_pct"] for r in closed]
        wins = sum(1 for r in rets if r > 0)
        eq_ret = sum(rets) / len(rets)
        print("  等权组合已实现收益率: {:+.2f}%   胜率 {:>5.1f}%".format(eq_ret, wins / len(rets) * 100))
        by_reason = defaultdict(int)
        for r in closed:
            by_reason[r["exit_reason"]] += 1
        print("  卖出原因分布:", dict(by_reason))
        # 平均持有天数
        avg_hold = sum(r["hold_days"] for r in closed) / len(closed)
        print("  平均持有天数: {:.1f}".format(avg_hold))
        print("\n  明细（按卖出日期）")
        print("  信号日     代码       名称      买入价   卖出价   持有   收益%   原因")
        for r in sorted(closed, key=lambda x: x["sell_date"]):
            print("  {}  {}  {:<8}  {:>6.2f}  {:>6.2f}  {:>3}天  {:>+6.2f}  {}".format(
                r["signal_date"], r["code"][2:], r["name"][:8], r["buy_price"],
                r["sell_price"], r["hold_days"], r["ret_pct"], r["exit_reason"]))

    # 当前持仓（浮动）
    if open_pos:
        print("\n【3】当前持仓（截至 {}，未触发卖出，浮动估值）".format(args.end))
        print("  信号日     代码       名称      买入价   现价     浮动%   持有")
        for r in sorted(open_pos, key=lambda x: (-x["score"], x["signal_date"])):
            print("  {}  {}  {:<8}  {:>6.2f}  {:>6.2f}  {:>+6.2f}  {:>3}天".format(
                r["signal_date"], r["code"][2:], r["name"][:8], r["buy_price"],
                r["sell_price"], r["ret_pct"], r["hold_days"]))

    print("\n" + "=" * 78)
    print("  说明")
    print("=" * 78)
    print("  - 买入=信号日收盘；卖出=逐日收盘价触发条件单（止盈/止损/最长持有，先到先卖）。")
    print("  - 等权、每笔一份本金、未复利、未扣佣金/印花税。真实成本下收益略低。")
    print("  - 参数: 止盈{:.0%}/止损{:.0%}/最长{}天（可用 --take-profit/--stop-loss/--max-hold 覆盖）。".format(
        args.take_profit, args.stop_loss, args.max_hold))
    print("  - '仍持有'为浮动估值，未计入已实现收益。")

    OUT.write_text(json.dumps({
        "params": {"take_profit": args.take_profit, "stop_loss": args.stop_loss,
                   "max_hold": args.max_hold, "end": args.end},
        "n_signals": len(sigs), "n_closed": len(closed), "n_open": len(open_pos),
        "closed_eq_ret": round(sum(r["ret_pct"] for r in closed) / len(closed), 2) if closed else None,
        "closed_win_rate": round(sum(1 for r in closed if r["ret_pct"] > 0) / len(closed) * 100, 1) if closed else None,
        "trades": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结果已写入: {}".format(OUT))


if __name__ == "__main__":
    main()
