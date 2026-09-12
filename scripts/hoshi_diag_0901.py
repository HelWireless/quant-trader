# -*- coding: utf-8 -*-
"""逐日信号诊断（H5S9 口径）：列出指定区间内每一天
   - 市场广度（前一日收盘 > 前一日 MA60 的股票占比）
   - 全部触发的超跌信号（不限评分门槛），标注是否达到 H5S9 的评分 9 门槛
   - 门控放行/拦截状态

只读诊断，与引擎共用 _detect_signal，不改动任何回测逻辑。

用法: python hoshi_diag_0901.py [start] [end]   默认 2026-09-01 2026-09-04
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None

START = sys.argv[1] if len(sys.argv) > 1 else '2026-09-01'
END = sys.argv[2] if len(sys.argv) > 2 else '2026-09-04'
MIN_SCORE = 9.0
BREADTH_THRESH = 20.0
MA_SLOW = hbe.MA_SLOW

code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

# 名称兜底：CSV 无 name 列时从文件名 "603758_秦安股份.csv" 解析
import re as _re
for _fn in os.listdir(os.path.join(HERE, 'hoshi_csv_long')):
    _m = _re.match(r'(\d{6})_(.+)\.csv$', _fn)
    if _m and not names.get(_m.group(1)):
        names[_m.group(1)] = _m.group(2)

sd = hbe._to_date(START)
ed = hbe._to_date(END)
days = [d for d in all_dates if sd <= d <= ed]

print('诊断区间 %s ~ %s（H5S9 口径：评分门槛 %.0f，广度门槛 %.0f%%）' % (START, END, MIN_SCORE, BREADTH_THRESH))

for today in days:
    n_valid = 0
    n_above = 0
    sigs = []
    for code, bars in code_bars.items():
        k = None
        for i in range(len(bars) - 1, -1, -1):
            if bars[i].date <= today:
                k = i
                break
        if k is None:
            continue
        full = bars[:k + 1]
        if len(full) < MA_SLOW + 6:
            continue
        c = [x.close for x in full]
        cp = c[:-1]
        if len(cp) >= MA_SLOW:
            ma60 = sum(cp[-MA_SLOW:]) / MA_SLOW
            if ma60 > 0:
                n_valid += 1
                if cp[-1] > ma60:
                    n_above += 1
        if len(full) >= 66:
            o = [x.open for x in full]
            h = [x.high for x in full]
            l = [x.low for x in full]
            score = hbe._detect_signal(o[:-1], h[:-1], l[:-1], c[:-1])
            if score is not None:
                sigs.append((score, code))

    breadth = (n_above * 100.0 / n_valid) if n_valid >= hbe.BREADTH_MIN_SAMPLE else None
    sigs.sort(key=lambda x: -x[0])
    pass_cnt = sum(1 for s, _ in sigs if s >= MIN_SCORE)
    gate = '放行' if (breadth is not None and breadth >= BREADTH_THRESH) else '拦截'

    print('\n================ %s ================' % today)
    print('  广度: %s （%d / %d 只站上 MA60） | 广度门控: %s'
          % (('%.1f%%' % breadth) if breadth is not None else 'NA(样本不足)',
             n_above, n_valid, gate))
    print('  触发信号 %d 个，其中 >= %.0f 分的 %d 个' % (len(sigs), MIN_SCORE, pass_cnt))
    if sigs:
        print('  %-3s %-7s %-10s %-8s %s' % ('#', '代码', '名称', '评分', '是否达门槛'))
        for i, (s, c) in enumerate(sigs[:20], 1):
            mark = '✓ 可买' if (s >= MIN_SCORE and gate == '放行') else ('评分不足' if s < MIN_SCORE else '被门控拦截')
            print('  %-3d %-7s %-10s %-8.2f %s' % (i, c, names.get(c, ''), s, mark))
        if len(sigs) > 20:
            print('  ... 其余 %d 个略' % (len(sigs) - 20))
    else:
        print('  （当日无任何超跌信号）')
