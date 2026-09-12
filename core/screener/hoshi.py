"""Hoshi (ほし/星) 筛选策略

核心思想: 在上升趋势中捕捉连跌后的企稳买点。

形态描述 (来自用户讨论):
  "均线多头排列，近两个交易日股价下跌的个股。
   均线多头排列，近3个交易日前两个交易日股价下跌，最后一个交易日股价上涨。
   前两个交易日都大跌，但昨天稳住了，今天就封板了。
   真正好的买点就是昨天，企稳那个点。
   昨天收长下引线，单针探底。上影线不太好。"

红星发展 600367 典型案例 (2026-06-22 ~ 06-26):
  Day1 (6/22): 涨停 62.22 (+10.00%)
  Day2 (6/23): 跌停 56.00 (-10.00%)  ← 连跌开始
  Day3 (6/24): 续跌 51.00 (-8.93%)    ← 第二天大跌
  Day4 (6/25): 企稳 52.98 (+3.88%)    ← ★ 最佳买点 (小实体+下影线)
  Day5 (6/26): 封板 58.28 (+10.00%)   ← 确认上涨

策略两种模式:
  - Mode A "stabilization": 在企稳日发出信号 (Day4, 激进买点)
  - Mode B "confirmation":  在确认日发出信号 (Day5, 稳健买点)

使用方式:
    from core.screener.hoshi import HoshiScreener

    screener = HoshiScreener(mode="confirmation")
    results = screener.screen_batch(df_dict, name_map)
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from core.screener.screener import ScreeningResult


# ---------------------------------------------------------------------------
# K线形态判定函数
# ---------------------------------------------------------------------------

def is_bearish(row: pd.Series) -> bool:
    """阴线: 收盘 < 开盘"""
    return row["close"] < row["open"]


def body_size(row: pd.Series) -> float:
    """实体大小 (绝对值)"""
    return abs(row["close"] - row["open"])


def upper_shadow(row: pd.Series) -> float:
    """上影线长度"""
    return row["high"] - max(row["open"], row["close"])


def lower_shadow(row: pd.Series) -> float:
    """下影线长度"""
    return min(row["open"], row["close"]) - row["low"]


def candle_range(row: pd.Series) -> float:
    """当日振幅 (最高-最低)"""
    return row["high"] - row["low"]


def is_hammer(row: pd.Series, body_ratio: float = 0.3, lower_factor: float = 1.5,
              upper_max_ratio: float = 0.5) -> bool:
    """锤子线 / 单针探底

    条件:
    - 实体占振幅比 < body_ratio (小实体)
    - 下影线 > 实体 * lower_factor (长下影)
    - 上影线 < 振幅 * upper_max_ratio (上影不太长)
    """
    rng = candle_range(row)
    if rng <= 0 or row["close"] <= 0:
        return False

    body = body_size(row)
    lower = lower_shadow(row)
    upper = upper_shadow(row)

    # 实体占比
    body_pct = body / rng
    if body_pct > body_ratio:
        return False

    # 下影线要显著
    if body > 0 and lower < body * lower_factor:
        return False
    if body == 0 and lower < rng * 0.4:
        return False

    # 上影线不能太长
    if upper > rng * upper_max_ratio:
        return False

    return True


def is_doji(row: pd.Series, body_pct_max: float = 0.15) -> bool:
    """十字星: 实体极小"""
    rng = candle_range(row)
    if rng <= 0 or row["close"] <= 0:
        return False
    return body_size(row) / rng < body_pct_max


# ---------------------------------------------------------------------------
# 数据健壮性工具
# ---------------------------------------------------------------------------

def _resolve_change_pct(df: pd.DataFrame, pos: int) -> Optional[float]:
    """取第 pos 行（支持负数索引，-1 = 最后一行）的日涨跌幅 %。

    优先级：
      1. change_pct 列（来自 raw_basic_daily）
      2. preclose 列
      3. 前一根 K 线的 close

    **三者都拿不到时返回 None（未知），绝不返回 0。**
    老版本在这里 append(0)，会把"数据缺失"当成"平盘"，
    导致 `-2 <= chg <= 5` 的企稳判定被错误通过 —— 这是漏/误信号的根因。
    """
    row = df.iloc[pos]
    close = row.get("close")
    if close is None or pd.isna(close):
        return None
    close = float(close)

    # 1) change_pct 列
    if "change_pct" in df.columns:
        v = row.get("change_pct")
        if v is not None and not pd.isna(v):
            return float(v)

    # 2) preclose 列
    if "preclose" in df.columns:
        pc = row.get("preclose")
        if pc is not None and not pd.isna(pc) and float(pc) > 0:
            return (close - float(pc)) / float(pc) * 100.0

    # 3) 前一根收盘价
    n = len(df)
    abs_pos = pos if pos >= 0 else n + pos
    if abs_pos < 1:
        return None
    pc = df["close"].iloc[abs_pos - 1]
    if pc is None or pd.isna(pc) or float(pc) <= 0:
        return None
    return (close - float(pc)) / float(pc) * 100.0


def is_st_name(name: str) -> bool:
    """ST / *ST / 退市整理 股名称判定"""
    if not name:
        return False
    n = str(name).upper().replace(" ", "")
    if "ST" in n:
        return True
    return n.startswith("退") or n.endswith("退")


def is_suspended(row: pd.Series) -> bool:
    """停牌判定：无成交量 或 无收盘价 或 一字线(最高=最低)"""
    if row.get("close") is None or pd.isna(row.get("close")):
        return True
    vol = row.get("volume", 0)
    if vol is None or pd.isna(vol) or float(vol) <= 0:
        return True
    hi, lo = row.get("high"), row.get("low")
    if hi is not None and lo is not None and not pd.isna(hi) and not pd.isna(lo):
        if float(hi) <= float(lo):
            return True  # 一字板 / 无波动，非有效企稳形态
    return False


def is_stabilization_candle(row: pd.Series) -> bool:
    """企稳K线: 锤子线 或 十字星 或 小实体+长下影"""
    return is_hammer(row) or is_doji(row)


# ---------------------------------------------------------------------------
# Hoshi 模式检测
# ---------------------------------------------------------------------------

def detect_hoshi_pattern(df: pd.DataFrame, mode: str = "confirmation") -> Optional[dict]:
    """检测 Hoshi 模式

    Args:
        df: DataFrame（需 close 列；ma20/ma60 缺失时本函数会自动计算）
        mode: 'stabilization' (企稳日信号) 或 'confirmation' (确认日信号)

    Returns:
        dict with pattern details, or None if no match
    """
    if df is None or len(df) < 65:  # 需要至少 60 天算 MA60
        return None

    # 兼容直接调用：本函数曾被外部直接调用而不经过 HoshiScreener，
    # 那时 df 没有 ma20/ma60，条件 1 会读到 0 并直接 return None（静默漏信号）。
    if "ma20" not in df.columns or "ma60" not in df.columns:
        from core.analysis.indicators import sma
        df = df.copy()
        if "ma20" not in df.columns:
            df["ma20"] = sma(df["close"], 20)
        if "ma60" not in df.columns:
            df["ma60"] = sma(df["close"], 60)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None
    prev2 = df.iloc[-3] if len(df) >= 3 else None
    prev3 = df.iloc[-4] if len(df) >= 4 else None

    if prev is None or prev2 is None:
        return None

    # ---- 条件 1: 中期上升趋势 ----
    ma20 = latest.get("ma20", 0)
    ma60 = latest.get("ma60", 0)
    if pd.isna(ma20) or pd.isna(ma60) or ma20 <= 0 or ma60 <= 0:
        return None

    trend_up = ma20 > ma60  # 中期趋势向上
    if not trend_up:
        return None

    # ---- 条件 2: 近期连跌 ----
    # 倒数 3 天涨跌幅；任一天无法解析 → 放弃（不再静默当 0%）
    changes = []
    for p in (-3, -2, -1):
        chg = _resolve_change_pct(df, p)
        if chg is None:
            return None
        changes.append(chg)

    # Mode A (stabilization): 倒数第 2、3 天连跌, 最后一天企稳
    # Mode B (confirmation):  倒数第 3、4 天连跌, 倒数第 2 天企稳, 最后一天确认上涨

    if mode == "confirmation":
        # 需要 prev3 存在
        if prev3 is None:
            return None

        # 计算 prev3 的涨跌幅（同样不允许静默 0）
        chg_prev3 = _resolve_change_pct(df, -4)
        if chg_prev3 is None:
            return None

        # 连跌: prev3 和 prev2 都是下跌
        drop_days = []
        if chg_prev3 < -2:
            drop_days.append(("D-4", chg_prev3, prev3))
        if changes[0] < -2:  # prev2
            drop_days.append(("D-3", changes[0], prev2))

        if len(drop_days) < 2:
            return None

        total_drop = sum(d[1] for d in drop_days)

        # 企稳: prev (D-2) 是企稳K线 或 小幅上涨
        stabilization = is_stabilization_candle(prev) or (
            -2 <= changes[1] <= 5 and body_size(prev) / max(prev["close"], 0.01) < 0.03
        )
        if not stabilization:
            return None

        # 确认: latest (D-1) 上涨
        if changes[2] <= 0:
            return None

        return {
            "mode": "confirmation",
            "trend": f"MA20({ma20:.2f}) > MA60({ma60:.2f})",
            "drop_days": [(d[0], f"{d[1]:+.2f}%") for d in drop_days],
            "total_drop": f"{total_drop:+.2f}%",
            "stabilization_day": f"D-2 ({prev.name if hasattr(prev, 'name') else ''})",
            "confirmation_day": f"D-1 (涨 {changes[2]:+.2f}%)",
            "score": _calc_hoshi_score(drop_days, changes, prev, latest),
        }

    else:  # mode == "stabilization"
        # 连跌: prev2 和 prev 都下跌
        drop_days = []
        if changes[0] < -2:  # prev2
            drop_days.append(("D-3", changes[0], prev2))
        if changes[1] < -2:  # prev
            drop_days.append(("D-2", changes[1], prev))

        if len(drop_days) < 2:
            return None

        total_drop = sum(d[1] for d in drop_days)

        # 企稳: latest 是企稳K线
        if not is_stabilization_candle(latest):
            return None

        return {
            "mode": "stabilization",
            "trend": f"MA20({ma20:.2f}) > MA60({ma60:.2f})",
            "drop_days": [(d[0], f"{d[1]:+.2f}%") for d in drop_days],
            "total_drop": f"{total_drop:+.2f}%",
            "stabilization_day": "D-1 (今日)",
            "confirmation_day": "待确认",
            "score": _calc_hoshi_score(drop_days, changes, latest, None),
        }


def _calc_hoshi_score(drop_days: list, changes: list,
                      stabilization_row: pd.Series,
                      confirmation_row: Optional[pd.Series]) -> float:
    """计算 Hoshi 模式评分 (0-10)

    评分因子:
    - 跌幅深度: 越深越好 (洗盘越彻底)
    - 企稳K线质量: 锤子线 > 十字星 > 普通小实体
    - 确认力度: 确认日涨幅越大越好
    """
    score = 3.0  # 基础分

    # 跌幅因子（数据实证 2026-07~09 回放: 跌幅越深 T+5 越差，深跌是"接刀"而非"机会"）
    #   跌幅 >-6%     均值 -4.15% 胜率 36.6%  ← 最优
    #   -10~-6%      -7.44% 25.0%
    #   -15~-10%      -8.50% 23.1%
    #   <-20%         -9.02% 11.5%  ← 最差
    # → 反转原"深跌加分"逻辑：越浅的连跌越可能真正企稳，给予更高分。
    total_drop = abs(sum(d[1] for d in drop_days))
    if total_drop < 6:
        score += 2.0  # 浅跌洗盘，企稳概率高
    elif total_drop < 10:
        score += 1.5
    elif total_drop < 15:
        score += 1.0
    else:
        score += 0.5  # 深跌多为下跌中继，谨慎

    # 企稳K线质量
    if is_hammer(stabilization_row):
        score += 2.5  # 锤子线最佳
    elif is_doji(stabilization_row):
        score += 2.0  # 十字星次之
    else:
        score += 1.0  # 普通小实体

    # 下影线长度加分
    ls = lower_shadow(stabilization_row)
    rng = candle_range(stabilization_row)
    if rng > 0 and ls / rng > 0.5:
        score += 1.0  # 下影线占比 > 50%

    # 确认日加分（数据实证: 确认日大涨 >5% 反而更差，温和上涨最佳）
    #   当日 0~2%   -6.74% 28.9%  ← 温和确认最优
    #   当日 >9%    -8.73% 23.2%  ← 大幅高开/拉高多为诱多
    if confirmation_row is not None:
        confirm_chg = changes[-1] if changes else 0
        if 0 < confirm_chg <= 2:
            score += 1.5
        elif 2 < confirm_chg <= 5:
            score += 1.0
        elif confirm_chg > 5:
            score += 0.0  # 大涨确认不再加分

    return round(min(score, 10.0), 1)


# ---------------------------------------------------------------------------
# Hoshi 筛选器
# ---------------------------------------------------------------------------

class HoshiScreener:
    """Hoshi 策略筛选器

    使用方式:
        screener = HoshiScreener(mode="confirmation")
        results = screener.screen_batch(df_dict, name_map)
    """

    def __init__(
        self,
        mode: str = "confirmation",
        min_score: float = 4.0,
        exclude_st: bool = True,
        exclude_suspended: bool = True,
        min_amount: float = 0.0,
        as_of=None,
        max_daily_signals: int = None,
    ):
        """
        Args:
            mode: 'stabilization' (企稳日) 或 'confirmation' (确认日)
            min_score: 最低评分
            exclude_st: 剔除 ST / *ST / 退市整理
            exclude_suspended: 剔除停牌 / 一字板（无成交量或最高=最低）
            min_amount: 最低当日成交额（元），0 = 不限制。
                        建议实盘用 5e7（5000万）过滤僵尸股。
            as_of: 只接受最新一根 K 线日期 == 该日期的信号。
                   用于防止用陈旧数据发出"今日"信号（回测必填）。
            max_daily_signals: 每日信号拥挤度上限。某日初步命中数超过该值则整日放弃
                   （说明当日全市场处于普跌/普涨，多数"企稳"是接刀）。
                   实证（2026-07~09 回放 T+5）:
                     冷清日(<10)  +0.91%  胜率 49.2%  ← 优质
                     中性(10~50)  -3.82%  33.9%
                     拥挤日(>50)  -9.14%  20.4%  ← 灾难
                   None = 不限（保持原行为）。
        """
        self.mode = mode
        self.min_score = min_score
        self.exclude_st = exclude_st
        self.exclude_suspended = exclude_suspended
        self.min_amount = float(min_amount)
        self.as_of = as_of
        self.max_daily_signals = max_daily_signals

        # 统计（便于排查"为什么没信号"）
        self.stats = {
            "total": 0, "no_data": 0, "st": 0, "suspended": 0,
            "stale": 0, "low_amount": 0, "no_pattern": 0, "low_score": 0,
            "crowded": 0, "hit": 0,
        }

    def _ensure_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """确保有 MA 列"""
        if "ma20" not in df.columns or "ma60" not in df.columns:
            from core.analysis.indicators import sma
            if "ma20" not in df.columns:
                df = df.copy()
                df["ma20"] = sma(df["close"], 20)
            if "ma60" not in df.columns:
                df["ma60"] = sma(df["close"], 60)
        return df

    def screen_one(self, symbol: str, name: str, df: pd.DataFrame) -> Optional[ScreeningResult]:
        """筛选单只股票"""
        self.stats["total"] += 1

        if df is None or len(df) == 0:
            self.stats["no_data"] += 1
            return None

        # ---- 可执行性过滤（在形态判定之前，省算力）----
        if self.exclude_st and is_st_name(name):
            self.stats["st"] += 1
            return None

        latest = df.iloc[-1]

        if self.as_of is not None:
            # 日期优先取 date 列；DataFrame 的 index 通常是 RangeIndex，
            # 拿 index[-1] 当日期会把 69 当成 1970-01-01，导致信号被全部误判为陈旧。
            if "date" in df.columns:
                last_date = pd.Timestamp(df["date"].iloc[-1]).date()
            else:
                last_date = pd.Timestamp(df.index[-1]).date()
            if last_date != pd.Timestamp(self.as_of).date():
                self.stats["stale"] += 1
                return None

        if self.exclude_suspended and is_suspended(latest):
            self.stats["suspended"] += 1
            return None

        if self.min_amount > 0:
            amt = latest.get("amount", 0)
            amt = 0.0 if amt is None or pd.isna(amt) else float(amt)
            if amt < self.min_amount:
                self.stats["low_amount"] += 1
                return None

        # ---- 形态判定 ----
        df = self._ensure_indicators(df)
        pattern = detect_hoshi_pattern(df, mode=self.mode)

        if pattern is None:
            self.stats["no_pattern"] += 1
            return None

        if pattern["score"] < self.min_score:
            self.stats["low_score"] += 1
            return None

        self.stats["hit"] += 1
        latest = df.iloc[-1]
        signals = [
            f"中期多头 ({pattern['trend']})",
            f"连跌{len(pattern['drop_days'])}日 ({pattern['total_drop']})",
        ]

        if pattern["mode"] == "stabilization":
            signals.append("企稳信号 (锤子线/十字星)")
        else:
            signals.append("企稳+确认上涨")

        # 涨跌幅安全取值（NaN → 0.0，不要裸 float(nan)）
        raw_pct = latest.get("change_pct", 0)
        if raw_pct is None or pd.isna(raw_pct):
            raw_pct = _resolve_change_pct(df, -1)
        pct = 0.0 if raw_pct is None or pd.isna(raw_pct) else float(raw_pct)

        price = latest.get("close", 0.0)
        price = 0.0 if price is None or pd.isna(price) else float(price)

        return ScreeningResult(
            code=symbol,
            name=name,
            score=pattern["score"],
            signals=signals,
            price=price,
            pct_change=pct,
        )

    def screen_batch(
        self,
        df_dict: dict,
        name_map: dict = None,
        top_n: int = 50,
    ) -> list[ScreeningResult]:
        """批量筛选"""
        if name_map is None:
            name_map = {}

        results = []
        total = len(df_dict)

        for i, (symbol, df) in enumerate(df_dict.items()):
            name = name_map.get(symbol, "")
            result = self.screen_one(symbol, name, df)
            if result:
                results.append(result)

            if (i + 1) % 500 == 0:
                logger.info(f"Hoshi screening: {i+1}/{total}, hits: {len(results)}")

        results.sort(key=lambda x: x.score, reverse=True)

        # 每日拥挤度门控：初步命中数超过上限 → 当日整日放弃。
        # （在 screen_batch 层实现，因为"当日拥挤度"是跨股票的整体统计，
        #   单只股票 screen_one 时无法知道当日全市场会命中多少只。）
        if self.max_daily_signals is not None and len(results) > self.max_daily_signals:
            self.stats["crowded"] = len(results)
            logger.info(
                f"Hoshi daily-crowding gate: {len(results)} hits > "
                f"{self.max_daily_signals} → 整日放弃（市场普跌，避免接刀）"
            )
            return []

        logger.info(f"Hoshi complete: {len(results)} hits from {total} stocks")
        return results[:top_n]


# ---------------------------------------------------------------------------
# 便捷: 在 TdxDB 上直接运行 Hoshi 扫描
# ---------------------------------------------------------------------------

def run_hoshi_on_tdx(
    db_path: str = "data/tdx.duckdb",
    mode: str = "confirmation",
    top_n: int = 30,
    days: int = 120,
    min_score: float = 5.0,
    min_amount: float = 0.0,
    as_of=None,
    exclude_st: bool = True,
    max_daily_signals: int = None,
) -> list[ScreeningResult]:
    """在通达信 DuckDB 上运行 Hoshi 策略全市场扫描

    Args:
        db_path: DuckDB 路径
        mode: 'stabilization' 或 'confirmation'
        top_n: 返回前 N 只
        days: 加载最近 N 天数据
        min_score: 最低评分
        min_amount: 最低当日成交额（元）
        as_of: 信号截止日。None = 用库内最新交易日。
               指定后只加载 date <= as_of 的数据，且只接受最新一根 == as_of 的信号，
               避免拿旧数据冒充"今日信号"。
        exclude_st: 剔除 ST / 退市

    Returns:
        ScreeningResult 列表
    """
    from core.data.duckdb_source import TdxDB

    tdx = TdxDB(db_path)
    try:
        if as_of is None:
            row = tdx.conn.execute(
                "SELECT MAX(date) FROM raw_kline_daily k "
                "JOIN raw_symbol_class c ON c.symbol = k.symbol AND c.class = 'stock'"
            ).fetchone()
            as_of = row[0] if row and row[0] else None

        symbols = tdx.get_all_stock_symbols()
        name_map = tdx.get_symbol_name_map()

        logger.info(
            f"Loading {len(symbols)} stocks for Hoshi screening "
            f"(mode={mode}, as_of={as_of})..."
        )
        df_dict = tdx.batch_load_daily(
            symbols=symbols, days=days, fq="bfq",
            end_date=str(as_of) if as_of else None,
        )

        screener = HoshiScreener(
            mode=mode, min_score=min_score, exclude_st=exclude_st,
            min_amount=min_amount, as_of=as_of,
            max_daily_signals=max_daily_signals,
        )
        results = screener.screen_batch(df_dict, name_map, top_n=top_n)
        logger.info(f"screener stats: {screener.stats}")
        return results
    finally:
        tdx.close()


def print_hoshi_results(results: list[ScreeningResult]):
    """格式化打印 Hoshi 结果"""
    print(f"\n{'='*80}")
    print(f"  Hoshi 策略筛选结果 ({len(results)} 只)")
    print(f"{'='*80}")
    print(f"{'#':>3}  {'代码':<10} {'名称':<10} {'得分':>5} {'价格':>8} {'涨跌%':>7}  信号")
    print(f"{'-'*80}")

    for i, r in enumerate(results, 1):
        code_display = r.code[2:] if len(r.code) > 2 and r.code[:2] in ("sh", "sz", "bj") else r.code
        signals_str = ", ".join(r.signals[:3])
        print(
            f"{i:>3}  {code_display:<10} {r.name:<10} {r.score:>5.1f} "
            f"{r.price:>8.2f} {r.pct_change:>+7.2f}  {signals_str}"
        )

    print(f"{'='*80}")
