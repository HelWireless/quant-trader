# -*- coding: utf-8 -*-
"""
================================================================================
 Hoshi 策略 —— 独立重建实现（v2）
================================================================================
 本文件是**双盲重建**：实现时**只允许参照《Hoshi 终局报告_2026-09-13》第三节的规格**，
 不参考 hoshi_backtest_exp5.py 等任何现有策略代码。目的是检验报告规格是否自洽到
 "脱离原实现也能重建出同样结论"。

 规格来源：docs/Hoshi_终局报告_2026-09-13.md  §3 最优方案 B' 完整规格

 用法：
   python hoshi_rebuild_v2.py --data scripts/hoshi_csv_2005 --windows xxx.csv --out out.csv
================================================================================
"""
import argparse
import csv
import os
import sys
from datetime import date, timedelta

# ================================================================================
# §3.7 固定参数（三方案共用）
# ================================================================================
TOTAL_CAPITAL = 500000.0
MAX_POSITION_R = 0.10
MAX_SLOTS = 10
LOT_SIZE = 100

MA_FAST, MA_SLOW = 20, 60
DROP_THRESH = -2.0

PROFIT_ARM_PCT = 5.2
PROFIT_TRAIL_PCT = 1.2
PROFIT_ARM_PCT_LATE = 3.2
PROFIT_TRAIL_PCT_LATE = 1.0
LOSS_ARM_PCT = -5.2
LOSS_REBOUND_PCT = 2.2
LOSS_START_DAY = 15
DEADLINE_DAY = 25
MAX_HOLD = 40

BREADTH_THRESH = 20.0
BREADTH_MIN_SAMPLE = 30

HEALTH_N = 10
HEALTH_THRESH = -1.0

R3_DD_THRESH = 25.0
R3_COOLDOWNS = [60, 120, 120]
R3_ESCALATE_WINDOW = 120

COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001

# §4 三方案参数对照
SCHEMES = {
    'base': dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, LOSS_HARD_PCT=-8.2,
                 USE_R3_GATE=True),
    'B':    dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, LOSS_HARD_PCT=-8.2,
                 USE_R3_GATE=False),
    'Bp':   dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, LOSS_HARD_PCT=-6.0,
                 USE_R3_GATE=False),
}


# ================================================================================
# §3.3 K 线形态
# ================================================================================
def body_size(o, c):
    return abs(c - o)


def upper_shadow(o, h, c):
    return h - max(o, c)


def lower_shadow(o, c, l):
    return min(o, c) - l


def is_hammer(o, h, l, c):
    rng = h - l
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
    rng = h - l
    if rng <= 0 or c <= 0:
        return False
    return body_size(o, c) / rng < 0.15


# ================================================================================
# §3.3 评分
# ================================================================================
def calc_score(total_drop, o1, h1, l1, c1, confirm_chg):
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
    rng = h1 - l1
    if rng > 0 and ls / rng > 0.5:
        score += 1.0
    if confirm_chg > 5:
        score += 1.5
    elif confirm_chg > 2:
        score += 1.0
    return round(min(score, 10.0), 1)


# ================================================================================
# 数据加载
# ================================================================================
class Bar(object):
    __slots__ = ('date', 'open', 'high', 'low', 'close', 'volume')

    def __init__(self, d, o, h, l, c, v):
        self.date = d
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v


def load_data(input_path):
    """返回 code -> [Bar]，按日期升序。"""
    import glob
    code_bars = {}
    names = {}
    for path in sorted(glob.glob(os.path.join(input_path, '*.csv'))):
        fname = os.path.basename(path)
        stem = fname[:-4]
        code = stem.split('_')[0]
        name = stem[len(code) + 1:] if len(stem) > len(code) + 1 else ''
        rows = []
        try:
            with open(path, encoding='utf-8') as f:
                rd = csv.reader(f)
                header = next(rd, None)
                for r in rd:
                    if len(r) < 6:
                        continue
                    try:
                        d = date(int(r[0][0:4]), int(r[0][5:7]), int(r[0][8:10]))
                        rows.append(Bar(d, float(r[1]), float(r[2]), float(r[3]),
                                        float(r[4]), float(r[5])))
                    except (ValueError, IndexError):
                        continue
        except Exception:
            continue
        if rows:
            rows.sort(key=lambda b: b.date)
            code_bars[code] = rows
            names[code] = name
    return code_bars, names


