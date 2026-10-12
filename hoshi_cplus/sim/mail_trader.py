# -*- coding: utf-8 -*-
"""Hoshi-cplus 邮件驱动 · 纸面交易模拟（mail-driven paper trading）。

一句话：每个交易日，
  1) 从 QQ 邮件里「Hoshi实盘」指导拿到"下一交易日开盘要买的"清单（信号源）；
  2) 到交易日开盘，按**真实开盘价**虚拟买入（含 涨停过滤 / 10% 仓位上限 / 手续费）；
  3) 用 hoshi-cplus 的出场规则（step_exit）管理持仓（T+1、D5 硬止损 −6%、
     D14/15 武装止盈、D25 超时、D40 兜底）；
  4) 收盘按收盘价 mark-to-market，逐日落台账。

数据源：data/tdx.duckdb（跑之前先 scripts/refresh_tdx_duckdb.py 刷新到最新交易日）。
状态：hoshi_cplus/sim/state.json ｜ 台账：ledger.csv、trades.csv

用法
----
  python hoshi_cplus/sim/mail_trader.py init --capital 300000 --start 2026-09-15
  python hoshi_cplus/sim/mail_trader.py set-pending --for 2026-09-15 "002365:永安药业,300901:中胤时尚,300736:百邦科技"
  python hoshi_cplus/sim/mail_trader.py run 2026-09-15
  python hoshi_cplus/sim/mail_trader.py status
"""
import argparse
import csv
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))          # 仓库根
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.config import (get_preset, MAX_POSITION_R, MAX_SLOTS, LOT_SIZE,
                                COMMISSION_RATE, COMMISSION_MIN, STAMP_TAX_RATE,
                                TRANSFER_FEE_RATE, HEALTH_N, HEALTH_THRESH)
from hoshi_cplus.exits import new_position, step_exit

DEFAULT_STATE = os.path.join(_HERE, 'state.json')
LEDGER = os.path.join(_HERE, 'ledger.csv')
TRADES = os.path.join(_HERE, 'trades.csv')
DB = os.path.join(_ROOT, 'data', 'tdx.duckdb')
CAL_SYMBOL = 'sz000001'          # 平安银行 作交易日历代理


# ------------------------------------------------------------------ 工具
def _sym(code):
    return ('sh' if code[0] == '6' else 'sz') + code


def _limit_pct(code):
    """涨停幅度（%）：创业板 30x / 科创板 68x = 20%，其余 10%。"""
    return 20.0 if (code[:2] in ('30', '68')) else 10.0


def _valid_day(s):
    from datetime import datetime
    datetime.strptime(s, '%Y-%m-%d')
    return s


def _con():
    import duckdb
    return duckdb.connect(DB, read_only=True)


def trading_days(a, b):
    """[a, b] 闭区间内的交易日（升序）。"""
    con = _con()
    sql = ("SELECT DISTINCT date FROM raw_kline_daily WHERE symbol=? "
           "AND date >= DATE '%s' AND date <= DATE '%s' ORDER BY date" % (a, b))
    rows = con.execute(sql, [CAL_SYMBOL]).fetchall()
    con.close()
    return [str(r[0]) for r in rows]


def bar(code, day):
    """返回 (open, high, low, close, prev_close) 或 None。"""
    con = _con()
    r = con.execute("SELECT open,high,low,close FROM raw_kline_daily WHERE symbol='%s' AND date = DATE '%s'"
                    % (_sym(code), day)).fetchone()
    if not r:
        con.close()
        return None
    p = con.execute("SELECT close FROM raw_kline_daily WHERE symbol='%s' AND date < DATE '%s' ORDER BY date DESC LIMIT 1"
                    % (_sym(code), day)).fetchone()
    con.close()
    return r[0], r[1], r[2], r[3], (p[0] if p else None)


