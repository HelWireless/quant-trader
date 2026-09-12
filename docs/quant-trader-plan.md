## Quant-Trader 选股筛选与分析系统 — 全面规划报告

**日期:** 2026-06-27
**项目:** C:\Users\cody\PycharmProjects\quant-trader

---

## 一、已完成的环境搭建

### 1.1 基础项目框架

在 PycharmProjects 下创建了 `quant-trader` 项目，基于 Python + FastAPI，包含以下核心模块:

- `app/` — FastAPI Web 应用入口、路由、配置
- `core/data/` — 数据获取层（已封装 AkShare）
- `core/strategy/` — 策略基类 + 双均线示例策略
- `core/backtest/` — 简易回测引擎骨架
- `core/analysis/` — 技术指标计算（SMA/EMA/MACD/RSI/KDJ/BOLL）
- `tests/` — 单元测试

### 1.2 已安装的工具与库

| 工具/库 | 版本 | 用途 |
|---------|------|------|
| Python | 3.9.13 | 主开发语言 |
| Node.js | 25.4.0 | ttskill CLI 运行时 |
| BaoStock | 0.9.20 | A 股分钟级 K 线数据 |
| AkShare | 1.18.64 | 东方财富等数据源爬虫封装 |
| ttskill CLI | 0.1.2 | 天天基金 API 工具（已登录，26 个 Skill 已安装） |
| mx-moni 技能 | 已下载 | 东方财富模拟投资组合插件（MX_APIKEY 已配置） |

### 1.3 已克隆的外部代码库

| 仓库 | 技术栈 | 核心能力 |
|------|--------|----------|
| **daily_stock_analysis** | Python + FastAPI + React | AI 股票分析系统：11 个数据源自动 fallback、16 种策略、14 种通知渠道、多 Agent 架构、Web/桌面/CLI/API |
| **OpenStock-Enhanced** | Next.js + TypeScript + MongoDB | 开源股票追踪平台：实时行情、价格预警、公司洞察、TradingView 图表 |
| **TradingAgents** | Python + LangGraph | 多 Agent LLM 交易决策框架：13 个角色（分析师/研究员/交易员/风控/基金经理）、辩论机制、自反思学习 |
| **obscura** | Rust 二进制 | 无头浏览器引擎：30MB 内存、85ms 加载、反检测、CDP 兼容，适合爬虫 |

### 1.4 本地数据资产盘点

**东方财富交易软件数据 (`C:\eastmoney\dfcf\data\ClosedDownload`):**

| 目录 | 内容 | 格式 | 大小 |
|------|------|------|------|
| `Data/SHANGHAI` | 上海全市场日线 + 5 分钟线 | .dat 二进制 (V43) | ~560MB |
| `Data/SHENZHEN` | 深圳全市场日线 + 5 分钟线 | .dat 二进制 (V43) | ~716MB |
| `Data/BANKUAI` | 板块日线 + 5 分钟线 | .dat 二进制 (V43) | ~230MB |
| `day64/sh`, `sz`, `bk` | 按日期的日线快照 | .dat 文件/日期 | 近期 17 个交易日 |
| `min5/sh`, `sz`, `bk` | 按日期的 5 分钟线快照 | .dat 文件/日期 | 近期 17 个交易日 |
| `month64/`, `year64/` | 月线、年线快照 | .dat 文件/日期 | 近期数据 |