# ================================================================================
# 预计算：均线、信号、广度（等价性说明见文件末尾）
# ================================================================================
def precompute(code_bars):
    """返回 (dates, sig_by_date, bready_by_date, idx_of)

    约定（对齐报告 §3.3）：对交易日 D（索引 i），使用【截止 D 的前一天】的数据，
    即 bars[:i]。因此：
      - 信号要求 i >= 65（报告 §3.3 的 n >= 65）
      - 广度要求 i >= 60
    """
    dateset = set()
    for bars in code_bars.values():
        for b in bars:
            dateset.add(b.date)
    dates = sorted(dateset)
    didx = {d: i for i, d in enumerate(dates)}

    idx_of = {}
    for code, bars in code_bars.items():
        m = {}
        for k, b in enumerate(bars):
            m[b.date] = k
        idx_of[code] = m

    n_above = [0] * len(dates)
    n_valid = [0] * len(dates)
    sig_by_date = {}

    for code, bars in code_bars.items():
        n = len(bars)
        # 前缀和 -> O(1) 取任意窗口均值
        pre = [0.0] * (n + 1)
        for k in range(n):
            pre[k + 1] = pre[k] + bars[k].close

        def ma_at(i, win):
            """bars[:i] 的最后 win 根收盘均值（i = 截止索引，不含 i）。"""
            if i - win < 0:
                return None
            return (pre[i] - pre[i - win]) / float(win)

        for k in range(n):
            d = bars[k].date
            # k 是 D 在【该股票自身 bars】中的索引，bars[:k] 即截止昨天。
            # 广度数组按【全局日期索引】累加，故需换算 di = didx[d]。
            if k >= 65:
                di = didx[d]
                ma60_prev = ma_at(k, MA_SLOW)
                if ma60_prev is not None and ma60_prev > 0:
                    n_valid[di] += 1
                    if bars[k - 1].close > ma60_prev:
                        n_above[di] += 1
                s = detect_signal_at(bars, k)
                if s is not None:
                    sig_by_date.setdefault(d, []).append((s, code))
    return dates, sig_by_date, n_above, n_valid, idx_of


def detect_signal_at(bars, k):
    """用 bars[:k]（截止昨天）计算信号，k >= 65。返回 score 或 None。"""
    closes = [b.close for b in bars[:k]]
    n = len(closes)
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

    drop_days = []
    if chg_d3 < DROP_THRESH:
        drop_days.append(chg_d3)
    if chg_d2 < DROP_THRESH:
        drop_days.append(chg_d2)
    if len(drop_days) < 2:
        return None
    total_drop = sum(drop_days)

    b1 = bars[n - 2]          # 企稳日 = D-2
    o1, h1, l1, c1 = b1.open, b1.high, b1.low, b1.close
    stab = is_hammer(o1, h1, l1, c1) or is_doji(o1, h1, l1, c1) or (
        -2 <= chg_d1 <= 5 and c1 > 0 and body_size(o1, c1) / c1 < 0.03
    )
    if not stab:
        return None
    if chg_d0 <= 0:
        return None
    return calc_score(total_drop, o1, h1, l1, c1, chg_d0)


# ================================================================================
# 费用
# ================================================================================
def buy_fee(amount):
    return max(amount * COMMISSION_RATE, COMMISSION_MIN)


def sell_fee(amount, code):
    fee = max(amount * COMMISSION_RATE, COMMISSION_MIN) + amount * STAMP_TAX_RATE
    if str(code).startswith('6'):
        fee += amount * TRANSFER_FEE_RATE
    return fee


# ================================================================================
# §3.6 R3 门控
# ================================================================================
class R3Gate(object):
    def __init__(self):
        self.stop_since = None
        self.peak_offset = 0
        self.last_recover = None
        self.level = 0

    def __call__(self, completed, cur_date):
        if not completed:
            return True
        if self.stop_since is not None and cur_date is not None:
            if (cur_date - self.stop_since).days < R3_COOLDOWNS[self.level]:
                return False
            self.peak_offset = len(completed)
            self.stop_since = None
            self.last_recover = cur_date
            return True
        eq = 1.0
        for t in completed[:self.peak_offset]:
            eq *= (1 + t / 100.0)
        peak = eq
        for t in completed[self.peak_offset:]:
            eq *= (1 + t / 100.0)
            peak = max(peak, eq)
        dd = (eq - peak) / peak * 100.0 if peak > 0 else 0.0
        if dd < -R3_DD_THRESH:
            if self.last_recover is not None and cur_date is not None:
                if (cur_date - self.last_recover).days < R3_ESCALATE_WINDOW:
                    self.level = min(self.level + 1, len(R3_COOLDOWNS) - 1)
                else:
                    self.level = 0
            self.stop_since = cur_date
            return False
        return True


