# -*- coding: utf-8 -*-
"""回测引擎（hoshi-cplus）。

规格来源：docs/Hoshi_终局报告_2026-09-13.md §3.2 / §3.4 / §3.5

该实现与 hoshi_backtest_exp5.py 做过锚点对拍，三个窗口的收益与笔数**逐位一致**
（见 docs/Hoshi_二次验证_180窗_2026-09-13.md §1.2）。
"""
from datetime import date

from .config import (TOTAL_CAPITAL, MAX_POSITION_R, MAX_SLOTS, LOT_SIZE,
                     HEALTH_N, HEALTH_THRESH, COUNT_ENTRY_DAY, ENFORCE_T1,
                     COMMISSION_RATE, COMMISSION_MIN, STAMP_TAX_RATE,
                     TRANSFER_FEE_RATE, get_preset)
from .exits import new_position, step_exit
from .gates import R3Gate, breadth_ok


# ---------------------------------------------------------------- 费用
def buy_fee(amount):
    return max(amount * COMMISSION_RATE, COMMISSION_MIN)


def sell_fee(amount, code):
    fee = max(amount * COMMISSION_RATE, COMMISSION_MIN) + amount * STAMP_TAX_RATE
    if str(code).startswith('6'):      # 沪市过户费
        fee += amount * TRANSFER_FEE_RATE
    return fee


def _to_date(s):
    if isinstance(s, date):
        return s
    return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


# ---------------------------------------------------------------- 主回测
def run_backtest(prepared, preset='cplus', start=None, end=None,
                 capital=TOTAL_CAPITAL, code_bars=None):
    """跑一个窗口。

    prepared : data.precompute() 的返回值 (dates, sig_by_date, n_above, n_valid, idx_of)
    preset   : 方案名/别名，见 config.PRESETS
    code_bars: load_data() 的 code_bars（用于取 bar 与期末强平）
    """
    if code_bars is None:
        raise ValueError('需要传入 code_bars')
    dates, sig_by_date, n_above, n_valid, idx_of = prepared
    p = get_preset(preset)

    sd = _to_date(start) if start else dates[0]
    ed = _to_date(end) if end else dates[-1]
    window_dates = [d for d in dates if sd <= d <= ed]
    if not window_dates:
        return None

    didx = {d: i for i, d in enumerate(dates)}
    gate = R3Gate() if p.use_r3_gate else None

    cash = capital
    positions = {}
    closed = []                 # 每笔已完成交易的收益率(%)
    trades = []                 # 明细
    buys = []
    last_bar = {}               # code -> 窗口内最后一次见到的 bar

    for today in window_dates:
        # ---------- 1. 出场 ----------
        for code in list(positions.keys()):
            k = idx_of[code].get(today)
            if k is None:
                continue                      # 停牌：不推进 hold_day
            b = code_bars[code][k]
            last_bar[code] = b
            pos = positions[code]
            allow_sell = (not ENFORCE_T1) or (pos['hold_day'] >= 1)
            res = step_exit(pos, b.high, b.low, b.open, b.close, allow_sell,
                            p.loss_hard_start_day, p.loss_hard_pct)
            if res is None:
                continue
            sell_price, reason = res
            p_ = positions.pop(code)
            gross = p_['shares'] * sell_price
            fee = sell_fee(gross, code)
            proceeds = gross - fee
            pnl = proceeds - p_['cost']
            ret = pnl / p_['cost'] * 100.0 if p_['cost'] > 0 else 0.0
            cash += proceeds
            closed.append(ret)
            trades.append(dict(date=today, code=code, side='sell',
                               price=sell_price, shares=p_['shares'],
                               pnl=pnl, ret=ret, reason=reason))

        # ---------- 2. 门控 ----------
        gate_open = gate(closed, today) if gate is not None else True

        # ---------- 3. 广度 + 买入 ----------
        if gate_open and len(positions) < MAX_SLOTS:
            di = didx[today]
            if breadth_ok(n_above[di], n_valid[di]):
                sigs = [x for x in sig_by_date.get(today, ())
                        if x[0] >= p.min_score and x[1] not in positions]
                sigs.sort(key=lambda x: -x[0])        # 稳定排序：同分按标的代码顺序
                recent = closed[-HEALTH_N:]
                health = (sum(recent) / len(recent)) if recent else None
                use_s4 = health is not None and health < HEALTH_THRESH

                for score, code in sigs:
                    if len(positions) >= MAX_SLOTS:
                        break
                    if code in positions:
                        continue
                    k = idx_of[code].get(today)
                    if k is None:
                        continue
                    b = code_bars[code][k]
                    buy_price = b.open
                    if buy_price <= 0:
                        continue
                    pos_cost = sum(q['cost'] for q in positions.values())
                    equity = cash + pos_cost
                    budget = equity * MAX_POSITION_R
                    shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
                    if shares <= 0:
                        continue
                    gross = shares * buy_price
                    cost = gross + buy_fee(gross)
                    if cost > cash:
                        shares = int(cash // buy_price // LOT_SIZE) * LOT_SIZE
                        if shares <= 0:
                            continue
                        gross = shares * buy_price
                        cost = gross + buy_fee(gross)
                        if cost > cash:
                            continue
                    cash -= cost
                    positions[code] = new_position(
                        code, buy_price, shares, cost,
                        mode='S4' if use_s4 else 'S3', score=score)
                    buys.append(dict(date=today, code=code, score=score,
                                     price=buy_price, shares=shares, cost=cost))
                    trades.append(dict(date=today, code=code, side='buy',
                                       price=buy_price, shares=shares, cost=cost,
                                       reason=''))
                    # 买入当天用当日 OHLC 推进一次出场状态（关键！漏了会让所有出场晚一天）
                    if COUNT_ENTRY_DAY:
                        step_exit(positions[code], b.high, b.low, b.open, b.close,
                                  False, p.loss_hard_start_day, p.loss_hard_pct)

    # ---------- 4. 期末强平：用窗口内最后一根 bar ----------
    for code, pos in list(positions.items()):
        b = last_bar.get(code)
        if b is None:
            cand = [x for x in code_bars[code] if x.date <= ed]
            if not cand:
                continue
            b = cand[-1]
        gross = pos['shares'] * b.close
        fee = sell_fee(gross, code)
        cash += gross - fee
        pnl = (gross - fee) - pos['cost']
        ret = pnl / pos['cost'] * 100.0 if pos['cost'] > 0 else 0.0
        closed.append(ret)
        trades.append(dict(date=b.date, code=code, side='sell', price=b.close,
                           shares=pos['shares'], pnl=pnl, ret=ret, reason='期末强平'))

    return dict(
        final_capital=cash,
        ret=(cash - capital) / capital * 100.0,
        n_trades=len(closed),
        n_buys=len(buys),
        closed=closed,
        trades=trades,
        buys=buys,
        preset=p.key,
        start=sd, end=ed,
    )


# ---------------------------------------------------------------- 便捷入口
class Strategy(object):
    """把准备好的数据与一个方案绑在一起，便于反复跑多个窗口。"""

    def __init__(self, data_dir, preset='cplus'):
        from .data import load_data, precompute
        self.preset = preset
        self.code_bars, self.names = load_data(data_dir)
        self.prepared = precompute(self.code_bars)

    def run(self, start, end, capital=TOTAL_CAPITAL):
        return run_backtest(self.prepared, preset=self.preset, start=start, end=end,
                            capital=capital, code_bars=self.code_bars)
