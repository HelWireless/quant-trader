# -*- coding: utf-8 -*-
"""2026-09-07 开盘前决策：原版 hoshi 在 09-01~09-07(今) 会买入什么 + 每笔持仓的条件单。

口径 = 权威原版：MIN_SCORE=8.0 / LOSS_HARD_START_DAY=15 / 不限买 / S3-S4自适应 / R3+广度门控 / 50万 10%×10槽。

技巧：数据只到 09-04(周五)。为让引擎"走到 09-07"捕捉【09-04确认、周一开盘买入】的信号，
给每只股票在内存里追加一根 09-07 合成bar(OHLC=09-04收盘, 量0)。
- 09-07 的买入清单 = buy_date=='2026-09-07' 的记录（买入价=合成open=周五收盘，仅作参考，实际以周一开盘价成交）
- sell_date=='2026-09-07' 的出场是合成日的伪触发（数据重复），持仓视为仍持有，标注"贴近触发线"
- 其余 sell_date<=09-04 的出场为真实出场。
"""
import importlib.util
import os
from datetime import date

spec = importlib.util.spec_from_file_location(
    'hbe', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_backtest_exp.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_csv_long')

code_bars, names, all_dates = hbe.load_data(CSV_DIR)

# 文件名补全中文名（csv内容无name列，文件名形如 000001_平安银行.csv）
name_by_code = {}
for fn in os.listdir(CSV_DIR):
    if fn.endswith('.csv') and '_' in fn:
        code6 = fn.split('_')[0]
        name_by_code[code6] = fn[:-4].split('_', 1)[1]

SYN_DAY = date(2026, 9, 7)
for code, bars in code_bars.items():
    last = bars[-1]
    if last.date >= SYN_DAY:
        continue
    c = last.close
    bars.append(hbe.Bar(SYN_DAY, c, c, c, c, 0))
all_dates = list(all_dates)
if all_dates[-1] < SYN_DAY:
    all_dates.append(SYN_DAY)

# ---- 原版参数 ----
for k, v in dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, LOSS_HARD_START_DAY=15,
                 MIN_SCORE=8.0, MAX_SLOTS=10, EXIT_MODE='AUTO').items():
    setattr(hbe, k, v)

res = hbe.run_backtest(code_bars, names, all_dates,
                       start='2026-08-31', end='2026-09-07')
closed = res['closed']
INIT = 500000.0


def nm(code):
    return name_by_code.get(code, '')


def pos_lines(code, buy_date, entry):
    """按原版规则生成某持仓的条件单要素。读该股csv取 buy_date~09-04 高点。"""
    fp = None
    for fn in os.listdir(CSV_DIR):
        if fn.startswith(code + '_') or fn == code + '.csv':
            fp = os.path.join(CSV_DIR, fn)
            break
    peak = entry
    lowest = entry
    if fp:
        with open(fp, encoding='utf-8') as f:
            for line in f.read().strip().splitlines()[1:]:
                p = line.split(',')
                d = p[0]
                if buy_date <= d <= '2026-09-04':
                    peak = max(peak, float(p[2]))
                    lowest = min(lowest, float(p[3]))
    armed = peak >= entry * (1 + hbe.PROFIT_ARM_PCT / 100.0)
    trail = peak * (1 - hbe.PROFIT_TRAIL_PCT / 100.0)
    return armed, peak, (trail if armed else None), lowest


# ---------- 汇总 ----------
buys = [t for t in closed if str(t['buy_date']) >= '2026-09-01'
        and str(t['buy_date']) <= '2026-09-04']
monday_buys = [t for t in closed if str(t['buy_date']) == '2026-09-07']
# 09-07 伪出场（合成日触发）→ 持仓仍视为在手
fake_exits = [t for t in closed
              if str(t['sell_date']) == '2026-09-07'
              and t['exit_reason'] != '回测结束强平']
open_pos = [t for t in closed if t['exit_reason'] == '回测结束强平'
            and str(t['buy_date']) <= '2026-09-04']
real_exits = [t for t in closed if str(t['sell_date']) <= '2026-09-04']

print()
print('===== 原版 hoshi 09-01 ~ 09-07 回放（50万，10%%×10槽）=====')
print()
print('--- A. 本周已买入持仓（09-01~09-04，截至周五收盘仍持有 %d 只）---' % len(open_pos))
for t in sorted(open_pos, key=lambda x: x['buy_date']):
    armed, peak, trail, lowest = pos_lines(t['code'], str(t['buy_date']), t['buy_price'])
    flag = '已武装止盈' if armed else '未武装'
    print('  %s %s | 买%s 开盘%.2f | 评分%.1f %s | %d股 成本%.0f | 区间高点%.2f(%s)'
          % (t['code'], nm(t['code']), t['buy_date'], t['buy_price'],
             t['score'], t['mode'], t['shares'], t['cost'], peak, flag))
    if armed:
        print('      ↳ 止盈触发价(峰值回落1.2%%) = %.2f' % trail)
    print('      ↳ 硬止损价(第15天起) = %.2f | 止损武装线 = %.2f | 第%d个交易日未武装超时清仓'
          % (t['buy_price'] * (1 + hbe.LOSS_HARD_PCT / 100.0),
             t['buy_price'] * (1 + hbe.LOSS_ARM_PCT / 100.0), hbe.DEADLINE_DAY))

print()
print('--- B. 周一(09-07)开盘买入清单：09-04确认信号 %d 只 ---' % len(monday_buys))
for t in sorted(monday_buys, key=lambda x: -x['score']):
    print('  %s %s | 评分%.1f %s | 周五收盘%.2f(参考) | 预算%.0f元'
          % (t['code'], nm(t['code']), t['score'], t['mode'],
             t['buy_price'], t['cost']))

print()
print('--- C. 本周真实出场（09-01~09-04）---')
if not real_exits:
    print('  无')
for t in real_exits:
    print('  %s %s | 买%s@%.2f → 卖%s@%.2f | %s | %+.2f%%'
          % (t['code'], nm(t['code']), t['buy_date'], t['buy_price'],
             t['sell_date'], t['sell_price'], t['exit_reason'], t['return_pct']))

print()
print('--- D. 合成日伪触发提示（09-04价位已贴近/触及条件线，周一盯盘）---')
if not fake_exits:
    print('  无')
for t in fake_exits:
    print('  %s %s | 买%s@%.2f | 伪触发=%s | 卖参考%.2f | 实际仍持仓,周一开盘若≤%.2f将触发'
          % (t['code'], nm(t['code']), t['buy_date'], t['buy_price'],
             t['exit_reason'], t['sell_price'], t['sell_price']))

print()
print('回测最终权益(含合成日): %.0f | R3停手段数: %d' % (res['final_capital'], len(res['stops'])))
print('完成')
