"""技术指标模块测试"""

import numpy as np
import pandas as pd

from core.analysis.indicators import sma, ema, macd, rsi, bollinger_bands, kdj


def _make_close(n: int = 50) -> pd.Series:
    """生成模拟收盘价序列"""
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.Series(prices, name="close")


def test_sma():
    close = _make_close()
    result = sma(close, 5)
    assert len(result) == len(close)
    assert pd.isna(result.iloc[0])
    assert not pd.isna(result.iloc[4])


def test_ema():
    close = _make_close()
    result = ema(close, 12)
    assert len(result) == len(close)
    assert not pd.isna(result.iloc[-1])


def test_macd():
    close = _make_close()
    dif, dea, hist = macd(close)
    assert len(dif) == len(close)
    assert len(dea) == len(close)
    assert len(hist) == len(close)


def test_rsi():
    close = _make_close()
    result = rsi(close, 14)
    # RSI 应在 0-100 之间 (排除 NaN)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_bollinger_bands():
    close = _make_close()
    upper, middle, lower = bollinger_bands(close)
    valid_idx = ~upper.isna()
    assert (upper[valid_idx] >= middle[valid_idx]).all()
    assert (middle[valid_idx] >= lower[valid_idx]).all()


def test_kdj():
    close = _make_close()
    high = close + np.abs(np.random.randn(len(close)))
    low = close - np.abs(np.random.randn(len(close)))
    k, d, j = kdj(high, low, close)
    assert len(k) == len(close)
    assert len(d) == len(close)
    assert len(j) == len(close)
