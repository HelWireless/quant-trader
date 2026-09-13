# -*- coding: utf-8 -*-
"""出场规则（hoshi-cplus）。

规格来源：docs/Hoshi_终局报告_2026-09-13.md §3.5

出场优先级（自上而下，命中即返回）：
  1. 止盈（已武装且峰值回落）
  2. 提前硬止损兜底（第 LOSS_HARD_START_DAY ~ 14 天）
  3. 反弹卖出式止损（第 15 天起）
  4. 超时平仓（第 25 天开盘）
  5. 兜底强平（第 40 天收盘）
"""
from .config import (PROFIT_ARM_PCT, PROFIT_TRAIL_PCT, PROFIT_ARM_PCT_LATE,
                     PROFIT_TRAIL_PCT_LATE, LOSS_ARM_PCT, LOSS_REBOUND_PCT,
                     LOSS_START_DAY, DEADLINE_DAY, MAX_HOLD)


def new_position(code, entry, shares, cost, mode='S3', score=0.0):
    """建仓时的持仓字典。"""
    return dict(
        code=code, entry=entry, shares=shares, cost=cost,
        hold_day=0, peak=entry, armed=False,
        trail_pct=PROFIT_TRAIL_PCT, loss_armed=False,
        trough=entry, mode=mode, score=score,
    )


def step_exit(pos, high, low, open_, close, allow_sell,
              loss_hard_start_day, loss_hard_pct):
    """推进一个持仓一天的出场判定。

    pos 会被就地更新（hold_day / armed / peak / loss_armed / trough）。
    返回 (卖价, 原因) 或 None（继续持有）。
    """
    pos['hold_day'] += 1
    hd = pos['hold_day']
    entry = pos['entry']
    mode = pos['mode']
    armed = pos['armed']
    trail_pct = pos['trail_pct']

    # ---- 止盈武装 ----
    if mode == 'S3':
        if hd == 14 and not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                armed = True
                trail_pct = PROFIT_TRAIL_PCT
                pos['peak'] = high
            else:
                pos['peak'] = max(pos['peak'], high)
        elif hd == 15 and not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT_LATE / 100.0):
                armed = True
                trail_pct = PROFIT_TRAIL_PCT_LATE
            pos['peak'] = max(pos['peak'], high)
        elif hd > 15:
            pos['peak'] = max(pos['peak'], high)
    else:  # S4
        if not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                armed = True
                trail_pct = PROFIT_TRAIL_PCT
                pos['peak'] = high
            else:
                pos['peak'] = max(pos['peak'], high)

    pos['armed'] = armed
    pos['trail_pct'] = trail_pct

    # ---- 1. 止盈 ----
    if armed:
        pos['peak'] = max(pos['peak'], high)
        trail_price = pos['peak'] * (1 - trail_pct / 100.0)
        if low <= trail_price:
            return (trail_price, '止盈') if allow_sell else None

    # ---- 2. 提前硬止损兜底 ----
    # 仅在 [loss_hard_start_day, LOSS_START_DAY) 窗口内、且未武装止盈时生效
    if loss_hard_start_day < LOSS_START_DAY and not armed:
        if loss_hard_start_day <= hd < LOSS_START_DAY:
            hard_price = entry * (1 + loss_hard_pct / 100.0)
            if low <= hard_price:
                return (hard_price, '止损(硬)') if allow_sell else None

    # ---- 3. 反弹卖出式止损 ----
    if hd >= LOSS_START_DAY and not armed:
        if not pos['loss_armed'] and low <= entry * (1 + LOSS_ARM_PCT / 100.0):
            pos['loss_armed'] = True
            pos['trough'] = low
        if pos['loss_armed']:
            pos['trough'] = min(pos['trough'], low)
            rebound = pos['trough'] * (1 + LOSS_REBOUND_PCT / 100.0)
            if high >= rebound:
                return (rebound, '止损(反弹)') if allow_sell else None
            if pos['trough'] <= entry * (1 + loss_hard_pct / 100.0):
                return (entry * (1 + loss_hard_pct / 100.0), '止损(硬)') if allow_sell else None

    # ---- 4. 超时 ----
    if not armed and hd == DEADLINE_DAY:
        return (open_, '超时') if allow_sell else None

    # ---- 5. 兜底强平 ----
    if hd >= MAX_HOLD:
        return (close, '强平') if allow_sell else None

    return None
