# Quant Trader

股票量化交易工具 — 行情数据获取、技术指标分析、策略回测一体化。

## 核心策略：hoshi-cplus

**hoshi-cplus** 是本仓库的现役 A 股**超跌反弹**策略。
研究阶段曾记作「**方案 B′ / B' / Bp**」，自 2026-09-13 起统一命名为 **hoshi-cplus**（两者完全等价）。

- 代码：`hoshi_cplus/`（纯标准库，零第三方依赖，含回测引擎与命令行）
- 策略说明：`hoshi_cplus/README.md`
- 命名规范：`docs/Hoshi_策略命名_hoshi-cplus.md`
- 研究报告：`docs/Hoshi_终局报告_2026-09-13.md`
- 二次验证：`docs/Hoshi_二次验证_180窗_2026-09-13.md`

```python
from hoshi_cplus import Strategy

s = Strategy('scripts/hoshi_csv_2005', preset='cplus')
r = s.run('2011-03-01', '2016-02-29')
print(r['ret'])        # 收益率 %
```

```bash
python -m hoshi_cplus --data scripts/hoshi_csv_2005 --preset cplus \
    --start 2011-03-01 --end 2016-02-29
```

**180 窗验证**（数据 2005 起，5310 只，179 个随机窗口）：

| 方案 | 几何收益 | 最差窗 | 负收益窗 |
|---|---:|---:|---:|
| 原版 | +15.82% | −33.53% | 68/179 |
| 方案 B | +89.19% | −8.11% | 13/179 |
| **hoshi-cplus** | **+109.07%** | **−6.78%** | **4/179** |

hoshi-cplus 相对方案 B **+24.39pp**（胜 160/179，t=11.83，p=5.8e-29）。

> ⚠️ 历史文档中出现的「方案 B′ / B' / Bp / C 配置」均指 **hoshi-cplus**，
> 对照表见 `docs/Hoshi_策略命名_hoshi-cplus.md`。

## 技术栈

- **Web 框架**: FastAPI + Uvicorn
- **数据源**: AkShare (A股行情)
- **数据处理**: Pandas / NumPy
- **技术指标**: 自研 (SMA, EMA, MACD, RSI, KDJ, BOLL)
- **回测引擎**: 内置简易引擎，支持扩展

## 获取代码

本仓库为 **Public**，**任何人无需 GitHub 账号即可克隆**：

```bash
git clone https://github.com/HelWireless/quant-trader.git
```

> 若本机已配置 GitHub SSH key，也可用 `git clone git@github.com:HelWireless/quant-trader.git`。
> 但注意：**SSH 方式必须有 GitHub 账号**（key 需绑定到账号），没账号的人请用上面的 HTTPS 地址。

> ⚠️ **仓库只含源码，不含数据。**
> `data/`（行情数据）、`scripts/hoshi_csv_long/`（回测 K 线长表）及所有 `*.csv`
> 均已被 `.gitignore` 排除。克隆后要跑回测，请用 `scripts/` 下的数据脚本自行构建
> （`refresh_tdx_duckdb.py`、`export_hoshi_csv.py` 等），并自备 `.env`。

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 启动 API 服务
uvicorn app.main:app --reload

# 4. 访问文档
# http://localhost:8000/docs
```

## 项目结构

```
quant-trader/
├── hoshi_cplus/      # ★ 现役策略：超跌反弹（纯标准库，可独立使用）
│   ├── config.py     #   参数常量与三个方案预设
│   ├── signals.py    #   K线形态、评分、入场信号
│   ├── exits.py      #   出场规则
│   ├── gates.py      #   广度门控 + R3
│   ├── data.py       #   数据加载与预计算
│   ├── backtest.py   #   回测引擎
│   ├── cli.py        #   命令行入口
│   └── selftest.py   #   零依赖自测（22 项）
├── app/              # FastAPI 应用
│   ├── main.py       # 入口
│   ├── config.py     # 配置
│   └── routers/      # 路由
├── core/             # 核心业务模块
│   ├── data/         # 数据获取
│   ├── strategy/     # 交易策略
│   ├── backtest/     # 回测引擎
│   └── analysis/     # 技术指标
├── scripts/          # 研究脚本、数据管道与历史回测器
├── docs/             # 研究报告
└── tests/            # 测试
```

## 运行测试

```bash
pytest -v
```
