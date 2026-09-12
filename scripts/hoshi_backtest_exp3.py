# -*- coding: utf-8 -*-
"""
================================================================================
 Hoshi 策略 —— 独立 CSV 回测器 (Python 3.6+ 兼容, 无外部依赖)
================================================================================
 吃一份（或一目录）完整的日线 CSV，跑 Hoshi 锁定版完整策略，
 直接产出每笔交易的：买入日/卖出日/买入价/卖出价/持有天数/出场原因/
 出场模式/股数/净盈亏/收益率，以及回测汇总。

 逻辑与参数逐条对齐 WSL 项目 scripts/hoshi_final_adaptive.py（最终锁定版）
 以及 QMT 移植版 hoshi_qmt_backtest.py。这里把数据源从 Postgres/QMT 换成
 纯 CSV，其余买卖点、持有天数、S3/S4 出场、R3 门控、动态仓位完全一致。

 -------------------------------------------------------------------------------
 【输入 CSV 格式】
   支持两种：
   1) 单文件(合并)：列 code,date,open,high,low,close[,volume][,name]
      例：000001,2026-08-31,11.20,11.35,11.10,11.28,12345678,平安银行
   2) 目录(每只一股一个 CSV)：每个文件列 date,open,high,low,close[,volume]
      （文件名含 6 位代码，或用 --code-in-name 指定）
   date 支持 2026-08-31 / 20260831 / 2026/08/31 任意格式。
   不复权/前复权都可，但整份数据要一致（脚本不替你复权）。

 【用法】
   python hoshi_backtest_csv.py --input kline_sample.csv --out ./result
   python hoshi_backtest_csv.py --input ./daily_csv_dir/ --out ./result --start 2020-01-01

 【输出】
   <out>/hoshi_trades.csv      每笔成交明细（完整买卖点+持有天数）
   <out>/hoshi_summary.csv     区间汇总
   控制台打印汇总与逐笔卖出日志（DEBUG=True 时）

 仅依赖 Python 标准库。numpy 不是必须的。
================================================================================
"""

import argparse
import csv
import datetime
import os
import sys

# ================================================================================
# 一、可调参数（锁定版，与 WSL/QMT 版一致，一般不要动）
# ================================================================================

# ---- 信号参数 ----
MIN_SCORE = 8.0             # 合格信号最低评分
DROP_THRESH = -2.0          # 单日跌幅超过此值算"连跌"中的一天
MA_FAST, MA_SLOW = 20, 60   # 趋势过滤均线
MIN_AMOUNT = 0.0            # 最低当日成交额(元), 0=不限; >0 过滤僵尸股(建议 5e7)

# ---- 资金管理 ----
TOTAL_CAPITAL = 500000.0    # 起始本金
MAX_POSITION_R = 0.10       # 单股仓位上限比例
MAX_SLOTS = 10              # 最多同时持有几只
MAX_BUY_PER_DAY = 0         # 每日最多买入几只 (0 = 不限, 原版行为)
LOT_SIZE = 100              # 最小交易单位

# ---- 出场参数 ----
MAX_HOLD = 40               # 兜底最大持有交易日数
PROFIT_ARM_PCT = 5.2        # 止盈武装阈值 +5.2%
PROFIT_TRAIL_PCT = 1.2      # 武装后峰值回落 1.2% 卖出
PROFIT_ARM_PCT_LATE = 3.2   # 第15天放宽后的武装阈值
PROFIT_TRAIL_PCT_LATE = 1.0 # 放宽后的回落容忍度
LOSS_ARM_PCT = -5.2         # 止损武装阈值 -5.2%
LOSS_REBOUND_PCT = 2.2      # 止损后反弹 +2.2% 卖出
LOSS_HARD_PCT = -8.2        # 硬止损 -8.2%
LOSS_START_DAY = 15         # 从第几天开始监控"反弹卖出"式止损(原版=15即第15天才止损,前14天裸奔)
LOSS_HARD_START_DAY = 15    # 从第几天开始监控"硬止损"(跌到-8.2%无条件割)。原版=15与LOSS_START_DAY同；