# ================================================================================
# §3.5 出场
# ================================================================================
def step_exit(pos, high, low, open_, close, allow_sell, LOSS_HARD_START_DAY,
              LOSS_HARD_PCT):
    pos['hold_day'] += 1
    hd = pos['hold_day']
    entry = pos['entry']
    mode = pos['mode']
    armed = pos['armed']
    trail_pct = pos['trail_pct']

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
    else:
        if not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                armed = True
                trail_pct = PROFIT_TRAIL_PCT
                pos['peak'] = high
            else:
                pos['peak'] = max(pos['peak'], high)

    pos['armed'] = armed
    pos['trail_pct'] = trail_pct

    if armed:
        pos['peak'] = max(pos['peak'], high)
        trail_price = pos['peak'] * (1 - trail_pct / 100.0)
        if low <= trail_price:
            return (trail_price, '止盈') if allow_sell else None

    # §3.5.C 提前硬止损兜底（仅 LOSS_HARD_START_DAY < 15 时存在该窗口）
    if LOSS_HARD_START_DAY < LOSS_START_DAY and not armed:
        if LOSS_HARD_START_DAY <= hd < LOSS_START_DAY:
            hard_price = entry * (1 + LOSS_HARD_PCT / 100.0)
            if low <= hard_price:
                return (hard_price, '止损(硬)') if allow_sell else None

    # §3.5.D 反弹卖出式止损
    if hd >= LOSS_START_DAY and not armed:
        if not pos['loss_armed'] and low <= entry * (1 + LOSS_ARM_PCT / 100.0):
            pos['loss_armed'] = True
            pos['trough'] = low
        if pos['loss_armed']:
            pos['trough'] = min(pos['trough'], low)
            rebound = pos['trough'] * (1 + LOSS_REBOUND_PCT / 100.0)
            if high >= rebound:
                return (rebound, '止损(反弹)') if allow_sell else None
            if pos['trough'] <= entry * (1 + LOSS_HARD_PCT / 100.0):
                return (entry * (1 + LOSS_HARD_PCT / 100.0), '止损(硬)') if allow_sell else None

    # §3.5.E 超时
    if not armed and hd == DEADLINE_DAY:
        return (open_, '超时') if allow_sell else None

    # §3.5.F 兜底
    if hd >= MAX_HOLD:
        return (close, '强平') if allow_sell else None

    return None


