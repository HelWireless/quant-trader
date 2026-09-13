# -*- coding: utf-8 -*-
"""hoshi-cplus —— A 股超跌反弹策略（Hoshi 策略的优化版）。

命名
----
2026-09-12~09-13 的研究中该方案称为 **方案 B′（B prime）**，
自 2026-09-13 起统一命名为 **hoshi-cplus**。

    hoshi-cplus  ==  方案 B′  ==  评分9 + 硬止损启用日5 + R3关 + 广度20 + 硬止损 −6.0%

快速使用
--------
```python
from hoshi_cplus import Strategy

s = Strategy('scripts/hoshi_csv_2005', preset='cplus')
r = s.run('2011-03-01', '2016-02-29')
print(r['ret'])        # 收益率(%)
print(r['n_trades'])   # 交易笔数
```

命令行
------
```bash
python -m hoshi_cplus --data scripts/hoshi_csv_2005 --preset cplus \
    --start 2011-03-01 --end 2016-02-29
```
"""
from .config import (PRESETS, DEFAULT_PRESET, get_preset, TOTAL_CAPITAL)
from .signals import detect_signal, calc_score, is_hammer, is_doji
from .exits import step_exit, new_position
from .gates import R3Gate, breadth_ok, breadth_value
from .data import load_data, precompute, Bar
from .backtest import run_backtest, Strategy, buy_fee, sell_fee

__version__ = '1.0.0'
__all__ = [
    'PRESETS', 'DEFAULT_PRESET', 'get_preset', 'TOTAL_CAPITAL',
    'detect_signal', 'calc_score', 'is_hammer', 'is_doji',
    'step_exit', 'new_position',
    'R3Gate', 'breadth_ok', 'breadth_value',
    'load_data', 'precompute', 'Bar',
    'run_backtest', 'Strategy', 'buy_fee', 'sell_fee',
]
