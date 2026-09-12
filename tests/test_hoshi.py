"""Hoshi 策略单元测试

覆盖本次修复的 3 个核心问题：
  1. 涨跌幅缺失时"静默当 0%"  →  改为 None 并放弃（旧行为会漏信号）
  2. 无可执行性过滤（ST / 停牌 / 僵尸股 / 陈旧数据）
  3. batch_load_daily 的 end_date 切片（回测不能用未来数据）

运行：
    <venv>/python -m pytest tests/test_hoshi.py -v
"""
import numpy as np
import pandas as pd
import pytest

from core.screener.hoshi import (
    HoshiScreener,
    _resolve_change_pct,
    detect_hoshi_pattern,
    is_st_name,
    is_suspended,
)


# ---------------------------------------------------------------------------
# 构造合成 K 线
# ---------------------------------------------------------------------------

def _uptrend(n: int, start: float = 10.0, step: float = 0.08):
    """生成上升趋势 OHLCV（close 线性上行，保证 MA20 > MA60）"""
    rows = []
    for i in range(n):
        c = start + step * i
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "open": c * 0.995,
                "high": c * 1.008,
                "low": c * 0.992,
                "close": c,
                "volume": 1_000_000 + i * 1000,
                "amount": (1_000_000 + i * 1000) * c,
            }
        )
    return pd.DataFrame(rows)


def _add_change_pct(df: pd.DataFrame) -> pd.DataFrame:
    """按 close 补出 change_pct / preclose 列"""
    df = df.copy()
    df["preclose"] = df["close"].shift(1)
    df["change_pct"] = (df["close"] - df["preclose"]) / df["preclose"] * 100.0
    return df


def _append_candle(df, open_, high, low, close, volume=1_200_000):
    """在末尾追加一根 K 线"""
    last_date = df["date"].iloc[-1]
    row = {
        "date": last_date + pd.Timedelta(days=1),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": volume * close,
    }
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def build_confirmation_case(with_change_pct: bool = True, corrupt_change: bool = False):
    """构造一个标准的 hoshi confirmation 形态。

    结构（最后 5 根）：
        D-5 : 趋势中
        D-4 : -6%  (prev3, 连跌第1天)
        D-3 : -6%  (prev2, 连跌第2天)
        D-2 : 锤子线 +1.0%  (prev, 企稳)
        D-1 : +7%  (latest, 确认)
    """
    df = _uptrend(66)                      # 66 根上升趋势，末根 close = 10 + 0.08*65 = 15.2
    base = df["close"].iloc[-1]            # 15.2

    d4 = base * 0.94                       # 14.288  (-6.0%)
    d3 = d4 * 0.94                         # 13.431  (-6.0%)
    # 锤子线：小实体 + 长下影 + 短上影
    d2 = d3 * 1.01                         # 13.565  (+1.0%)
    d1 = d2 * 1.07                         # 14.515  (+7.0%)

    df = _append_candle(df, d4 * 0.998, d4 * 1.005, d4 * 0.992, d4)
    df = _append_candle(df, d3 * 0.998, d3 * 1.005, d3 * 0.992, d3)
    df = _append_candle(df, d3 * 1.0014, d2 * 1.0026, d3 * 0.96, d2)   # 锤子
    df = _append_candle(df, d1 * 0.995, d1 * 1.008, d1 * 0.992, d1)

    if corrupt_change:
        df = _add_change_pct(df)
        # 模拟"只补了 raw_kline_daily、没补 raw_basic_daily"的情形
        df["change_pct"] = np.nan
        df["preclose"] = np.nan
    elif with_change_pct:
        df = _add_change_pct(df)
    return df


# ---------------------------------------------------------------------------
# 1. _resolve_change_pct：不允许静默 0
# ---------------------------------------------------------------------------

def test_resolve_change_pct_prefers_column():
    df = _add_change_pct(_uptrend(10))
    got = _resolve_change_pct(df, -1)
    assert got is not None
    assert abs(got - df["change_pct"].iloc[-1]) < 1e-9


