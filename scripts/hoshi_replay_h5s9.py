# -*- coding: utf-8 -*-
"""H5S9 实盘复盘：模拟从指定日起以 30 万资金真实运行 H5S9 的每日操作。

参数（H5S9，评分9 + 止损5 + R3开 + 广度20）:
    TOTAL_CAPITAL=300000, MIN_SCORE=9.0, LOSS_HARD_START_DAY=5,
    USE_R3_GATE=True, BREADTH_THRESH=20.0, 其余默认

输出：
  1) 每日操作明细（买入/卖出，含代码、名称、评分、价格、股数、金额）
  2) 期末持仓（引擎会按窗口末强平，本脚本按其还原为"当前持仓"并算浮盈亏，不扣卖出费）
  3) 每日现金 / 持仓市值 / 权益
  4) 汇总

用法: python hoshi_replay_h5s9.py [start] [end] [capital]
  默认 start=2026-09-01, end=最新数据日, capital=300000
"""
import csv
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False

START = sys.argv[1] if len(sys.argv) > 1 else '2026-09-01'
END = sys.argv[2] if len(sys.argv) > 2 else None
CAPITAL = float(sys.argv[3]) if len(sys.argv) > 3 else 300000.0

for k, v in dict(
        TOTAL_CAPITAL=CAPITAL,
        MIN_SCORE=9.0,               # H5S9: 评分门槛 9
        LOSS_START_DAY=15,
        LOSS_HARD_START_DAY=5,       # H5S9: 硬止损第 5 日生效
        USE_R3_GATE=True,            # H5S9: R3 开
        USE_BREADTH_GATE=True, BREADTH_THRESH=20.0,
        MAX_SLOTS=10, MAX_BUY_PER_DAY=0, EXIT_MODE='AUTO',
        ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
        SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False).items():
    setattr(hbe, k, v)

hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

# 名称兜底：CSV 无 name 列时从文件名 "603758_秦安股份.csv" 解析
import re as _re
for _fn in os.listdir(os.path.join(HERE, 'hoshi_csv_long')):
    _m = _re.match(r'(\d{6})_(.+)\.csv$', _fn)
    if _m and not names.get(_m.group(1)):
        names[_m.group(1)] = _m.group(2)

r = hbe.run_backtest(code_bars, names, all_dates, start=START, end=END)

buys = r['buys']
closed = r['closed']
eq = r['equity_curve']
last_date = eq[-1][0] if eq else None

real_sells = [t for t in closed if t['exit_reason'] != '回测结束强平']
holdings = [t for t in closed if t['exit_reason'] == '回测结束强平']

# 最新收盘价
last_close = {}
for c in set(t['code'] for t in holdings):
    bs = [b for b in code_bars[c] if b.date <= last_date]
    last_close[c] = bs[-1].close if bs else None

print('=' * 96)
print('H5S9 实盘复盘 | 起点 %s | 数据末 %s | 初始资金 %.0f 元' % (START, last_date, CAPITAL))
print('=' * 96)

# ---- 每日操作 ----
by_day_buy = {}
for b in buys:
    by_day_buy.setdefault(b['date'], []).append(b)
by_day_sell = {}
for t in real_sells:
    by_day_sell.setdefault(t['sell_date'], []).append(t)

all_days = sorted(set(list(by_day_buy) + list(by_day_sell)))
for d in all_days:
    bl = by_day_buy.get(d, [])
    sl = by_day_sell.get(d, [])
    print('\n---- %s ----' % d)
    if not bl and not sl:
        print('  (无操作)')
    for b in sorted(bl, key=lambda x: -x['score']):
        print('  买入  %-7s %-8s 评分 %.1f | %6.2f 元 × %5d 股 = %9.2f 元 | %s'
              % (b['code'], b['name'], b['score'], b['price'], b['shares'], b['cost'], b['mode']))
    for t in sorted(sl, key=lambda x: x['code']):
        print('  卖出  %-7s %-8s | 买 %6.2f (%s) -> 卖 %6.2f (%s) | 收益 %+7.2f%% | %s'
              % (t['code'], t['name'], t['buy_price'], t['buy_date'], t['sell_price'],
                 t['sell_date'], t['return_pct'], t['exit_reason']))
    if d not in (by_day_buy or {}) and not sl:
        pass

