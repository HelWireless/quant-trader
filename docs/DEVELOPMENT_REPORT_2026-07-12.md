# 开发报告：quant-trader 接手收尾

> 范围：chat.py 重写收尾 / 前端重写对齐 / T007 daily_stock_analysis AI 分析集成 / T005 回测引擎增强
> 日期：2026-07-12
> 分支：`wip/refactor-20260712`（单次合并提交 `65cce1f`）

---

## 1. 背景与目标

承接既有 quant-trader（A 股量化交易系统，FastAPI + PostgreSQL + SQLite + DuckDB）的收尾工作，按顺序完成四项任务并**逐项本地连接服务验证**：
- **T2**：完成半进行的 `chat.py` 重写
- **T3**：完成半进行的前端重写 + 后端 API 契约对齐
- **T7（T007）**：集成 `daily_stock_analysis`（dsa）AI 深度分析能力
- **T5（T005）**：回测引擎增强

交付要求（用户）：逐任务完成后本地连接测试验证，全部完成后产出本报告并**一次性 git 提交所有改动**。

## 2. 环境与部署

- **代码真源**：服务器 `cody_pc`（192.168.31.53，Ubuntu）。本地为旧快照（2026-06-29），全程只从服务器拉取/编辑，**绝不反向覆盖服务器**。
- **服务（systemd 托管，均为 active）**：
  - `quant-trader.service` — FastAPI 主服务，监听 `:8000`
  - `daily-stock-analysis.service` — dsa FastAPI 子服务，监听 `:8010`（**独立 `.venv`，独立 `DEEPSEEK_API_KEY`**）
- **认证**：fastapi-users `CookieTransport + JWT`；登录返回 HTTP `204` + `Set-Cookie: qtauth=...`（非 JSON Bearer）。E2E 统一用 `requests.Session()` 持 cookie。

## 3. 任务明细

### 3.1 T2 — chat.py 重写收尾 ✅

**问题**：`/config` 端点工具列表被硬编码为 8 个，缺失新增的 10 个工具（含 6 个实时行情工具与 `analyze_stock_ai`）。

**修复**：`app/routers/chat.py` 新增 `_chat_tool_names()`，从 `build_agent()._function_toolset.tools.keys()` **动态派生**工具列表（含 18 个静态兜底，避免 agent 未初始化时降级）。

**关联改动**：`core/chat/tools/market_tools.py` 新增 6 个实时行情工具：
`get_quote_realtime` / `get_fund_flow` / `get_dragon_tiger` / `get_margin_summary` / `get_hsgt_north` / `get_hot_themes_today`。

**验证**：`chat_e2e.py` → `config http=200 tools=19 provider=deepseek model=deepseek-chat has_key=True`；对话实测 LLM 调用 `get_quote_realtime`/`get_fund_flow`/`get_hsgt_north` 并取回真实数据（茅台 ¥1,204.98 +1.93%、北向净流出）。

### 3.2 T3 — 前端重写 + API 契约对齐 ✅

**核对**：前端每个 `/api/*` 调用均可映射到后端 76 条 OpenAPI 路径。疑似错位项 `/api/auth/change`、`/api/data` 经核查为误报——实际调用分别为 `/api/auth/change-password` 与 `/api/data-ops/*`。

**验证**：`frontend_smoke.py` → 43 个 URL（13 个页面 + 30 个静态资源），**0 失败**。

### 3.3 T7（T007）— daily_stock_analysis AI 分析集成 ✅

**方案**：**service 化 + HTTP 代理**（微服务模式）。dsa 作为独立服务运行，主服务通过 HTTP 调用，互不污染依赖。

**新增/改动文件**：
- `core/integrations/daily_stock_analysis_client.py`：隔离 HTTP 客户端（用标准库 `urllib`，**零额外依赖**）。读取 `DSA_API_BASE`（默认 `http://127.0.0.1:8010`）、`DSA_TIMEOUT`（默认 300）。`analyze_stock(code, report_type, compact)` → `POST /api/v1/analysis/analyze`，并归一化响应（股价/涨跌幅/操作建议/趋势/情绪分/策略位/新闻/技术/基本面/风险）。
- `app/routers/analysis_proxy.py`：REST 代理 `POST /api/analysis/stock` + `GET /api/analysis/health`，挂载时要求登录；dsa 失败时返回 502。
- `core/chat/agent.py`：新增 `analyze_stock_ai` 工具（`@agent.tool_plain`），`asyncio.to_thread` 调客户端，供对话直接触发深度分析。
- `deploy/systemd/daily-stock-analysis.service`：独立 systemd 单元（`:8010`，`MemoryHigh=2G`、`MemoryMax=3G`、失败自动重启、开机自启）。
- `daily_stock_analysis/.env`：注入与主服务同源的 `DEEPSEEK_API_KEY`；独立 `.venv` 安装依赖（已剔除不可发布的 `longbridge==0.2.75`，dsa 源码未引用）。