# ---- 市场状态自适应钩子（exp3 新增，默认全关 → 行为等同 exp）----
MARKET_FEAT = {}            # date -> dict(breadth20,breadth60,uptrend,eq_ret,xdisp,limitup,limitdn,vol20)
MARKET_M20 = {}             # date -> 市场等权20日涨幅(小数)
ADAPTIVE_SCORE = False      # 广度自适应评分门槛
BREADTH_HI = 55.0           # 广度20 >= 此值 判为"普涨/参与市场"
SCORE_BREADTH_HI_MODE = 8.0 # 普涨时用(放宽，参与)
SCORE_BREADTH_LO_MODE = 9.0 # 非普涨时用(收紧，防守)
ADAPTIVE_STOP = False       # 波动率自适应硬止损起点
VOL_HI = 1.8                # 20日波动率(%) >= 此值 判为"高波动/易崩"
STOP_VOL_HI = 5             # 高波动时第5天起硬止损(早保护)
STOP_VOL_LO = 15            # 低波动时第15天(避免震荡误杀)
RS_FILTER = False           # 相对强度过滤：不买落后于市场的票
RS_ALPHA = 1.0              # 要求 个股20日涨幅 >= alpha × 市场等权20日涨幅


def load_market_features(path):
    """加载 hoshi_market_features.csv 与由其推导的市场20日涨幅。"""
    import csv as _csv
    from datetime import date as _date
    global MARKET_FEAT, MARKET_M20
    rows = []
    with open(path, encoding='utf-8') as f:
        for r in _csv.DictReader(f):
            d = _date.fromisoformat(r['date'])
            rec = dict(breadth20=float(r['breadth20']), breadth60=float(r['breadth60']),
                       uptrend=float(r['uptrend']), eq_ret=float(r['eq_ret']),
                       xdisp=float(r['xdisp']), limitup=float(r['limitup']),
                       limitdn=float(r['limitdn']), vol20=float(r['vol20']))
            MARKET_FEAT[d] = rec
            rows.append((d, rec['eq_ret']))
    acc = []
    for d, r in rows:
        acc.append(r)
        if len(acc) > 20:
            acc.pop(0)
        m = 1.0
        for x in acc:
            m *= (1 + x)
        MARKET_M20[d] = m - 1
                            # 实验版可设早(如2~5)让深套票早割,防-30~-50%裸奔,而反弹卖出仍留15天不误杀回踩。
DEADLINE_DAY = 25           # 第25天未武装止盈则开盘价卖出

# ---- 出场模式切换 ----
EXIT_MODE = 'AUTO'          # 'AUTO'=S3/S4自适应 / 'S3' / 'S4'
HEALTH_N = 10               # 健康度看最近几笔已完成交易
HEALTH_THRESH = -1.0        # 平均收益率低于此值改用 S4

# ---- 大盘保护 ----
USE_R3_GATE = True          # R3 回撤门控
R3_DD_THRESH = 25.0         # 权益回撤超过 25% 停手
R3_BASE_COOLDOWN = 60       # 基础冷却自然日
R3_ESCALATE_COOLDOWN = 120  # 升级后的冷却自然日(封顶)
R3_ESCALATE_WINDOW = 120    # 恢复后多少天内再触发就升级

USE_BREADTH_GATE = True     # 市场广度门控
BREADTH_THRESH = 20.0       # 广度低于 20% 不开新仓
BREADTH_MIN_SAMPLE = 30     # 有效样本少于 30 只时不给广度信号

# ---- 执行口径 ----
ENFORCE_T1 = True           # True=买入当天不允许卖出(实盘口径); False=复现原 WSL 口径
COUNT_ENTRY_DAY = True      # 买入当天用当日 OHLC 推进一次出场状态(hold_day 计为 1)
DEBUG = True                # 打印逐笔卖出日志
LOG_EVERY = 0               # 每 N 个交易日打印一次进度(0=不打印)

# ---- 费率 ----
COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001


# ================================================================================
# 二、工具函数
# ================================================================================

def _log(msg):
    print(msg, flush=True)


def _buy_fee(amount):
    return max(amount * COMMISSION_RATE, COMMISSION_MIN)


def _sell_fee(amount, code):
    fee = max(amount * COMMISSION_RATE, COMMISSION_MIN) + amount * STAMP_TAX_RATE
    if str(code).startswith('6'):
        fee += amount * TRANSFER_FEE_RATE
    return fee


def _mean(seq):
    if not seq:
        return 0.0
    return sum(seq) / float(len(seq))


# ---- K 线形态（逐条对齐 core/screener/hoshi.py）----

