# Hoshi 策略机制说明（权威最终版口径）

> 本文档描述当前实盘/回测使用的 hoshi 策略完整计算逻辑。对应代码：`code/hoshi_backtest_csv.py`（权威回测器）与 `code/hoshi_backtest_exp.py`（参数化实验引擎，两者口径一致）。

---

## 一、需要什么数据

### 1. 数据内容
- **A股日线 K 线**：`date, open, high, low, close, volume`（成交量单位：股）
- **时间范围**：建议从回测开始日前推 **至少 66 个交易日**（信号需要 MA60 + 最少 65 根历史）；实盘研究用 2009-06 至今全量。
- **股票范围（白名单，必须用白名单不能用黑名单）**：

| 市场 | 允许的代码前缀 |
|---|---|
| 沪市 sh | 600 / 601 / 603 / 605 / 688 / 689 |
| 深市 sz | 000 / 001 / 002 / 003 / 300 / 301 |

  再剔除：**ST / *ST / 退市股 / 上市首日 N 股**。
  ⚠️ 血泪教训：数据库里若混入指数(sh000xxx)、ETF、北交所(bj*)、债券、**国债逆回购(sh204xxx)** 会彻底污染回测——GC003 的"价格"是年化利率 145.50，当股价算出 −98.96% 假暴跌。

### 2. 数据文件格式（CSV 目录模式）
```
scripts/hoshi_csv_long/
├── 000001_平安银行.csv      # 文件名: <6位代码>_<名称>.csv
├── 000002_万 科Ａ.csv
└── ...（每只一个文件）
每个文件内容:
date,open,high,low,close,volume
2009-06-01,18.09,18.5,17.96,18.3,30023500
...
```

### 3. 数据获取链路（见 code/）
```
TDX 行情服务器(pytdx) → data/tdx.duckdb (raw_kline_daily + raw_basic_daily)
                      → export_hoshi_csv.py / append_kline_to_csv.py → CSV 目录
```
- `refresh_tdx_duckdb.py`：pytdx 增量补 K 线（7642 只约 3.5 分钟）。⚠️ 盘前运行会拿到当日假 K 线（OHLC=昨收、量0），必须用 `--max-date` 过滤。
- `export_hoshi_csv.py`：全量导出（含白名单过滤）；`append_kline_to_csv.py`：增量追加新交易日。

---

## 二、策略怎么算

### 1. 入场信号（D 日收盘确认，D+1 开盘买入）
对全市场逐票检测（数据截止 D-1 日）：

| # | 条件 | 参数 |
|---|---|---|
| ① | 均线多头排列 | MA20 > MA60 |
| ② | 近 4 天内 ≥2 天下跌 | 日跌幅 < DROP_THRESH |
| ③ | D-1 为企稳日 | 十字星/小实体（实体 < 3%），或 −2%≤跌幅≤5% 的小阴小阳 |
| ④ | D 日收阳确认 | 当日涨幅 > 0 |
| ⑤ | 评分达标 | score ≥ **8.0**（score 由总跌幅、企稳形态、确认日涨幅加权计算） |

- 确认后 **D+1 开盘价买入**，按 score 从高到低排队。
- **仓位**：本金 50 万，单股 10%（5 万），最多 10 只同时持仓（100股/手取整）。
- **T+1**：买入当日禁止卖出。

### 2. 大盘门控（任一关闭则当日不开新仓）
- **R3 回撤门控**：账户权益从峰值回撤 > 25% → 停手 60 自然日；恢复后 120 天内再触发升级为 120 天。
- **广度门控**：全市场（白名单内）收盘价站上 MA60 的比例 < **20%** → 不开新仓。

### 3. 出场规则（S3/S4 自适应）
- **模式切换**：看最近 10 笔已完成交易的平均收益率，< −1% 切 S4（立即武装），否则 S3（第 14/15 天武装）。
- **止盈（峰值回落跟踪）**：
  - 武装：盘中触及 **+5.2%**（第 15 天后放宽为 +3.2%）；
  - 卖出：武装后从持仓期最高价回落 **1.2%**（放宽后 1.0%）→ 市价卖出。
- **止损（第 15 个交易日起才监控——前 14 天不设止损是原版设计）**：
  - 武装：收盘跌破 **−5.2%** → 记录低点；
  - 反弹卖出：从低点反弹 **+2.2%** → 卖出；
  - 硬止损：跌破 **−8.2%** → 无条件市价割。
- **超时**：第 **25 个交易日**仍未武装止盈 → 开盘价清仓。

### 4. 费用口径
- 佣金 0.025%（最低 5 元，双边）+ 印花税 0.05%（仅卖出）。

---

## 三、怎么跑

```bash
# 1) 全历史回测（目录模式，50万本金）
python code/hoshi_backtest_csv.py --input scripts/hoshi_csv_long \
    --start 2016-01-01 --end 2021-12-31 --out result_node1

# 2) 参数化实验（如：第5天硬止损 + 评分门槛9）
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('hbe','code/hoshi_backtest_exp.py')
hbe = importlib.util.module_from_spec(spec); spec.loader.exec_module(hbe)
hbe.MIN_SCORE=9.0; hbe.LOSS_HARD_START_DAY=5
hbe.TOTAL_CAPITAL=500000
cb,nm,ad = hbe.load_data('scripts/hoshi_csv_long')
r = hbe.run_backtest(cb,nm,ad,start='2016-01-01',end='2021-12-31')
print((r['final_capital']-500000)/500000*100)
"

# 3) 数据刷新（收盘后运行）
python scripts/refresh_tdx_duckdb.py --max-date 2026-09-05
python scripts/append_kline_to_csv.py --start 2026-09-05 --end 2026-09-05
```
⚠️ 回测器要求每只标的 ≥66 根 K 线；导出区间必须远早于回测开始日。
