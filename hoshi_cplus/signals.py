# -*- coding: utf-8 -*-
"""K 线形态与入场信号（hoshi-cplus）。

规格来源：docs/Hoshi_终局报告_2026-09-13.md §3.3
"""
from .config import (MA_FAST, MA_SLOW, DROP_THRESH, MIN_BARS)


# ---------------------------------------------------------------- 形态基元
def body_size(o, c):
    return abs(c - o)


def upper_shadow(o, h, c):
    return h - max(o, c)


def lower_shadow(o, c, l):
    return min(o, c) - l


def candle_range(h, l):
    return h - l


def is_hammer(o, h, l, c):
    """锤子线：小实体 + 长下影 + 短上影。"""
    rng = candle_range(h, l)
    if rng <= 0 or c <= 0:
        return False
    body = body_size(o, c)
    low_sh = lower_shadow(o, c, l)
    up_sh = upper_shadow(o, h, c)
    if body / rng > 0.3:
        return False
    if body > 0 and low_sh < body * 1.5:
        return False
    if body == 0 and low_sh < rng * 0.4:
        return False
    if up_sh > rng * 0.5:
        return False
    return True


def is_doji(o, h, l, c):
    """十字星：实体极小。"""
    rng = candle_range(h, l)
    if rng <= 0 or c <= 0:
        return False
    return body_size(o, c) / rng < 0.15


def is_stabilization(o, h, l, c):
    return is_hammer(o, h, l, c) or is_doji(o, h, l, c)


# ---------------------------------------------------------------- 评分
def calc_score(total_drop, o1, h1, l1, c1, confirm_chg):
    """Hoshi 评分（0~10，1 位小数）。

    total_drop  : 连跌两日涨幅之和（负数）
    o1,h1,l1,c1: 企稳日（D-2）的 OHLC
    confirm_chg : 确认日（D-1）涨幅百分比
    """
    score = 3.0
    d = abs(total_drop)
    if 10 <= d <= 25:
        score += 2.0
    elif d > 25:
        score += 1.5
    elif d >= 5:
        score += 1.0

    if is_hammer(o1, h1, l1, c1):
        score += 2.5
    elif is_doji(o1, h1, l1, c1):
        score += 2.0
    else:
        score += 1.0

    ls = lower_shadow(o1, c1, l1)
    rng = candle_range(h1, l1)
    if rng > 0 and ls / rng > 0.5:
        score += 1.0

    if confirm_chg > 5:
        score += 1.5
    elif confirm_chg > 2:
        score += 1.0

    return round(min(score, 10.0), 1)


# ---------------------------------------------------------------- 信号
def detect_signal(opens, highs, lows, closes):
    """检测 Hoshi confirmation 信号。

    传入序列是【截止信号日 D 的昨天】的 OHLC（即已去掉 D 当天）。
    索引约定：closes[-1] = D-1（确认日）、[-2] = D-2（企稳日）、[-3] = D-3、[-4] = D-4。

    返回 score（float）或 None（无信号）。
    """
    n = len(closes)
    if n < MIN_BARS - 1:          # MIN_BARS=66 -> 截止昨天至少 65 根
        return None
    ma20 = sum(closes[-MA_FAST:]) / float(MA_FAST)
    ma60 = sum(closes[-MA_SLOW:]) / float(MA_SLOW)
    if ma60 <= 0 or ma20 <= ma60:
        return None

    def chg(i):
        prev = closes[i - 1]
        if prev <= 0:
            return 0.0
        return (closes[i] - prev) / prev * 100.0

    chg_d3 = chg(n - 4)
    chg_d2 = chg(n - 3)
    chg_d1 = chg(n - 2)
    chg_d0 = chg(n - 1)

    # 连跌两天
    drop_days = []
    if chg_d3 < DROP_THRESH:
        drop_days.append(chg_d3)
    if chg_d2 < DROP_THRESH:
        drop_days.append(chg_d2)
    if len(drop_days) < 2:
        return None
    total_drop = sum(drop_days)

    # 企稳日 = D-2
    i_d1 = n - 2
    o1, h1, l1, c1 = opens[i_d1], highs[i_d1], lows[i_d1], closes[i_d1]
    stabilization = is_stabilization(o1, h1, l1, c1) or (
        -2 <= chg_d1 <= 5 and c1 > 0 and body_size(o1, c1) / c1 < 0.03
    )
    if not stabilization:
        return None

    # 确认日必须收阳
    if chg_d0 <= 0:
        return None

    return calc_score(total_drop, o1, h1, l1, c1, chg_d0)
