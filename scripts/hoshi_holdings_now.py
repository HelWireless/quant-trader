# -*- coding: utf-8 -*-
"""当前持仓体检：给定持仓清单，输出技术状态、止损触发价、出场倒计时。

用途：把「WSL 实盘当前持仓」放到本地引擎口径下体检，给出处置依据。

用法:
  python hoshi_holdings_now.py            # 用内置持仓（华钰矿业 / 青山纸业）
  python hoshi_holdings_now.py 601020:22.048:4000:2026-09-07 600103:3.90:7300:2026-09-08
     格式  代码:买入价:股数:买入日
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None

DEFAULT = ['601020:22.048:4000:2026-09-07', '600103:3.900:7300:2026-09-08']

args = sys.argv[1:] or DEFAULT
holds = []
for a in args:
    code, price, shares, bdate = a.split(':')
    holds.append(dict(code=code, buy=float(price), shares=int(shares), bdate=bdate))

hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))
import re as _re
for _fn in os.listdir(os.path.join(HERE, 'hoshi_csv_long')):
    _m = _re.match(r'(\d{6})_(.+)\.csv$', _fn)
    if _m and not names.get(_m.group(1)):
        names[_m.group(1)] = _m.group(2)

LAST = max(d for d in all_dates)
MA_FAST, MA_SLOW = hbe.MA_FAST, hbe.MA_SLOW
HARD_82 = -8.2
HARD_60 = -6.0

print('=' * 108)
print('当前持仓体检 | 数据末 %s | 下一交易日待定' % LAST)
print('=' * 108)

for h in holds:
    code = h['code']
    bars = code_bars.get(code)
    if not bars:
        print('\n!! 无数据 %s' % code)
        continue
    bs = [b for b in bars if b.date <= LAST]
    if len(bs) < MA_SLOW + 6:
        print('\n!! 数据不足 %s' % code)
        continue
    closes = [b.close for b in bs]
    last = bs[-1]
    cur = last.close
    ma20 = sum(closes[-MA_FAST:]) / MA_FAST
    ma60 = sum(closes[-MA_SLOW:]) / MA_SLOW

    # 持有交易日（按 all_dates 计数）
    from datetime import date as _d
    bd = _d.fromisoformat(h['bdate'])
    hd = sum(1 for d in all_dates if bd <= d <= LAST)

    pnl_pct = (cur - h['buy']) / h['buy'] * 100.0
    cost = h['buy'] * h['shares']
    mv = cur * h['shares']

    # 最新一天是否仍有买入信号（用截至 LAST 前一日的序列）
    op = [b.open for b in bs][:-1]
    hp = [b.high for b in bs][:-1]
    lp = [b.low for b in bs][:-1]
    cp = closes[:-1]
    score = hbe._detect_signal(op, hp, lp, cp)

    trig82 = h['buy'] * (1 + HARD_82 / 100.0)
    trig60 = h['buy'] * (1 + HARD_60 / 100.0)

    print('\n■ %s  %s' % (code, names.get(code, '')))
    print('  买入 %s @ %.3f × %d 股  成本 %.2f 元' % (h['bdate'], h['buy'], h['shares'], cost))
    print('  现价 %.2f（%s 收盘）  市值 %.2f 元  浮盈亏 %+.2f 元（%+.2f%%）' % (cur, LAST, mv, mv - cost, pnl_pct))
    print('  持有交易日 %d 天 | 距 DEADLINE(第%d天) %d 天 | 距 MAX_HOLD(第%d天) %d 天'
          % (hd, hbe.DEADLINE_DAY, hbe.DEADLINE_DAY - hd, hbe.MAX_HOLD, hbe.MAX_HOLD - hd))
    print('  MA20 %.2f（现价 %+.2f%%）  MA60 %.2f（现价 %+.2f%%）  MA20%sMA60'
          % (ma20, (cur / ma20 - 1) * 100, ma60, (cur / ma60 - 1) * 100,
             '>' if ma20 > ma60 else '<'))
    print('  近 5 日 %+.2f%%   近 10 日 %+.2f%%   近 20 日 %+.2f%%'
          % ((cur / closes[-6] - 1) * 100 if len(closes) > 6 else 0,
             (cur / closes[-11] - 1) * 100 if len(closes) > 11 else 0,
             (cur / closes[-21] - 1) * 100 if len(closes) > 21 else 0))
    print('  硬止损触发价： -6.0%%(他的p6) = %.2f（现价尚有 %+.2f%%） | -8.2%%(引擎默认/方案B) = %.2f（现价尚有 %+.2f%%）'
          % (trig60, (trig60 / cur - 1) * 100, trig82, (trig82 / cur - 1) * 100))
    print('  当前是否仍触发买入信号：%s' % ('有，评分 %.1f' % score if score is not None else '无'))

print('\n' + '=' * 108)
