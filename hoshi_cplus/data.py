# -*- coding: utf-8 -*-
"""数据加载与预计算（hoshi-cplus）。

性能要点：把【均线 / 信号 / 广度】预计算成查表结构，回测主循环只做 O(1) 查询。
相比"每天重算全市场"的实现，537 窗次可从数小时压到 ~7 分钟。
"""
import csv
import glob
import os
from datetime import date

from .config import MA_FAST, MA_SLOW, MIN_BARS
from .signals import detect_signal


class Bar(object):
    __slots__ = ('date', 'open', 'high', 'low', 'close', 'volume')

    def __init__(self, d, o, h, l, c, v):
        self.date = d
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v

    def __repr__(self):
        return '<Bar %s o=%.2f h=%.2f l=%.2f c=%.2f>' % (
            self.date, self.open, self.high, self.low, self.close)


def load_data(input_path):
    """目录模式：每个 CSV 一列 date,open,high,low,close,volume，文件名 <code>_<name>.csv。

    返回 (code_bars: dict code -> [Bar 按日期升序], names: dict code -> name)
    """
    code_bars = {}
    names = {}
    for path in sorted(glob.glob(os.path.join(input_path, '*.csv'))):
        stem = os.path.basename(path)[:-4]
        code = stem.split('_')[0]
        name = stem[len(code) + 1:] if len(stem) > len(code) + 1 else ''
        rows = []
        try:
            with open(path, encoding='utf-8-sig') as f:
                rd = csv.reader(f)
                next(rd, None)          # 跳过表头
                for r in rd:
                    if len(r) < 6:
                        continue
                    try:
                        rows.append(Bar(
                            date(int(r[0][0:4]), int(r[0][5:7]), int(r[0][8:10])),
                            float(r[1]), float(r[2]), float(r[3]),
                            float(r[4]), float(r[5])))
                    except (ValueError, IndexError):
                        continue
        except Exception:
            continue
        if rows:
            rows.sort(key=lambda b: b.date)
            code_bars[code] = rows
            names[code] = name
    return code_bars, names


def precompute(code_bars, verbose=True):
    """预计算全局日期、逐日信号、逐日广度。

    返回 (dates, sig_by_date, n_above, n_valid, idx_of)
      dates        : 全部交易日（升序）
      sig_by_date  : {date: [(score, code), ...]}
      n_above[i]   : dates[i] 当日"昨日收盘 > 自身 MA60"的标的数
      n_valid[i]   : dates[i] 当日有效样本数
      idx_of       : {code: {date: bar_index}}
    """
    dateset = set()
    for bars in code_bars.values():
        for b in bars:
            dateset.add(b.date)
    dates = sorted(dateset)
    didx = {d: i for i, d in enumerate(dates)}

    idx_of = {}
    for code, bars in code_bars.items():
        idx_of[code] = {b.date: k for k, b in enumerate(bars)}

    n_above = [0] * len(dates)
    n_valid = [0] * len(dates)
    sig_by_date = {}

    for code, bars in code_bars.items():
        n = len(bars)
        pre = [0.0] * (n + 1)
        for k in range(n):
            pre[k + 1] = pre[k] + bars[k].close

        for k in range(n):
            # k = 该股票自身 bars 的索引；bars[:k] 即"截止昨天"
            if k < MIN_BARS - 1:          # 65
                continue
            d = bars[k].date
            di = didx[d]                  # 广度按全局日期索引累加（停牌会错位，务必换算）

            ma60 = (pre[k] - pre[k - MA_SLOW]) / float(MA_SLOW) if k >= MA_SLOW else None
            if ma60 is not None and ma60 > 0:
                n_valid[di] += 1
                if bars[k - 1].close > ma60:
                    n_above[di] += 1

            # 只取末尾 MIN_BARS 根即可 —— detect_signal 仅用最后 60 根算均线、
            # 最后 5 根算涨幅、倒数第 2 根作企稳日。切片 O(k) 会让预计算退化成 O(n^2)，
            # 5000+ 标的 × 4000+ 天时会慢到十几分钟；取固定 66 根后降到 O(1)。
            lo = max(0, k - MIN_BARS)
            seg = bars[lo:k]
            s = detect_signal(
                [b.open for b in seg],
                [b.high for b in seg],
                [b.low for b in seg],
                [b.close for b in seg],
            )
            if s is not None:
                sig_by_date.setdefault(d, []).append((s, code))

    if verbose:
        print('  预计算完成：%d 只标的，%d 个交易日（%s ~ %s）'
              % (len(code_bars), len(dates), dates[0], dates[-1]))
    return dates, sig_by_date, n_above, n_valid, idx_of