def _body_size(o, c):
    return abs(c - o)


def _upper_shadow(o, h, c):
    return h - max(o, c)


def _lower_shadow(o, c, l):
    return min(o, c) - l


def _candle_range(h, l):
    return h - l


def _is_hammer(o, h, l, c):
    rng = _candle_range(h, l)
    if rng <= 0 or c <= 0:
        return False
    body = _body_size(o, c)
    lower = _lower_shadow(o, c, l)
    upper = _upper_shadow(o, h, c)
    if body / rng > 0.3:
        return False
    if body > 0 and lower < body * 1.5:
        return False
    if body == 0 and lower < rng * 0.4:
        return False
    if upper > rng * 0.5:
        return False
    return True


def _is_doji(o, h, l, c):
    rng = _candle_range(h, l)
    if rng <= 0 or c <= 0:
        return False
    return _body_size(o, c) / rng < 0.15


def _is_stabilization(o, h, l, c):
    return _is_hammer(o, h, l, c) or _is_doji(o, h, l, c)


def _calc_score(total_drop, stab_o, stab_h, stab_l, stab_c, confirm_chg):
    """Hoshi 评分（对齐 _calc_hoshi_score）"""
    score = 3.0
    d = abs(total_drop)
    if 10 <= d <= 25:
        score += 2.0
    elif d > 25:
        score += 1.5
    elif d >= 5:
        score += 1.0
    if _is_hammer(stab_o, stab_h, stab_l, stab_c):
        score += 2.5
    elif _is_doji(stab_o, stab_h, stab_l, stab_c):
        score += 2.0
    else:
        score += 1.0
    ls = _lower_shadow(stab_o, stab_c, stab_l)
    rng = _candle_range(stab_h, stab_l)
    if rng > 0 and ls / rng > 0.5:
        score += 1.0
    if confirm_chg > 5:
        score += 1.5
    elif confirm_chg > 2:
        score += 1.0
    return round(min(score, 10.0), 1)


def _detect_signal(opens, highs, lows, closes):
    """检测 Hoshi confirmation 信号。

    传入的序列是【截止信号日 D 的昨天】的数据（即已去掉 D 当天），
    最后一个元素 = D-1（确认日的前一天）。返回 score 或 None。
    索引约定：closes[-1]=D-1(确认日), [-2]=D-2(企稳日), [-3]=D-3, [-4]=D-4。
    """
    n = len(closes)
    if n < 65:
        return None
    ma20 = _mean(closes[-MA_FAST:])
    ma60 = _mean(closes[-MA_SLOW:])
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

    i_d1 = n - 2
    o1, h1, l1, c1 = opens[i_d1], highs[i_d1], lows[i_d1], closes[i_d1]
    stabilization = _is_stabilization(o1, h1, l1, c1) or (
        -2 <= chg_d1 <= 5 and c1 > 0 and _body_size(o1, c1) / c1 < 0.03
    )
    if not stabilization:
        return None
    if chg_d0 <= 0:
        return None
    return _calc_score(total_drop, o1, h1, l1, c1, chg_d0)


# ================================================================================
# 三、R3 门控
# ================================================================================

class R3Gate(object):
    def __init__(self, dd_thresh, base_cd, esc_cd, esc_window):
        self.dd_thresh = dd_thresh
        self.cooldowns = [base_cd, esc_cd, esc_cd]
        self.esc_window = esc_window
        self.stop_since = None
        self.peak_offset = 0
        self.last_recover = None
        self.level = 0

    def __call__(self, completed, current_date):
        if not completed:
            return True
        if self.stop_since is not None and current_date is not None:
            cd = self.cooldowns[self.level]
            if (current_date - self.stop_since).days < cd:
                return False
            self.peak_offset = len(completed)
            self.stop_since = None
            self.last_recover = current_date
            return True
        eq = 1.0
        for t in completed[:self.peak_offset]:
            eq *= (1 + t['return_pct'] / 100.0)
        peak = eq
        for t in completed[self.peak_offset:]:
            eq *= (1 + t['return_pct'] / 100.0)
            peak = max(peak, eq)
        dd = (eq - peak) / peak * 100.0 if peak > 0 else 0.0
        if dd < -self.dd_thresh:
            if self.last_recover is not None and current_date is not None:
                if (current_date - self.last_recover).days < self.esc_window:
                    self.level = min(self.level + 1, len(self.cooldowns) - 1)
                else:
                    self.level = 0
            self.stop_since = current_date
            return False
        return True


