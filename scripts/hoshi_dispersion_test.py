# -*- coding: utf-8 -*-
"""
hoshi 分散约束(A方案)稳健性实验
================================
在同一份长历史数据上，随机抽取 5 个"节点"(起始年)，每节点连续跑 L 年，
对比不同"每日最多买入 N 只"上限下的最终权益/收益率/胜率等。

口径(唯一最终版, 与 hoshi_backtest_csv.py 一致)：
  - 信号收盘确认 -> D+1 开盘买入
  - MAX_SLOTS=10, 单股仓位<=权益10%
  - 广度门控 + R3 门控均开启
  - MAX_BUY_PER_DAY: 0=原版不限(同日信号全买), N>0=每日最多买N只(A方案)
用法:
  python hoshi_dispersion_test.py [--seed 7] [--windows 5] [--caps 0,3,5,8,10]
"""
import argparse, importlib.util, itertools, random, sys, time

SPEC_PATH = 'scripts/hoshi_backtest_limitn.py'
DATA_DIR = 'scripts/hoshi_csv_long'

spec = importlib.util.spec_from_file_location('hbl', SPEC_PATH)
hbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbl)
hbl._log = lambda *a, **k: None   # 静默

def _fmt_date(y, m, d):
    return '%04d-%02d-%02d' % (y, m, d)

def _analyze(res, init_cap):
    closed = res['closed']
    n = len(closed)
    wins = len([t for t in closed if t['pnl'] > 0])
    total_pnl = sum(t['pnl'] for t in closed)
    winrate = (wins * 100.0 / n) if n else None
    # 自然平仓(非"回测结束强平")口径
    nat = [t for t in closed if t['exit_reason'] != '回测结束强平']
    n_nat = len(nat)
    nat_pnl = sum(t['pnl'] for t in nat)
    # 最大回撤(逐日权益近似, 以现金+持仓市值估算)
    return dict(
        final=res['final_capital'],
        ret=(res['final_capital'] - init_cap) / init_cap * 100.0,
        n=n, wins=wins, winrate=winrate,
        total_pnl=total_pnl,
        n_nat=n_nat, nat_pnl=nat_pnl,
        skipped=res['skipped'], n_s4=res['n_s4'], stops=len(res['stops']),
    )

