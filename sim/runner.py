# -*- coding: utf-8 -*-
"""双系统模拟交易 —— 驱动层。

逐日把系统 A 与系统 B 串起来：
    T 日盘前  A.before_open()  -> 委托
    T 日收盘  B.execute()      -> 回报（含偏差）
              A.after_close()  -> 更新账本
            净值由驱动层用当日收盘价独立计算（不参与 A 的决策）

用法：
    python -m sim.runner --data scripts/hoshi_csv_2005 \
        --start 2020-01-20 --end 2026-09-01 --capital 300000
"""
import argparse
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hoshi_cplus.data import load_data, precompute          # noqa: E402
from sim.broker_sim import BrokerSim                        # noqa: E402
from sim.protocol import DEV_LABELS                         # noqa: E402
from sim.strategy_sys import StrategySystem                 # noqa: E402


def run_simulation(prepared, code_bars, names, start, end, capital=300000.0,
                   biased=True, seed=20260913, preset='cplus', collect=True):
    A = StrategySystem(prepared, code_bars, names, preset=preset, capital=capital)
    B = BrokerSim(code_bars, seed=seed, biased=biased)

    dates = [d for d in A.dates if start <= d <= end]
    if not dates:
        raise SystemExit('区间内无交易日')

    idx = A.idx_of
    equity_curve = []
    n_orders = 0
    for today in dates:
        orders = A.before_open(today)
        n_orders += len(orders)
        reps = B.execute(orders, today)
        reps = [r for r in reps if r is not None]
        A.after_close(reps)
        A.end_of_day(today)

        # 净值：用当日收盘价（驱动层视角，不回流给 A）
        mv = 0.0
        for code, pos in A.positions.items():
            k = idx[code].get(today)
            if k is None:
                px = pos['entry']
            else:
                px = code_bars[code][k].close
            mv += pos['shares'] * px
        equity_curve.append(dict(date=today, cash=A.cash, mv=mv,
                                 equity=A.cash + mv, n_pos=len(A.positions)))

    A.force_close(dates[-1])
    final = A.cash
    return dict(
        A=A, B=B, equity_curve=equity_curve, dates=dates,
        init_capital=capital, final_capital=final,
        ret=(final - capital) / capital * 100.0,
        n_orders=n_orders, biased=biased, seed=seed, preset=preset,
    )


def _dump_trades(res, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['date', 'code', 'name', 'side', 'price', 'shares', 'amount',
                    'fee', 'deviation', 'reason', 'pnl', 'ret_pct'])
        for t in res['A'].trade_log:
            w.writerow([t['date'], t['code'], t.get('name', ''), t['side'],
                        t['price'], t['shares'], round(t['amount'], 2),
                        round(t['fee'], 2), t['deviation'], t['reason'],
                        t['pnl'], t['ret']])


def _dump_equity(res, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['date', 'cash', 'market_value', 'equity', 'n_pos'])
        for r in res['equity_curve']:
            w.writerow([r['date'], round(r['cash'], 2), round(r['mv'], 2),
                        round(r['equity'], 2), r['n_pos']])


