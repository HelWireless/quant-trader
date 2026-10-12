# -*- coding: utf-8 -*-
"""把纸面模拟账户与**真实成交**对账（mirror 模式）。

用途：邮件里的信号是「计划」，真实账户会因为资金/挂单/情绪等原因没买成、少买、
或者买在不同价位。本脚本把 state.json 的持仓/成本改写成**实际成交**，
并重算现金、当日权益、台账与流水。

口径
----
- `--positions` 里给出的持仓是**当前实际全部持仓**（本策略口径内的），authoritative。
- 每只可带建仓日：`代码:名称:股数:成本价[:建仓日]`；省略则默认 = `--day`。
- 持仓的 hold_day / peak / trough / armed 由**从建仓日到 --day 逐日重放 K 线**得出，
  与引擎口径一致（建仓日当天推进一次 hold_day，回放时不允许卖出）。
- `--sells` 登记**当日卖出**（`代码:名称:成交价:股数[:原因]`）——不登记就会丢流水、算错现金。
- 现金 = 起始本金 + 历史卖出净额 + 当日卖出净额 − 非本次持仓的历史买入净额 − 本次持仓买入成本。
  （即：不在此次清单里的标的，其买入/卖出一进一出只留下已实现盈亏。）

用法
----
  python hoshi_cplus/sim/resync.py --day 2026-09-16 \
      --positions "002365:永安药业:1900:14.302:2026-09-15,\
300901:中胤时尚:1500:18.593:2026-09-15,\
002631:德尔未来:2400:10.732,300647:超频三:3500:7.761,301216:万凯新材:1500:17.343" \
      --note "按实盘成交对账"

  # 当日有卖出时，必须用 --sells 显式登记（--positions 只表达对账后仍持有的仓位）
  python hoshi_cplus/sim/resync.py --day 2026-09-21 \
      --positions "002365:永安药业:1900:14.302:2026-09-15,..." \
      --sells "300647:超频三:8.14:3500,300901:中胤时尚:17.71:1500" \
      --cash 95013.71 --mode S4 --note "09-21 早盘卖出对账"

  --positions 传空串表示当日空仓（全部未买成）。
  --sells 传空串表示当日无卖出。
  本脚本**幂等**：同一天重复跑会用 --positions/--sells 完全重建该日的持仓、流水与台账行，
  因此**收盘后再跑一次即可把盘中的临时估值刷成收盘口径**。
  对账记录追加到 reconcile.csv。
"""
import argparse
import csv
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.config import get_preset
from hoshi_cplus.exits import new_position, step_exit
from hoshi_cplus.sim.mail_trader import (buy_fees, sell_fees, bar, close_of,
                                         trading_days, load_state, save_state,
                                         _append_csv)

LEDGER = os.path.join(_HERE, 'ledger.csv')
TRADES = os.path.join(_HERE, 'trades.csv')
RECON = os.path.join(_HERE, 'reconcile.csv')

T_HEADER = ['date', 'side', 'code', 'name', 'price', 'shares', 'amount', 'reason']
L_HEADER = ['date', 'cash', 'mkt_value', 'equity', 'ret_vs_start', 'n_pos']


def parse_spec(s, default_day):
    out = []
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        f = part.split(':')
        code, name, shares, entry = f[0].strip(), f[1].strip(), int(f[2]), float(f[3])
        bdate = f[4].strip() if len(f) > 4 and f[4].strip() else default_day
        out.append((code, name, shares, entry, bdate))
    return out


def parse_sells(s):
    """解析当日卖出：`代码:名称:成交价:股数[:原因]`，逗号分隔。

    为什么需要它：`--positions` 只能表达"对账后仍持有的仓位"，
    当日的**卖出**不会体现在里面；不显式登记就会丢掉流水、也算不清现金。
    """
    out = []
    if not s:
        return out
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        f = part.split(':')
        code, name = f[0].strip(), f[1].strip()
        price, shares = float(f[2]), int(f[3])
        reason = f[4].strip() if len(f) > 4 and f[4].strip() else '实盘卖出(对账修正)'
        out.append((code, name, price, shares, reason))
    return out


