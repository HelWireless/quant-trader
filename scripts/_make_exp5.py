# -*- coding: utf-8 -*-
"""生成 exp5：修复"强平用全数据集最后一根 bar"的 bug。"""
import io
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(HERE, 'hoshi_backtest_exp4.py')
dst = os.path.join(HERE, 'hoshi_backtest_exp5.py')
shutil.copyfile(src, dst)
s = io.open(dst, encoding='utf-8').read()

old = """    # 收尾：强平剩余持仓（按最后一根可见 bar 的收盘价）
    for code in list(positions.keys()):
        p = positions.pop(code)
        last_bar = code_bars[code][-1]
        sell_price = last_bar.close"""
new = """    # 收尾：强平剩余持仓
    # BUGFIX: 原实现用 code_bars[code][-1]，即整个数据集的最后一根 bar（2026-09-04），
    # 导致任何窗口的未平仓头寸都按 2026 年价格强平，窗口越早失真越大。
    # 改为：取窗口内（日期 <= 窗口最后一天）的最后一根 bar。
    _end_d = dates[-1] if dates else None
    for code in list(positions.keys()):
        p = positions.pop(code)
        last_bar = None
        for _b in reversed(code_bars[code]):
            if _end_d is None or _b.date <= _end_d:
                last_bar = _b
                break
        if last_bar is None:
            last_bar = code_bars[code][0]
        sell_price = last_bar.close"""

assert old in s, 'anchor miss'
s = s.replace(old, new, 1)
io.open(dst, 'w', encoding='utf-8').write(s)
with open(os.path.join(HERE, '_make_exp5.txt'), 'w', encoding='utf-8') as f:
    f.write('exp5 created and patched: %s' % dst)