def close_of(code, day):
    con = _con()
    r = con.execute("SELECT close FROM raw_kline_daily WHERE symbol='%s' AND date <= DATE '%s' ORDER BY date DESC LIMIT 1"
                    % (_sym(code), day)).fetchone()
    con.close()
    return r[0] if r else None


def buy_fees(code, price, shares):
    amt = price * shares
    fee = max(COMMISSION_MIN, amt * COMMISSION_RATE)
    if code[0] == '6':
        fee += amt * TRANSFER_FEE_RATE
    return fee


def sell_fees(code, price, shares):
    amt = price * shares
    fee = max(COMMISSION_MIN, amt * COMMISSION_RATE)
    fee += amt * STAMP_TAX_RATE
    if code[0] == '6':
        fee += amt * TRANSFER_FEE_RATE
    return fee


# ------------------------------------------------------------------ 状态
def load_state(path=DEFAULT_STATE):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_state(st, path=DEFAULT_STATE):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def _append_csv(path, header, row):
    new = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


# ------------------------------------------------------------------ 命令
def cmd_init(args):
    st = dict(start_capital=float(args.capital), start_date=args.start,
              cash=float(args.capital), positions=[], pending=[],
              last_day=None, history=[], closed=[])
    save_state(st, args.state)
    print('已建仓：本金 %.0f 元，起始日 %s，状态 → %s' % (args.capital, args.start, args.state))


def _parse_pending(s):
    out = []
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            code, name = part.split(':', 1)
        else:
            code, name = part, ''
        out.append(dict(code=code.strip(), name=name.strip()))
    return out


def cmd_set_pending(args):
    st = load_state(args.state)
    p = _parse_pending(args.items)
    for x in p:
        x['for_day'] = _valid_day(args.for_day)
    st['pending'] = p
    save_state(st, args.state)
    print('已登记下一交易日(%s)买入：%s' % (args.for_day, ', '.join('%s %s' % (x['code'], x['name']) for x in p) or '（无）'))


def _equity_at_close(st, day):
    mkt = 0.0
    for pos in st['positions']:
        c = close_of(pos['code'], day)
        mkt += pos['shares'] * (c if c else pos['entry'])
    return st['cash'] + mkt


