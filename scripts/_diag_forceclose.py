# -*- coding: utf-8 -*-
"""诊断：强平用的是全数据集最后一根 bar，而非窗口内最后一根。量化影响。"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp4.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

out = []
out.append('数据集交易日范围: %s ~ %s，共 %d 天'
           % (all_dates[0], all_dates[-1], len(all_dates)))
out.append('股票数: %d' % len(code_bars))

# 每只股票的"最后一根 bar"日期分布
from collections import Counter
c = Counter(bars[-1].date for bars in code_bars.values())
out.append('')
out.append('各股票最后一根 bar 的日期（Top15）:')
for d, n in c.most_common(15):
    out.append('   %s  %d 只' % (d, n))
from datetime import date as _date
late = sum(n for d, n in c.items() if d >= _date(2025, 1, 1))
out.append('   最后bar在 2025 年之后的股票: %d 只 (%.0f%%)'
           % (late, late / len(code_bars) * 100))

with open(os.path.join(HERE, '_diag_forceclose.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
