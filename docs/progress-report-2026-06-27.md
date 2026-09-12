## Quant-Trader 项目进展报告

**日期**: 2026-06-27  
**项目**: A股量化筛选系统 (quant-trader)

---

### 一、全市场分钟K线数据入库

完成了A股全市场分钟级数据的采集、入库和聚合，数据从通达信服务器（pytdx）实时拉取，写入 PostgreSQL 18.4 分区表。

**入库规模**

| 频率 | 行数 | 股票代码数 | 时间范围 | 耗时 |
|------|------|-----------|---------|------|
| 5分钟 | 121,526,912 | 5,204 | 2024-03-22 ~ 2026-06-26 | 81分钟 (1.3只/秒) |
| 15分钟 | 40,542,848 | 5,204 | 同上 | 22分钟 |
| 30分钟 | 20,271,424 | 5,204 | 同上 | 19分钟 |
| 60分钟 | 10,135,712 | 5,204 | 同上 | 17分钟 |

**PostgreSQL 数据库总大小**: 28 GB  
**分区表结构**: 每个频率按月分区（2015-01 ~ 2027-12，共 156 个分区/频率，4 频率 = 624 个分区表）  
**入库日志**: `data/import_log.txt`、`data/aggregate_log.txt`

**技术实现要点**:

- `core/data/pytdx_minute.py` — 通达信分钟数据拉取，支持批量提交、断点续传、自动重连
- `core/data/pg_storage.py` — PostgreSQL 存储层，COPY + temp table merge 批量写入，ON CONFLICT DO NOTHING 去重
- `core/data/minute_aggregator.py` — 5分钟 → 15/30/60分钟聚合引擎，正确处理午间休市（11:30-13:00）
- `scripts/minute_cli.py` — CLI 管理工具，支持 `import-pytdx`、`aggregate`、`stats` 等子命令
- `data/a_share_codes.txt` — 6,142 只A股代码清单（从 quant.db SQLite 提取）

**导入失败**: 357 只（主要是 399xxx 系列深证指数代码，非个股），不影响个股数据完整性。

---

### 二、数据源调研

#### 2.1 a-stock-data（simonlin1212）

GitHub: https://github.com/simonlin1212/a-stock-data

A股全栈数据工具包 V3.2.4，覆盖 7 层数据架构、28 个端点，全部实测可用。

**数据源优先级**:

| 优先级 | 数据源 | 封IP风险 | 覆盖范围 |
|--------|--------|---------|---------|
| 1（首选） | mootdx（通达信） | 不封IP | K线、五档盘口、逐笔成交、财务快照 |
| 2 | 腾讯财经 | 不封IP | PE/PB/市值/换手率/涨跌停、指数、ETF |
| 3 | 新浪/巨潮/同花顺 | 低 | 财报三表、公告、热点归因 |
| 4（仅独有数据） | 东财 eastmoney | 有风控 | 龙虎榜、解禁、融资融券、大宗交易、股东户数、分红、资金流 |

**核心端点（已提取集成）**:

- `tencent_quote()` — 批量 PE/PB/市值，`https://qt.gtimg.cn/q=`，GBK编码，~分隔88字段
- `eastmoney_fund_flow_minute()` — 分钟级资金流向，push2 API
- `stock_fund_flow_120d()` — 120日历史资金流向，push2his API
- `margin_trading()` — 融资融券明细，RPTA_WEB_RZRQ_GGMX
- `block_trade()` — 大宗交易，RPT_DATA_BLOCKTRADE
- `holder_num_change()` — 股东户数变化，RPT_HOLDERNUMLATEST
- `dividend_history()` — 分红送转，RPT_SHAREBONUS_DET
- `dragon_tiger_board()` — 龙虎榜+席位，3个 datacenter 报表串联
- `ths_hot_reason()` — 同花顺热点强势股+题材归因，73ms
- `hsgt_realtime()` — 北向资金分钟级流向，262个时间点

**防封机制**: `em_get()` 全局节流（最小间隔1秒+随机抖动）+ Keep-Alive 会话复用。

#### 2.2 Microsoft Qlib

GitHub: https://github.com/microsoft/qlib

微软开源量化投资平台，6层架构：Infrastructure → Data → Model → Learning → Application → Workflow。

**核心特性**:

- **表达式引擎**: 字符串定义因子，如 `Mean($close, 20)`、`Ref($close, 5)`、`Corr($close, Log($volume+1), 5)`
- **Alpha158**: 158个预构建因子（K线形态、价格特征、滚动特征），窗口 [5, 10, 20, 30, 60]
- **二进制数据格式**: float32 数组，`{field}.{freq}.bin` per instrument，比 HDF5 快 7.4x
- **34种ML模型**: LightGBM、XGBoost、CatBoost、LSTM、GRU、ALSTM、Transformer、GATs 等
- **A股回测配置**: `trade_unit=100`（100股整手）、`limit_threshold=0.095`（涨跌停限制）、`open_cost=0.0005`（手续费）
- **TopkDropoutStrategy**: 维持 top-K 组合，每日 drop n_drop 最差、buy n_drop 最优

**可借鉴点**: 表达式引擎设计、Alpha158 因子体系、二进制存储格式、A股回测参数配置。

#### 2.3 百度网盘历史数据（waizaowang.com）

路径: `E:\BaiduNetdiskDownload\财经数据`

来源: waizaowang.com，预计算好的分钟级CSV数据，按月打包为 zip 文件。