# ================================================================================
# 四、出场判定（逐条对齐 exit_s3_day14 / exit_s4_immediate_arm）
# ================================================================================

def _step_exit(pos, high, low, open_, close, allow_sell):
    """推进一个持仓一天的出场判定。pos 就地更新。返回 (卖价, 原因) 或 None。"""
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
            if allow_sell:
                return trail_price, '止盈(峰值回落%.1f%%)' % trail_pct
            return None

    # 【提前硬止损兜底窗口】仅在 hd 处于 [LOSS_HARD_START_DAY, LOSS_START_DAY) 时生效。
    # 目的：前14天(或LOSS_START_DAY前)若已深跌到-8.2%则无条件早割,防深套到-30~-50%裸奔。
    # 一旦 hd >= LOSS_START_DAY, 完全交还原版反弹卖出逻辑, 不改触发语义。
    if LOSS_HARD_START_DAY < LOSS_START_DAY and not armed:
        if LOSS_HARD_START_DAY <= hd < LOSS_START_DAY:
            hard_price = entry * (1 + LOSS_HARD_PCT / 100.0)
            if low <= hard_price:
                if allow_sell:
                    return hard_price, '止损(硬止损)'
                return None

    # 原版反弹卖出式止损(LOSS_START_DAY起)：先 loss_armed(跌破-5.2%记低点), 反弹+2.2%或硬止损。
    if hd >= LOSS_START_DAY and not armed:
        if not pos['loss_armed'] and low <= entry * (1 + LOSS_ARM_PCT / 100.0):
            pos['loss_armed'] = True
            pos['trough'] = low
        if pos['loss_armed']:
            pos['trough'] = min(pos['trough'], low)
            rebound = pos['trough'] * (1 + LOSS_REBOUND_PCT / 100.0)
            if high >= rebound:
                if allow_sell:
                    return rebound, '止损(反弹卖出)'
                return None
            if pos['trough'] <= entry * (1 + LOSS_HARD_PCT / 100.0):
                if allow_sell:
                    return entry * (1 + LOSS_HARD_PCT / 100.0), '止损(硬止损)'
                return None

    if not armed and hd == DEADLINE_DAY:
        if allow_sell:
            return open_, '止盈超时(第%d天开盘卖出)' % DEADLINE_DAY
        return None

    if hd >= MAX_HOLD:
        if allow_sell:
            return close, '超%d日强制平仓' % MAX_HOLD
        return None

    return None


# ================================================================================
# 五、CSV 加载
# ================================================================================

def _to_date(s):
    s = str(s).strip().replace('-', '').replace('/', '').replace(' ', '')
    if len(s) >= 8:
        return datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    raise ValueError('无法解析日期: %r' % s)


def _to_float(s):
    return float(str(s).strip())


class Bar(object):
    __slots__ = ('date', 'open', 'high', 'low', 'close', 'volume')

    def __init__(self, date, o, h, l, c, v):
        self.date = date
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v


HEADER_KEYS = {'code', 'date', 'open', 'high', 'low', 'close', 'volume', 'vol',
                'amount', 'name', 'names'}


def _read_rows(path):
    """读一个 CSV 文件，返回 (rows, header_present)。

    rows 是归一化字典列表，键为 code/date/open/high/low/close/volume/name。
    自动识别表头：首行含这些关键字则视为表头并跳过；否则按位置
    [code,date,open,high,low,close,volume?,name?] 解析。
    """
    import re
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        raw = list(csv.reader(f))
    if not raw:
        return [], False
    first = [c.strip().lower() for c in raw[0]]
    if any(k in HEADER_KEYS for k in first):
        header = raw[0]
        data = raw[1:]
    else:
        header = None
        data = raw
    out = []
    for r in data:
        if not r or all(not c.strip() for c in r):
            continue
        if header is None:
            d = {
                'code': r[0] if len(r) > 0 else '',
                'date': r[1] if len(r) > 1 else '',
                'open': r[2] if len(r) > 2 else '',
                'high': r[3] if len(r) > 3 else '',
                'low': r[4] if len(r) > 4 else '',
                'close': r[5] if len(r) > 5 else '',
                'volume': r[6] if len(r) > 6 else '1',
                'name': r[7] if len(r) > 7 else '',
            }
        else:
            d = {}
            for i, c in enumerate(header):
                key = c.strip().lower()
                if key in ('vol', 'volume'):
                    key = 'volume'
                elif key in ('name', 'names'):
                    key = 'name'
                d[key] = r[i] if i < len(r) else ''
        out.append(d)
    return out, header is not None