**百度网盘下载 (`E:\BaiduNetdiskDownload\`):**

- `股票历史日线数据.rar` — 历史日线数据包（待解压分析）

---

## 二、各代码库能力矩阵

### 2.1 daily_stock_analysis — 最完整的参考实现

这是目前功能最丰富的开源 A 股分析系统，值得深度参考和复用:

**数据获取层（11 个数据源，自动 fallback）:**

| 优先级 | 数据源 | 特点 |
|--------|--------|------|
| P0 | efinance (东方财富) | 免费、无需 token、A 股首选 |
| P0 | TickFlow | 市场指数、涨跌家数 |
| P1 | AkShare | 东方财富爬虫封装、基本面数据 |
| P2 | Tushare Pro | 需 token、数据全面 |
| P2 | Pytdx (通达信) | 直连行情服务器 |
| P3 | BaoStock | A 股免费数据 |
| P4 | YFinance | 美股/港股/日韩 |
| P5 | Longbridge | 美股/港股备用 |
| — | Finnhub / Alpha Vantage / Tencent | 补充数据源 |

**新闻搜索（7 个引擎，多 key 轮询）:** Anspire AI Search、SerpAPI、Tavily、Bocha、Brave Search、MiniMax、SearXNG

**AI 分析层:** 通过 LiteLLM 统一调用 Gemini/Claude/GPT/DeepSeek/Qwen/Ollama 等 8+ 模型提供商

**16 种内置策略（YAML 驱动，可扩展）:** 牛趋势、均线金叉、缩量回踩、放量突破、龙头战法、底部放量、一阳三线、缠论、波浪理论、箱体震荡、热点题材、事件驱动、成长质量、预期重估、情绪周期

**14 种通知渠道:** 企业微信、飞书、Telegram、Discord、Slack、Email、钉钉、Pushover、PushPlus、ServerChan3、Gotify、Ntfy、AstrBot、自定义 Webhook

**关键特性:** 多市场交易日历（A/港/美/日/韩）、GitHub Actions 零成本定时运行、Docker 部署、Web/桌面/CLI/API/Bot 多种运行模式、历史回测评估

### 2.2 TradingAgents — AI 决策层参考

适合作为高级选股决策的 AI Agent 层参考:

**5 阶段分析流水线:** 分析师团队（市场/情绪/新闻/基本面）→ 研究辩论（多空博弈）→ 交易员提案 → 风控辩论（激进/保守/中立）→ 基金经理最终决策

**数据源:** Yahoo Finance（核心）、Alpha Vantage（备用）、FRED 宏观数据（40+ 指标）、Polymarket 预测市场、StockTwits/Reddit 社交情绪

**特色:** 决策记忆 + 自反思学习（用实际收益评估过去决策，注入未来分析）

### 2.3 OpenStock-Enhanced — Web 展示层参考

Next.js 全栈 Web 应用，适合作为用户界面参考: TradingView 图表集成、实时价格追踪、自定义预警、公司洞察面板。使用 Finnhub 作为行情数据源，MongoDB 持久化。

### 2.4 obscura — 数据采集增强

Rust 编写的无头浏览器，可作为高级数据采集工具: 内存占用仅 30MB（Chrome 200MB+）、内置反检测、支持 CDP 协议。可从 Python 通过 subprocess 或 Playwright CDP 连接调用。

---

## 三、建议开发的模块规划

基于以上分析，建议按以下模块逐步构建选股筛选与分析系统:

### Phase 1: 数据基础设施（优先）

**模块 M1 — 统一数据采集器**

复用 daily_stock_analysis 的 DataFetcherManager 策略模式，构建多源自动 fallback 的数据获取层:

- 核心数据源: AkShare（首选，已安装）+ BaoStock（已安装）+ efinance
- 补充数据源: Tushare Pro（需注册 token）、Pytdx（通达信服务器）
- 东方财富本地 .dat 文件解析器（已有约 1.5GB 本地数据）
- 百度网盘历史数据解压导入

**模块 M2 — 本地数据存储与管理**

- SQLite/PostgreSQL 存储历史行情数据
- 增量更新机制（每日收盘后自动拉取新数据）
- 数据清洗与标准化（复权处理、停牌填充）

**模块 M3 — 东方财富数据解析**

- 解析 `C:\eastmoney\dfcf\data\ClosedDownload` 下的 V43 格式 .dat 文件
- 将日线、5 分钟线、月线、年线数据导入统一数据库
- 这是已有的约 1.5GB 高质量本地数据，无需重新下载

### Phase 2: 选股筛选引擎

**模块 M4 — 技术指标计算引擎**

在现有 `core/analysis/indicators.py` 基础上扩展:

- 完善技术指标: MA 系列（含 BOLL）、MACD、RSI、KDJ、ATR、OBV、CCI、威廉指标
- 形态识别: 头肩顶/底、双底、三角形、旗形等经典形态
- 缠论指标: 笔/线段/中枢/背驰

**模块 M5 — 多条件选股筛选器**

- 条件组合引擎: 支持 AND/OR/NOT 逻辑组合
- 内置筛选条件: 均线排列、MACD 金叉/死叉、量价配合、突破形态、板块轮动
- 全市场扫描: 一次遍历全部 A 股，输出符合条件的股票列表
- 筛选结果排名: 按评分排序（技术面 + 资金面 + 基本面综合打分）

**模块 M6 — 基本面筛选**

- 财务指标筛选: PE/PB/ROE/营收增长率/净利润增长率/现金流
- 行业/概念板块筛选
- 机构持仓变动、北向资金流向
- 龙虎榜数据

### Phase 3: AI 增强分析

**模块 M7 — AI 分析引擎**

参考 daily_stock_analysis + TradingAgents 的架构:

- 通过 LiteLLM 接入多个 LLM（DeepSeek/Qwen 成本较低，适合 A 股分析）
- 将技术指标 + 新闻 + 基本面打包成结构化 prompt
- LLM 输出结构化分析报告（评分、趋势、买卖点、风险提示）

**模块 M8 — 新闻/情报采集**

- 多引擎新闻搜索（参考 daily_stock_analysis 的 7 引擎方案）
- 财经日历: 业绩预告、解禁日期、股东大会
- 政策/行业热点追踪
- 可选: obscura 无头浏览器爬取东方财富/同花顺等动态页面

### Phase 4: 策略回测与验证

**模块 M9 — 回测引擎**

在现有 `core/backtest/engine.py` 基础上增强:

- 支持多股票组合回测
- 手续费/滑点/涨跌停模拟
- 绩效指标: 年化收益、夏普比率、最大回撤、胜率
- 与 AI 分析结果交叉验证

**模块 M10 — 策略管理**

参考 daily_stock_analysis 的 YAML 策略定义方式:

- 策略注册表 + 热加载
- 策略版本管理
- 策略参数优化

### Phase 5: 通知与推送

**模块 M11 — 多渠道通知**

参考 daily_stock_analysis 的 14 渠道方案，优先实现:

- 微信推送（企业微信 Webhook 或 ServerChan3）
- 钉钉机器人
- 邮件通知
- Telegram（如有需要）

**模块 M12 — 定时任务调度**

- 每日收盘后自动运行全市场扫描
- AI 分析 + 筛选结果定时推送
- GitHub Actions / 本地 schedule / Docker cron 三种模式

### Phase 6: 基金工具（天天基金集成）

**模块 M13 — 天天基金 Skill 集成**

已通过 ttskill CLI 安装了 26 个技能包，可直接调用:

- 基金搜索/选基（条件选基、关键字搜索）
- 基金详情/净值/重仓股/基金经理信息
- 宏观经济数据、指数行情、黄金/债市行情
- 账户持仓/收益查询、交易记录
- 组合回测、模拟交易

---

## 四、数据获取方案对比

| 数据源 | 覆盖范围 | 频率 | 成本 | 是否需要 Token | 推荐用途 |
|--------|----------|------|------|----------------|----------|
| **AkShare** | A 股全量 + 基本面 + 资金流 | 实时/日级 | 免费 | 否 | 日常首选数据源 |
| **BaoStock** | A 股历史 K 线 | 分钟/日/周/月 | 免费 | 否 | 历史数据回测 |
| **efinance** | 东方财富行情 | 实时 | 免费 | 否 | 实时行情补充 |
| **Tushare Pro** | A 股 + 基金 + 宏观 | 日级 | 积分制(基础免费) | 是 | 全面数据补充 |
| **Pytdx** | 通达信服务器 | 实时 | 免费 | 否 | 分钟线数据 |
| **东方财富本地 .dat** | 沪深全市场 | 日级/5 分钟 | 已有 | 否 | 离线历史数据 |
| **天天基金 ttskill** | 基金全量 | 实时 | 免费(已登录) | 已配 | 基金数据 |
| **mx-moni (东方财富 API)** | 行情+资讯 | 实时 | 免费(已配 key) | 已配 | 模拟投资组合 |
| **Yahoo Finance** | 全球市场 | 日级 | 免费 | 否 | 港股/美股 |
| **Finnhub** | 全球市场 | 实时 | 免费额度 | 是 | 美股补充 |
| **obscura 爬虫** | 任意网页 | 按需 | 免费 | 否 | 动态页面采集 |

---

## 五、建议的开发优先级

```
高优先级 (第 1-2 周):
  M1 统一数据采集器  →  M2 本地数据存储  →  M3 东方财富数据解析
  
中优先级 (第 3-4 周):
  M4 技术指标引擎  →  M5 多条件选股筛选器  →  M6 基本面筛选
  
中后期 (第 5-6 周):
  M7 AI 分析引擎  →  M8 新闻情报采集  →  M11 通知推送
  
后期 (第 7-8 周):
  M9 回测引擎  →  M10 策略管理  →  M12 定时调度  →  M13 天天基金集成
```

---

## 六、待讨论的关键问题

见报告末尾「讨论问题」部分。
