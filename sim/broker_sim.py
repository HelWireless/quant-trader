# -*- coding: utf-8 -*-
"""双系统模拟交易 —— 系统 B：模拟撮合（带执行偏差）。

铁律：**只使用 T 日的 OHLC**。它不知道策略逻辑，只执行 A 给的委托与条件单。

三类成交障碍，分开统计：
  1. 结构性：涨跌停封板买不进 / 卖不出（用真实股价判断）
  2. 随机偏差：20% 概率的滑点 / 侥幸 / 漏单
  3. 正常成交
"""
import random

from .protocol import (FillReport, COND_STOP, COND_ARM_TRAIL, COND_REBOUND,
                       COND_OPEN_SELL,
                       DEV_OK, DEV_SLIP_UP, DEV_LUCKY_LOW, DEV_BUY_MISSED,
                       DEV_LIMIT_UP_BLOCK, DEV_SLIP_DOWN, DEV_LUCKY_HIGH,
                       DEV_SELL_MISSED, DEV_LIMIT_DOWN_BLOCK)

# 随机偏差概率（总异常 20%）
P_SLIP_UP = 0.08          # 买入追高
P_LUCKY_LOW = 0.04        # 买在当日最低
P_BUY_MISSED = 0.08       # 买入失败
P_SLIP_DOWN = 0.08        # 卖出割肉
P_LUCKY_HIGH = 0.03       # 卖在当日最高
P_SELL_MISSED = 0.09      # 卖出漏单

FEE_RATE, FEE_MIN = 0.00025, 5.0
STAMP, TRANSFER = 0.0005, 0.00001


def limit_pct(code):
    """涨跌停幅度：创业板/科创板 20%，其余主板 10%。"""
    return 0.20 if code.startswith(('300', '301', '688', '689')) else 0.10


def _fee_buy(amount):
    return max(amount * FEE_RATE, FEE_MIN)


def _fee_sell(amount, code):
    f = max(amount * FEE_RATE, FEE_MIN) + amount * STAMP
    if code.startswith('6'):
        f += amount * TRANSFER
    return f