def run_one(code_bars, names, all_dates, start, end, cap, init_cap):
    hbl.TOTAL_CAPITAL = init_cap
    hbl.MAX_SLOTS = 10
    hbl.MAX_BUY_PER_DAY = cap
    t0 = time.time()
    res = hbl.run_backtest(code_bars, names, all_dates, start=start, end=end)
    a = _analyze(res, init_cap)
    a['secs'] = time.time() - t0
    return a

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--windows', type=int, default=5, help='随机节点数')
    ap.add_argument('--caps', default='0,3,5,8,10', help='每日限买N的档位(0=原版不限)')
    ap.add_argument('--unique', action='store_true', help='强制各窗口互不重叠(避免重复计权)')
    args = ap.parse_args()
    caps = [int(x) for x in args.caps.split(',')]

    random.seed(args.seed)

    print('加载数据 ...', flush=True)
    t0 = time.time()
    code_bars, names, all_dates = hbl.load_data(DATA_DIR)
    print('load_data %.1fs | 标的%d 交易日%d 区间%s~%s'
          % (time.time()-t0, len(code_bars), len(all_dates), all_dates[0], all_dates[-1]), flush=True)

    DATA_END_Y = 2026
    DATA_START_Y = 2010
    MIN_WARM = 0.5        # 起点前至少留0.5年做指标预热(数据2009-06起)

    # ---- 生成随机节点: (start_year, length_years) ----
    nodes = []
    years_pool = list(range(DATA_START_Y, DATA_END_Y))  # 2010..2025
    tried = 0
    while len(nodes) < args.windows and tried < 400:
        tried += 1
        L = random.choice([2, 3, 4, 5])
        # 终点尽量靠近"到现在"(2026), 在 [start+L, 2026] 内随机定终点年, 反推起点
        end_year = random.randint(DATA_START_Y + L, DATA_END_Y)  # 最少起点2010
        start_year = end_year - L
        if start_year < DATA_START_Y:
            continue
        if args.unique:
            # 区间重叠判定: 新窗 [start_year, end_year] 与已有窗不相交
            overlap = any(not (end_year < sy or start_year > ey) for (sy, L0, ey) in nodes)
            if overlap:
                continue
        nodes.append((start_year, L, end_year))
    # 若没凑够(极端, 无重叠可行解不足), 直接补一组(可能重叠)
    if len(nodes) < args.windows:
        for i, L in enumerate([2, 3, 4, 5][:args.windows - len(nodes)]):
            nodes.append((DATA_END_Y - L, L, DATA_END_Y))

    print('\n=== 随机节点(seed=%d) ===' % args.seed, flush=True)
    for i, (sy, L, ey) in enumerate(nodes):
        print(' 节点%d: %d-01-01 ~ %d-12-31 (跨度%d年)' % (i+1, sy, ey, L), flush=True)

    # ---- 逐节点逐档跑 ----
    all_rows = []
    for i, (sy, L, ey) in enumerate(nodes):
        start = _fmt_date(sy, 1, 1)
        end = _fmt_date(ey, 12, 31)
        if end > '2026-09-01':
            end = '2026-09-01'
        print('\n--- 节点%d  %s ~ %s ---' % (i+1, start, end), flush=True)
        for cap in caps:
            init_cap = 500000.0
            a = run_one(code_bars, names, all_dates, start, end, cap, init_cap)
            tag = ('原版(不限)' if cap == 0 else '限买%d只' % cap)
            print('  [%s] 终值¥%.0f  收益率%+6.2f%%  笔数%d(自然%d)  胜率%s  自然盈亏¥%+.0f  停手%d  用时%.0fs'
                  % (tag, a['final'], a['ret'], a['n'], a['n_nat'],
                     ('%.1f%%' % a['winrate']) if a['winrate'] is not None else 'NA',
                     a['nat_pnl'], a['stops'], a['secs']), flush=True)
            all_rows.append(dict(node=i+1, sy=sy, ey=ey, L=L, cap=cap,
                                 tag=tag, **{k: a[k] for k in
                                 ('final','ret','n','winrate','total_pnl','nat_pnl','stops')}))

    # ---- 汇总表 ----
    print('\n' + '=' * 100, flush=True)
    print('汇总(每节点横比限买档位):', flush=True)
    print('%-6s %-18s %12s %10s %6s %8s %12s %8s' %
          ('节点', '窗口', '限买档', '终值¥', '收益率%', '笔数', '胜率%', '停手'), flush=True)
    for r in all_rows:
        print('%-6s %-18s %-10s %12.0f %+10.2f %6d %8s %8d' %
              (r['node'], '%d~%d' % (r['sy'], r['ey']), r['tag'], r['final'],
               r['ret'], r['n'],
               ('%.1f' % r['winrate']) if r['winrate'] is not None else 'NA',
               r['stops']), flush=True)

    # ---- 跨节点求各档均值 ----
    print('\n跨节点平均(每档):', flush=True)
    by_cap = {}
    for r in all_rows:
        by_cap.setdefault(r['cap'], []).append(r)
    print('%-14s %12s %10s %10s' % ('限买档', '平均终值¥', '均收益率%', '平均笔数'), flush=True)
    for cap in caps:
        rs = by_cap[cap]
        avg_final = sum(r['final'] for r in rs) / len(rs)
        avg_ret = sum(r['ret'] for r in rs) / len(rs)
        avg_n = sum(r['n'] for r in rs) / len(rs)
        tag = ('原版(不限)' if cap == 0 else '限买%d只' % cap)
        print('%-14s %12.0f %+10.2f %10.1f' % (tag, avg_final, avg_ret, avg_n), flush=True)

if __name__ == '__main__':
    main()
