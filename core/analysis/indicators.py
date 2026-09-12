"""M4: 技术指标计算引擎

纯函数式设计，输入 DataFrame，输出带指标列的 DataFrame。
支持: MA, EMA, MACD, RSI, KDJ, BOLL, ATR, OBV, CCI, VWAP 等。
"""

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 均线系列
# ---------------------------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    """简单移动平均线"""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """指数移动平均线"""
    return series.ewm(span=span, adjust=False).mean()


def add_ma(df: pd.DataFrame, windows: list = [5, 10, 20, 60]) -> pd.DataFrame:
    """添加多条 MA 均线"""
    for w in windows:
        df[f"ma{w}"] = sma(df["close"], w)
    return df


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple:
    """MACD 指标

    Returns:
        (dif, dea, macd_hist)
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal)
    macd_hist = (dif - dea) * 2
    return dif, dea, macd_hist


def add_macd(df: pd.DataFrame) -> pd.DataFrame:
    """添加 MACD 列"""
    dif, dea, hist = macd(df["close"])
    df["macd_dif"] = dif
    df["macd_dea"] = dea
    df["macd_hist"] = hist
    return df


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI 相对强弱指标"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_rsi(df: pd.DataFrame, periods: list = [6, 12, 24]) -> pd.DataFrame:
    """添加多周期 RSI"""
    for p in periods:
        df[f"rsi{p}"] = rsi(df["close"], p)
    return df


# ---------------------------------------------------------------------------
# KDJ
# ---------------------------------------------------------------------------

def kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> tuple:
    """KDJ 随机指标

    Returns:
        (k, d, j)
    """
    low_n = low.rolling(window=n, min_periods=n).min()
    high_n = high.rolling(window=n, min_periods=n).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def add_kdj(df: pd.DataFrame) -> pd.DataFrame:
    """添加 KDJ 列"""
    k, d, j = kdj(df["high"], df["low"], df["close"])
    df["kdj_k"] = k
    df["kdj_d"] = d
    df["kdj_j"] = j
    return df


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple:
    """布林带

    Returns:
        (upper, middle, lower)
    """
    middle = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def add_boll(df: pd.DataFrame) -> pd.DataFrame:
    """添加 BOLL 列"""
    upper, middle, lower = bollinger_bands(df["close"])
    df["boll_upper"] = upper
    df["boll_mid"] = middle
    df["boll_lower"] = lower
    return df


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """平均真实波幅"""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """添加 ATR 列"""
    df[f"atr{period}"] = atr(df["high"], df["low"], df["close"], period)
    return df


# ---------------------------------------------------------------------------
# OBV (On Balance Volume)
# ---------------------------------------------------------------------------

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """能量潮指标"""
    direction = np.where(close > close.shift(1), 1, np.where(close < close.shift(1), -1, 0))
    return (volume * direction).cumsum()


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    """添加 OBV 列"""
    df["obv"] = obv(df["close"], df["volume"])
    return df


# ---------------------------------------------------------------------------
# CCI (Commodity Channel Index)
# ---------------------------------------------------------------------------

def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """顺势指标"""
    tp = (high + low + close) / 3
    ma_tp = tp.rolling(window=period, min_periods=period).mean()
    md = tp.rolling(window=period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean()
    )
    return (tp - ma_tp) / (0.015 * md)


def add_cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """添加 CCI 列"""
    df[f"cci{period}"] = cci(df["high"], df["low"], df["close"], period)
    return df


# ---------------------------------------------------------------------------
# 量价指标
# ---------------------------------------------------------------------------

def volume_ratio(volume: pd.Series, window: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 过去N日平均成交量"""
    avg_vol = volume.rolling(window=window, min_periods=window).mean()
    return volume / avg_vol.replace(0, np.nan)


