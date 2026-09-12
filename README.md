# Quant Trader

股票量化交易工具 — 行情数据获取、技术指标分析、策略回测一体化。

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
├── app/              # FastAPI 应用
│   ├── main.py       # 入口
│   ├── config.py     # 配置
│   └── routers/      # 路由
├── core/             # 核心业务模块
│   ├── data/         # 数据获取
│   ├── strategy/     # 交易策略
│   ├── backtest/     # 回测引擎
│   └── analysis/     # 技术指标
└── tests/            # 测试
```

## 运行测试

```bash
pytest -v
```