def read_trades():
    if not os.path.exists(TRADES):
        return []
    with open(TRADES, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write_trades(rows):
    with open(TRADES, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(T_HEADER)
        for r in rows:
            w.writerow([r[k] for k in T_HEADER])


def write_ledger(history):
    with open(LEDGER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(L_HEADER)
        for h in history:
            w.writerow([h['date'], '%.2f' % h['cash'], '%.2f' % h['mkt_value'],
                        '%.2f' % h['equity'], '%.4f' % h['ret_vs_start'], h['n_pos']])


def rebuild_position(code, name, shares, entry, buy_date, day, preset, mode='S3'):
    """从建仓日回放到 day，得到与引擎一致持仓状态。"""
    pos = new_position(code, entry, shares, shares * entry, mode=mode)
    pos['name'] = name
    pos['buy_date'] = buy_date
    if buy_date > day:
        return pos
    for d in trading_days(buy_date, day):
        b = bar(code, d)
        if not b:
            continue
        o, h, l, c, pc = b
        step_exit(pos, h, l, o, c, d != buy_date,
                  preset.loss_hard_start_day, preset.loss_hard_pct)
    return pos


def main():
    ap = argparse.ArgumentParser(description='纸面模拟与真实成交对账')
    ap.add_argument('--day', required=True, help='对账基准交易日 YYYY-MM-DD')
    ap.add_argument('--positions', default='',
                    help='"代码:名称:股数:成本价[:建仓日]" 逗号分隔；空串=空仓')
    ap.add_argument('--sells', default='',
                    help='当日卖出 "代码:名称:成交价:股数[:原因]" 逗号分隔（当日卖出必须显式登记）')
    ap.add_argument('--preset', default='cplus')
    ap.add_argument('--mode', default='S3', choices=['S3', 'S4'],
                    help='给重建持仓的出场模式（S3=仅第14/15天检查武装；'
                         'S4=随时武装/吊灯止盈）。真实账户近期为亏损时用 S4。')
    ap.add_argument('--cash', type=float, default=None,
                    help='显式指定对账后的可用现金（覆盖按本金推算出的值；'
                         '用于真实账户部分资金被非本策略标的占用时）')
    ap.add_argument('--note', default='', help='对账原因，写入 reconcile.csv')
    args = ap.parse_args()

    p = get_preset(args.preset)
    day = args.day
    spec = parse_spec(args.positions, day)
    spec_codes = set(x[0] for x in spec)
    sells = parse_sells(args.sells)

    st = load_state()
    old_rows = read_trades()
    kept = [r for r in old_rows if r['date'] != day]
    real_dropped = [r for r in old_rows if r['date'] == day]

    # ---- 1. 现金 ----
    cash = st['start_capital']
    for r in kept:
        amt = float(r['amount'])
        if r['side'] == 'SELL':
            cash += amt - sell_fees(r['code'], float(r['price']), int(r['shares']))
        elif r['side'] == 'BUY' and r['code'] not in spec_codes:
            cash -= amt + buy_fees(r['code'], float(r['price']), int(r['shares']))
    # 当日卖出：卖出净额进现金；其原始买入成本已在上面的 kept 里被扣过
    for code, name, price, shares, _reason in sells:
        cash += shares * price - sell_fees(code, price, shares)

    # ---- 2. 重建持仓 + 本日买入流水 ----
    positions, new_rows = [], []
    for code, name, shares, entry, bdate in spec:
        fee = buy_fees(code, entry, shares)
        cash -= shares * entry + fee
        pos = rebuild_position(code, name, shares, entry, bdate, day, p, args.mode)
        positions.append(pos)
        print('  %s %-8s %5d股 @%.3f  建仓%s  持%d天  peak%.3f trough%.3f'
              % (code, name, shares, entry, bdate, pos['hold_day'],
                 pos['peak'], pos['trough']))
        if bdate == day:
            new_rows.append(dict(date=day, side='BUY', code=code, name=name,
                                 price='%.3f' % entry, shares=str(shares),
                                 amount='%.2f' % (shares * entry),
                                 reason='信号买入(对账修正)'))

    # ---- 2.5 显式现金覆盖（真实账户部分资金被非本策略标的占用时用） ----
    if args.cash is not None:
        cash = args.cash

    # ---- 2.6 当日卖出流水 ----
    sell_rows = []
    for code, name, price, shares, reason in sells:
        net = shares * price - sell_fees(code, price, shares)
        sell_rows.append(dict(date=day, side='SELL', code=code, name=name,
                              price='%.3f' % price, shares=str(shares),
                              amount='%.2f' % (shares * price), reason=reason))
        print('  卖出 %s %-8s %5d股 @%.3f  净额 %.2f  [%s]' % (code, name, shares, price, net, reason))

    # ---- 3. 收盘 mark-to-market ----
    mkt = 0.0
    for pos in positions:
        cc = close_of(pos['code'], day)
        mkt += pos['shares'] * (cc if cc else pos['entry'])
    equity = cash + mkt

    # ---- 4. 落盘 ----
    write_trades(kept + new_rows + sell_rows)
    hist = [h for h in st['history'] if h['date'] != day]
    hist.append(dict(date=day, cash=round(cash, 2), mkt_value=round(mkt, 2),
                     equity=round(equity, 2),
                     ret_vs_start=round(equity / st['start_capital'] - 1, 6),
                     n_pos=len(positions)))
    hist.sort(key=lambda x: x['date'])
    st['history'] = hist
    st['positions'] = positions
    st['cash'] = cash
    st['pending'] = []                      # 对账即视为当日信号已处理完
    if st.get('last_day') is None or st['last_day'] < day:
        st['last_day'] = day
    save_state(st)
    write_ledger(hist)

    print()
    for r in real_dropped:
        print('  撤销原记录 %s %s %s %s股 @%s' % (r['date'], r['side'], r['code'],
                                                  r['shares'], r['price']))
    if args.note:
        detail = args.positions or '（空仓）'
        if args.sells:
            detail += ' | 卖出: ' + args.sells
        _append_csv(RECON, ['ts', 'day', 'action', 'detail', 'note'],
                    [datetime.datetime.now().isoformat(timespec='seconds'),
                     day, 'RESYNC', detail, args.note])
    print('对账完成：现金 %.2f | 市值 %.2f | 权益 %.2f (%+.2f%%) | 持仓 %d'
          % (cash, mkt, equity, (equity / st['start_capital'] - 1) * 100, len(positions)))


if __name__ == '__main__':
    main()