def _row_to_bar(d):
    """把一行归一化字典转成 Bar，无效返回 None。"""
    try:
        dt = _to_date(d.get('date', ''))
        o = _to_float(d.get('open', '0'))
        h = _to_float(d.get('high', '0')) if d.get('high') not in (None, '') else o
        l = _to_float(d.get('low', '0')) if d.get('low') not in (None, '') else o
        c = _to_float(d.get('close', '0'))
        v = _to_float(d.get('volume', '1')) if d.get('volume') not in (None, '') else 1.0
    except Exception:
        return None
    if c <= 0 or o <= 0:
        return None
    return Bar(dt, o, h, l, c, v)


def load_data(input_path):
    """加载日线。input_path 可以是单 CSV 或目录。返回 code_bars, names, all_dates。"""
    import re
    code_bars = {}
    names = {}

    if os.path.isdir(input_path):
        files = [os.path.join(input_path, f) for f in os.listdir(input_path)
                 if f.lower().endswith('.csv')]
        _log('加载目录 %s : %d 个 CSV' % (input_path, len(files)))
        for fp in files:
            rows, _ = _read_rows(fp)
            code = None
            name = ''
            bars = []
            for d in rows:
                if not code and d.get('code', '').strip():
                    code = d['code'].strip()
                if not name and d.get('name', '').strip():
                    name = d['name'].strip()
                bar = _row_to_bar(d)
                if bar:
                    bars.append(bar)
            if not code:
                m = re.search(r'(\d{6})', os.path.basename(fp))
                if m:
                    code = m.group(1)
            if code and bars:
                code_bars[code] = sorted(bars, key=lambda b: b.date)
                names[code] = name
    else:
        _log('加载单文件 %s' % input_path)
        rows, _ = _read_rows(input_path)
        groups = {}
        gnames = {}
        for d in rows:
            code = d.get('code', '').strip()
            if not code:
                continue
            bar = _row_to_bar(d)
            if not bar:
                continue
            if d.get('name', '').strip():
                gnames[code] = d['name'].strip()
            groups.setdefault(code, []).append(bar)
        for code, bars in groups.items():
            code_bars[code] = sorted(bars, key=lambda b: b.date)
            if code in gnames:
                names[code] = gnames[code]

    if not code_bars:
        _log('未加载到任何有效数据，退出。')
        sys.exit(1)
    dateset = set()
    for bars in code_bars.values():
        for b in bars:
            dateset.add(b.date)
    all_dates = sorted(dateset)
    _log('共 %d 只标的, %d 个交易日, 区间 %s ~ %s'
         % (len(code_bars), len(all_dates), all_dates[0], all_dates[-1]))
    return code_bars, names, all_dates


# ================================================================================
# 六、回测主循环
# ================================================================================

