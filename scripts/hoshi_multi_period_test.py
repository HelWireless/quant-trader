# -*- coding: utf-8 -*-
"""
================================================================================
 Hoshi：多区间稳健性检验 —— 原版(第15天才止损) vs 全程硬止损
================================================================================
 只在单一区间对比容易过拟合（比如近两月单边下跌，全程止损天然占优）。
 本脚本把 2025-09-01~2026-09-01 切成多个子区间（季度/半年/全年），
 每个区间分别用两版规则跑，看"全程硬止损"是否在各段稳定占优。

 复用 load_data() 只加载一次全市场数据，再逐区间调用 run_backtest()，
 避免每个区间都重读 5016 个 CSV。

 用法：
   python scripts/hoshi_multi_period_test.py
================================================================================
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(ROOT, "scripts", "hoshi_csv3")
BASE = os.path.join(ROOT, ".workbuddy", "hoshi_qmt_kit", "Hoshi_QMT_Kit",
                    "独立CSV回测器", "hoshi_backtest_csv.py")
FULLSTOP = os.path.join(ROOT, "scripts", "hoshi_backtest_fullstop.py")
V3 = os.path.join(ROOT, "scripts", "hoshi_backtest_v3.py")

CAPITAL = 500000.0

# 子区间：(标签, start, end)
PERIODS = [
    ("2025Q4", "2025-09-01", "2025-11-30"),
    ("2026Q1", "2025-12-01", "2026-02-28"),
    ("2026Q2", "2026-03-01", "2026-05-31"),
    ("2026Q3", "2026-06-01", "2026-09-01"),
    ("2025H2", "2025-09-01", "2025-12-31"),
    ("2026H1", "2026-01-01", "2026-06-30"),
    ("全年  ", "2025-09-01", "2026-09-01"),
]


def load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    m.DEBUG = False   # 关掉逐笔日志
    return m


def summarize(res):
    closed = res["closed"]
    n = len(closed)
    if not n:
        return dict(ret=0.0, n=0, win=0.0, pnl=0.0, worst=0.0, med=0.0, stops=len(res["stops"]))
    rets = sorted(t["return_pct"] for t in closed)
    wins = sum(1 for t in closed if t["pnl"] > 0)
    return dict(
        ret=(res["final_capital"] - CAPITAL) / CAPITAL * 100.0,
        n=n,
        win=wins * 100.0 / n,
        pnl=sum(t["pnl"] for t in closed),
        worst=rets[0],
        med=rets[len(rets) // 2],
        stops=len(res["stops"]),
    )


def main():
    print("加载数据（三版各一次，约 30s）...", flush=True)
    mods = {
        "原版": load_mod(BASE, "hbase"),
        "全程止损": load_mod(FULLSTOP, "hfull"),
        "V3硬止损优先": load_mod(V3, "hv3"),
    }
    data = {}
    for k, m in mods.items():
        cb, nm, dt = m.load_data(CSV_DIR)
        data[k] = (m, cb, nm, dt)
    print("加载完成: 各 %d 只\n" % len(data["原版"][1]), flush=True)

    print("=" * 112)
    print("多区间稳健性检验 —— 原版 vs 全程硬止损 vs V3(全程+硬止损优先)")
    print("=" * 112)
    print("%-7s | %-25s | %-25s | %-25s" % ("区间", "原版(第15天止损)", "全程止损", "V3 全程+硬止损优先"))
    print("%-7s | %7s %4s %6s %7s | %7s %4s %6s %7s | %7s %4s %6s %7s"
          % ("", "收益%", "笔", "胜率%", "最差笔", "收益%", "笔", "胜率%", "最差笔",
             "收益%", "笔", "胜率%", "最差笔"))
    print("-" * 112)

    keys = ["原版", "全程止损", "V3硬止损优先"]
    wins = {k: 0 for k in keys}
    tot = {k: 0.0 for k in keys}
    for label, s, e in PERIODS:
        rs = {}
        for k in keys:
            m, cb, nm, dt = data[k]
            rs[k] = summarize(m.run_backtest(cb, nm, dt, start=s, end=e))
            tot[k] += rs[k]["ret"]
        best = max(keys, key=lambda k: rs[k]["ret"])
        wins[best] += 1
        row = "%-7s |" % label
        for k in keys:
            r = rs[k]
            row += " %7.2f %4d %6.1f %7.2f |" % (r["ret"], r["n"], r["win"], r["worst"])
        print(row)

    print("-" * 112)
    print("各版取得最优的区间数: " + "  ".join("%s %d/%d" % (k, wins[k], len(PERIODS)) for k in keys))
    print("累计收益率之和:      " + "  ".join("%s %.2f%%" % (k, tot[k]) for k in keys))
    print()
    print("说明：各区间独立跑（权益曲线/R3 门控每段重置），只看版本间相对差异，")
    print("      不是可累加的策略收益。")


if __name__ == "__main__":
    main()
