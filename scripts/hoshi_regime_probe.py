# -*- coding: utf-8 -*-
"""
================================================================================
 Hoshi 近两月 regime 深挖：市场广度(收盘>MA60占比) vs 信号买入日
================================================================================
 用完整1年数据(hoshi_csv3)算全市场每日广度(收盘>MA60占比，与回测器口径一致：
 昨日收盘>昨日MA60)，对齐 hoshi 原版近两月买入日，验证：
   - 下跌初期(6-25~7-17)广度是否仍≥20%(门控放行)→ 此时买=接飞刀
   - 见底回升后(7-17~9-01)广度与信号的表现
 结论支持是否应给 hoshi 加"下跌初期 regime 闸门"。

 用法：python scripts/hoshi_regime_probe.py
================================================================================
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(ROOT, "scripts", "hoshi_csv3")
BASE = os.path.join(ROOT, ".workbuddy", "hoshi_qmt_kit", "Hoshi_QMT_Kit",
                    "独立CSV回测器", "hoshi_backtest_csv.py")


def load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    m.DEBUG = False
    return m


def compute_breadth_fast(code_bars, date_from="2026-06-20", date_to="2026-09-02"):
    """用每日收盘数组, 每只滑动MA60, 汇总每日广度"""
    from collections import defaultdict
    above = defaultdict(int)
    total = defaultdict(int)
    for bars in code_bars.values():   # bars: [Bar, ...]，Bar有.date/.close
        closes = [(b.date.strftime('%Y-%m-%d'), b.close) for b in bars]
        closes = [x for x in closes if x[0] <= date_to]
        n = len(closes)
        # 找起点：date_from 前至少60根
        # 滑窗算MA60
        for i in range(59, n):
            d = closes[i][0]
            if d < date_from:
                continue
            win = closes[i-59:i+1]
            ma60 = sum(x[1] for x in win) / 60.0
            total[d] += 1
            if closes[i][1] > ma60:
                above[d] += 1
    dates = sorted(above.keys())
    return [(d, above[d] * 100.0 / total[d], total[d]) for d in dates]


def main():
    print("加载数据(含MA预热) ...", flush=True)
    m = load_mod(BASE, "hbase")
    code_bars, names, all_dates = m.load_data(CSV_DIR)
    print(f"标的 {len(code_bars)} 只", flush=True)

    print("\n=== 近两月每日市场广度 (收盘>MA60占比) ===")
    print("日期         广度%   样本")
    rows = compute_breadth_fast(code_bars, "2026-06-20", "2026-09-02")
    # 隔天采样显示, 关键日全显
    key = ("2026-06-25", "2026-06-30", "2026-07-01", "2026-07-06", "2026-07-13",
           "2026-07-17", "2026-07-21", "2026-07-27", "2026-08-03", "2026-08-10",
           "2026-08-17", "2026-08-24", "2026-08-31", "2026-09-01")
    prev = None
    for d, b, n in rows:
        if d in key:
            mark = ""
            if prev is not None and b < 20 and prev >= 20:
                mark = "  <-- 跌破20%门控线"
            if prev is not None and b >= 20 and prev < 20:
                mark = "  <-- 升破20%门控线"
            print(f"{d}   {b:6.1f}  {n}{mark}")
            prev = b


if __name__ == "__main__":
    main()