def _summary(res, tag):
    eq = [r['equity'] for r in res['equity_curve']]
    peak = eq[0]
    mdd = 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, (v - peak) / peak * 100.0)
    trades = res['A'].trade_log
    sells = [t for t in trades if t['side'] == 'SELL' and t.get('ret') not in ('', None)]
    wins = sum(1 for t in sells if float(t['ret']) > 0)
    return dict(
        tag=tag, biased=res['biased'], final=res['final_capital'],
        ret=res['ret'], mdd=mdd, n_buy=sum(1 for t in trades if t['side'] == 'BUY'),
        n_sell=len(sells),
        win_rate=(100.0 * wins / len(sells)) if sells else 0.0,
        avg_ret=(sum(float(t['ret']) for t in sells) / len(sells)) if sells else 0.0,
        n_orders=res['n_orders'], dev_stats=dict(res['B'].stats),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(prog='sim.runner', description='hoshi-cplus 双系统模拟')
    ap.add_argument('--data', default='scripts/hoshi_csv_2005')
    ap.add_argument('--start', default='2020-01-20')
    ap.add_argument('--end', default='2026-09-01')
    ap.add_argument('--capital', type=float, default=300000.0)
    ap.add_argument('--preset', default='cplus')
    ap.add_argument('--seed', type=int, default=20260913)
    ap.add_argument('--outdir', default='sim_out')
    ap.add_argument('--no-baseline', action='store_true', help='不跑无偏差对照组')
    args = ap.parse_args(argv)

    s = date.fromisoformat(args.start)
    e = date.fromisoformat(args.end)

    print('加载数据: %s' % args.data, flush=True)
    code_bars, names = load_data(args.data)
    print('  标的数 %d' % len(code_bars), flush=True)
    prepared = precompute(code_bars)

    os.makedirs(args.outdir, exist_ok=True)

    print('\n[1/2] 有偏差模拟（20%% 异常）...', flush=True)
    r_biased = run_simulation(prepared, code_bars, names, s, e,
                              capital=args.capital, biased=True, seed=args.seed,
                              preset=args.preset)
    _dump_trades(r_biased, os.path.join(args.outdir, 'trades_biased.csv'))
    _dump_equity(r_biased, os.path.join(args.outdir, 'equity_biased.csv'))
    sb = _summary(r_biased, '有偏差')
    print('     期末资金 %.0f  收益率 %+.2f%%  最大回撤 %.2f%%  交易 %d 笔'
          % (sb['final'], sb['ret'], sb['mdd'], sb['n_sell']), flush=True)

    results = [sb]
    if not args.no_baseline:
        print('\n[2/2] 无偏差对照组（理想执行）...', flush=True)
        r_ideal = run_simulation(prepared, code_bars, names, s, e,
                                 capital=args.capital, biased=False, seed=args.seed,
                                 preset=args.preset)
        _dump_trades(r_ideal, os.path.join(args.outdir, 'trades_ideal.csv'))
        _dump_equity(r_ideal, os.path.join(args.outdir, 'equity_ideal.csv'))
        si = _summary(r_ideal, '无偏差')
        print('     期末资金 %.0f  收益率 %+.2f%%  最大回撤 %.2f%%  交易 %d 笔'
              % (si['final'], si['ret'], si['mdd'], si['n_sell']), flush=True)
        results.append(si)

    # ---- 报告 ----
    lines = []
    W = lines.append
    W('# hoshi-cplus 双系统模拟交易结果')
    W('')
    W('- 区间：%s ~ %s' % (args.start, args.end))
    W('- 初始资金：%.0f' % args.capital)
    W('- 方案：%s（%s）' % (args.preset, '有偏差' if True else ''))
    W('- 随机种子：%d' % args.seed)
    W('')
    W('| 版本 | 期末资金 | 收益率 | 最大回撤 | 买入 | 卖出 | 胜率 | 平均单笔 |')
    W('|---|---:|---:|---:|---:|---:|---:|---:|')
    for r in results:
        W('| %s | %.0f | %+.2f%% | %.2f%% | %d | %d | %.1f%% | %+.2f%% |'
          % (r['tag'], r['final'], r['ret'], r['mdd'], r['n_buy'], r['n_sell'],
             r['win_rate'], r['avg_ret']))
    if len(results) == 2:
        loss = results[1]['final'] - results[0]['final']      # 理想 − 有偏差 = 执行损耗
        W('')
        W('**执行偏差的代价：%.0f 元**（理想执行 %.0f → 有偏差 %.0f）'
          % (loss, results[1]['final'], results[0]['final']))
        if loss < 0:
            W('')
            W('> ⚠️ 出现「有偏差反而更好」，短区间 + 小样本时可能是随机波动；'
              '也需检查偏差概率是否被好运气方向主导。')
    W('')
    W('## 偏差统计（有偏差版）')
    W('')
    W('| 类型 | 次数 |')
    W('|---|---:|')
    for k, v in sorted(sb['dev_stats'].items(), key=lambda x: -x[1]):
        W('| %s | %d |' % (DEV_LABELS.get(k, k), v))
    W('')

    txt = '\n'.join(lines)
    print('\n' + txt)
    with open(os.path.join(args.outdir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(txt + '\n')
    print('\n输出目录: %s' % args.outdir)


if __name__ == '__main__':
    main()