# ================================================================================
# 主回测
# ================================================================================
def run_one(code_bars, dates, sig_by_date, n_above, n_valid, idx_of,
            scheme, start, end):
    MIN_SCORE = scheme['MIN_SCORE']
    LOSS_HARD_START_DAY = scheme['LOSS_HARD_START_DAY']
    LOSS_HARD_PCT = scheme['LOSS_HARD_PCT']
    USE_R3_GATE = scheme['USE_R3_GATE']

    sd = date.fromisoformat(start) if isinstance(start, str) else start
    ed = date.fromisoformat(end) if isinstance(end, str) else end
    window_dates = [d for d in dates if sd <= d <= ed]
    if not window_dates:
        return None

    capital = TOTAL_CAPITAL
    positions = {}
    closed = []
    gate = R3Gate()
    universe = list(code_bars.keys())
    last_bar_in_window = {}

    for today in window_dates:
        # ---- 出场 ----
        for code in list(positions.keys()):
            k = idx_of[code].get(today)
            if k is None:
                continue
            b = code_bars[code][k]
            last_bar_in_window[code] = b
            pos = positions[code]
            allow_sell = pos['hold_day'] >= 1
            res = step_exit(pos, b.high, b.low, b.open, b.close, allow_sell,
                            LOSS_HARD_START_DAY, LOSS_HARD_PCT)
            if res is None:
                continue
            sell_price, reason = res
            p = positions.pop(code)
            gross = p['shares'] * sell_price
            fee = sell_fee(gross, code)
            proceeds = gross - fee
            pnl = proceeds - p['cost']
            ret = pnl / p['cost'] * 100.0 if p['cost'] > 0 else 0.0
            capital += proceeds
            closed.append(ret)

        # ---- R3 ----
        gate_open = gate(closed, today) if USE_R3_GATE else True

        # ---- 广度 + 买入 ----
        if gate_open and len(positions) < MAX_SLOTS:
            di = None
            # dates 索引
            di = _date_index(dates, today, window_dates)
            nv = n_valid[di]
            na = n_above[di]
            breadth = (na * 100.0 / nv) if nv >= BREADTH_MIN_SAMPLE else None
            breadth_ok = (breadth is not None and breadth >= BREADTH_THRESH)
            if breadth_ok:
                sigs = sig_by_date.get(today, [])
                sigs = [x for x in sigs if x[0] >= MIN_SCORE and x[1] not in positions]
                sigs.sort(key=lambda x: -x[0])
                # 出场模式 AUTO
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
                    pos_cost_sum = sum(p['cost'] for p in positions.values())
                    equity = capital + pos_cost_sum
                    budget = equity * MAX_POSITION_R
                    shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
                    if shares <= 0:
                        continue
                    gross = shares * buy_price
                    cost = gross + buy_fee(gross)
                    if cost > capital:
                        shares = int(capital // buy_price // LOT_SIZE) * LOT_SIZE
                        if shares <= 0:
                            continue
                        gross = shares * buy_price
                        cost = gross + buy_fee(gross)
                        if cost > capital:
                            continue
                    capital -= cost
                    positions[code] = dict(
                        code=code, entry=buy_price, shares=shares, cost=cost,
                        hold_day=0, peak=buy_price, armed=False,
                        trail_pct=PROFIT_TRAIL_PCT, loss_armed=False,
                        trough=buy_price, mode='S4' if use_s4 else 'S3',
                        score=score)
                    # 买入当天用当日 OHLC 推进一次出场状态（hold_day 计为 1）；
                    # T+1 不允许卖出，故 allow_sell=False
                    step_exit(positions[code], b.high, b.low, b.open, b.close,
                              False, LOSS_HARD_START_DAY, LOSS_HARD_PCT)

    # ---- 期末强平：用窗口内最后一根 bar ----
    for code, pos in list(positions.items()):
        b = last_bar_in_window.get(code)
        if b is None:
            # 取该股票日期 <= ed 的最后一根
            bars = code_bars[code]
            cand = [x for x in bars if x.date <= ed]
            if not cand:
                continue
            b = cand[-1]
        gross = pos['shares'] * b.close
        fee = sell_fee(gross, code)
        capital += gross - fee
        pnl = (gross - fee) - pos['cost']
        closed.append(pnl / pos['cost'] * 100.0 if pos['cost'] > 0 else 0.0)

    return dict(final_capital=capital, n_trades=len(closed),
                ret=(capital - TOTAL_CAPITAL) / TOTAL_CAPITAL * 100.0)


_idx_cache = {}


def _date_index(dates, today, window_dates):
    """today 在 dates 中的全局索引（带缓存）。"""
    key = id(dates)
    if key not in _idx_cache:
        _idx_cache[key] = {d: i for i, d in enumerate(dates)}
    return _idx_cache[key][today]


# ================================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='scripts/hoshi_csv_2005')
    ap.add_argument('--windows', required=True, help='窗口 CSV: start,end,len_months')
    ap.add_argument('--schemes', default='base,B,Bp')
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()

    print('加载数据: %s' % args.data, flush=True)
    code_bars, names = load_data(args.data)
    print('  标的数 %d' % len(code_bars), flush=True)
    print('预计算均线/信号/广度...', flush=True)
    dates, sig_by_date, n_above, n_valid, idx_of = precompute(code_bars)
    print('  交易日 %d  范围 %s ~ %s' % (len(dates), dates[0], dates[-1]), flush=True)

    windows = []
    # utf-8-sig：Windows 下生成的 CSV 可能带 BOM，否则首列名会变成 '\ufeffstart'
    with open(args.windows, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            windows.append((r['start'], r['end'], int(r['len_months'])))
    print('窗口数 %d' % len(windows), flush=True)

    schemes = [s for s in args.schemes.split(',') if s]
    out_path = args.out

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['scheme', 'start', 'end', 'len_months', 'pct', 'trades'])
        for sk in schemes:
            for (s, e, m) in windows:
                r = run_one(code_bars, dates, sig_by_date, n_above, n_valid, idx_of,
                            SCHEMES[sk], s, e)
                if r is None:
                    w.writerow([sk, s, e, m, '', ''])
                else:
                    w.writerow([sk, s, e, m, '%.4f' % r['ret'], r['n_trades']])
                f.flush()
                print('  %-5s %s~%s (%2d月) %+9.2f%% 笔%d'
                      % (sk, s[:7], e[:7], m, r['ret'] if r else 0, r['n_trades'] if r else 0),
                      flush=True)
    print('DONE -> %s' % out_path)


if __name__ == '__main__':
    main()