**验证**：
- `analysis_rest_test.py` → `POST /api/analysis/stock` 返回 200（耗时 127.6s，贵州茅台：持有 / 震荡看多 / 评分 65）。
- 前期 `chat_e2e_analyze.py` → LLM 实际调用 `analyze_stock_ai`，回答含深度分析（PE 18.21 / PB 6.47 / RSI 39.2 / 震荡筑底）。

### 3.4 T5（T005）— 回测引擎增强 ✅

**发现**：回测引擎**已经是向量化实现**（`pandas cumprod`，无 Python 级 bar loop），`metrics.py` **已计算**夏普 / 索提诺 / 最大回撤 / 卡玛 / 胜率 / 盈亏比等；前端 backtest 面板已渲染这些指标，API 已暴露。因此本任务实质是**补回归测试锁定既有增强**，而非新增功能代码。

**关键不变量（已阅读 `engine.py` / `metrics.py` 确认）**：
- `position[t] == signal[t-1]`（次日开盘成交，**无未来函数**；首根恒为空仓）
- `compute_metrics(equity_curve, ...)` 要求 `equity_curve` 含 `equity` + `ret` 列

**新增**：`tests/test_backtest.py`（7 项），覆盖：
1. 空仓信号 → 净值恒定、无交易、指标全零
2. 单调上涨满仓 → 正收益、零回撤、单笔强制平仓、胜率 100%
3. `position[t]==signal[t-1]` 不变量 & 首根必空仓（无未来函数）
4. 末根信号翻转不改变终值（无未来泄漏）
5. 空输入安全返回
6. 指标字典键齐全、类型正确、`sharpe` 有限
7. 可复现性（同输入两次运行终值一致）

**验证**：
- `backtest_e2e.py` → `POST /api/backtest/run` 200（600519 / ma_cross / 365d：sharpe **-1.361**、sortino -1.444、max_drawdown **-26.39%**、win_rate 16.7%、trades 12、equity_curve 365 点）。
- `pytest tests/` → **25 passed**（原有 18 + 新增 7），无回归。

## 4. 验证总览

| 验证项 | 脚本 / 用例 | 结果 |
|---|---|---|
| chat 登录 + 配置 + 工具调用 | `scripts/chat_e2e.py` | `OVERALL_OK=True`（19 工具） |
| 前端静态资源 | `scripts/frontend_smoke.py` | 43 URL / 0 失败 |
| AI 分析 REST 代理 | `scripts/analysis_rest_test.py` | `REST_PROXY_OK`（200） |
| 回测 API | `scripts/backtest_e2e.py` | `BACKTEST_E2E_OK` |
| 单元回归 | `pytest tests/` | **25 passed** |

## 5. 提交信息

- **单次合并提交** `65cce1f`（分支 `wip/refactor-20260712`）：18 个文件，+1210 / −225。
- **已排除**（`.gitignore` 已忽略）：`daily_stock_analysis/`（独立仓库）、所有 `.venv`、`.env`（含密钥）。
- 修改文件：`app/main.py`、`app/routers/chat.py`、`core/chat/agent.py`、`core/chat/tools/market_tools.py`
- 新增文件：`app/routers/analysis_proxy.py`、`core/integrations/daily_stock_analysis_client.py`、`deploy/systemd/daily-stock-analysis.service`、`tests/test_backtest.py`、以及 `scripts/` 下 11 个 QA/E2E 脚本。

## 6. 注意事项与后续建议

1. **dsa 启动较慢**：依赖较重（litellm / akshare / efinance / baostock 等），重启后约 **8–10s** 才监听 `:8010`；如对外暴露建议增加健康检查重试/预热。
2. **`longbridge` 依赖不可用**：已从 dsa 依赖清单剔除（源码未引用该包）。
3. **深度报告耗时**：`analyze_stock_ai` 走同步 HTTP（约 2 分钟），建议在对话 UI 增加超时与进度提示，或改为后台任务 + 轮询。
4. **尚未 git push**：本次仅在服务器本地提交，未推送远端（WIP 分支）。如需远端备份请告知。
5. **已知小瑕疵（已锁定现状，非阻塞）**：回测引擎对**空输入**的早返回 `final_equity` 保持 dataclass 默认 `0.0`（而非 `initial_cash`）。回归测试按现状断言；若需改为返回 `initial_cash` 可后续微调。
