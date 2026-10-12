# -*- coding: utf-8 -*-
"""纸面模拟绩效统计：从 trades.csv + ledger.csv + state.json 算净口径指标。

用于日报/月报。所有 P&L 用 mail_trader 自带的手续费模型（买入：佣金(含最低5元)+过户费；
卖出：佣金+印花税+过户费），与引擎口径一致。

用法
----
  python hoshi_cplus/sim/pnl_report.py
  python hoshi_cplus/sim/pnl_report.py --from 2026-09-15 --to 2026-09-30
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.sim.mail_trader import buy_fees, sell_fees  # noqa: E402

SIM = os.path.join(_ROOT, 'hoshi_cplus', 'sim')


def load_trades():
    rows = []
    with open(os.path.join(SIM, 'trades.csv'), encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            r['price'] = float(r['price'])
            r['shares'] = int(r['shares'])
            r['amount'] = float(r['amount'])
            rows.append(r)
    return rows


def load_ledger():
    rows = []
    with open(os.path.join(SIM, 'ledger.csv'), encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            rows.append(dict(date=r['date'], cash=float(r['cash']),
                             mkt=float(r['mkt_value']), equity=float(r['equity']),
                             ret=float(r['ret_vs_start']), n=int(r['n_pos'])))
    return rows


def load_state():
    with open(os.path.join(SIM, 'state.json'), encoding='utf-8') as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='frm', default=None)
    ap.add_argument('--to', dest='to', default=None)
    args = ap.parse_args()

    st = load_state()
    trades = load_trades()
    ledger = load_ledger()
    if args.frm:
        trades = [t for t in trades if t['date'] >= args.frm]
    if args.to:
        trades = [t for t in trades if t['date'] <= args.to]

    # 配对：按 code FIFO 匹配 BUY -> SELL
    lots = defaultdict(list)
    rt = []                      # round trips
    for t in trades:
        if t['side'] == 'BUY':
            net = t['amount'] + buy_fees(t['code'], t['price'], t['shares'])
            lots[t['code']].append(dict(code=t['code'], name=t['name'], date=t['date'],
                                        price=t['price'], shares=t['shares'], cost=net))
        else:
            qty = t['shares']
            proceeds = t['amount'] - sell_fees(t['code'], t['price'], t['shares'])
            while qty > 0 and lots[t['code']]:
                lot = lots[t['code']][0]
                take = min(qty, lot['shares'])
                c = lot['cost'] * take / lot['shares']
                p = proceeds * take / qty
                rt.append(dict(code=t['code'], name=t['name'], buy_date=lot['date'],
                               sell_date=t['date'], buy=lot['price'], sell=t['price'],
                               shares=take, pnl=p - c, pct=(p / c - 1) * 100.0,
                               reason=t['reason']))
                lot['shares'] -= take
                lot['cost'] -= c
                if lot['shares'] <= 0:
                    lots[t['code']].pop(0)
                qty -= take

    print('=' * 78)
    print('纸面模拟绩效统计   区间：%s ~ %s' % (args.frm or '起始', args.to or '最新'))
    print('=' * 78)
    print('已平仓 %d 笔：' % len(rt))
    print('  %-10s %-8s %-10s %-10s %8s %8s %9s  %s'
          % ('买入日', '卖出日', '代码', '名称', '买入', '卖出', '净收益%', '原因'))
    for r in rt:
        print('  %-10s %-8s %-10s %-8s %8.3f %8.3f %+8.2f%%  %s'
              % (r['buy_date'], r['sell_date'], r['code'], r['name'],
                 r['buy'], r['sell'], r['pct'], r['reason']))

    if rt:
        wins = [r for r in rt if r['pnl'] > 0]
        total = sum(r['pnl'] for r in rt)
        navg = sum(r['pct'] for r in rt) / len(rt)
        print('-' * 78)
        print('  累计已实现净盈亏 : %+.2f 元' % total)
        print('  胜率             : %d/%d = %.1f%%' % (len(wins), len(rt),
                                                     100.0 * len(wins) / len(rt)))
        print('  平均每笔净收益   : %+.2f%%' % navg)
        print('  最好 / 最差      : %+.2f%% / %+.2f%%'
              % (max(r['pct'] for r in rt), min(r['pct'] for r in rt)))
        print('  平均盈利 / 平均亏损: %+.2f%% / %+.2f%%'
              % (sum(r['pct'] for r in wins) / len(wins),
                 sum(r['pct'] for r in rt if r['pnl'] <= 0) /
                 max(1, len(rt) - len(wins))))

    # 权益曲线
    eqs = [l['equity'] for l in ledger]
    base = st.get('start_capital', 0)

    def _mdd(seq):
        pk = seq[0] if seq else 0
        m = 0.0
        for e in seq:
            pk = max(pk, e)
            if pk > 0:
                m = min(m, e / pk - 1)
        return m

    # 资金池曾被 rebase（划出资金 ⇒ 权益断崖），必须分段算回撤，否则出现假"巨额回撤"
    segs, cur = [], []
    for l in ledger:
        if cur and l['equity'] < cur[-1]['equity'] * 0.8:
            segs.append(cur)
            cur = []
        cur.append(l)
    if cur:
        segs.append(cur)
    segs = [s for s in segs if len(s) >= 2] or ([ledger] if ledger else [])

    mdd_all = _mdd(eqs)
    # 同口径段：取最后一段（与当前池基准一致）
    same = segs[-1] if segs else []
    mdd_same = _mdd([l['equity'] for l in same]) if same else 0.0

    print('-' * 78)
    print('  起始(池基准)     : %.2f 元' % base)
    print('  期末总权益       : %.2f 元' % (eqs[-1] if eqs else 0))
    print('  累计收益率       : %+.2f%%' % ((eqs[-1] / base - 1) * 100 if eqs and base else 0))
    print('  最大回撤(全序列) : %.2f%%  ← 含资金池 rebase 断崖，非真实回撤' % (mdd_all * 100))
    if same:
        print('  最大回撤(同口径) : %.2f%%  （%s ~ %s，rebase 之后）'
              % (mdd_same * 100, same[0]['date'], same[-1]['date']))
    print('  台账天数         : %d' % len(ledger))
    print('\n  逐日权益曲线：')
    for l in ledger:
        bar = '#' * max(0, int((l['equity'] / base - 1) * 200)) if base else ''
        print('    %s  %10.2f  %+6.2f%%  %s' % (l['date'], l['equity'], l['ret'] * 100, bar))
    return 0


if __name__ == '__main__':
    sys.exit(main())