def test_resolve_change_pct_falls_back_to_prev_close():
    """没有 change_pct / preclose 列时，用前一根 close 推算 —— 这正是旧代码的漏洞点"""
    df = _uptrend(10)                      # 只有 OHLCV
    got = _resolve_change_pct(df, -1)
    expected = (df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100
    assert got is not None
    assert abs(got - expected) < 1e-9
    assert abs(got) > 1e-6                 # 绝不能是 0


def test_resolve_change_pct_returns_none_when_unknown():
    """首行无法推算前收盘 → 必须返回 None，不能返回 0"""
    df = _uptrend(3)
    assert _resolve_change_pct(df, 0) is None


def test_resolve_change_pct_returns_none_on_nan_close():
    df = _uptrend(5)
    df.loc[3, "close"] = np.nan
    assert _resolve_change_pct(df, 3) is None


# ---------------------------------------------------------------------------
# 2. detect_hoshi_pattern：核心形态 + 数据缺失回归
# ---------------------------------------------------------------------------

def test_detect_confirmation_hit():
    df = build_confirmation_case(with_change_pct=True)
    pat = detect_hoshi_pattern(df, mode="confirmation")
    assert pat is not None, "标准 hoshi 确认形态应命中"
    assert pat["mode"] == "confirmation"
    assert len(pat["drop_days"]) == 2
    # 评分改革后（2026-09）：深跌/大涨确认不再加分，浅跌/温和确认更优。
    # 本用例总跌 -12%、确认 +7%，得分 7.5（基础3 + 跌幅1.0 + 锤子2.5 + 下影1.0 + 大涨0）。
    assert pat["score"] >= 7.0


def test_detect_no_longer_misses_when_basic_table_stale():
    """回归：change_pct/preclose 全是 NaN（只补了 kline 没补 basic）时，
    旧实现走 `changes.append(0)` → 判不出连跌 → 静默漏信号。新实现应照常命中。"""
    good = build_confirmation_case(with_change_pct=True)
    stale = build_confirmation_case(corrupt_change=True)

    pat_good = detect_hoshi_pattern(good, mode="confirmation")
    pat_stale = detect_hoshi_pattern(stale, mode="confirmation")

    assert pat_good is not None
    assert pat_stale is not None, "数据缺失不应导致漏信号"
    assert pat_stale["score"] == pytest.approx(pat_good["score"], abs=0.05)
    assert pat_stale["drop_days"] == pat_good["drop_days"]


def test_detect_returns_none_when_close_unusable():
    """收盘价损坏（无法推算涨跌幅）→ 放弃，而不是当成平盘"""
    df = build_confirmation_case(corrupt_change=True)
    df.loc[len(df) - 1, "close"] = np.nan
    assert detect_hoshi_pattern(df, mode="confirmation") is None


def test_detect_requires_uptrend():
    """MA20 < MA60（下降趋势）不应出信号"""
    df = build_confirmation_case()
    n = len(df)
    # 把最近 25 天砸下去，破坏 MA20 > MA60
    df.loc[n - 25:, ["open", "high", "low", "close"]] *= 0.5
    df = _add_change_pct(df)
    assert detect_hoshi_pattern(df, mode="confirmation") is None


def test_detect_stabilization_mode():
    """企稳模式：D-3/D-2 连跌，D-1 为锤子线"""
    df = _uptrend(66)
    base = df["close"].iloc[-1]
    d3 = base * 0.94
    d2 = d3 * 0.94
    d1 = d2 * 1.008                     # 企稳日，小涨
    df = _append_candle(df, d3 * 0.998, d3 * 1.005, d3 * 0.992, d3)
    df = _append_candle(df, d2 * 0.998, d2 * 1.005, d2 * 0.992, d2)
    # 锤子线：小实体 + 长下影
    df = _append_candle(df, d2 * 1.001, d1 * 1.003, d2 * 0.955, d1)
    df = _add_change_pct(df)

    pat = detect_hoshi_pattern(df, mode="stabilization")
    assert pat is not None, "企稳形态应命中"
    assert pat["mode"] == "stabilization"
    assert pat["confirmation_day"] == "待确认"


def test_detect_rejects_insufficient_history():
    df = build_confirmation_case().tail(40)     # 不足 65 根，算不出 MA60
    assert detect_hoshi_pattern(df, mode="confirmation") is None


# ---------------------------------------------------------------------------
# 3. 可执行性过滤
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,expected",
    [
        ("贵州茅台", False),
        ("ST中安", True),
        ("*ST海航", True),
        ("st 银河", True),
        ("退市美吉", True),
        ("", False),
        (None, False),
    ],
)
def test_is_st_name(name, expected):
    assert is_st_name(name) is expected


def test_is_suspended():
    ok = pd.Series({"close": 10.0, "volume": 1_000_000, "high": 10.2, "low": 9.8})
    assert is_suspended(ok) is False
    assert is_suspended(pd.Series({"close": 10.0, "volume": 0, "high": 10.2, "low": 9.8})) is True
    assert is_suspended(pd.Series({"close": 10.0, "volume": 1e5, "high": 10.0, "low": 10.0})) is True
    assert is_suspended(pd.Series({"close": np.nan, "volume": 1e5, "high": 10.0, "low": 9.8})) is True


