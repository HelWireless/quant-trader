# 前端优化报告：基于 impeccable 设计语言

> 范围：使用 [pbakaus/impeccable](https://github.com/pbakaus/impeccable) 的设计语言（AI 设计守门员）规则，对 quant-trader 前端做一轮「去 AI slop / 提工艺 / 补 a11y」优化
> 日期：2026-07-12
> 寄存器（register）：`product`（应用 / 仪表盘 / 工具类界面，设计服务于产品）

## 1. impeccable 是什么

impeccable 是一套「让 AI 编程助手更擅长设计」的设计语言 + 反模式检测系统。它规定了一套绝对禁令（absolute bans）与按寄存器（brand / product / …）细分的规则，用来阻止生成「千篇一律的 AI 丑界面」。本次优化以 **product 寄存器** 为准则（仪表盘属于该寄存器），逐条对照其规则落地。

## 2. 优化前诊断

前端是基于 Pico.css 的 GitHub 暗色主题仪表盘，整体基调正确（Restrained 配色、系统字体、无渐变文字、无过度圆角）。但仍存在可被 impeccable 判为 slop 的硬伤：

| 问题 | 位置 | 违反的规则 |
|---|---|---|
| **左侧色条** `border-left: 3px solid <色>` 作为强调 | chat.css（`.tool-card`/`.err-box`/`.no-key-banner`）、backtest.css（`.metric-card`）、stocks.css（`.signal-item`）、profile/change-password/knowledge/login.html 内联样式 | **绝对禁令：Side-stripe borders**（>1px 的左右色条） |
| **幽灵卡片** `1px border + box-shadow: 0 8px 32px` 同元素 | style.css `.modal` | **绝对禁令：ghost-card**（1px 边框 + ≥16px 宽阴影） |
| 无 `:focus-visible` 焦点环 | 全局 | product 规则：组件需具备全部状态（含 focus） |
| 无 `prefers-reduced-motion` | 全局 | 通用规则：每个动画都需要降级替代 |
| 任意 `z-index: 1000 / 50` | style.css / stocks.css | 通用规则：建立语义化 z-index 层级，禁用 999/9999 之类魔法值 |
| 散落的硬编码十六进制色 | 各 css / 内联 | 一致性：应集中为语义 token |

## 3. 采取的优化（已落地）

### 3.1 清除绝对禁令
- 删除全部 `border-left/right: 3px` 色条，改写为 **全 1px 边框 + 同色系低透明度描边 + 色调背景**（如 `.metric-card.good` → 绿色描边 + 绿色淡底），符合「full borders / background tints / leading indicators」的替代方案。
- `.modal` 阴影模糊从 32px 收到 14px（保留 1px 边框），消除 ghost-card 组合。

### 3.2 设计系统 Token 化（style.css）
新增 `:root` 设计令牌块，统一全站语义色与尺度：
- 语义色：`--c-accent / --c-up(涨·红) / --c-down(跌·绿) / --c-warn / --c-success / --c-danger / --c-info / --c-purple`（**A 股约定：涨红跌绿已保留**）。
- 间距尺度 `--space-1..6`、圆角 `--radius-sm/md/lg/pill`、阴影 `--shadow-sm/md`、语义 `z-index` 层级 `--z-sticky/dropdown/modal-backdrop/modal/toast/tooltip`。
- 全站散落 hex（#ef5350/#26a69a/#ffb84d/#75d589/#58a6ff 等）统一改写为对应 token，消除「同义多色」不一致。

### 3.3 无障碍与动效（a11y）
- 新增全局 `:focus-visible` 焦点环（覆盖 a/button/input/select/textarea/可聚焦列表项/卡片），统一键盘可达性外观。
- 新增 `@media (prefers-reduced-motion: reduce)`：将所有 `animation`/`transition`/`scroll-behavior` 降级为近乎瞬时，满足「每个动画都有替代」。
- `h1–h3` 加 `text-wrap: balance`，标题换行更均衡。

### 3.4 细节打磨
- `.kpi-card` 增加 hover 微抬升（`translateY(-2px)` + 边框高亮），动效受 reduced-motion 约束。
- 下拉浮层（搜索结果）`z-index` 接入语义层级 `--z-dropdown`。

## 4. 验证

- **反模式审计**：全站 `grep border-left/right` → 0 命中；`background-clip:text` / `backdrop-filter` / `repeating-linear-gradient` / 超大圆角（≥24px）→ 0 命中。
- **前端冒烟**（`scripts/frontend_smoke.py`）：43 个 URL（13 页面 + 30 静态资源），**0 失败**，全部 200。
- **CSS 语法**：5 个改动 CSS 文件大括号配对（open==close）均平衡。
- 服务已热加载最新 `web/`（`restart` 非必须，静态文件直接生效；本次未重启主服务）。

## 5. 变更文件清单

| 文件 | 改动 |
|---|---|
| `web/assets/style.css` | 设计令牌块、`:focus-visible`、reduced-motion、`text-wrap:balance`、语义 z-index、阴影收口、KPI hover |
| `web/assets/chat.css` | `.tool-card`/`.err-box`/`.no-key-banner` 去色条；颜色 token 化 |
| `web/assets/backtest.css` | `.metric-card` 去色条；`.ret-* / .hist-row .ret` 颜色 token 化 |
| `web/assets/stocks.css` | `.signal-item` 去色条；`.stock-price / .quote-row / .search-results z-index` token 化 |
| `web/assets/screening.css` | `.status-badge / .strat-tag / .hit-cnt / .score-cell / .pct-cell` 颜色 token 化 |
| `web/index.html` | activity tag、进度条颜色 token 化 |
| `web/profile.html` | `.msg` 去色条 |
| `web/change-password.html` | `.force-banner`/`.msg` 去色条 |
| `web/knowledge.html` | `.hit-card`/`.status-line` 去色条、颜色 token 化 |
| `web/login.html` | `.login-error` 去色条 |

## 6. 说明与后续建议

1. **未改视觉方向**：遵循 impeccable「身份保留优先」原则，保留既有 GitHub 暗色品牌色，仅清理 slop 与补工艺，未做主题切换。
2. **检测器未实际运行**：impeccable 的 `detect.mjs` 依赖 `detector/` + `cli/engine` 整棵模块树（含可能的前端依赖），接入成本较高；本次以逐条对照规则手册的人工审计替代，结论可靠。若希望用 CLI 做客观复检，可在项目内安装该 skill 后运行 `$impeccable audit web/`。
3. **未提交/未推送**：按「单任务单提交」原则，本批前端改动作为**一次独立 git 提交**（不并入之前的 WIP 收尾提交）。需要推远端请告知。
4. **可进一步做**：空状态文案教学化（impeccable 要求 empty state 教会用户而非「暂无数据」）、骨架屏加载态、light 主题对照。属于增强项，非必需。
