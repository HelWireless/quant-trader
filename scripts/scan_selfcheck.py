# -*- coding: utf-8 -*-
"""扫描器自检：确认 `hoshi_scan_live.py` 不是"静默失效"（0 信号/0 universe 假象）。

用途：每天扫描后跑一次。若某天报「0 只合格」，用它看分数分布（universe 应 ~5000、
有信号的票应是个位数~几十只、max 分 < 9.0 才算"真无信号"），避免把
"数据没更新/加载失败"误判成"市场没机会"。

用法
----
  python scripts/scan_selfcheck.py
  python scripts/scan_selfcheck.py --data scripts/hoshi_csv_long
  python scripts/scan_selfcheck.py --day 2026-09-30
"""
import argparse
import os
import sys
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.config import MIN_BARS, get_preset
from hoshi_cplus.data import load_data
from hoshi_cplus.signals import detect_signal


def main():
    ap = argparse.ArgumentParser(description='扫描器自检（分数分布）')
    ap.add_argument('--data', default='scripts/hoshi_csv_2005')
    ap.add_argument('--day', help='确认日 YYYY-MM-DD（默认取数据里最新）')
    ap.add_argument('--preset', default='cplus')
    ap.add_argument('--top', type=int, default=10)
    args = ap.parse_args()

    p = get_preset(args.preset)
    result = load_data(args.data)
    # load_data 返回 tuple (dict, names)；兼容只返回 dict 的情况
    code_bars, names = result if isinstance(result, tuple) else (result, {})
    if not code_bars:
        print('!! load_data 返回空 —— 数据目录可能不存在或为空：%s' % args.data)
        return 2

    if args.day:
        from datetime import date as _date
        confirm_day = _date.fromisoformat(args.day)
    else:
        # Bar.date 是 datetime.date 对象，直接 max 最稳（不要和字符串比）
        confirm_day = max(b[-1].date for b in code_bars.values() if b)

    n_universe = len(code_bars)
    n_today = 0
    n_scored = 0
    n_ge9 = 0
    scores = []
    scored_rows = []
    for code, bars in code_bars.items():
        if not bars or bars[-1].date != confirm_day:
            continue
        n_today += 1
        k = len(bars) - 1
        seg = bars[max(0, k - (MIN_BARS - 1)):k + 1]
        if len(seg) < MIN_BARS - 1:
            continue
        s = detect_signal([b.open for b in seg], [b.high for b in seg],
                          [b.low for b in seg], [b.close for b in seg])
        if s is None:
            continue
        n_scored += 1
        scores.append(s)
        scored_rows.append((s, code, names.get(code, ''), bars[k].close))
        if s >= p.min_score:
            n_ge9 += 1

    scores.sort(reverse=True)
    scored_rows.sort(key=lambda x: (-x[0], x[1]))

    print('=' * 72)
    print('扫描器自检   目录=%s   确认日=%s   预设=%s(阈值 %.1f)'
          % (args.data, confirm_day, args.preset, p.min_score))
    print('=' * 72)
    print('  universe（CSV 文件数）      : %d' % n_universe)
    print('  确认日有 K 线的标的         : %d' % n_today)
    print('  detect_signal 非空（有信号）: %d' % n_scored)
    print('  评分 >= %.1f（合格）        : %d' % (p.min_score, n_ge9))
    if scores:
        print('  最高分 / 中位 / 最低        : %.1f / %.1f / %.1f'
              % (scores[0], scores[len(scores) // 2], scores[-1]))
        band = Counter()
        for s in scores:
            if s >= 9.0:
                band['>=9.0'] += 1
            elif s >= 8.0:
                band['8.0-8.9'] += 1
            elif s >= 6.0:
                band['6.0-7.9'] += 1
            else:
                band['<6.0'] += 1
        print('  分数分档                    : %s'
              % ', '.join('%s=%d' % (k, band[k])
                          for k in ('>=9.0', '8.0-8.9', '6.0-7.9', '<6.0')))
        print('\n  Top %d：' % args.top)
        for s, code, name, close in scored_rows[:args.top]:
            print('    %s %-8s 评分%5.1f  收%.3f' % (code, name, s, close))
    else:
        print('  ⚠ 一个非空信号都没有 —— 高度可疑，请检查数据是否已更新！')

    print('\n  判读：universe ≈ 5000 且 确认日有 K 线 ≈ 4984 才是正常加载；'
          '\n        若 max < 阈值 则"0 合格"为真，否则是漏报。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