def test_screener_filters_st():
    df = build_confirmation_case()
    assert HoshiScreener(mode="confirmation").screen_one("sh600000", "ST某某", df) is None
    assert HoshiScreener(mode="confirmation", exclude_st=False).screen_one(
        "sh600000", "ST某某", df
    ) is not None


def test_screener_filters_suspended():
    df = build_confirmation_case()
    df.loc[len(df) - 1, "volume"] = 0
    assert HoshiScreener(mode="confirmation").screen_one("sh600000", "测试", df) is None


def test_screener_filters_low_amount():
    df = build_confirmation_case()
    assert HoshiScreener(mode="confirmation", min_amount=1e9).screen_one(
        "sh600000", "测试", df
    ) is None
    assert HoshiScreener(mode="confirmation", min_amount=1e5).screen_one(
        "sh600000", "测试", df
    ) is not None


def test_screener_filters_stale_data():
    """as_of 与数据最后一天不符 → 丢弃（防止用旧数据发"今日"信号）"""
    df = build_confirmation_case()
    last_day = df["date"].iloc[-1].date()
    assert HoshiScreener(mode="confirmation", as_of=last_day).screen_one(
        "sh600000", "测试", df
    ) is not None
    stale_day = last_day - pd.Timedelta(days=3).to_pytimedelta()
    assert HoshiScreener(mode="confirmation", as_of=stale_day).screen_one(
        "sh600000", "测试", df
    ) is None


def test_screener_stats_accounting():
    """stats 各口径之和应等于 total，便于排查"为什么没信号" """
    df = build_confirmation_case()
    df_ok = build_confirmation_case()
    df_ok["amount"] = df_ok["amount"] * 1000        # 抬高成交额，使其通过流动性门槛

    s = HoshiScreener(mode="confirmation", min_amount=1e9)
    s.screen_one("sh600000", "测试", df)      # 被 low_amount 挡掉
    s.screen_one("sh600001", "ST某某", df)    # 被 st 挡掉
    s.screen_one("sh600002", "正常", df_ok)   # 命中
    assert s.stats["total"] == 3
    assert (
        s.stats["st"] + s.stats["suspended"] + s.stats["stale"] + s.stats["low_amount"]
        + s.stats["no_pattern"] + s.stats["low_score"] + s.stats["hit"] + s.stats["no_data"]
    ) == 3
    assert s.stats["low_amount"] == 1
    assert s.stats["st"] == 1
    assert s.stats["hit"] == 1


def test_screener_result_has_no_nan():
    """输出给下游的 pct_change / price 不能是 NaN"""
    df = build_confirmation_case(corrupt_change=True)
    r = HoshiScreener(mode="confirmation").screen_one("sh600000", "测试", df)
    assert r is not None
    assert not pd.isna(r.pct_change)
    assert not pd.isna(r.price)


# ---------------------------------------------------------------------------
# 4. 真实数据校验（需要 data/tdx.duckdb）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not __import__("pathlib").Path("data/tdx.duckdb").exists(),
    reason="需要 data/tdx.duckdb",
)
def test_real_case_600367():
    """红星发展 600367 是策略文档记录的典型案例，必须能复现"""
    from core.data.duckdb_source import TdxDB

    tdx = TdxDB("data/tdx.duckdb")
    try:
        df = tdx.load_daily("sh600367", days=0, end_date="2026-06-26", fq="bfq")
    finally:
        tdx.close()
    if df.empty or len(df) < 65:
        pytest.skip("本地库数据不足")

    pat = detect_hoshi_pattern(df, mode="confirmation")
    assert pat is not None, "600367 在 2026-06-26 应命中 hoshi 确认形态"
    # 评分改革后深跌(-18.9%)+涨停确认(+10%)被降权，得分约 5.5，仍高于默认门槛 5.0。
    assert pat["score"] >= 5.0


@pytest.mark.skipif(
    not __import__("pathlib").Path("data/tdx.duckdb").exists(),
    reason="需要 data/tdx.duckdb",
)
def test_batch_load_end_date_prevents_lookahead():
    """end_date 之后的数据不得出现在结果里（回测正确性底线）"""
    from core.data.duckdb_source import TdxDB

    tdx = TdxDB("data/tdx.duckdb")
    try:
        cutoff = "2026-06-26"
        d = tdx.batch_load_daily(symbols=["sh600367"], days=30, end_date=cutoff, min_records=1)
        assert "sh600367" in d
        assert d["sh600367"]["date"].max() <= pd.Timestamp(cutoff)
        # 不带 end_date 时应该能取到更晚的数据
        full = tdx.batch_load_daily(symbols=["sh600367"], days=30, min_records=1)
        assert full["sh600367"]["date"].max() >= d["sh600367"]["date"].max()
    finally:
        tdx.close()
