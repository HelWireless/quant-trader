# Quant Trader

股票量化交易工具 — 行情数据获取、技术指标分析、策略回测一体化。

## 技术栈

- **Web 框架**: FastAPI + Uvicorn
- **数据源**: AkShare (A股行情)
- **数据处理**: Pandas / NumPy
- **技术指标**: 自研 (SMA, EMA, MACD, RSI, KDJ, BOLL)
- **回测引擎**: 内置简易引擎，支持扩展

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
