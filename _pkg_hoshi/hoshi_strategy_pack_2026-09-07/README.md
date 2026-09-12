# Hoshi 策略包（2026-09-07）

量化策略 hoshi 的完整机制说明 + 实验验证结论 + 全部源代码。

## 先看这两个文件

1. **`01_strategy_mechanism_and_data.md`** —— 策略怎么算：入场信号 5 条件、仓位规则、双门控、S3/S4 出场规则、数据格式与获取链路、运行命令。
2. **`02_experiment_results.md`** —— 我们验证下来哪些更好：
   - **实盘稳健首选 = hard5_score9**（评分门槛 9 + 第 5 天硬止损）：10 个窗口（5 指定 + 5 随机）全部正收益，累加 328 万 > 原版 308 万，且通过涨跌停失真审计。
   - **吃满牛市 = baseline 原版**：大牛窗口收益最高，但亏损窗口 −8%~−14%。
   - **S4 系（423 万/465 万）是虚高假象**：未建模涨跌停导致，实盘不可实现，勿用。

## 目录

```
├── 01_strategy_mechanism_and_data.md          ← 策略机制 + 数据说明
├── 02_experiment_results.md        ← 实验结果汇总
├── code/                             ← 源代码（纯 Python 标准库，回测器无第三方依赖）
│   ├── hoshi_backtest_csv.py         权威原版回测器（CLI）
│   ├── hoshi_backtest_exp.py         参数化实验引擎（MIN_SCORE / LOSS_HARD_START_DAY 可调）
│   ├── hoshi_exp_matrix.py           7方案×5节点批量实验驱动
│   ├── hoshi_random_test.py          随机窗口 out-of-sample 稳健性检验
│   ├── hoshi_audit.py                涨跌停失真审计
│   ├── hoshi_diag_node2.py           评分分桶诊断（单窗口）
│   ├── hoshi_diag_crosswindow.py     评分分桶诊断（跨窗口 trade-off）
│   ├── refresh_tdx_duckdb.py         TDX 行情 → DuckDB 增量刷新（需 pytdx/duckdb/loguru）
│   ├── export_hoshi_csv.py           DuckDB → CSV 白名单导出
│   └── append_kline_to_csv.py        CSV 增量追加新交易日
├── logs/                             ← 实验原始日志
│   ├── hoshi_exp_matrix.log          7方案×5节点矩阵结果
│   ├── hoshi_random_test.log         随机窗口复测结果
│   ├── hoshi_audit.log               失真审计结果
│   └── hoshi_live_replay_0907.log    09-07 开盘前实盘回放
└── docs/
    ├── Hoshi_improvement_results_2026-09-04.md   完整阶段报告（含性能瓶颈分析）
    └── Hoshi_opening_decision_2026-09-07.md            实盘决策单样例
```

## 快速开始

```bash
# 回测（无需任何第三方依赖）
python code/hoshi_backtest_csv.py --input <CSV目录> --start 2016-01-01 --end 2021-12-31 --out result

# CSV 目录格式：每只股票一个文件 <6位代码>_<名称>.csv
# 内容：date,open,high,low,close,volume （日线，至少回测开始前 66 个交易日）
```

数据链路（刷新/导出需要 pytdx + duckdb + loguru）见 `01_strategy_mechanism_and_data.md` 第三节。
