# Quant-Trader 项目审计报告

> 审计日期：2026-07-13
> 审计范围：服务器 `cody_pc`（192.168.31.53）+ 本地 Windows 副本
> 目的：全面盘点文档、数据、策略的完备性，标注所有缺失项

---

## 一、项目概况

| 维度 | 服务器 | 本地 |
|------|--------|------|
| 路径 | `/home/cody/projects/quant-trader/` | `C:\Users\cody\PycharmProjects\quant-trader\` |
| Git 分支 | `wip/refactor-20260712`（56 文件 +7237/-5714） | 无 .git（手动拷贝快照，停留 2026-06-29） |
| Git 远程 | 无 remote 配置 | N/A |
| Python | .venv (3.10+) | 无 venv |
| 数据库 | PostgreSQL `quant_minute`（65 GB） | 无本地数据库 |
| 服务状态 | 2 个 systemd 服务运行中 | 无 |

### 服务状态
- `quant-trader.service`：**active (running)**，端口 8000，内存 24.6M
- `daily-stock-analysis.service`：**active (running)**，端口 8010，内存 284M

### 技术栈
- 后端：FastAPI + Uvicorn + SQLAlchemy + APScheduler
- 数据库：PostgreSQL（分区表，分钟K线按月分区）
- AI：DeepSeek (LLM) + DashScope (Embedding) + Zvec (向量库)
- 前端：Pico.css + 原生 JS（13 个 HTML 页面）
- 数据源：AkShare / Baostock / efinance / 通达信

---

## 二、模块清单

| 模块 | 路径 | 状态 | 说明 |
|------|------|------|------|
| **app** | `app/` | ✅ 完整 | FastAPI 入口 + 11 个路由 |
| **core/data** | `core/data/` | ✅ 完整 | 19 个文件：存储/采集/健康检查/聚合 |
| **core/analysis** | `core/analysis/` | ✅ 完整 | 技术指标引擎（SMA/EMA/MACD/RSI/KDJ/BOLL/ATR/OBV/CCI/ADX 等） |
| **core/backtest** | `core/backtest/` | ✅ 完整 | 7 个文件：引擎/指标/模型/优化器/组合/仓库/运行器 |
| **core/screening** | `core/screening/` | ✅ 完整 | 6 个策略文件 + 基本面筛选 + 仓库/运行器 |
| **core/strategies** | `core/strategies/` | ✅ 完整 | DSL 引擎 + 用户策略 ORM + 雷达扫描 |
| **core/strategy** | `core/strategy/` | ⚠️ 遗留 | 基类 + DualMA 示例（使用"收盘"列名，与 DB schema 不一致） |
| **core/chat** | `core/chat/` | ✅ 完整 | Agent + 4 工具包（market/sql/backtest/watchlist） |
| **core/auth** | `core/auth/` | ✅ 完整 | fastapi-users 集成 + JWT + 白名单 |
| **core/vector** | `core/vector/` | ✅ 完整 | DashScope embedding + Zvec 向量库 + RAG |
| **core/screener** | `core/screener/` | ✅ 完整 | 多条件选股 + 基本面 + Hoshi 星选 |
| **core/watchlist** | `core/watchlist/` | ✅ 完整 | 自选股 CRUD |
| **core/scheduler** | `core/scheduler/` | ✅ 完整 | 交易日历 + 定时任务 |
| **core/integrations** | `core/integrations/` | ✅ 完整 | daily_stock_analysis 客户端 |
| **daily_stock_analysis** | `daily_stock_analysis/` | ✅ 完整 | 独立微服务：AI 深度个股分析（端口 8010） |
| **web** | `web/` | ✅ 完整 | 13 个 HTML 页面 + CSS/JS |
| **deploy** | `deploy/` | ✅ 完整 | systemd 服务文件 + 安装脚本 |
| **scripts** | `scripts/` | ✅ 完整 | 23 个工具脚本 |
| **tests** | `tests/` | ⚠️ 不足 | 5 个测试文件（25 passed），覆盖率低 |

---

## 三、数据盘点

### 3.1 已有数据

| 表 | 行数 | 股票数 | 时间范围 | 状态 |
|----|------|--------|----------|------|
| `daily_kline` | 15,516,644 | 5,964 | 1991-01-02 ~ 2026-07-13 | ⚠️ 近期残缺 |
| `kline_15min` | 10,705,335 | 5,198 | 2021-09-01 ~ 2026-07-31 | ✅ 正常 |
| `kline_30min` | 6,174,814 | 5,190 | 2021-09-01 ~ 2026-07-31 | ✅ 正常 |
| `kline_60min` | 3,087,442 | 5,199 | 2021-09-01 ~ 2026-07-31 | ✅ 正常 |
| `stock_info` | 12,045 | — | — | ✅ 正常 |
| `kline_5min` | 0 | 0 | — | ❌ 空表（已删除，任务已停） |
| `kline_1min` | 已删除 | — | — | ❌ 已删除（释放 3GB，任务已停） |

### 3.2 数据缺口（⚠️ 需修复）

| 缺口 | 严重度 | 详情 | 修复建议 |
|------|--------|------|----------|
| **daily_kline 近 5 天残缺** | 🔴 高 | 7/13 仅 94 只、7/10 仅 106 只、7/9 仅 180 只、7/8 起 ~5500 只正常 | 运行 `scripts/update_daily_akshare.py` 补全 7/9~7/13 |
| **kline_5min 完全为空** | 🟡 中 | 数据已删除，定时任务已停用，分区表 2015-2027 有 95 个空分区 | 如需 5 分钟级别，重新启用采集任务；否则删除空分区 |
| **kline_1min 已删除** | 🟡 中 | 原 ~3GB 数据已清空，任务已停用 | 如需 1 分钟级别，需重新全量导入；否则在文档中标记为废弃 |
| **5min 历史空分区** | 🟡 低 | 2015-01 ~ 2021-07 共 78 个空分区（从未导入数据） | `DROP PARTITION` 清理，或保留占位 |

### 3.3 缺失的数据表（❌ 完全没有）

| 数据类型 | 说明 | 影响 |
|----------|------|------|
| **基本面数据表** | PE/PB/ROE/市值等财务指标未入库，仅通过 akshare 实时拉取 | 基本面筛选依赖网络，无法回测基本面策略 |
| **财务报表数据** | 营收/净利润/资产负债等未存储 | 无法做财报驱动策略、估值回测 |
| **龙虎榜数据** | 未持久化，仅 akshare 实时拉取 | 无法回测龙虎榜策略 |
| **北向资金数据** | 未持久化 | 无法做北向资金流入策略 |
| **板块/行业分类** | `stock_info` 有 `industry` 字段但未充分填充 | 无法做板块轮动、行业对比 |
| **复权因子** | 无除权除息复权数据 | 日线回测可能受除权影响（当前用原始价格） |
| **分笔/Tick 数据** | 无 | 无法做高频策略 |
| **新闻/舆情数据** | 未持久化（daily_stock_analysis 服务实时抓取） | 无法做情绪因子回测 |
| **指数数据** | 上证/深证/创业板指数未单独存储 | 无法做市场 Beta 对比、择时 |
| **ETF/基金数据** | 未存储 | 无法做 ETF 轮动策略 |
| **可转债数据** | 未存储 | 无法做可转债策略 |
| **期货/期权数据** | 未存储 | 无法做衍生品策略 |

### 3.4 数据架构问题

| 问题 | 详情 |
|------|------|
| **无远程 Git 仓库** | 服务器 git 无 remote，所有代码仅本地存在，存在丢失风险 |
| **本地副本过时** | 本地停留 2026-06-29，缺少 T2/T3/T5/T7 全部新代码 |
| **无数据备份策略** | 65GB 数据库无定期备份/快照机制 |
| **交易日历依赖 DB** | `trading_calendar.py` 依赖 daily_kline 判断交易日，若数据残缺会导致连锁 skip |

---

## 四、策略盘点

### 4.1 已有策略

#### 回测信号生成器（`core/backtest/strategies.py` — SIGNAL_REGISTRY）

| 名称 | 标题 | 参数 | 逻辑 |
|------|------|------|------|
| `ma_cross` | 双均线 | fast=5, slow=20 | MA5 > MA20 持有 |
| `macd_cross` | MACD 金叉 | — | DIF > DEA 持有 |
| `breakout` | 平台突破 | lookback=60 | 突破60日新高入场，跌破MA20出场 |
| `hoshi` | Hoshi 星选 | mode=confirmation, hold_days=20 | 连跌企稳确认点入场，持有20天 |
| `chan_simple` | 缠论简版 | lookback=20 | 突破中枢上沿入场，跌破下沿出场 |

#### 选股策略（`core/screening/strategies/` — STRATEGY_REGISTRY）

| 名称 | 类 | 说明 |
|------|-----|------|
| `ma_cross` | MACrossStrategy | 双均线金叉/死叉 |
| `macd_cross` | MACDCrossStrategy | MACD 金叉/死叉 |
| `breakout` | BreakoutStrategy | 平台突破 |
| `chan_simple` | ChanSimpleStrategy | 缠论简版 |
| `hoshi` | HoshiStrategy | Hoshi 星选 |

#### 自定义 DSL 策略引擎（`core/strategies/dsl.py`）

支持的指标：sma, ema, rsi, macd_dif/dea/hist, bollinger_upper/mid/lower, atr, volume_ratio, obv, cci, williams_r, adx
支持的操作符：and/or/not, gt/lt/ge/le/eq, cross_above/cross_below, mul/add/sub/div, max/min/abs/shift

#### 其他策略模块

| 模块 | 说明 |
|------|------|
| `core/strategies/radar.py` | 自选股 DSL 盯盘扫描（entry/exit/holding/no_signal） |
| `core/screener/fundamentals.py` | 基本面筛选（value/growth 策略，依赖 akshare 实时数据） |
| `core/screener/hoshi.py` | Hoshi 形态检测（连跌企稳买点） |
| `core/strategy/base.py` | ⚠️ 遗留基类 + DualMAStrategy 示例（使用"收盘"列名，与当前 DB schema 不一致） |

### 4.2 缺失的策略（❌ 需补充）

#### 技术面策略

| 策略 | 优先级 | 说明 | 依赖数据 |
|------|--------|------|----------|
| **量价配合策略** | 🔴 高 | 放量突破/缩量回调/量价背离 | daily_kline（已有） |
| **KDJ 策略** | 🟡 中 | K/D 金叉死叉、J 值超买超卖 | daily_kline（已有） |
| **布林带策略** | 🟡 中 | 触上轨/下轨回归、带宽收缩突破 | daily_kline（已有） |
| **RSI 超买超卖** | 🟡 中 | RSI < 30 买入 / > 70 卖出 | daily_kline（已有） |
| **ATR 通道突破** | 🟡 中 | 基于 ATR 的动态止损/通道 | daily_kline（已有） |
| **多周期共振** | 🟡 中 | 日线+周线+月线趋势一致时入场 | daily_kline（已有，需聚合） |
| **缺口回补策略** | 🟢 低 | 跳空缺口回补统计 | daily_kline（已有） |
| **N 日突破（海龟）** | 🟢 低 | Donchian 通道突破 | daily_kline（已有） |

#### 基本面策略

| 策略 | 优先级 | 说明 | 依赖数据 |
|------|--------|------|----------|
| **价值策略（PE/PB）** | 🔴 高 | 低 PE/低 PB 选股 | ❌ 需建基本面数据表 |
| **成长策略（ROE/营收增长）** | 🔴 高 | 高 ROE + 营收增长 | ❌ 需建财务报表表 |
| **股息率策略** | 🟡 中 | 高股息率选股 | ❌ 需分红数据 |
| **PEG 策略** | 🟡 中 | PE/盈利增长比 | ❌ 需财务数据 |

#### 资金面策略

| 策略 | 优先级 | 说明 | 依赖数据 |
|------|--------|------|----------|
| **北向资金跟随** | 🟡 中 | 北向净流入个股跟随 | ❌ 需北向资金数据 |
| **主力资金流** | 🟡 中 | 主力净流入/流出跟随 | ❌ 需资金流向数据（实时有，未持久化） |
| **龙虎榜跟随** | 🟢 低 | 机构/游资席位跟踪 | ❌ 需龙虎榜数据 |

#### 组合/风控策略

| 策略 | 优先级 | 说明 | 依赖数据 |
|------|--------|------|----------|
| **板块轮动** | 🟡 中 | 行业 ETF 动量轮动 | ❌ 需板块/指数数据 |
| **配对交易** | 🟢 低 | 协整性统计套利 | daily_kline（已有） |
| **均值回归** | 🟡 中 | 价格偏离均值后回归 | daily_kline（已有） |
| **动量策略** | 🟡 中 | N 日涨幅排名选股 | daily_kline（已有） |
| **多因子模型** | 🟢 低 | 价值+成长+动量+质量因子复合 | ❌ 需多维度数据 |

#### 风控/仓位管理（❌ 完全缺失）

| 模块 | 优先级 | 说明 |
|------|--------|------|
| **止损/止盈** | 🔴 高 | 当前策略无止损止盈逻辑，只有入场/出场信号 |
| **仓位管理** | 🔴 高 | 当前只有全仓/空仓，无凯利公式/固定比例/波动率调整 |
| **资金管理** | 🟡 中 | 无最大回撤限制、单标的仓位上限 |
| **风险预算** | 🟢 低 | 按波动率分配风险权重 |

#### 回测增强（❌ 缺失）

| 功能 | 优先级 | 说明 |
|------|--------|------|
| **Walk-forward 优化** | 🟡 中 | 无滚动窗口参数优化 |
| **参数网格搜索** | 🟡 中 | `backtest/optimizer.py` 存在但功能未知 |
| **蒙特卡洛模拟** | 🟢 低 | 无随机重排交易顺序评估策略稳健性 |
| **滑点/手续费建模** | 🟡 中 | 回测引擎未考虑交易成本 |

---

## 五、文档盘点

### 5.1 已有文档

| 文档 | 服务器 | 本地 | 内容 |
|------|--------|------|------|
| `README.md` | ✅ | ✅ | 基础项目说明（⚠️ 过时，未反映当前架构） |
| `docs/quant-trader-plan.md` | ✅ | ✅ | 2026-06-27 原始规划（13 模块开发计划） |
| `docs/progress-report-2026-06-27.md` | ✅ | ✅ | 数据基础设施进度报告 |
| `docs/DEVELOPMENT_REPORT_2026-07-12.md` | ✅ | ✅ | T2/T3/T7/T5 开发冲刺报告 |
| `docs/FRONTEND_OPTIMIZATION_REPORT.md` | ✅ | ❌ 缺失 | 前端优化报告（未同步到本地） |
| `claude-progress.txt` | ✅ (46KB) | ❌ 缺失 | 开发进度日志（T005~T020 全记录） |
| `deploy/README.md` | ✅ | ❌ 缺失 | 部署说明 |
| 各模块 docstring | ✅ | ⚠️ 过时 | 代码内文档（本地停留 6/29） |

### 5.2 缺失的文档（❌ 需创建）

| 文档 | 优先级 | 内容 |
|------|--------|------|
| **API 参考文档** | 🔴 高 | 所有 HTTP 端点的完整说明（当前仅有 OpenAPI /docs，无离线文档） |
| **架构设计文档** | 🔴 高 | 系统架构图、模块依赖关系、数据流 |
| **数据字典** | 🔴 高 | 所有数据库表的字段说明、类型、约束、索引 |
| **策略规格说明书** | 🔴 高 | 每个策略的详细逻辑、参数、适用场景、回测表现 |
| **部署运维手册** | 🟡 中 | systemd 服务管理、PG 维护、日志查看、故障排查 |
| **用户使用手册** | 🟡 中 | 前端各页面的操作指南 |
| **DSL 语法手册** | 🟡 中 | 自定义策略 DSL 的完整语法说明（代码内有但无独立文档） |
| **开发规范** | 🟡 中 | 代码风格、提交规范、测试要求、分支策略 |
| **测试文档** | 🟡 中 | 测试覆盖报告、E2E 测试说明 |
| **配置参考** | 🟢 低 | .env 所有配置项说明 |
| **CHANGELOG** | 🟢 低 | 版本变更记录（当前散落在 claude-progress.txt） |
| **数据库 ER 图** | 🟢 低 | 表关系可视化 |

---

## 六、本地 vs 服务器同步状态

### 6.1 文件差异

| 类别 | 服务器有、本地无 | 说明 |
|------|------------------|------|
| 文档 | `docs/FRONTEND_OPTIMIZATION_REPORT.md` | 前端优化报告 |
| 文档 | `claude-progress.txt` | 46KB 开发日志 |
| 文档 | `deploy/README.md` | 部署说明 |
| 代码 | `core/chat/tools/` 整个包 | T2 新增的 18 工具 |
| 代码 | `core/strategies/` 整个包 | DSL + 雷达扫描 |
| 代码 | `core/screening/` 整个包 | 选股策略框架 |
| 代码 | `core/vector/` 整个包 | 向量库/RAG |
| 代码 | `core/integrations/` | 微服务客户端 |
| 代码 | `app/routers/chat.py` 重写 | 动态工具发现 |
| 代码 | `app/routers/strategies.py` | 用户策略 API |
| 代码 | `app/routers/analysis_proxy.py` | T007 代理 |
| 代码 | `app/routers/data_ops.py` | 数据运维 API |
| 代码 | `app/routers/admin.py` | 管理员路由 |
| 代码 | `core/backtest/optimizer.py` | 参数优化器 |
| 代码 | `core/backtest/portfolio.py` | 组合回测 |
| 代码 | `core/data/health.py` | 数据健康检查 |
| 代码 | `core/data/job_runs.py` | 任务运行记录 |
| 代码 | `web/` 全部前端文件 | 13 个页面重写 |
| 代码 | `deploy/systemd/` | systemd 服务文件 |
| 代码 | `scripts/` 多个新脚本 | E2E 测试 + 补丁脚本 |
| 代码 | `daily_stock_analysis/` | 独立微服务 |

### 6.2 同步建议

1. **本地 → 服务器：禁止**。本地是旧快照，不能反向覆盖服务器。
2. **服务器 → 本地：推荐**。使用 `scp -r` 或 `rsync` 全量同步。
3. **服务器 → 远程 Git：紧急**。无 remote = 无灾备，强烈建议立即推送到 GitHub/GitLab。
4. **本地无需 venv**。本地仅用于阅读/参考，开发在服务器进行。

---

## 七、待办事项汇总

### 🔴 紧急（数据完整性）

- [ ] 补全 daily_kline 7/9~7/13 残缺数据（运行 `scripts/update_daily_akshare.py`）
- [ ] 配置 Git 远程仓库并推送（当前无 remote，代码仅存于服务器磁盘）
- [ ] 将 `docs/FRONTEND_OPTIMIZATION_REPORT.md` + `claude-progress.txt` 同步到本地

### 🟡 重要（策略/功能补全）

- [ ] 添加止损/止盈逻辑到回测引擎
- [ ] 添加仓位管理（固定比例/凯利公式/波动率调整）
- [ ] 量价配合策略（放量突破/缩量回调）
- [ ] KDJ / RSI / 布林带策略
- [ ] 建立基本面数据表（PE/PB/ROE/市值），支持基本面策略回测
- [ ] 添加交易成本（手续费/滑点）到回测引擎
- [ ] 增加测试覆盖率（当前仅 5 个测试文件）

### 🟢 增强（文档/运维）

- [ ] 创建 API 参考文档
- [ ] 创建架构设计文档 + 数据字典
- [ ] 创建策略规格说明书
- [ ] 创建部署运维手册
- [ ] 创建 DSL 语法手册
- [ ] 数据库定期备份策略（pg_dump cron）
- [ ] 清理 kline_5min 空分区
- [ ] 更新 README.md（当前严重过时）
- [ ] 清理遗留 `core/strategy/base.py`（与 `core/screening/strategies/` 重复，且列名不一致）

---

## 八、附录：API 端点清单

| 路由前缀 | 文件 | 端点数 | 说明 |
|----------|------|--------|------|
| `/api/auth` | `auth.py` | 4 | 登录/登出/me/改密码 |
| `/api/market` | `market.py` | 6+ | 行情/K线/批量报价/搜索 |
| `/api/screening` | `screening.py` | 6 | 策略列表/扫描批次/触发扫描 |
| `/api/backtest` | `backtest.py` | 5+ | 回测/历史/组合回测 |
| `/api/strategies` | `strategies.py` | 6+ | 用户自定义策略 CRUD + DSL |
| `/api/watchlist` | `watchlist.py` | 6+ | 自选股 CRUD |
| `/api/chat` | `chat.py` | 4+ | 会话 CRUD + SSE 流式 |
| `/api/rag` | `rag.py` | 5+ | 知识库文档/检索 |
| `/api/data-ops` | `data_ops.py` | 4+ | 数据健康/缺口告警/补全进度 |
| `/api/admin` | `admin.py` | 3+ | 用户白名单管理 |
| `/api/analysis` | `analysis_proxy.py` | 2+ | AI 深度分析代理 |
| `/api/strategy` | `strategy.py` | 1 | ⚠️ 遗留策略列表（与 strategies.py 重复） |

---

*审计人：CodeBuddy | 审计时间：2026-07-13 19:12 CST*
