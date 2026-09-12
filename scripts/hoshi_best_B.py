# -*- coding: utf-8 -*-
"""Hoshi 最优方案 B —— 参数锁定、可直接复现的回测入口。

方案 B（2026-09-11 双组 60 窗样本外验证后的最终选定方案）
--------------------------------------------------------------
    MIN_SCORE            = 9.0    入场评分下限（0~10，越高要求跌得越急越深）
    LOSS_HARD_START_DAY  = 5      止损线从第 5 个持有日起生效
    USE_R3_GATE          = False  ★关闭 R3 回撤序列门控（本方案唯一的关键改动）
    USE_BREADTH_GATE     = True   保留市场广度门控
    BREADTH_THRESH       = 20.0   广度低于 20% 不开新仓
    其余参数 = 原版默认

等价表述：**原版 hoshi 参数，只把 R3 门控关掉**（评分同样取 9、止损同样取 5）。

--------------------------------------------------------------
用法
--------------------------------------------------------------
    # 1) 复现双组 60 窗验证（约数小时）
    python hoshi_best_B.py --export-windows        # 生成 hoshi_validation_windows.csv
    python hoshi_best_B.py --windows hoshi_validation_windows.csv --out hoshi_bestB_60.csv

    # 2) 回测任意区间
    python hoshi_best_B.py --start 2015-01-01 --end 2020-12-31

    # 3) 引擎一致性自检（跑 2 个已知窗口，与已落盘结果逐位比对）
    python hoshi_best_B.py --verify

依赖：同目录 hoshi_backtest_exp5.py（唯一可信引擎）、hoshi_csv_long/、hoshi_market_features.csv
"""
import argparse
import csv
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 方案 B 参数（唯一真源，勿在别处重复定义）
# ---------------------------------------------------------------------------
SCHEME_B = dict(
    TOTAL_CAPITAL=500000.0,
    MIN_SCORE=9.0,
    LOSS_START_DAY=15,
    LOSS_HARD_START_DAY=5,
    USE_R3_GATE=False,
    USE_BREADTH_GATE=True,
    BREADTH_THRESH=20.0,
    MAX_SLOTS=10,
    MAX_BUY_PER_DAY=0,
    EXIT_MODE='AUTO',
    ADAPTIVE_SCORE=False,
    ADAPTIVE_STOP=False,
    RS_FILTER=False,
    SCORE_TIER_SIZING=False,
    SCORE_TIER_ADAPTIVE=False,
)

# 自检用：来自已完成验证的落盘结果（不容许漂移）
EXPECT = [
    ('2011-03-01', '2016-02-29', 153.1699),
    ('2014-12-01', '2016-11-30', 146.8178),
    ('2020-10-01', '2022-09-30', 52.7429),
]


def load_engine():
    spec = importlib.util.spec_from_file_location(
        'hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
    hbe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hbe)
    hbe._log = lambda *a, **k: None
    hbe.DEBUG = False
    for k, v in SCHEME_B.items():
        setattr(hbe, k, v)
    mf = os.path.join(HERE, 'hoshi_market_features.csv')
    if os.path.exists(mf):
        hbe.load_market_features(mf)
    return hbe


def load_all(hbe, data_dir=None):
    d = data_dir or os.path.join(HERE, 'hoshi_csv_long')
    return hbe.load_data(d)


def run_one(hbe, code_bars, names, all_dates, start, end):
    r = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    ret = (r['final_capital'] - SCHEME_B['TOTAL_CAPITAL']) / SCHEME_B['TOTAL_CAPITAL'] * 100.0
    return ret, r


def geo(v):
    p = 1.0
    for x in v:
        p *= (1 + x / 100.0)
    return (p ** (1.0 / len(v)) - 1.0) * 100.0 if p > 0 else -100.0