def cmd_run(args):
    p = get_preset(args.preset)
    st = load_state(args.state)
    day = _valid_day(args.day)

    # 断点续跑：补齐 last_day 之后、DAY（含）之前的所有交易日
    if st['last_day']:
        days = trading_days(_next_day(st['last_day']), day)
    else:
        days = trading_days(st['start_date'], day)
    if not days:
        print('无待处理交易日（%s ~ %s）' % (st['start_date'] if not st['last_day'] else st['last_day'], day))
        return
    if days[-1] != day:
        print('⚠️ %s 非交易日或无数据；实际处理到 %s' % (day, days[-1]))

    for d in days:
        prev_equity = st['history'][-1]['equity'] if st['history'] else st['start_capital']
        budget = prev_equity * MAX_POSITION_R
        acted = []

        # ---- 1. 成交：pending 里 for_day <= d 的买单，按 d 开盘价买入 ----
        still = []
        for item in st['pending']:
            if item.get('for_day', d) > d:
                still.append(item)
                continue
            code = item['code']
            if any(x['code'] == code for x in st['positions']):
                continue                                   # 已持有，跳过
            if len(st['positions']) >= MAX_SLOTS:
                still.append(item)
                continue
            b = bar(code, d)
            if not b:
                still.append(item)                             # 当日无数据（停牌），顺延
                continue
            o, h, l, c, pc = b
            if pc and (o / pc - 1) * 100 >= _limit_pct(code) - 0.05:
                print('  [跳过] %s %s 开盘涨停(+%.2f%%)，买不进' % (code, item['name'], (o / pc - 1) * 100))
                continue
            shares = int(budget // o // LOT_SIZE) * LOT_SIZE
            if shares <= 0:
                continue
            if shares * o + buy_fees(code, o, shares) > st['cash']:
                shares = int(st['cash'] // o // LOT_SIZE) * LOT_SIZE
                if shares <= 0:
                    still.append(item)
                    continue
            fee = buy_fees(code, o, shares)
            st['cash'] -= shares * o + fee
            # 模式判定（与回测一致）：最近 10 笔已完成交易平均收益 < −1% → S4（随时武装），否则 S3
            recent = st.setdefault('closed', [])[-HEALTH_N:]
            health = (sum(recent) / len(recent)) if recent else None
            use_s4 = health is not None and health < HEALTH_THRESH
            pos = new_position(code, o, shares, shares * o,
                               mode='S4' if use_s4 else 'S3', score=item.get('score', 0.0))
            pos['name'] = item['name']
            pos['buy_date'] = d
            # 买入当天推进一次 hold_day（COUNT_ENTRY_DAY，当日不可卖）
            step_exit(pos, h, l, o, c, False, p.loss_hard_start_day, p.loss_hard_pct)
            st['positions'].append(pos)
            acted.append('买入 %s %s @%.3f ×%d (%.0f元)' % (code, item['name'], o, shares, shares * o))
            _append_csv(TRADES, ['date', 'side', 'code', 'name', 'price', 'shares', 'amount', 'reason'],
                        [d, 'BUY', code, item['name'], '%.3f' % o, shares, '%.2f' % (shares * o), '信号买入'])
        st['pending'] = still

        # ---- 2. 出场：老仓按当日 OHLC 跑 step_exit ----
        for pos in list(st['positions']):
            if pos['buy_date'] == d:
                continue                                       # T+1：当天买入不卖
            b = bar(pos['code'], d)
            if not b:
                continue
            o, h, l, c, pc = b
            res = step_exit(pos, h, l, o, c, True, p.loss_hard_start_day, p.loss_hard_pct)
            if res:
                price, reason = res
                proceeds = pos['shares'] * price - sell_fees(pos['code'], price, pos['shares'])
                ret = (proceeds - pos['cost']) / pos['cost'] * 100.0 if pos['cost'] > 0 else 0.0
                st.setdefault('closed', []).append(ret)      # 供 S3/S4 健康度判定
                st['cash'] += proceeds
                st['positions'].remove(pos)
                acted.append('卖出 %s %s @%.3f ×%d [%s]' % (pos['code'], pos['name'], price, pos['shares'], reason))
                _append_csv(TRADES, ['date', 'side', 'code', 'name', 'price', 'shares', 'amount', 'reason'],
                            [d, 'SELL', pos['code'], pos['name'], '%.3f' % price, pos['shares'],
                             '%.2f' % (pos['shares'] * price), reason])

        # ---- 3. 收盘 mark-to-market ----
        mkt = 0.0
        for pos in st['positions']:
            cc = close_of(pos['code'], d)
            mkt += pos['shares'] * (cc if cc else pos['entry'])
        equity = st['cash'] + mkt
        st['history'].append(dict(date=d, cash=round(st['cash'], 2), mkt_value=round(mkt, 2),
                                  equity=round(equity, 2),
                                  ret_vs_start=round(equity / st['start_capital'] - 1, 6),
                                  n_pos=len(st['positions'])))
        _append_csv(LEDGER, ['date', 'cash', 'mkt_value', 'equity', 'ret_vs_start', 'n_pos'],
                    [d, '%.2f' % st['cash'], '%.2f' % mkt, '%.2f' % equity,
                     '%.4f' % (equity / st['start_capital'] - 1), len(st['positions'])])
        st['last_day'] = d
        print('[%s] %s | 权益 %.0f (%.2f%%) 持仓%d'
              % (d, ' ; '.join(acted) if acted else '无操作', equity,
                 (equity / st['start_capital'] - 1) * 100, len(st['positions'])))

    save_state(st, args.state)
    cmd_status(args)


def _next_day(s):
    from datetime import date, timedelta
    d = date.fromisoformat(s) + timedelta(days=1)
    return d.isoformat()


def cmd_status(args):
    st = load_state(args.state)
    last = st['history'][-1] if st['history'] else None
    eq = last['equity'] if last else st['start_capital']
    print('\n' + '=' * 70)
    print('Hoshi-cplus 邮件模拟账户   起始 %.0f 元 @ %s   最新日 %s'
          % (st['start_capital'], st['start_date'], st['last_day'] or '（未开始）'))
    print('现金 %.2f | 持仓市值 %.2f | **总权益 %.2f** | 累计 **%+.2f%%**'
          % (st['cash'], eq - st['cash'], eq, (eq / st['start_capital'] - 1) * 100))
    print('-' * 70)
    if not st['positions']:
        print('持仓：空仓')
    else:
        print('持仓 %d 只：' % len(st['positions']))
        for pos in st['positions']:
            c = close_of(pos['code'], st['last_day']) if st['last_day'] else pos['entry']
            pnl = (c / pos['entry'] - 1) * 100 if c else 0
            tag = ''
            if pos.get('armed'):
                trail = pos['peak'] * (1 - pos['trail_pct'] / 100.0)
                tag = ('准备卖出(止盈线%.3f)' % trail) if c <= trail else ('跟踪止盈中(线%.3f)' % trail)
            print('  %s %-8s %6d股 成本%.3f 现价%.3f 浮盈%+.2f%% 持%d天 %s'
                  % (pos['code'], pos.get('name', ''), pos['shares'], pos['entry'], c, pnl,
                     pos['hold_day'], tag))
    if st['pending']:
        print('待买入（下一交易日）：%s' % ', '.join('%s %s' % (x['code'], x['name']) for x in st['pending']))
    print('=' * 70)


def cmd_capital(args):
    """资金池管理：重置基准（剔除未投入本策略的资金）/ 追加资金。"""
    st = load_state(args.state)
    if args.rebase:
        eq = st['history'][-1]['equity'] if st['history'] else st['cash']
        old = st['start_capital']
        st['start_capital'] = round(eq, 2)
        st.setdefault('baseline_resets', []).append(
            dict(date=st.get('last_day'), frm=old, to=st['start_capital']))
        save_state(st, args.state)
        print('基准重置：起始本金 %.2f → %.2f（= 当前资金池权益，剔除未投入本策略的资金）'
              % (old, st['start_capital']))
    if args.add:
        amt = float(args.add)
        st['cash'] += amt
        st['start_capital'] += amt
        save_state(st, args.state)
        print('追加资金 %.2f → 现金 %.2f，起始本金 %.2f'
              % (amt, st['cash'], st['start_capital']))
    cmd_status(args)


def main():
    ap = argparse.ArgumentParser(description='Hoshi-cplus 邮件驱动纸面交易模拟')
    ap.add_argument('--state', default=DEFAULT_STATE)
    ap.add_argument('--preset', default='cplus')
    sub = ap.add_subparsers(dest='cmd', required=True)

    a = sub.add_parser('init'); a.add_argument('--capital', type=float, default=300000.0)
    a.add_argument('--start', required=True); a.set_defaults(func=cmd_init)

    a = sub.add_parser('set-pending'); a.add_argument('--for', dest='for_day', required=True)
    a.add_argument('items'); a.set_defaults(func=cmd_set_pending)

    a = sub.add_parser('run'); a.add_argument('day'); a.set_defaults(func=cmd_run)

    a = sub.add_parser('status'); a.set_defaults(func=cmd_status)

    a = sub.add_parser('capital', help='资金池：重置基准 / 追加资金')
    a.add_argument('--rebase', action='store_true',
                   help='把起始本金重置为当前资金池权益（剔除未投入本策略的资金）')
    a.add_argument('--add', type=float, default=0.0, help='追加资金（现金与起始本金同增）')
    a.set_defaults(func=cmd_capital)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
