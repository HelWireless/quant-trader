# -*- coding: utf-8 -*-
"""把所有回测脚本切到修复版引擎 exp5，并改输出文件名（保留污染版证据）。"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
log = []


def patch(src, dst, subs):
    s = io.open(os.path.join(HERE, src), encoding='utf-8').read()
    for a, b in subs:
        assert a in s, '%s: anchor miss -> %s' % (src, a[:60])
        s = s.replace(a, b)
    io.open(os.path.join(HERE, dst), 'w', encoding='utf-8').write(s)
    log.append('%s -> %s' % (src, dst))


# 1) 30 窗口（第一组）修复版
patch('hoshi_oos30.py', 'hoshi_fix30.py', [
    ("'hoshi_backtest_exp4.py'", "'hoshi_backtest_exp5.py'"),
    ("'hoshi_oos30_%s.csv' % sk", "'hoshi_fix30_%s.csv' % sk"),
])

# 2) 30 窗口（第二组）修复版
patch('hoshi_oos2.py', 'hoshi_fix2.py', [
    ("'hoshi_backtest_exp4.py'", "'hoshi_backtest_exp5.py'"),
    ("'hoshi_oos2_%s.csv' % sk", "'hoshi_fix2_%s.csv' % sk"),
])

# 3) 最差入场修复版
patch('hoshi_worst_entry.py', 'hoshi_worstfix.py', [
    ("'hoshi_backtest_exp4.py'", "'hoshi_backtest_exp5.py'"),
    ("'hoshi_worst_entry_%s.csv' % sk", "'hoshi_worstfix_%s.csv' % sk"),
])

with open(os.path.join(HERE, '_patch_exp5.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(log))
