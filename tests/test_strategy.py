"""策略模块测试"""

import numpy as np
import pandas as pd

from core.strategy.base import DualMAStrategy, StrategyRegistry


def _make_kline_df(n: int = 100) -> pd.DataFrame:
    """生成模拟K线 DataFrame"""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "股票代码": ["000001"] * n,
        "日期": pd.date_range("2024-01-01", periods=n),
        "开盘": close - np.random.rand(n) * 0.3,
        "收盘": close,
        "最高": close + np.random.rand(n) * 0.5,
        "最低": close - np.random.rand(n) * 0.5,
        "成交量": np.random.randint(10000, 100000, n),
    })


def test_dual_ma_strategy():
    strategy = DualMAStrategy(short_window=5, long_window=20)
    df = _make_kline_df()
    signal = strategy.on_bar(df)
    assert signal is not None
    assert signal.action in ("buy", "sell", "hold")
    assert signal.price > 0


def test_dual_ma_insufficient_data():
    strategy = DualMAStrategy(short_window=5, long_window=20)
    df = _make_kline_df(n=10)
    signal = strategy.on_bar(df)
    assert signal is None


def test_strategy_registry():
    registry = StrategyRegistry()
    registry.register(DualMAStrategy)
    strategies = registry.list_strategies()
    assert len(strategies) == 1
    assert strategies[0]["name"] == "dual_ma"

    cls = registry.get("dual_ma")
    assert cls is DualMAStrategy
    assert registry.get("nonexistent") is None
