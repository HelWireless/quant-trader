# -*- coding: utf-8 -*-
"""双系统模拟交易 —— 系统 A：策略引擎。

时序契约（很重要，写错会让出场整体错位）：

    before_open(T)   用 pos['hold_day'] 推出「T 日将是第几天」= hold_day + 1
                     用 T-1 的信号生成买入委托
    after_close(T)   消费 B 的回报：成交则建仓 / 平仓
    end_of_day(T)    用 T 日行情更新所有【仍在持仓】的状态，并把 hold_day += 1

    建仓时 hold_day = 0；买入日 end_of_day 后 = 1（即已持有 1 天）。

铁律：**买入信号只用 T-1 及之前的数据**。
T 日的价格只用于「收盘后更新持仓状态」（峰值/破位），用于 T+1 的挂单 —— 这与真实交易一致。
"""
from hoshi_cplus.config import (MAX_POSITION_R, MAX_SLOTS, LOT_SIZE, HEALTH_N,
                                HEALTH_THRESH, PROFIT_ARM_PCT, PROFIT_TRAIL_PCT,
                                PROFIT_ARM_PCT_LATE, PROFIT_TRAIL_PCT_LATE,
                                LOSS_ARM_PCT, LOSS_REBOUND_PCT, LOSS_START_DAY,
                                DEADLINE_DAY, MAX_HOLD, COMMISSION_RATE,
                                COMMISSION_MIN, STAMP_TAX_RATE, TRANSFER_FEE_RATE,
                                get_preset)
from hoshi_cplus.gates import breadth_ok, breadth_value

from .protocol import (OrderRequest, COND_STOP, COND_ARM_TRAIL, COND_REBOUND,
                       COND_OPEN_SELL)


def sell_fee(amount, code):
    f = max(amount * COMMISSION_RATE, COMMISSION_MIN) + amount * STAMP_TAX_RATE
    if str(code).startswith('6'):
        f += amount * TRANSFER_FEE_RATE
    return f