def run_backtest(code_bars, names, all_dates, start=None, end=None):
    # 建索引
    idx_of = {}
    for code, bars in code_bars.items():
        idx_of[code] = {b.date: i for i, b in enumerate(bars)}

    # 区间过滤
    dates = all_dates
    if start:
        sd = _to_date(start)
        dates = [d for d in dates if d >= sd]
    if end:
        ed = _to_date(end)
        dates = [d for d in dates if d <= ed]

    capital = TOTAL_CAPITAL
    positions = {}
    closed = []
    gate = R3Gate(R3_DD_THRESH, R3_BASE_COOLDOWN, R3_ESCALATE_COOLDOWN, R3_ESCALATE_WINDOW)
    in_stop = False
    stop_start = None
    stops = []
    skipped = 0
    n_s4 = 0
    day_count = 0

    universe = list(code_bars.keys())

    def history_upto(code, today):
        """返回 code 在 today 及之前的所有 bar（含 today），today 无数据返回 None。"""
        k = idx_of[code].get(today)
        if k is None:
            return None
        return code_bars[code][:k + 1]

    def bar_on(code, today):
        k = idx_of[code].get(today)
        return code_bars[code][k] if k is not None else None

    for today in dates:
        day_count += 1

        # ---- 0. 市场状态自适应参数（exp3 新增）----
        min_score_today = MIN_SCORE
        rs_min_today = None
        mf = MARKET_FEAT.get(today)
        if mf is not None:
            if ADAPTIVE_SCORE:
                min_score_today = (SCORE_BREADTH_HI_MODE
                                   if mf['breadth20'] * 100.0 >= BREADTH_HI
                                   else SCORE_BREADTH_LO_MODE)
            if ADAPTIVE_STOP:
                globals()['LOSS_HARD_START_DAY'] = (STOP_VOL_HI
                                                    if mf['vol20'] * 100.0 >= VOL_HI
                                                    else STOP_VOL_LO)
            if RS_FILTER:
                rs_min_today = MARKET_M20.get(today)

        # ---- 1. 持仓出场 ----
        for code in list(positions.keys()):
            b = bar_on(code, today)
            if b is None:
                continue          # 停牌/无数据，不推进 hold_day
            if ENFORCE_T1 and positions[code]['hold_day'] < 1:
                # T+1：买入当天不允许卖出，但状态已在买入日推进过一次
                pass
            pos = positions[code]
            allow_sell = (not ENFORCE_T1) or (pos['hold_day'] >= 1)
            res = _step_exit(pos, b.high, b.low, b.open, b.close, allow_sell)
            if res is None:
                continue
            sell_price, reason = res
            p = positions.pop(code)
            gross = p['shares'] * sell_price
            fee = _sell_fee(gross, code)
            proceeds = gross - fee
            cost = p['cost']
            pnl = proceeds - cost
            ret = pnl / cost * 100.0 if cost > 0 else 0.0
            capital += proceeds
            closed.append({
                'code': code, 'name': names.get(code, ''), 'score': p['score'],
                'mode': p['mode'], 'buy_date': p['buy_date'], 'sell_date': today,
                'buy_price': p['entry'], 'sell_price': sell_price,
                'shares': p['shares'], 'cost': cost, 'proceeds': proceeds,
                'fees': _buy_fee(p['shares'] * p['entry']) + fee,
                'pnl': pnl, 'return_pct': ret,
                'hold_days': p['hold_day'], 'exit_reason': reason,
            })
            if DEBUG:
                _log('  卖出 %s %s @ %.2f | %s | %s | 收益 %+.2f%% | 持有 %d 天'
                     % (code, names.get(code, ''), sell_price, p['mode'], reason, ret, p['hold_day']))

        # ---- 2. R3 门控 ----
        gate_open = True
        if USE_R3_GATE:
            gate_open = gate(closed, today)
            if not gate_open:
                if not in_stop:
                    in_stop = True
                    stop_start = today
            else:
                if in_stop:
                    stops.append((stop_start, today))
                    in_stop = False
                    stop_start = None

        # ---- 3. 广度 + 信号扫描 ----
        signals = []
        breadth = None
        breadth_ok = True
        if gate_open and len(positions) < MAX_SLOTS:
            n_valid = 0
            n_above = 0
            for code in universe:
                full = history_upto(code, today)
                if full is None or len(full) < MA_SLOW + 6:
                    continue
                c = [x.close for x in full]
                o = [x.open for x in full]
                h = [x.high for x in full]
                l = [x.low for x in full]
                # 广度：昨天收盘 > 昨天 MA60
                cp = c[:-1]
                if len(cp) >= MA_SLOW:
                    ma60 = _mean(cp[-MA_SLOW:])
                    if ma60 > 0:
                        n_valid += 1
                        if cp[-1] > ma60:
                            n_above += 1
                # 信号：用截止昨天的序列
                if code not in positions and len(full) >= 66:
                    op = o[:-1]; hp = h[:-1]; lp = l[:-1]; cpp = c[:-1]
                    score = _detect_signal(op, hp, lp, cpp)
                    if score is not None and score >= min_score_today:
                        if rs_min_today is not None and len(cpp) >= 21 and cpp[-21] > 0:
                            r20 = cpp[-1] / cpp[-21] - 1.0
                            if r20 < rs_min_today * RS_ALPHA:
                                continue
                        signals.append((score, code))
            breadth = (n_above * 100.0 / n_valid) if n_valid >= BREADTH_MIN_SAMPLE else None
            if USE_BREADTH_GATE:
                breadth_ok = (breadth is not None and breadth >= BREADTH_THRESH)
            if breadth_ok:
                signals.sort(key=lambda x: -x[0])
            else:
                signals = []

        # ---- 4. 买入（动态仓位预算，逐笔重算）----
        free_slots = MAX_SLOTS - len(positions)
        bought = 0
        if signals and free_slots > 0:
            if EXIT_MODE == 'S3':
                use_s4 = False
            elif EXIT_MODE == 'S4':
                use_s4 = True
            else:
                recent = closed[-HEALTH_N:]
                health = (sum(t['return_pct'] for t in recent) / len(recent)) if recent else None
                use_s4 = health is not None and health < HEALTH_THRESH

            for score, code in signals:
                if free_slots <= 0:
                    break
                if MAX_BUY_PER_DAY > 0 and bought >= MAX_BUY_PER_DAY:
                    break
                if code in positions:
                    continue
                buy_bar = bar_on(code, today)
                if buy_bar is None:
                    continue
                buy_price = buy_bar.open
                if buy_price <= 0:
                    continue
                pos_cost_sum = sum(p['cost'] for p in positions.values())
                equity = capital + pos_cost_sum
                budget = equity * MAX_POSITION_R
                shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
                if shares <= 0:
                    continue
                gross = shares * buy_price
                cost = gross + _buy_fee(gross)
                if cost > capital:
                    shares = int(capital // buy_price // LOT_SIZE) * LOT_SIZE
                    if shares <= 0:
                        continue
                    gross = shares * buy_price
                    cost = gross + _buy_fee(gross)
                    if cost > capital:
                        continue
                capital -= cost
                positions[code] = {
                    'code': code, 'entry': buy_price, 'buy_date': today,
                    'shares': shares, 'cost': cost, 'hold_day': 0,
                    'peak': buy_price, 'armed': False,
                    'trail_pct': PROFIT_TRAIL_PCT, 'loss_armed': False,
                    'trough': buy_price, 'mode': 'S4' if use_s4 else 'S3',
                    'score': score,
                }
                if COUNT_ENTRY_DAY:
                    _step_exit(positions[code], buy_bar.high, buy_bar.low,
                               buy_price, buy_bar.close, False)
                if use_s4:
                    n_s4 += 1
                free_slots -= 1
                bought += 1
            skipped += max(0, len(signals) - bought)

        if LOG_EVERY and day_count % LOG_EVERY == 0:
            mv = sum(p['shares'] * (bar_on(p['code'], today).close if bar_on(p['code'], today) else p['entry'])
                     for p in positions.values())
            eq = capital + mv
            _log('[%s] 权益 %.0f | 持仓 %d | 已完成 %d | 信号 %d 买 %d | 广度 %s | R3 %s'
                 % (today, eq, len(positions), len(closed), len(signals), bought,
                    ('%.1f%%' % breadth) if breadth is not None else 'NA',
                    '停手' if not gate_open else '放行'))

    # 收尾：强平剩余持仓（按最后一根可见 bar 的收盘价）
    for code in list(positions.keys()):
        p = positions.pop(code)
        last_bar = code_bars[code][-1]
        sell_price = last_bar.close
        gross = p['shares'] * sell_price
        fee = _sell_fee(gross, code)
        proceeds = gross - fee
        cost = p['cost']
        pnl = proceeds - cost
        ret = pnl / cost * 100.0 if cost > 0 else 0.0
        capital += proceeds
        closed.append({
            'code': code, 'name': names.get(code, ''), 'score': p['score'],
            'mode': p['mode'], 'buy_date': p['buy_date'], 'sell_date': last_bar.date,
            'buy_price': p['entry'], 'sell_price': sell_price,
            'shares': p['shares'], 'cost': cost, 'proceeds': proceeds,
            'fees': _buy_fee(p['shares'] * p['entry']) + fee,
            'pnl': pnl, 'return_pct': ret,
            'hold_days': p['hold_day'], 'exit_reason': '回测结束强平',
        })
    if in_stop and stop_start:
        stops.append((stop_start, dates[-1]))

    return dict(closed=closed, final_capital=capital, stops=stops,
                skipped=skipped, n_s4=n_s4)


# ================================================================================
# 七、输出
# ================================================================================

def write_outputs(result, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    closed = sorted(result['closed'], key=lambda t: (t['buy_date'], t['code']))
    trades_path = os.path.join(out_dir, 'hoshi_trades.csv')
    with open(trades_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['代码', '名称', '评分', '出场模式', '买入日', '卖出日', '买入价',
                    '卖出价', '股数', '买入成本', '卖出所得', '费用', '净盈亏',
                    '净收益率%', '持有天数', '出场原因'])
        for t in closed:
            w.writerow([t['code'], t['name'], '%.1f' % t['score'], t['mode'],
                        t['buy_date'], t['sell_date'], '%.2f' % t['buy_price'],
                        '%.2f' % t['sell_price'], t['shares'], '%.2f' % t['cost'],
                        '%.2f' % t['proceeds'], '%.2f' % t['fees'], '%.2f' % t['pnl'],
                        '%.2f' % t['return_pct'], t['hold_days'], t['exit_reason']])

    n = len(closed)
    wins = len([t for t in closed if t['pnl'] > 0])
    total_pnl = sum(t['pnl'] for t in closed)
    total_ret = (result['final_capital'] - TOTAL_CAPITAL) / TOTAL_CAPITAL * 100
    summary = {
        '起始本金': '%.2f' % TOTAL_CAPITAL,
        '最终权益': '%.2f' % result['final_capital'],
        '总收益率%': '%.2f' % total_ret,
        '成交笔数': n,
        'S4笔数': result['n_s4'],
        '胜率%': ('%.1f' % (wins * 100.0 / n)) if n else 'NA',
        '累计盈亏': '%.2f' % total_pnl,
        'R3停手次数': len(result['stops']),
        '跳过信号数': result['skipped'],
    }
    summ_path = os.path.join(out_dir, 'hoshi_summary.csv')
    with open(summ_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['指标', '值'])
        for k, v in summary.items():
            w.writerow([k, v])

    _log('=' * 70)
    _log('Hoshi CSV 回测汇总')
    for k, v in summary.items():
        _log('  %s: %s' % (k, v))
    _log('=' * 70)
    _log('明细写入: %s' % trades_path)
    _log('汇总写入: %s' % summ_path)
    return trades_path, summ_path


# ================================================================================
# 八、入口
# ================================================================================

def main():
    global TOTAL_CAPITAL, MAX_SLOTS, MAX_BUY_PER_DAY, EXIT_MODE, USE_BREADTH_GATE, USE_R3_GATE, ENFORCE_T1, LOSS_START_DAY
    ap = argparse.ArgumentParser(description='Hoshi 策略独立 CSV 回测器')
    ap.add_argument('--input', required=True, help='日线 CSV 文件 或 目录')
    ap.add_argument('--out', default='./hoshi_result', help='输出目录')
    ap.add_argument('--start', default=None, help='起始日 YYYY-MM-DD（可选）')
    ap.add_argument('--end', default=None, help='结束日 YYYY-MM-DD（可选）')
    ap.add_argument('--capital', type=float, default=TOTAL_CAPITAL, help='起始本金')
    ap.add_argument('--max-slots', type=int, default=MAX_SLOTS, help='最大持仓数')
    ap.add_argument('--max-buy-per-day', type=int, default=0, help='每日最多买入几只 (0=不限, 原版)')
    ap.add_argument('--loss-start-day', type=int, default=LOSS_START_DAY,
                    help='从第几天起监控止损 (原版15=第15天才止损前14天裸奔; 1=全程硬止损兜底)')
    ap.add_argument('--mode', default=EXIT_MODE, choices=['AUTO', 'S3', 'S4'])
    ap.add_argument('--no-breadth', action='store_true', help='关闭广度门控')
    ap.add_argument('--no-r3', action='store_true', help='关闭 R3 门控')
    ap.add_argument('--no-t1', action='store_true', help='允许当天买当天卖(复现原WSL口径)')
    args = ap.parse_args()

    TOTAL_CAPITAL = args.capital
    MAX_SLOTS = args.max_slots
    MAX_BUY_PER_DAY = args.max_buy_per_day
    LOSS_START_DAY = args.loss_start_day
    EXIT_MODE = args.mode
    USE_BREADTH_GATE = not args.no_breadth
    USE_R3_GATE = not args.no_r3
    if args.no_t1:
        ENFORCE_T1 = False

    code_bars, names, all_dates = load_data(args.input)
    result = run_backtest(code_bars, names, all_dates, start=args.start, end=args.end)
    write_outputs(result, args.out)


if __name__ == '__main__':
    main()