def add_volume_ratio(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """添加量比列"""
    df[f"vol_ratio{window}"] = volume_ratio(df["volume"], window)
    return df


# ---------------------------------------------------------------------------
# 形态识别
# ---------------------------------------------------------------------------

def detect_golden_cross(ma_short: pd.Series, ma_long: pd.Series) -> pd.Series:
    """金叉检测: 短期均线上穿长期均线"""
    prev_short = ma_short.shift(1)
    prev_long = ma_long.shift(1)
    return (prev_short <= prev_long) & (ma_short > ma_long)


def detect_death_cross(ma_short: pd.Series, ma_long: pd.Series) -> pd.Series:
    """死叉检测: 短期均线下穿长期均线"""
    prev_short = ma_short.shift(1)
    prev_long = ma_long.shift(1)
    return (prev_short >= prev_long) & (ma_short < ma_long)


def detect_macd_golden_cross(dif: pd.Series, dea: pd.Series) -> pd.Series:
    """MACD 金叉"""
    return (dif.shift(1) <= dea.shift(1)) & (dif > dea)


def detect_macd_death_cross(dif: pd.Series, dea: pd.Series) -> pd.Series:
    """MACD 死叉"""
    return (dif.shift(1) >= dea.shift(1)) & (dif < dea)


def detect_volume_breakout(volume: pd.Series, multiplier: float = 2.0, window: int = 20) -> pd.Series:
    """放量突破: 成交量超过过去N日均量的 multiplier 倍"""
    avg_vol = volume.rolling(window=window, min_periods=window).mean()
    return volume > (avg_vol * multiplier)


# ---------------------------------------------------------------------------
# 一键添加所有指标
# ---------------------------------------------------------------------------

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为 DataFrame 添加所有常用技术指标"""
    if df.empty:
        return df
    df = df.copy()
    df = add_ma(df)
    df = add_macd(df)
    df = add_rsi(df)
    df = add_kdj(df)
    df = add_boll(df)
    df = add_atr(df)
    df = add_obv(df)
    df = add_cci(df)
    df = add_volume_ratio(df)
    return df


# ---------------------------------------------------------------------------
# 信号生成
# ---------------------------------------------------------------------------

def generate_signals(df: pd.DataFrame) -> dict:
    """基于最新一行数据生成交易信号摘要"""
    if len(df) < 60:
        return {"error": "数据不足60条，无法生成信号"}

    latest = df.iloc[-1]
    signals = {}

    # 均线趋势
    if "ma5" in df.columns and "ma10" in df.columns and "ma20" in df.columns:
        if latest["ma5"] > latest["ma10"] > latest["ma20"]:
            signals["ma_trend"] = "多头排列"
        elif latest["ma5"] < latest["ma10"] < latest["ma20"]:
            signals["ma_trend"] = "空头排列"
        else:
            signals["ma_trend"] = "震荡整理"

        # 金叉/死叉
        gc = detect_golden_cross(df["ma5"], df["ma10"])
        dc = detect_death_cross(df["ma5"], df["ma10"])
        if gc.iloc[-1]:
            signals["ma_cross"] = "MA5/MA10 金叉"
        elif dc.iloc[-1]:
            signals["ma_cross"] = "MA5/MA10 死叉"

    # MACD
    if "macd_dif" in df.columns:
        mgc = detect_macd_golden_cross(df["macd_dif"], df["macd_dea"])
        mdc = detect_macd_death_cross(df["macd_dif"], df["macd_dea"])
        if mgc.iloc[-1]:
            signals["macd"] = "MACD金叉"
        elif mdc.iloc[-1]:
            signals["macd"] = "MACD死叉"
        elif latest["macd_dif"] > latest["macd_dea"]:
            signals["macd"] = "MACD多头"
        else:
            signals["macd"] = "MACD空头"

    # RSI
    if "rsi12" in df.columns:
        rsi_val = latest["rsi12"]
        if rsi_val > 80:
            signals["rsi"] = f"超买 ({rsi_val:.1f})"
        elif rsi_val < 20:
            signals["rsi"] = f"超卖 ({rsi_val:.1f})"
        else:
            signals["rsi"] = f"中性 ({rsi_val:.1f})"

    # KDJ
    if "kdj_j" in df.columns:
        j_val = latest["kdj_j"]
        if j_val > 100:
            signals["kdj"] = f"超买 (J={j_val:.1f})"
        elif j_val < 0:
            signals["kdj"] = f"超卖 (J={j_val:.1f})"

    # 布林带
    if "boll_upper" in df.columns:
        price = latest["close"]
        if price > latest["boll_upper"]:
            signals["boll"] = "突破上轨"
        elif price < latest["boll_lower"]:
            signals["boll"] = "跌破下轨"
        else:
            pct = (price - latest["boll_lower"]) / (latest["boll_upper"] - latest["boll_lower"])
            signals["boll"] = f"带内运行 ({pct:.0%})"

    # 量比
    if "vol_ratio5" in df.columns:
        vr = latest["vol_ratio5"]
        if not pd.isna(vr):
            if vr > 2:
                signals["volume"] = f"放量 ({vr:.1f}x)"
            elif vr < 0.5:
                signals["volume"] = f"缩量 ({vr:.1f}x)"

    return signals