| 频率 | 压缩大小 | zip数 | 时间范围 | 每只/月行数 | 股票代码数 |
|------|---------|-------|---------|------------|-----------|
| 1分钟 | 6.9 GB | 17 | 2021-11 ~ 2023-02 | ~4,800 | 5,120 |
| 5分钟 | 3.7 GB | 19 | 2021-08 ~ 2023-02 | ~960 | 5,120 |
| 15分钟 | 1.3 GB | 19 | 2021-08 ~ 2023-02 | ~320 | 5,120 |
| 30分钟 | 0.7 GB | 19 | 2021-08 ~ 2023-02 | ~160 | 5,120 |
| 60分钟 | 0.4 GB | 19 | 2021-08 ~ 2023-02 | ~80 | 5,120 |

**总压缩大小**: 13.3 GB，解压后约 50+ GB

**CSV 格式差异**:

- 5/15/30/60分钟: `code,name,ktype,fq,tdate,open,close,high,low,cjl,cje,hsl`（含复权字段 fq=0不复权/fq=2前复权）
- 1分钟: `code,tdate,open,close,high,low,cjl,cje,cjjj`（无name/ktype/fq，多成交均价 cjjj）

**数据覆盖时间线**:

```
waizaowang:  2021-08 ──────────────── 2023-02
                                       ↑ 1年断层
pytdx:                                2024-03 ──────────────── 2026-06
```

**注意事项**: 202110.zip 的1分钟数据为空（仅有header）；5/15/30/60分钟数据含复权字段需去重；文件名GBK编码需特殊处理。

---

### 三、a-stock-data 模块集成

将 a-stock-data 的核心数据函数提取为 `core/data/` 下的独立模块，接入现有筛选流水线。

#### 3.1 新建模块清单

| 文件 | 行数 | 功能 | 依赖 |
|------|------|------|------|
| `core/data/em_client.py` | 141 | 东财统一限流层 + datacenter helper | requests |
| `core/data/tencent_quote.py` | 178 | 腾讯实时行情（PE/PB/市值/换手率） | urllib（标准库） |
| `core/data/eastmoney_flow.py` | 188 | 资金流向（分钟级 + 120日历史） | em_client |
| `core/data/eastmoney_capital.py` | 375 | 融资融券/大宗交易/股东户数/分红/龙虎榜 | em_client |
| `core/data/ths_signals.py` | 233 | 同花顺热点归因 + 北向资金 | requests |

**共计**: 1,115 行新代码

#### 3.2 模块架构

```
core/data/
├── em_client.py          ← 东财限流共享层（em_get, eastmoney_datacenter）
├── tencent_quote.py      ← 腾讯实时行情（TencentQuote 类）
├── eastmoney_flow.py     ← 资金流向（EastmoneyFundFlow 类）
├── eastmoney_capital.py  ← 资金面/筹码（EastmoneyCapital 类）
├── ths_signals.py        ← 同花顺信号（THSSignals 类）
├── realtime_bridge.py    ← [待创建] 桥接到筛选流水线
├── pg_storage.py         ← PostgreSQL 分钟K线存储
├── pytdx_minute.py       ← 通达信分钟数据拉取
├── minute_aggregator.py  ← 分钟K线聚合
├── minute_bridge.py      ← 分钟数据桥接到指标计算
└── ...
```

#### 3.3 使用示例

```python
# 腾讯实时行情
from core.data.tencent_quote import TencentQuote
tq = TencentQuote()
quotes = tq.batch_quote(["600519", "000858", "300750"])
# → {code: {name, price, pe_ttm, pb, mcap_yi, turnover_pct, ...}}

# 资金流向
from core.data.eastmoney_flow import EastmoneyFundFlow
ff = EastmoneyFundFlow()
summary = ff.flow_summary("600519", days=5)
# → {code, main_net_sum, super_net_sum, trend: "inflow"/"outflow"}

# 融资融券摘要
from core.data.eastmoney_capital import EastmoneyCapital
ec = EastmoneyCapital()
margin = ec.margin_summary("600519", days=10)
# → {rzye_latest(亿元), rzye_change, rzye_change_pct}

# 同花顺热点
from core.data.ths_signals import THSSignals
ths = THSSignals()
hot = ths.hot_reason()  # 当日强势股 + 题材归因
nb = ths.northbound_summary()  # 北向资金今日摘要
```

---

### 四、数据覆盖全景图

```
时间轴:
2021-08    2023-02    2024-03              2026-06
  │          │          │                    │
  ├── waizaowang ──┤   ├── pytdx 数据 ──────┤
  │  5/15/30/60min │   │   5/15/30/60min     │
  │  1min(2021-11起)│   │   1min(2024-03起)   │
  │                │   │                     │
  │    ← 1年断层 →  │   │                     │
  │                │   │                     │
  └── 13.3GB zip ──┘   └── 28GB PostgreSQL ──┘
```

**已有数据**:
- PostgreSQL: 5,204只股票 × 4频率 × 2年分钟K线 = 1.92亿行, 28GB
- 百度网盘: 5,120只股票 × 5频率 × 1.5年 = ~13.3GB（待导入）

**待解决**:
- 2023-03 ~ 2024-02 的1年数据断层（可用 pytdx 拉满 800 根 bar 覆盖，或从其他渠道补充）

---

### 五、待完成事项

1. **realtime_bridge.py** — 将实时数据（腾讯行情/资金流向/融资融券）桥接到 `core/screener/fundamentals.py` 的筛选流水线，替代或增强现有 AkShare 数据源
2. **waizaowang 历史数据导入** — 编写 zip 解压 + CSV 解析 + fq 去重的导入脚本，补充 2021-2023 历史
3. **数据断层补全** — 用 pytdx 或其他方式填补 2023-03 ~ 2024-02 的空白
4. **pyproject.toml** — 添加 `requests` 依赖（新模块需要）
5. **qlib 模式借鉴** — 考虑引入表达式引擎或 Alpha158 因子体系
