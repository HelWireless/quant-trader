# Hoshi 策略 · 运行与复盘

Hoshi（ほし/星）策略：在**中期上升趋势**中捕捉**连跌企稳**的买点。

## 一、日常运行（下次只需一条命令）

```bash
# 推荐：先增量补数据（幂等，可重复跑），再体检、再出今日信号
python scripts/run_hoshi_local.py --refresh

# 其他常用
python scripts/run_hoshi_local.py                          # 数据已最新，跳过补数直接跑
python scripts/run_hoshi_local.py --mode confirmation      # 只跑确认模式（更稳健）
python scripts/run_hoshi_local.py --max-per-day 20         # 收紧每日拥挤度门控
python scripts/run_hoshi_local.py --min-score 6.0          # 提高评分门槛
python scripts/run_hoshi_local.py --as-of 2026-08-25       # 复盘指定日期
```

`--refresh` 会调用 `scripts/refresh_tdx_duckdb.py`（TDX 行情 → `data/tdx.duckdb`）：
- **增量、幂等**：只补新于现有最大日期的 K 线，先删后插，可重复运行。
- **两张表一起写**：`raw_kline_daily`（OHLCV）+ `raw_basic_daily`（preclose/change_pct）。
  ⚠️ 只补 kline 不补 basic → change_pct 缺失 → hoshi **静默漏信号**。
- 数据过期（距今天数 > 5）会**拒绝出信号**，提示先 `--refresh`。

> 入口参数：`--mode`(both|confirmation|stabilization)、`--top`、`--days`、`--min-score`、
> `--min-amount`、`--max-per-day`、`--as-of`、`--no-exclude-st`、`--allow-stale`。
> 结果写入 `scripts/hoshi_local_result.json`。

## 二、两个月逐日复盘（看看会看到哪些机会）

```bash
# 回放 + 归因 + 生成自包含 HTML 报告
python scripts/hoshi_replay.py --start 2026-07-01 --end 2026-09-01 --max-per-day 30
python scripts/hoshi_replay_analysis.py        # 扣大盘 beta 的归因，附 HTML
```

产出：
- `scripts/hoshi_replay_result.json` — 全部信号明细（含 T+1/T+3/T+5/T+10 前瞻收益）
- `scripts/hoshi_replay_report.html` — 自包含可视化报告（信号分布、高频标的、明细表）
- `scripts/hoshi_replay_analysis.txt` — 归因（超额收益 / 按模式 / 按评分 / 按拥挤度）

设计纪律：
- **无未来数据**：每个回放日 d 只用 `date <= d` 的 K 线，并用 `as_of=d` 双保险。
- **只在真实交易日回放**，周末/节假日不空转。
- 前瞻收益相对信号日收盘价，未扣交易成本。

## 三、策略逻辑（`core/screener/hoshi.py`）

- **趋势**：MA20 > MA60（中期多头）。
- **连跌**：近 3 天有 2 天跌幅 < -2%（`confirmation` 模式看 D-4/D-3/D-2/D-1）。
- **企稳**：锤子线 / 十字星 / 小实体+长下影（单针探底）。
- **确认**（confirmation 模式）：企稳次日收涨。
- **过滤**：剔除 ST / 停牌 / 一字板 / 低成交额（僵尸股）/ 陈旧数据。

## 四、2026-09 改进（数据实证，2 个月回放归因驱动）

### 1. 每日拥挤度门控 `max_daily_signals`（最强因子）
当日全市场命中数超过阈值（默认 30）→ **整日放弃**。因为信号扎堆日 = 大盘系统性下跌，
个股"企稳"只是 beta，不是个股机会。

| 当日拥挤度 | 数量 | T+5 均值 | 胜率 |
|---|---|---|---|
| 冷清(<10) | 60 | **+0.91%** | 49.2% |
| 中性(10~50) | 377 | -3.86% | 34.0% |
| 拥挤(>50) | 1296 | -9.03% | 20.8% |

### 2. 评分反转（原评分完全反向）
- 深跌不再加分：跌幅 >-6% 最优（-4.15%/36.6%），<-20% 最差（-9.02%/11.5%）。
- 确认日大涨不再加分：温和 2~5% 最优，>9% 多为诱多。

### 3. 效果对比（2026-07-01 ~ 09-01，扣大盘 beta 后超额）

| 配置 | 信号数 | T+1超额 | T+5超额 | T+10超额 |
|---|---|---|---|---|
| 原策略（旧评分、无门控） | 1864 | -1.37% | -5.64% | -10.57% |
| +门控30 +新评分 | 528 | -0.68% | -3.38% | -3.68% |
| confirmation-only +门控30 +min6 | 234 | **+0.16%** | -2.47% | -4.53% |

> ⚠️ **样本局限**：仅 45 个交易日、单一下行 regime。策略已从"接刀"大幅改善，
> 高分+confirmation 组合接近盈亏平衡，但在**强正超额未出现前不宜重仓实盘**。
> 建议先用小资金/模拟盘跑一段时间，或补 1~2 年多 regime 回测后再定论。
