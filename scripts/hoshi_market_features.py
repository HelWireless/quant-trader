# -*- coding: utf-8 -*-
"""计算全市场每日形态特征，并按30个回测窗口聚合，与方案收益差做相关性分析。

特征（每日，白名单A股截面）：
  breadth20=收盘>MA20比例, breadth60=收盘>MA60比例, uptrend=MA20>MA60比例
  eq_ret=当日等权平均收益, xdisp=截面收益标准差(领涨/落后分化度)
  limitup=涨幅>9.8%比例, limitdn=跌幅<-9.8%比例
  vol20=等权收益20日滚动标准差(波动率)
窗口聚合：各特征取窗口内均值；mkt_ret=窗口内等权收益复合；与 gap=h5s9-原版 做Pearson。
"""
import csv
import os
import math
from datetime import date

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(HERE, '..', 'data', 'tdx.duckdb'))
FEAT_CSV = os.path.join(HERE, 'hoshi_market_features.csv')
WIN_CSV = os.path.join(HERE, 'hoshi_time_corr_windows.csv')

WL = ("(symbol LIKE 'sh600%' OR symbol LIKE 'sh601%' OR symbol LIKE 'sh603%' "
      "OR symbol LIKE 'sh605%' OR symbol LIKE 'sh688%' OR symbol LIKE 'sh689%' "
      "OR symbol LIKE 'sz000%' OR symbol LIKE 'sz001%' OR symbol LIKE 'sz002%' "
      "OR symbol LIKE 'sz003%' OR symbol LIKE 'sz300%' OR symbol LIKE 'sz301%')")

con = duckdb.connect(DB, read_only=True)
print('查询每日市场特征（约1-3分钟）...', flush=True)
rows = con.execute(f"""
WITH s AS (
  SELECT k.symbol AS symbol, k.date AS date, k.close AS close,
    AVG(k.close) OVER (PARTITION BY k.symbol ORDER BY k.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
    AVG(k.close) OVER (PARTITION BY k.symbol ORDER BY k.date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60,
    k.close / NULLIF(LAG(k.close) OVER (PARTITION BY k.symbol ORDER BY k.date),0) - 1 AS ret
  FROM raw_kline_daily k
  LEFT JOIN raw_symbol_name n USING (symbol)
  WHERE {WL}
    AND (n.name IS NULL OR (n.name NOT LIKE '%ST%' AND n.name NOT LIKE '%退%'))
)
SELECT date,
  COUNT(*) AS n,
  AVG(CASE WHEN close > ma20 THEN 1.0 ELSE 0 END) AS breadth20,
  AVG(CASE WHEN close > ma60 THEN 1.0 ELSE 0 END) AS breadth60,
  AVG(CASE WHEN ma20 > ma60 THEN 1.0 ELSE 0 END) AS uptrend,
  AVG(ret) AS eq_ret,
  STDDEV_SAMP(ret) AS xdisp,
  AVG(CASE WHEN ret > 0.098 THEN 1.0 ELSE 0 END) AS limitup,
  AVG(CASE WHEN ret < -0.098 THEN 1.0 ELSE 0 END) AS limitdn
FROM s WHERE ret IS NOT NULL AND date >= DATE '2009-06-01'
GROUP BY date ORDER BY date
""").fetchall()
con.close()
print('得到 %d 个交易日' % len(rows), flush=True)

# 计算 20 日滚动波动率（等权收益）
dates = [r[0] for r in rows]
rets = [r[5] or 0.0 for r in rows]
vol20 = []
acc = []
for v in rets:
    acc.append(v)
    if len(acc) > 20:
        acc.pop(0)
    if len(acc) >= 10:
        m = sum(acc) / len(acc)
        var = sum((x - m) ** 2 for x in acc) / (len(acc) - 1)
        vol20.append(math.sqrt(var))
    else:
        vol20.append(None)

with open(FEAT_CSV, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['date', 'n', 'breadth20', 'breadth60', 'uptrend', 'eq_ret', 'xdisp', 'limitup', 'limitdn', 'vol20'])
    for r, v in zip(rows, vol20):
        w.writerow([r[0]] + ['%.6f' % (x if x is not None else 0) for x in r[1:]] +
                   ['%.6f' % (v if v is not None else 0)])
print('特征已保存: %s' % FEAT_CSV, flush=True)