def median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def export_windows():
    """合并两组验证窗口成单一清单，便于一键复现。"""
    src = [('1', 'hoshi_time_corr_windows.csv'),
           ('2', 'hoshi_oos2_windows.csv')]
    rows = []
    for g, fn in src:
        p = os.path.join(HERE, fn)
        if not os.path.exists(p):
            print('  跳过（缺失）%s' % fn)
            continue
        with open(p, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                rows.append([g, r['start'], r['end'], r['len_months']])
    out = os.path.join(HERE, 'hoshi_validation_windows.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['group', 'start', 'end', 'len_months'])
        w.writerows(rows)
    print('已写出 %d 个验证窗口 -> %s' % (len(rows), out))


def main():
    ap = argparse.ArgumentParser(description='Hoshi 最优方案 B 回测（参数锁定）')
    ap.add_argument('--windows', help='窗口清单 CSV（列含 start,end），批量回测')
    ap.add_argument('--out', help='批量结果输出 CSV')
    ap.add_argument('--start', help='单区间回测起始日 YYYY-MM-DD')
    ap.add_argument('--end', help='单区间回测结束日 YYYY-MM-DD')
    ap.add_argument('--data-dir', help='K线 CSV 目录，默认 hoshi_csv_long')
    ap.add_argument('--export-windows', action='store_true', help='生成 60 窗清单')
    ap.add_argument('--verify', action='store_true', help='引擎一致性自检')
    args = ap.parse_args()

    if args.export_windows:
        export_windows()
        return 0

    hbe = load_engine()
    code_bars, names, all_dates = load_all(hbe, args.data_dir)

    if args.verify:
        print('=' * 74)
        print('方案 B 引擎自检（与已落盘验证结果比对）')
        print('=' * 74)
        ok = True
        for s, e, exp in EXPECT:
            got, r = run_one(hbe, code_bars, names, all_dates, s, e)
            diff = got - exp
            flag = 'OK ' if abs(diff) < 0.01 else '差异'
            if abs(diff) >= 0.01:
                ok = False
            print('  %s  %s~%s  本次 %+9.4f%%  期望 %+9.4f%%  差 %+0.4fpp  笔数 %d'
                  % (flag, s, e, got, exp, diff, len(r['closed'])))
        print('=' * 74)
        print('自检结果：%s' % ('通过 ✓' if ok else '不通过 ✗'))
        return 0 if ok else 1

    if args.windows:
        rows = []
        with open(args.windows, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                rows.append((r.get('group', ''), r['start'], r['end'],
                             r.get('len_months', '')))
        out = args.out or 'hoshi_bestB_results.csv'
        fout = open(out, 'w', newline='', encoding='utf-8')
        wcsv = csv.writer(fout)
        wcsv.writerow(['group', 'start', 'end', 'len_months', 'ret_pct', 'trades'])
        vals = []
        print('方案 B  批量回测 %d 个窗口' % len(rows))
        for i, (g, s, e, m) in enumerate(rows, 1):
            ret, r = run_one(hbe, code_bars, names, all_dates, s, e)
            wcsv.writerow([g, s, e, m, '%.4f' % ret, len(r['closed'])])
            fout.flush()
            vals.append(ret)
            print('  [%2d/%d] %s~%s  方案B %+8.2f%%  笔数 %d'
                  % (i, len(rows), s[:7], e[:7], ret, len(r['closed'])))
        fout.close()
        print('-' * 74)
        print('窗口数 %d | 等权均值 %+.2f%% | 几何均值 %+.2f%% | 中位数 %+.2f%%'
              % (len(vals), sum(vals) / len(vals), geo(vals), median(vals)))
        print('最差窗 %+.2f%% | 最好窗 %+.2f%% | 负收益窗 %d/%d'
              % (min(vals), max(vals), sum(1 for v in vals if v < 0), len(vals)))
        print('结果已写入 %s' % out)
        return 0

    if args.start or args.end:
        ret, r = run_one(hbe, code_bars, names, all_dates, args.start, args.end)
        print('方案 B  %s ~ %s' % (args.start or '(最早)', args.end or '(最新)'))
        print('  期末资金 %s 元 | 收益率 %+.2f%% | 成交 %d 笔'
              % (format(round(r['final_capital']), ','), ret, len(r['closed'])))
        return 0

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
