# -*- coding: utf-8 -*-
"""门控：市场广度 + R3 回撤停手（hoshi-cplus）。

规格来源：docs/Hoshi_终局报告_2026-09-13.md §3.2 / §3.6
"""
from .config import (BREADTH_THRESH, BREADTH_MIN_SAMPLE,
                     R3_DD_THRESH, R3_COOLDOWNS, R3_ESCALATE_WINDOW)


def breadth_ok(n_above, n_valid, thresh=BREADTH_THRESH):
    """市场广度门控：当日收盘价站上自身 MA60 的标的占比。

    n_above : 昨日收盘 > 自身 MA60 的标的数
    n_valid : 有效样本数（该标的至少 66 根 K 线、且截止昨日 >= 60 根）
    """
    if n_valid < BREADTH_MIN_SAMPLE:
        return False
    return (n_above * 100.0 / n_valid) >= thresh


def breadth_value(n_above, n_valid):
    if n_valid < BREADTH_MIN_SAMPLE:
        return None
    return n_above * 100.0 / n_valid


class R3Gate(object):
    """R3 权益回撤门控。

    用【已完成交易】的复利链计算回撤（不含现金与未平仓持仓），
    回撤超过阈值即停手，冷却期内不开新仓。

    注意：这是**顺周期**风控——超跌反弹策略在权益回撤后恰是信号最肥的时段，
    停手等于每次在最优点强制离场。实测 90/90 窗口会触发、平均每窗停手 5.9 次，
    因此 **hoshi-cplus 默认关闭 R3**。
    """

    def __init__(self, dd_thresh=R3_DD_THRESH, cooldowns=None,
                 esc_window=R3_ESCALATE_WINDOW):
        self.dd_thresh = dd_thresh
        self.cooldowns = list(cooldowns or R3_COOLDOWNS)
        self.esc_window = esc_window
        self.stop_since = None
        self.peak_offset = 0
        self.last_recover = None
        self.level = 0

    def __call__(self, completed_rets, cur_date):
        """completed_rets: 已完成交易的收益率列表（百分比，按时间顺序）。"""
        if not completed_rets:
            return True
        if self.stop_since is not None and cur_date is not None:
            if (cur_date - self.stop_since).days < self.cooldowns[self.level]:
                return False
            self.peak_offset = len(completed_rets)
            self.stop_since = None
            self.last_recover = cur_date
            return True

        eq = 1.0
        for t in completed_rets[:self.peak_offset]:
            eq *= (1 + t / 100.0)
        peak = eq
        for t in completed_rets[self.peak_offset:]:
            eq *= (1 + t / 100.0)
            peak = max(peak, eq)
        dd = (eq - peak) / peak * 100.0 if peak > 0 else 0.0

        if dd < -self.dd_thresh:
            if self.last_recover is not None and cur_date is not None:
                if (cur_date - self.last_recover).days < self.esc_window:
                    self.level = min(self.level + 1, len(self.cooldowns) - 1)
                else:
                    self.level = 0
            self.stop_since = cur_date
            return False
        return True