# ---- 按窗口聚合 ----
wins = []
with open(WIN_CSV, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        wins.append({'start': date.fromisoformat(r['start']), 'end': date.fromisoformat(r['end']),
                     'len': int(r['len_months']), 'base': float(r['base_pct']), 'h5s9': float(r['h5s9_pct'])})

# 直接用内存里的 SQL 结果（顺序: date, n, breadth20, breadth60, uptrend, eq_ret, xdisp, limitup, limitdn）
feats = []
for r, v in zip(rows, vol20):
    feats.append((r[0], float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                  float(r[6]), float(r[7]), float(r[8]), float(v if v is not None else 0)))


def agg(w):
    sub = [f for f in feats if w['start'] <= f[0] <= w['end']]
    n = len(sub)
    mkt = 1.0
    for f in sub:
        mkt *= (1 + f[4])
    return {
        'n': n,
        'breadth20': sum(f[1] for f in sub) / n * 100,
        'breadth60': sum(f[2] for f in sub) / n * 100,
        'uptrend': sum(f[3] for f in sub) / n * 100,
        'mkt_ret': (mkt - 1) * 100,
        'xdisp': sum(f[5] for f in sub) / n * 100,
        'limitup': sum(f[6] for f in sub) / n * 100,
        'limitdn': sum(f[7] for f in sub) / n * 100,
        'vol20': sum(f[8] for f in sub) / n * 100,
    }


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    return cov / (vx * vy) if vx > 0 and vy > 0 else float('nan')


print('\n===== 30窗口市场特征 vs 方案收益差 =====')
hdr = ('%-12s %5s %9s %9s %8s %8s %8s %7s %7s %7s %7s %8s' %
       ('窗口', '年', '原版%', 'h5s9%', 'gap', '市场涨%', '广度20', '广度60', '多头%', '离散度', '涨停%', '波动%'))
print(hdr)
recs = []
for w in wins:
    a = agg(w)
    gap = w['h5s9'] - w['base']
    recs.append(dict(w=w, a=a, gap=gap))
    print('%-12s %5d %9.2f %9.2f %+8.1f %8.1f %8.1f %8.1f %7.1f %7.2f %7.2f %8.2f' %
          ('%s~%s' % (w['start'].strftime('%Y-%m'), w['end'].strftime('%Y-%m')),
           w['len'] // 12, w['base'], w['h5s9'], gap, a['mkt_ret'], a['breadth20'],
           a['breadth60'], a['uptrend'], a['xdisp'], a['limitup'], a['vol20']))

print('\n--- 收益差 gap(h5s9-原版) 与市场特征的 Pearson 相关 ---')
for key, label in [('mkt_ret', '市场涨幅'), ('breadth20', '广度MA20'), ('breadth60', '广度MA60'),
                   ('uptrend', '多头排列占比'), ('xdisp', '截面离散度'), ('limitup', '涨停占比'),
                   ('limitdn', '跌停占比'), ('vol20', '波动率20d')]:
    xs = [r['a'][key] for r in recs]
    ys = [r['gap'] for r in recs]
    print('%-14s r = %+.3f' % (label, pearson(xs, ys)))

print('\n--- 原版收益 与 市场特征的 Pearson 相关 ---')
for key, label in [('mkt_ret', '市场涨幅'), ('breadth20', '广度MA20'), ('limitup', '涨停占比'),
                   ('xdisp', '截面离散度'), ('vol20', '波动率20d')]:
    xs = [r['a'][key] for r in recs]
    ys = [r['w']['base'] for r in recs]
    print('%-14s r = %+.3f' % (label, pearson(xs, ys)))

print('\n--- 三个问题窗口的特征定位 ---')
targets = [('A 2014-12', date(2014, 12, 1)), ('B 2019-05', date(2019, 5, 1)),
           ('C 2018-10', date(2018, 10, 1))]
for name, d in targets:
    r = [x for x in recs if x['w']['start'] == d][0]
    print('%s: gap=%+.1fpp | 市场涨%+.1f%% 广度20=%.0f%% 多头=%.0f%% 离散=%.2f 涨停=%.2f%% 波动=%.2f%%'
          % (name, r['gap'], r['a']['mkt_ret'], r['a']['breadth20'], r['a']['uptrend'],
             r['a']['xdisp'], r['a']['limitup'], r['a']['vol20']))
print('\n完成')