class BrokerSim(object):
    def __init__(self, code_bars, seed=20260913, biased=True, verbose=False):
        self.code_bars = code_bars
        self.rng = random.Random(seed)
        self.biased = biased          # False = 理想执行（对照组）
        self.verbose = verbose
        self.stats = {}               # deviation -> count
        self.idx_cache = {}

    def _bar(self, code, day):
        bars = self.code_bars.get(code)
        if not bars:
            return None, None
        m = self.idx_cache.get(code)
        if m is None:
            m = {b.date: i for i, b in enumerate(bars)}
            self.idx_cache[code] = m
        k = m.get(day)
        if k is None:
            return None, None
        prev_close = bars[k - 1].close if k > 0 else None
        return bars[k], prev_close

    # ------------------------------------------------------------ 条件单触发判定
    def _check_stop(self, od, bar):
        if od.cond_price and bar.low <= od.cond_price:
            return od.cond_price, '硬止损'
        return None, ''

    def _check_rebound(self, od, bar):
        trough = od.trough if od.trough is not None else bar.low
        armed = trough < od.loss_arm
        if not armed and bar.low <= od.loss_arm:
            armed = True
            trough = min(trough, bar.low)
        if armed:
            trough = min(trough, bar.low)
            rebound = trough * (1 + od.rebound_pct / 100.0)
            if bar.high >= rebound:
                return rebound, '反弹卖出'
            if od.cond_price and trough <= od.cond_price:
                return od.cond_price, '硬止损'
        return None, ''

    def _check_condition(self, od, bar, prev_close):
        """返回 (卖价, 原因) 或 (None, '')（未触发）。"""
        code = od.code
        # 结构性障碍：全天封跌停 → 卖不出
        if prev_close:
            ld = round(prev_close * (1 - limit_pct(code)), 2)
            if bar.high <= ld:
                return None, DEV_LIMIT_DOWN_BLOCK, '跌停封板，卖不出'

        if od.cond_kind == COND_OPEN_SELL:
            return bar.open, DEV_OK, od.reason

        if od.cond_kind == COND_STOP:
            p, r = self._check_stop(od, bar)
            return (p, DEV_OK, r) if p else (None, None, '')

        if od.cond_kind == COND_ARM_TRAIL:
            # 已武装：无条件跟踪止盈（回测里 armed 后不再看 arm_price，
            # 否则「不再创新高」就等于放弃跟踪，会被硬拖到超时）
            if od.armed:
                peak = max(od.peak or 0.0, bar.high)
                trail = peak * (1 - od.trail_pct / 100.0)
                if bar.low <= trail:
                    return trail, DEV_OK, '止盈'
                return None, None, ''
            if bar.high >= od.arm_price:
                # 武装当天 peak 直接取当日高点（对齐回测，不复用历史峰值）
                peak = bar.high
                trail = peak * (1 - od.trail_pct / 100.0)
                if bar.low <= trail:
                    return trail, DEV_OK, '止盈'
                return None, None, ''        # 当日刚武装、但未回落到位
            # 未武装 → 按 fallback 回退
            if od.fallback_kind == 'REBOUND':
                p, r = self._check_rebound(od, bar)
                return (p, DEV_OK, r) if p else (None, None, '')
            p, r = self._check_stop(od, bar)
            return (p, DEV_OK, r) if p else (None, None, '')

        if od.cond_kind == COND_REBOUND:
            p, r = self._check_rebound(od, bar)
            return (p, DEV_OK, r) if p else (None, None, '')

        return None, None, ''

    # ------------------------------------------------------------ 主入口
    def execute(self, orders, today):
        reports = []
        for od in orders:
            bar, prev_close = self._bar(od.code, today)
            if bar is None:
                # 当日停牌：委托无法执行
                reports.append(self._miss(od, today, DEV_BUY_MISSED if od.kind == 'BUY'
                                          else DEV_SELL_MISSED, '当日停牌'))
                continue
            market = dict(open=bar.open, high=bar.high, low=bar.low, close=bar.close)
            if od.kind == 'BUY':
                reports.append(self._do_buy(od, bar, prev_close, today, market))
            else:
                reports.append(self._do_sell(od, bar, prev_close, today, market))
        return reports

    def _miss(self, od, today, dev, note):
        self._bump(dev)
        return FillReport(date=today, code=od.code, kind=od.kind, status='MISSED',
                          deviation=dev, reason=od.reason, note=note)

    def _bump(self, dev):
        self.stats[dev] = self.stats.get(dev, 0) + 1

    # ------------------------------------------------------------ 买入
    def _do_buy(self, od, bar, prev_close, today, market):
        code = od.code
        # 结构性：全天封涨停 → 买不进
        if prev_close:
            lu = round(prev_close * (1 + limit_pct(code)), 2)
            if bar.low >= lu:
                return self._miss(od, today, DEV_LIMIT_UP_BLOCK, '涨停封板，买不进')

        dev = DEV_OK
        price = bar.open
        if self.biased:
            r = self.rng.random()
            if r < P_SLIP_UP:
                u = self.rng.uniform(0.003, 0.02)
                price = min(bar.open * (1 + u), bar.high)
                dev = DEV_SLIP_UP
            elif r < P_SLIP_UP + P_LUCKY_LOW:
                price = bar.low
                dev = DEV_LUCKY_LOW
            elif r < P_SLIP_UP + P_LUCKY_LOW + P_BUY_MISSED:
                return self._miss(od, today, DEV_BUY_MISSED, '委托未成交')

        if price <= 0:
            return self._miss(od, today, DEV_BUY_MISSED, '价格异常')
        # 股数按【实际成交价】重算 —— 对齐回测：A 只给金额预算，手数由成交价决定
        shares = od.shares
        if od.budget:
            cap = od.budget
            if od.available_cash:
                cap = min(cap, od.available_cash)
            shares = int(cap // price // 100) * 100
            if shares <= 0:
                return self._miss(od, today, DEV_BUY_MISSED, '资金不足')
        gross = shares * price
        fee = _fee_buy(gross)
        self._bump(dev)
        return FillReport(date=today, code=code, kind='BUY', status='FILLED',
                          fill_price=round(price, 3), shares=shares, fee=round(fee, 2),
                          deviation=dev, reason=od.reason, market=market,
                          note='基准开盘价 %.2f' % bar.open)

    # ------------------------------------------------------------ 卖出
    def _do_sell(self, od, bar, prev_close, today, market):
        trig, dev, note = self._check_condition(od, bar, prev_close)
        if trig is None:
            if dev == DEV_LIMIT_DOWN_BLOCK:
                return self._miss(od, today, DEV_LIMIT_DOWN_BLOCK, note)
            # 条件未触发：A 侧持仓继续保留（B 不出回报也意味着"没卖成"）
            return None

        price = trig
        out_dev = DEV_OK
        if self.biased:
            r = self.rng.random()
            if r < P_SLIP_DOWN:
                u = self.rng.uniform(0.003, 0.02)
                price = max(trig * (1 - u), bar.low)
                out_dev = DEV_SLIP_DOWN
            elif r < P_SLIP_DOWN + P_LUCKY_HIGH:
                price = bar.high
                out_dev = DEV_LUCKY_HIGH
            elif r < P_SLIP_DOWN + P_LUCKY_HIGH + P_SELL_MISSED:
                return self._miss(od, today, DEV_SELL_MISSED, '委托未成交')

        gross = od.shares * price
        fee = _fee_sell(gross, od.code)
        self._bump(out_dev)
        return FillReport(date=today, code=od.code, kind='SELL', status='FILLED',
                          fill_price=round(price, 3), shares=od.shares, fee=round(fee, 2),
                          deviation=out_dev, reason=note or od.reason, market=market,
                          note='触发价 %.2f' % trig)
