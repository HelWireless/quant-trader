# -*- coding: utf-8 -*-
"""统计 hoshi 每天选出的信号股数量（2个月回放）"""
import json
from collections import defaultdict

d = json.load(open("scripts/hoshi_replay_result.json", encoding="utf-8"))
sigs = d["signals"]

per_day = defaultdict(list)
for s in sigs:
    per_day[s["date"]].append(s)
dates = sorted(per_day.keys())

print("=== 每天运行选出的信号股数量 ===")
hdr = "{:<12}{:>6}{:>6}{:>6}".format("日期", "信号数", "确认", "企稳")
print(hdr)
for dt in dates:
    ss = per_day[dt]
    nc = sum(1 for s in ss if s["mode"] == "confirmation")
    print("{:<12}{:>6}{:>6}{:>6}".format(dt, len(ss), nc, len(ss) - nc))

print()
print("交易日天数: {}, 总信号: {}, 日均: {:.1f} 只".format(len(dates), len(sigs), len(sigs) / len(dates)))

# 汇总各模式
n_conf = sum(1 for s in sigs if s["mode"] == "confirmation")
n_stab = sum(1 for s in sigs if s["mode"] == "stabilization")
print("确认模式: {} 只, 企稳模式: {} 只".format(n_conf, n_stab))