class StrategySystem(object):
    def __init__(self, prepared, code_bars, names, preset='cplus',
                 capital=300000.0, verbose=False):
        self.dates, self.sig_by_date, self.n_above, self.n_valid, self.idx_of = prepared
        self.code_bars = code_bars
        self.names = names
        self.preset = get_preset(preset)
        self.init_capital = capital
        self.cash = capital
        self.positions = {}
        self.closed = []
        self.trade_log = []
        self.signal_log = []
        self.verbose = verbose
        self._di = {d: i for i, d in enumerate(self.dates)}
        self._pending_mode = {}

    # ------------------------------------------------------------ 账务
    def equity_cost(self):
        """权益（成本口径，用于仓位计算，与回测一致）。"""
        return self.cash + sum(p['cost'] for p in self.positions.values())

    # ------------------------------------------------------------ T 日盘前
    def before_open(self, today):
        di = self._di.get(today)
        if di is None or di == 0:
            return []
        prev = self.dates[di - 1]            # 仅供估算股数（A 看不到 T 日开盘价）

        orders = []
        # ---- 1. 出场条件单 ----
        for code, pos in self.positions.items():
            hd = pos['hold_day'] + 1          # T 日将是第几天
            od = self._build_exit_order(today, code, pos, hd)
            if od is not None:
                orders.append(od)

        # ---- 2. 买入 ----
        # 关键：sig_by_date[D] 的定义就是「以 D 为执行日、用截止 D-1 数据算出的信号」
        #（detect_signal 用 bars[:k]，不含当天）。所以 T 日该查 sig_by_date[T]，
        # 查 T-1 会让所有进出场整体晚一天。广度同理用 n_above[di]。
        # 当日已发出卖出委托的持仓会腾出位置（回测里卖出是当天确定成交的）
        n_selling = len([o for o in orders if o.kind == 'SELL'])
        if (len(self.positions) - n_selling) < MAX_SLOTS \
                and breadth_ok(self.n_above[di], self.n_valid[di]):
            avail = MAX_SLOTS - (len(self.positions) - n_selling)
            cands = sorted([x for x in self.sig_by_date.get(today, ())
                            if x[0] >= self.preset.min_score
                            and x[1] not in self.positions],
                           key=lambda x: -x[0])
            recent = self.closed[-HEALTH_N:]
            health = (sum(recent) / len(recent)) if recent else None
            use_s4 = health is not None and health < HEALTH_THRESH

            bought = 0
            reserved = 0.0
            for score, code in cands:
                if bought >= avail:
                    break
                if self.idx_of[code].get(today) is None:
                    continue                  # 今日停牌
                kprev = self.idx_of[code].get(prev)
                if kprev is None:
                    continue
                ref = self.code_bars[code][kprev].close
                if ref <= 0:
                    continue
                cash_cap = self.cash - reserved
                if cash_cap <= 0:
                    break
                budget = min(self.equity_cost() * MAX_POSITION_R, cash_cap)
                if budget < ref * LOT_SIZE:
                    continue
                reserved += budget
                orders.append(OrderRequest(date=today, kind='BUY', code=code,
                                           shares=0, reason='score=%.1f' % score,
                                           ref_price=ref, budget=budget,
                                           available_cash=cash_cap))
                self._pending_mode[code] = 'S4' if use_s4 else 'S3'
                bought += 1

        self.signal_log.append(dict(
            date=today, ref_prev=prev,
            breadth=breadth_value(self.n_above[di], self.n_valid[di]),
            n_pos=len(self.positions), n_orders=len(orders)))
        return orders

    def _build_exit_order(self, today, code, pos, hd):
        """按持有天数生成 T 日的条件单。"""
        entry = pos['entry']
        p = self.preset
        base = dict(date=today, kind='SELL', code=code, shares=pos['shares'])

        # 已武装 → 移动止盈（任何一天都优先）
        if pos['armed']:
            return OrderRequest(cond_kind=COND_ARM_TRAIL, armed=True,
                                arm_price=entry * (1 + PROFIT_ARM_PCT / 100.0),
                                trail_pct=pos['trail_pct'], peak=pos['peak'],
                                reason='止盈跟踪', **base)

        # 超时 / 兜底
        if hd >= MAX_HOLD:
            return OrderRequest(cond_kind=COND_OPEN_SELL, reason='兜底强平', **base)
        if hd == DEADLINE_DAY:
            return OrderRequest(cond_kind=COND_OPEN_SELL, reason='超时平仓', **base)

        hard = entry * (1 + p.loss_hard_pct / 100.0)
        loss_arm = entry * (1 + LOSS_ARM_PCT / 100.0)

        # ---- 回退条件（对齐回测 _step_exit 的判定顺序）----
        if hd < p.loss_hard_start_day:
            fb_kind = None                       # 前 4 天裸奔
        elif hd < LOSS_START_DAY:
            fb_kind = COND_STOP                  # 硬止损窗口（第 5~14 天）
        else:
            fb_kind = COND_REBOUND               # 第 15 天起：反弹卖出 / 硬止损

        # ---- 武装机会（对齐回测）----
        #   S4：每天都能武装，阈值 +5.2% / 峰值回落 1.2%
        #   S3：仅第 14 天（+5.2%/1.2%）与第 15 天（+3.2%/1.0%）
        can_arm, arm_price, trail = False, None, None
        if pos['mode'] == 'S4':
            can_arm = True
            arm_price, trail = entry * (1 + PROFIT_ARM_PCT / 100.0), PROFIT_TRAIL_PCT
        elif hd == 14:
            can_arm = True
            arm_price, trail = entry * (1 + PROFIT_ARM_PCT / 100.0), PROFIT_TRAIL_PCT
        elif hd == 15:
            can_arm = True
            arm_price, trail = (entry * (1 + PROFIT_ARM_PCT_LATE / 100.0),
                                PROFIT_TRAIL_PCT_LATE)

        if can_arm:
            return OrderRequest(cond_kind=COND_ARM_TRAIL, armed=False,
                                arm_price=arm_price, trail_pct=trail, peak=pos['peak'],
                                cond_price=hard, loss_arm=loss_arm,
                                rebound_pct=LOSS_REBOUND_PCT, trough=pos['trough'],
                                fallback_kind=fb_kind,
                                reason='武装尝试(第%d天)' % hd, **base)

        if fb_kind == COND_STOP:
            return OrderRequest(cond_kind=COND_STOP, cond_price=hard,
                                reason='硬止损', **base)
        if fb_kind == COND_REBOUND:
            return OrderRequest(cond_kind=COND_REBOUND, loss_arm=loss_arm,
                                rebound_pct=LOSS_REBOUND_PCT, cond_price=hard,
                                trough=pos['trough'], reason='反弹卖出/硬止损', **base)
        return None

    # ------------------------------------------------------------ T 日收盘后
    def after_close(self, reports):
        """消费 B 的回报：只做建仓 / 平仓。"""
        for r in reports:
            code = r.code
            if r.kind == 'BUY' and r.status == 'FILLED':
                gross = r.shares * r.fill_price
                cost = gross + r.fee
                self.cash -= cost
                self.positions[code] = dict(
                    code=code, entry=r.fill_price, shares=r.shares, cost=cost,
                    hold_day=0, peak=r.fill_price, armed=False,
                    trail_pct=PROFIT_TRAIL_PCT, loss_armed=False,
                    trough=r.fill_price,
                    mode=self._pending_mode.get(code, 'S3'), buy_date=r.date)
                self.trade_log.append(dict(
                    date=r.date, code=code, name=self.names.get(code, ''),
                    side='BUY', price=r.fill_price, shares=r.shares, amount=gross,
                    fee=r.fee, deviation=r.deviation, reason=r.reason, pnl='', ret=''))

            elif r.kind == 'SELL' and r.status == 'FILLED':
                pos = self.positions.pop(code, None)
                if pos is None:
                    continue
                gross = r.shares * r.fill_price
                proceeds = gross - r.fee
                self.cash += proceeds
                pnl = proceeds - pos['cost']
                ret = pnl / pos['cost'] * 100.0 if pos['cost'] > 0 else 0.0
                self.closed.append(ret)
                self.trade_log.append(dict(
                    date=r.date, code=code, name=self.names.get(code, ''),
                    side='SELL', price=r.fill_price, shares=r.shares, amount=gross,
                    fee=r.fee, deviation=r.deviation, reason=r.reason,
                    pnl=round(pnl, 2), ret=round(ret, 4)))
            # MISSED：持仓保留 → 次日 A 自然重新生成同样的条件单
            # （这就是「把漏卖反馈给策略、代入继续计算」）

    def end_of_day(self, today):
        """用 T 日行情更新【仍在持仓】的状态，并把 hold_day 推进 1。

        注意：这与「买入信号只用 T-1」不冲突 ——
        这里只是把 T 日已经确定的价格记下来，用于 T+1 的挂单，与真实交易一致。
        """
        for code, pos in self.positions.items():
            k = self.idx_of[code].get(today)
            if k is None:
                continue                     # 停牌：不推进持有天数
            bar = self.code_bars[code][k]
            hi, lo = bar.high, bar.low
            entry = pos['entry']
            hd = pos['hold_day'] + 1         # T 日实际是第几天

            pos['peak'] = max(pos['peak'], hi) if (
                pos['armed'] or pos['mode'] == 'S4' or hd >= 14) else pos['peak']
            if not pos['armed']:
                if pos['mode'] == 'S4' and hi >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                    pos['armed'] = True
                    pos['trail_pct'] = PROFIT_TRAIL_PCT
                    pos['peak'] = hi
                elif pos['mode'] == 'S3' and hd == 14 \
                        and hi >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                    pos['armed'] = True
                    pos['trail_pct'] = PROFIT_TRAIL_PCT
                    pos['peak'] = hi
                elif pos['mode'] == 'S3' and hd == 15 \
                        and hi >= entry * (1 + PROFIT_ARM_PCT_LATE / 100.0):
                    pos['armed'] = True
                    pos['trail_pct'] = PROFIT_TRAIL_PCT_LATE
                    pos['peak'] = hi

            # 破位低点：回测里这段只在 hd >= LOSS_START_DAY 且未武装时才记录
            if hd >= LOSS_START_DAY and not pos['armed']:
                if lo <= entry * (1 + LOSS_ARM_PCT / 100.0):
                    pos['loss_armed'] = True
                    pos['trough'] = min(pos['trough'], lo)

            pos['hold_day'] = hd

    # ------------------------------------------------------------ 收尾
    def force_close(self, today):
        for code, pos in list(self.positions.items()):
            k = self.idx_of[code].get(today)
            if k is None:
                cand = [i for i, b in enumerate(self.code_bars[code]) if b.date <= today]
                if not cand:
                    continue
                k = cand[-1]
            bar = self.code_bars[code][k]
            gross = pos['shares'] * bar.close
            fee = sell_fee(gross, code)
            self.cash += gross - fee
            pnl = (gross - fee) - pos['cost']
            ret = pnl / pos['cost'] * 100.0 if pos['cost'] > 0 else 0.0
            self.closed.append(ret)
            self.trade_log.append(dict(
                date=today, code=code, name=self.names.get(code, ''),
                side='SELL', price=bar.close, shares=pos['shares'], amount=gross,
                fee=fee, deviation='FORCE_CLOSE', reason='期末强平',
                pnl=round(pnl, 2), ret=round(ret, 4)))
            del self.positions[code]
