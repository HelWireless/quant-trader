# -*- coding: utf-8 -*-
"""汇总 hoshi 邮件纸面模拟结果，导出 Markdown 报告 + 逐笔收益 CSV。

用法：
  python hoshi_cplus/sim/report.py                       # → sim/report.md + sim/trades_paired.csv
  python hoshi_cplus/sim/report.py --out xxx.md --csv yyy.csv
"""
import argparse
import csv
import datetime
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(_HERE, 'state.json')
LEDGER = os.path.join(_HERE, 'ledger.csv')
TRADES = os.path.join(_HERE, 'trades.csv')


def load_csv(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def pair_trades(rows):
    """把买入/卖出发水按"同代码开仓→平仓"配对，返回 [(buy, sell), ...]。"""
    open_buys = {}
    closed = []
    for r in rows:
        if r['side'] == 'BUY':
            open_buys[r['code']] = r
        elif r['side'] == 'SELL' and r['code'] in open_buys:
            closed.append((open_buys.pop(r['code']), r))
    return closed, open_buys


def mdd(series):
    """series: [(date, equity)] 按日期升序 → (最大回撤%, 峰值日, 谷值日)"""
    peak, peak_d = None, None
    worst, wd = 0.0, None
    for d, v in series:
        if peak is None or v > peak:
            peak, peak_d = v, d
        if peak > 0:
            dd = v / peak - 1
            if dd < worst:
                worst, wd = dd, d
    return worst * 100, peak_d, wd


def main():
    ap = argparse.ArgumentParser(description='导出 hoshi 模拟结果报告')
    ap.add_argument('--out', default=os.path.join(_HERE, 'report.md'))
    ap.add_argument('--csv', default=os.path.join(_HERE, 'trades_paired.csv'))
    args = ap.parse_args()

    st = json.load(open(STATE, encoding='utf-8'))
    ledger = load_csv(LEDGER)
    trades = load_csv(TRADES)
    closed, open_buys = pair_trades(trades)

    # ---- 逐笔收益 ----
    rows = []
    for b, s in closed:
        bp, sp = float(b['price']), float(s['price'])
        sh = int(s['shares'])
        ret = (sp / bp - 1) * 100.0
        rows.append(dict(code=b['code'], name=b['name'], buy_date=b['date'], buy_price=bp,
                         sell_date=s['date'], sell_price=sp, shares=sh,
                         pnl=(sp - bp) * sh, ret=ret, reason=s['reason']))
    rows.sort(key=lambda x: x['sell_date'])
    wins = [r for r in rows if r['ret'] > 0]
    losses = [r for r in rows if r['ret'] <= 0]
    tot = sum(r['ret'] for r in rows)
    win_avg = sum(r['ret'] for r in wins) / len(wins) if wins else 0.0
    loss_avg = sum(r['ret'] for r in losses) / len(losses) if losses else 0.0
    ratio = (win_avg / abs(loss_avg)) if loss_avg else float('inf')
    net_pnl = sum(r['pnl'] for r in rows)

    with open(args.csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['code', 'name', 'buy_date', 'buy_price', 'sell_date', 'sell_price',
                    'shares', 'pnl', 'ret_pct', 'reason'])
        for r in rows:
            w.writerow([r['code'], r['name'], r['buy_date'], '%.3f' % r['buy_price'],
                        r['sell_date'], '%.3f' % r['sell_price'], r['shares'],
                        '%.2f' % r['pnl'], '%.2f' % r['ret'], r['reason']])

    # ---- 权益曲线 ----
    series = [(h['date'], float(h['equity'])) for h in ledger]
    start_cap = st['start_capital']
    cur = series[-1][1] if series else start_cap
    ret_all = (cur / start_cap - 1) * 100 if start_cap else 0.0
    # 资金池重置会造成权益跳变（不是亏损），最大回撤只按"当前资金池段"算
    resets = st.get('baseline_resets', [])
    seg_start = resets[-1]['date'] if resets else None
    seg = [(d, v) for d, v in series if (seg_start is None or d >= seg_start)]
    d, peak_d, trough_d = mdd(seg)
    mdd_label = '当前资金池段（%s 起）' % seg_start if seg_start else '全区间'
    n_buy = sum(1 for t in trades if t['side'] == 'BUY')

    # ---- 报告 ----
    L = []
    A = L.append
    A('# Hoshi-cplus 邮件纸面模拟 · 结果报告')
    A('')
    A('> 生成时间：%s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    A('> 数据区间：%s ~ %s（台账最后处理日）' % (ledger[0]['date'] if ledger else '-', ledger[-1]['date'] if ledger else '-'))
    A('> 信号来源：QQ 邮件「Hoshi实盘」每日指导（自发邮件，2587225803@qq.com）')
    A('')
    A('## 一、账户概况')
    A('')
    A('| 项 | 值 |')
    A('|---|---|')
    A('| 起始资金池（2026-09-18 重置后） | **%.0f** 元 |' % start_cap)
    A('| 期末权益 | **%.2f** 元 |' % cur)
    A('| **累计收益率** | **%+.2f%%** |' % ret_all)
    A('| 净盈亏（已平仓） | %+.2f 元 |' % net_pnl)
    A('| 期间买入 / 卖出 | %d 笔 / %d 笔 |' % (n_buy, len(closed)))
    A('| 期间最大回撤（%s） | **%.2f%%** |' % (mdd_label, d))
    A('| 期末持仓 | %d 只 |' % len(st['positions']))
    A('| 期末可用现金 | %.2f 元 |' % st['cash'])
    A('')
    A('## 二、逐日权益曲线')
    A('')
    A('| 日期 | 现金 | 持仓市值 | 权益 | 收益率 | 持仓数 |')
    A('|---|---:|---:|---:|---:|---:|')
    for h in ledger:
        A('| %s | %s | %s | %s | %+.2f%% | %s |'
          % (h['date'], h['cash'], h['mkt_value'], h['equity'],
             float(h['ret_vs_start']) * 100, h['n_pos']))
    A('')
    A('> ⚠️ 2026-09-18 行是**资金池重置点**（起始 30 万 → %.0f，剔除被非策略标的占用的约 9.7 万）；'
      '该行的 -32.3%% 是旧口径残值，**不是亏损**。' % start_cap)
    A('')
    A('## 三、逐笔平仓明细')
    A('')
    A('| 代码 | 名称 | 买入日 | 买价 | 卖出日 | 卖价 | 股数 | 盈亏 | 收益率 | 原因 |')
    A('|---|---|---|---:|---|---:|---:|---:|---:|---|')
    for r in rows:
        A('| %s | %s | %s | %.3f | %s | %.3f | %d | %+.0f | %+.2f%% | %s |'
          % (r['code'], r['name'], r['buy_date'], r['buy_price'], r['sell_date'],
             r['sell_price'], r['shares'], r['pnl'], r['ret'], r['reason']))
    A('')
    A('## 四、统计')
    A('')
    A('| 指标 | 值 |')
    A('|---|---|')
    A('| 平仓笔数 | %d |' % len(rows))
    A('| 盈利 / 亏损 | %d / %d |' % (len(wins), len(losses)))
    A('| **胜率** | **%.1f%%** |' % (100.0 * len(wins) / len(rows) if rows else 0))
    A('| 平均每笔收益 | %+.2f%% |' % (tot / len(rows) if rows else 0))
    A('| 盈利笔均 | %+.2f%% |' % win_avg)
    A('| 亏损笔均 | %+.2f%% |' % loss_avg)
    A('| **盈亏比** | **%.2f** |' % ratio)
    A('')
    A('## 五、期末持仓 / 待买入')
    A('')
    if st['positions']:
        A('| 代码 | 名称 | 股数 | 成本 | 持有天数 |')
        A('|---|---|---:|---:|---:|')
        for p in st['positions']:
            A('| %s | %s | %d | %.3f | %d |' % (p['code'], p.get('name', ''), p['shares'],
                                                p['entry'], p['hold_day']))
    else:
        A('（空仓）')
    A('')
    if st.get('pending'):
        A('待买入（下一交易日）：%s' % ', '.join('%s %s' % (x['code'], x['name']) for x in st['pending']))
        A('')
    A('## 六、口径与注意事项')
    A('')
    A('- **实盘镜像口径**：账户跟踪你真实持仓（用 `resync.py` 对账），非纯策略模拟；'
      '要评估策略本身请另跑回测。')
    A('- **绝对收益不可信**：回测/模拟绝对值与实盘未对齐；本报告只看"买卖触发点"与账面。')
    A('- 模拟窗口前（2026-09-15 前）的历史亏损（青山 −17.19%、华钰 −6.03%）**已体现在资金池重置前的口径**，'
      '不重复计入本次收益率。')
    A('- 期间遇国庆中秋休市（10-01~10-07），10-08 恢复交易。')
    A('- 明细 CSV：`%s`' % os.path.basename(args.csv))
    A('')
    A('## 七、结论')
    A('')
    A('**截至 %s，资金池 %+.2f%%**（%.0f → %.2f 元），期间最大回撤 %.2f%%，'
      '平仓 %d 笔、胜率 %.1f%%、盈亏比 %.2f。'
      % (ledger[-1]['date'] if ledger else '-', ret_all, start_cap, cur, d,
         len(rows), 100.0 * len(wins) / len(rows) if rows else 0, ratio))
    A('')
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print('已导出报告：%s' % args.out)
    print('已导出逐笔 CSV：%s' % args.csv)
    print('\n'.join(L[-6:]))


if __name__ == '__main__':
    main()
