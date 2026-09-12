"""回测引擎 / 指标 回归测试 — 锁定向量化实现与指标计算契约。

被测契约
--------
- ``BacktestEngine.run(df, signal, code)`` -> ``BacktestResult``
    * ``df`` 需要列: ``t`` / ``open`` / ``close``（引擎也接受 high/low/volume）
    * ``signal``: 与 df 同 index 的 bool Series（True=持仓，False=空仓）
    * 关键不变量: ``position[t] == signal[t-1]``（次日开盘成交，无未来函数）
- ``compute_metrics(equity_curve, trades, initial_cash, risk_free)`` -> dict
    * ``equity_curve`` 需要 ``equity`` + ``ret`` 两列
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.backtest.engine import BacktestEngine, BacktestResult
from core.backtest.metrics import compute_metrics, _empty_metrics


def _make_df(n: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.01, size=n))
    open_ = close * (1.0 + rng.normal(0, 0.002, size=n))
    t = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "t": t,
            "open": open_,
            "high": np.maximum(open_, close) * 1.001,
            "low": np.minimum(open_, close) * 0.999,
            "close": close,
            "volume": rng.integers(1_000, 10_000, size=n).astype(float),
        }
    )


def _signal_all(n: int, value: bool) -> pd.Series:
    return pd.Series([value] * n)


def test_always_flat_no_position():
    df = _make_df(60)
    eng = BacktestEngine(initial_cash=100_000)
    res = eng.run(df, _signal_all(len(df), False), code="TEST")
    assert isinstance(res, BacktestResult)
    assert res.final_equity == pytest.approx(100_000.0)
    assert res.trades == []
    assert len(res.equity_curve) == len(df)
    for col in ("t", "close", "position", "equity", "ret"):
        assert col in res.equity_curve.columns
    m = compute_metrics(res.equity_curve, res.trades, initial_cash=100_000)
    assert m["total_return_pct"] == pytest.approx(0.0)
    assert m["trade_count"] == 0
    assert m["sharpe"] == 0.0
    assert m["max_drawdown_pct"] == 0.0
    assert m["win_rate_pct"] == 0.0


def test_always_long_rising_market_profits():
    n = 60
    # 严格单调上涨 -> 无回撤、单笔强制平仓交易、必胜
    close = np.linspace(100.0, 200.0, n)
    df = pd.DataFrame(
        {
            "t": pd.date_range("2024-01-02", periods=n, freq="B"),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1000.0,
        }
    )
    eng = BacktestEngine(initial_cash=100_000, commission=0.0, slippage=0.0)
    res = eng.run(df, _signal_all(n, True), code="UP")
    assert res.final_equity > 100_000.0
    m = compute_metrics(res.equity_curve, res.trades, initial_cash=100_000)
    assert m["total_return_pct"] > 0
    assert m["max_drawdown_pct"] == pytest.approx(0.0)  # 单调上涨无回撤
    assert m["trade_count"] == 1  # 1 买 + 末日强制平
    assert m["win_rate_pct"] == 100.0


def test_first_bar_always_flat_no_lookahead():
    df = _make_df(60)
    eng = BacktestEngine()
    res = eng.run(df, _signal_all(len(df), True), code="X")
    # 即便信号在第 0 根就喊买，第 0 根仓位也必须是空仓
    assert int(res.equity_curve["position"].iloc[0]) == 0
    # 不变量: position[t] == signal[t-1]
    sig = _signal_all(len(df), True)
    expected = pd.Series(sig).shift(1).fillna(False).astype(int).values
    assert (res.equity_curve["position"].values == expected).all()


def test_no_future_leak_on_last_signal():
    df = _make_df(60)
    eng = BacktestEngine(commission=0.0, slippage=0.0)
    base = eng.run(df, _signal_all(len(df), True), code="B")
    # 只把最后一根信号改成 False —— 最后一根仓位由 signal[-2] 决定，
    # 所以终值必须不变（验证没有用到当根未来信号）
    sig = _signal_all(len(df), True)
    sig.iloc[-1] = False
    alt = eng.run(df, sig, code="B2")
    assert alt.final_equity == pytest.approx(base.final_equity)


def test_empty_inputs_safe():
    eng = BacktestEngine()
    res = eng.run(pd.DataFrame(), pd.Series([], dtype=bool), code="E")
    # 空输入：引擎直接返回空 equity_curve（final_equity 保持 dataclass 默认 0.0）
    assert res.equity_curve.empty
    assert res.trades == []
    m = compute_metrics(res.equity_curve, res.trades, initial_cash=100_000)
    assert m == _empty_metrics(100_000.0)
    assert m["final_equity"] == 100_000.0


def test_metrics_keys_and_types():
    df = _make_df(120)
    eng = BacktestEngine()
    # 周期性持仓/空仓，制造多笔交易
    sig = pd.Series(range(len(df))) // 10 % 2 == 0
    res = eng.run(df, sig, code="K")
    m = compute_metrics(res.equity_curve, res.trades, initial_cash=100_000)
    required = {
        "total_return_pct",
        "annual_return_pct",
        "volatility_pct",
        "sharpe",
        "sortino",
        "max_drawdown_pct",
        "max_drawdown_duration_days",
        "calmar",
        "win_rate_pct",
        "profit_factor",
        "expectancy_pct",
        "trade_count",
        "avg_hold_days",
        "best_trade_pct",
        "worst_trade_pct",
        "n_bars",
        "years",
        "initial_cash",
        "final_equity",
    }
    assert required.issubset(set(m.keys()))
    assert isinstance(m["sharpe"], (int, float))
    assert isinstance(m["max_drawdown_pct"], (int, float))
    assert m["trade_count"] >= 0
    assert np.isfinite(m["sharpe"])


def test_deterministic():
    df = _make_df(60)
    eng = BacktestEngine()
    r1 = eng.run(df, _signal_all(len(df), True), code="D")
    r2 = eng.run(df, _signal_all(len(df), True), code="D")
    assert r1.final_equity == pytest.approx(r2.final_equity)
    assert len(r1.trades) == len(r2.trades)
