"""M5: 多条件选股筛选器

支持技术指标筛选 + 基本面筛选 + 综合打分。
全市场扫描，输出符合条件的股票列表。
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd
from loguru import logger

from core.analysis.indicators import (
    add_all_indicators,
    detect_death_cross,
    detect_golden_cross,
    detect_macd_death_cross,
    detect_macd_golden_cross,
    detect_volume_breakout,
)


# ---------------------------------------------------------------------------
# 筛选条件定义
# ---------------------------------------------------------------------------

@dataclass
class FilterCondition:
    """筛选条件"""
    name: str
    description: str
    check_func: Callable  # (df_with_indicators) -> bool
    weight: float = 1.0


@dataclass
class ScreeningResult:
    """单只股票的筛选结果"""
    code: str
    name: str
    score: float
    signals: list = field(default_factory=list)
    price: float = 0.0
    pct_change: float = 0.0

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "score": self.score,
            "signals": ", ".join(self.signals),
            "price": self.price,
            "pct_change": self.pct_change,
        }


# ---------------------------------------------------------------------------
# 内置筛选条件
# ---------------------------------------------------------------------------

def _check_ma_bull_alignment(df: pd.DataFrame) -> bool:
    """多头排列: MA5 > MA10 > MA20"""
    if len(df) < 20:
        return False
    r = df.iloc[-1]
    return r["ma5"] > r["ma10"] > r["ma20"]


def _check_ma_golden_cross(df: pd.DataFrame) -> bool:
    """MA5/MA10 金叉 (最近3日内)"""
    if len(df) < 22:
        return False
    gc = detect_golden_cross(df["ma5"], df["ma10"])
    return gc.iloc[-3:].any()


def _check_macd_golden_cross(df: pd.DataFrame) -> bool:
    """MACD 金叉 (最近3日内)"""
    if len(df) < 30:
        return False
    gc = detect_macd_golden_cross(df["macd_dif"], df["macd_dea"])
    return gc.iloc[-3:].any()


def _check_macd_above_zero(df: pd.DataFrame) -> bool:
    """MACD DIF 在零轴上方"""
    if len(df) < 30:
        return False
    return df.iloc[-1]["macd_dif"] > 0


def _check_volume_breakout(df: pd.DataFrame) -> bool:
    """放量: 量比 > 2"""
    if len(df) < 25:
        return False
    vr = df.iloc[-1].get("vol_ratio5", 0)
    return not pd.isna(vr) and vr > 2.0


def _check_rsi_not_overbought(df: pd.DataFrame) -> bool:
    """RSI 未超买 (< 80)"""
    if len(df) < 20:
        return False
    rsi_val = df.iloc[-1].get("rsi12", 50)
    return not pd.isna(rsi_val) and rsi_val < 80


def _check_rsi_oversold_rebound(df: pd.DataFrame) -> bool:
    """RSI 超卖反弹: RSI 从 <30 回升到 >30"""
    if len(df) < 20:
        return False
    rsi_series = df["rsi12"].tail(5)
    if rsi_series.isna().all():
        return False
    return rsi_series.min() < 30 and rsi_series.iloc[-1] > 30


def _check_price_above_boll_mid(df: pd.DataFrame) -> bool:
    """价格在布林中轨上方"""
    if len(df) < 25:
        return False
    r = df.iloc[-1]
    return r["close"] > r["boll_mid"]


def _check_kdj_golden_cross(df: pd.DataFrame) -> bool:
    """KDJ 金叉: K 上穿 D"""
    if len(df) < 15:
        return False
    k = df["kdj_k"]
    d = df["kdj_d"]
    return k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1]


def _check_price_above_ma60(df: pd.DataFrame) -> bool:
    """价格在 60 日均线上方 (中期趋势向上)"""
    if len(df) < 60:
        return False
    return df.iloc[-1]["close"] > df.iloc[-1]["ma60"]


# ---------------------------------------------------------------------------
# 预设筛选策略
# ---------------------------------------------------------------------------

PRESET_STRATEGIES = {
    "bull_trend": {
        "name": "多头趋势",
        "description": "均线多头排列 + MACD零轴上方 + 未超买",
        "conditions": [
            FilterCondition("ma_bull", "均线多头排列", _check_ma_bull_alignment, weight=2.0),
            FilterCondition("macd_above_zero", "MACD零轴上方", _check_macd_above_zero, weight=1.5),
            FilterCondition("rsi_not_ob", "RSI未超买", _check_rsi_not_overbought, weight=1.0),
            FilterCondition("above_ma60", "站上60日线", _check_price_above_ma60, weight=1.5),
        ],
        "min_score": 4.0,
    },
    "golden_cross": {
        "name": "金叉突破",
        "description": "近期出现 MA/MACD 金叉 + 放量",
        "conditions": [
            FilterCondition("ma_gc", "MA金叉", _check_ma_golden_cross, weight=2.0),
            FilterCondition("macd_gc", "MACD金叉", _check_macd_golden_cross, weight=2.0),
            FilterCondition("vol_breakout", "放量", _check_volume_breakout, weight=1.5),
            FilterCondition("rsi_not_ob", "RSI未超买", _check_rsi_not_overbought, weight=1.0),
        ],
        "min_score": 3.5,
    },
    "oversold_rebound": {
        "name": "超卖反弹",
        "description": "RSI超卖后反弹 + KDJ金叉",
        "conditions": [
            FilterCondition("rsi_rebound", "RSI超卖反弹", _check_rsi_oversold_rebound, weight=2.5),
            FilterCondition("kdj_gc", "KDJ金叉", _check_kdj_golden_cross, weight=2.0),
            FilterCondition("above_boll_mid", "站上布林中轨", _check_price_above_boll_mid, weight=1.0),
        ],
        "min_score": 3.0,
    },
    "volume_breakout": {
        "name": "放量突破",
        "description": "放量 + 均线多头 + 站上60日线",
        "conditions": [
            FilterCondition("vol_breakout", "放量", _check_volume_breakout, weight=2.5),
            FilterCondition("ma_bull", "均线多头", _check_ma_bull_alignment, weight=2.0),
            FilterCondition("above_ma60", "站上60日线", _check_price_above_ma60, weight=1.5),
            FilterCondition("macd_above_zero", "MACD零轴上", _check_macd_above_zero, weight=1.0),
        ],
        "min_score": 4.0,
    },
}


# ---------------------------------------------------------------------------
# 筛选器
# ---------------------------------------------------------------------------

class StockScreener:
    """多条件选股筛选器

    使用方式:
        screener = StockScreener()
        # 使用预设策略
        results = screener.screen(df_dict, strategy="bull_trend")
        # 自定义条件
        screener.add_condition(FilterCondition(...))
        results = screener.screen(df_dict)
    """

    def __init__(self, strategy: str = "bull_trend"):
        self.conditions: list[FilterCondition] = []
        self.min_score: float = 0.0
        if strategy and strategy in PRESET_STRATEGIES:
            self.load_preset(strategy)

    def load_preset(self, strategy_name: str):
        """加载预设策略"""
        preset = PRESET_STRATEGIES.get(strategy_name)
        if not preset:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(PRESET_STRATEGIES.keys())}")
        self.conditions = preset["conditions"]
        self.min_score = preset["min_score"]
        logger.info(f"Loaded strategy: {preset['name']} - {preset['description']}")

    def add_condition(self, condition: FilterCondition):
        """添加自定义筛选条件"""
        self.conditions.append(condition)

    def clear_conditions(self):
        """清空所有条件"""
        self.conditions = []

    def screen_one(self, code: str, name: str, df: pd.DataFrame) -> Optional[ScreeningResult]:
        """筛选单只股票"""
        if df.empty or len(df) < 20:
            return None

        try:
            df_with_indicators = add_all_indicators(df)
        except Exception as e:
            logger.debug(f"Indicator calc failed for {code}: {e}")
            return None

        score = 0.0
        signals = []

        for cond in self.conditions:
            try:
                if cond.check_func(df_with_indicators):
                    score += cond.weight
                    signals.append(cond.description)
            except Exception:
                pass

        if score < self.min_score:
            return None

        latest = df_with_indicators.iloc[-1]
        return ScreeningResult(
            code=code,
            name=name,
            score=round(score, 2),
            signals=signals,
            price=float(latest.get("close", 0)),
            pct_change=0.0,
        )

    def screen_batch(
        self,
        df_dict: dict[str, pd.DataFrame],
        name_map: dict[str, str] = None,
        top_n: int = 50,
    ) -> list[ScreeningResult]:
        """批量筛选

        Args:
            df_dict: {code: kline_dataframe}
            name_map: {code: stock_name}
            top_n: 返回前 N 名

        Returns:
            按 score 降序排列的筛选结果列表
        """
        if name_map is None:
            name_map = {}

        results = []
        total = len(df_dict)

        for i, (code, df) in enumerate(df_dict.items()):
            result = self.screen_one(code, name_map.get(code, ""), df)
            if result:
                results.append(result)
            if (i + 1) % 100 == 0:
                logger.info(f"Screening progress: {i+1}/{total}, hits: {len(results)}")

        results.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"Screening complete: {len(results)} hits from {total} stocks")
        return results[:top_n]

    def get_available_strategies(self) -> list[dict]:
        """获取所有可用策略"""
        return [
            {"name": k, "description": v["description"], "min_score": v["min_score"]}
            for k, v in PRESET_STRATEGIES.items()
        ]