# 无操作日的提示（9-01 到末日间没有出现在操作表里的交易日）
print('\n（未列出的交易日 = 当天无买卖信号或无操作）')

# ---- 期末持仓 ----
print('\n' + '=' * 96)
print('期末持仓（截至 %s，按当日收盘价计，未扣卖出费）' % last_date)
print('=' * 96)
print('%-7s %-8s %10s %12s %10s %8s %9s %12s %12s' %
      ('代码', '名称', '买入日', '买入价', '现价', '持有日', '评分', '市值(元)', '浮盈亏'))
print('-' * 96)
tot_mv = 0.0
for t in sorted(holdings, key=lambda x: x['buy_date']):
    cur = last_close.get(t['code'])
    mv = (cur or t['sell_price']) * t['shares']
    pnl = (cur or t['sell_price'] - t['buy_price'] if cur else t['sell_price'] - t['buy_price']) * t['shares']
    if cur:
        pnl = (cur - t['buy_price']) * t['shares']
    tot_mv += mv
    print('%-7s %-8s %10s %11.2f %10.2f %8d %9.1f %12.2f %+11.2f (%+.2f%%)'
          % (t['code'], t['name'], str(t['buy_date']), t['buy_price'],
             cur if cur else t['sell_price'], t['hold_days'], t['score'], mv, pnl,
             (cur - t['buy_price']) / t['buy_price'] * 100.0 if cur else t['return_pct']))

# ---- 每日权益 ----
print('\n' + '=' * 96)
print('每日账户状态')
print('=' * 96)
print('%-12s %14s %14s %14s' % ('日期', '现金(元)', '持仓市值(元)', '权益(元)'))
print('-' * 96)
for (d, cash, mv, e) in eq:
    print('%-12s %14.2f %14.2f %14.2f' % (d, cash, mv, e))

# ---- 汇总 ----
closed_pnl = sum(t['pnl'] for t in real_sells)
last = eq[-1]
print('\n' + '=' * 96)
print('汇总')
print('=' * 96)
print('  已实现收益（已卖出 %d 笔）: %+.2f 元' % (len(real_sells), closed_pnl))
print('  期末现金    : %.2f 元' % last[1])
print('  期末持仓市值: %.2f 元（%d 只）' % (tot_mv, len(holdings)))
print('  期末权益    : %.2f 元' % last[3])
print('  区间收益率  : %+.2f%%' % ((last[3] - CAPITAL) / CAPITAL * 100.0))
print('  跳过信号    : %d 次（评分未达 9 / 广度 < 20 / 仓位满）' % r['skipped'])

# 导出 CSV 便于核对
out = os.path.join(HERE, 'hoshi_replay_h5s9.csv')
with open(out, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['action', 'date', 'code', 'name', 'score', 'price', 'shares', 'amount', 'mode_or_reason'])
    for b in sorted(buys, key=lambda x: (x['date'], -x['score'])):
        w.writerow(['买入', b['date'], b['code'], b['name'], '%.1f' % b['score'],
                    '%.2f' % b['price'], b['shares'], '%.2f' % b['cost'], b['mode']])
    for t in sorted(real_sells, key=lambda x: x['sell_date']):
        w.writerow(['卖出', t['sell_date'], t['code'], t['name'], '%.1f' % (t['score'] or 0),
                    '%.2f' % t['sell_price'], t['shares'], '%.2f' % t['proceeds'], t['exit_reason']])
    for t in sorted(holdings, key=lambda x: x['buy_date']):
        cur = last_close.get(t['code']) or t['sell_price']
        w.writerow(['持仓', last_date, t['code'], t['name'], '%.1f' % (t['score'] or 0),
                    '%.2f' % cur, t['shares'], '%.2f' % (cur * t['shares']), '买入日 %s @%.2f' % (t['buy_date'], t['buy_price'])])
print('\n明细已导出 %s' % out)
