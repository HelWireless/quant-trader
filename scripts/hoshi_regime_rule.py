# -*- coding: utf-8 -*-
"""能否"提前"知道该用哪个变体？—— 市场状态切换规则搜索。

用 30 个随机窗口的 (原版收益, h5s9收益) 与对应市场特征，搜索单特征切分规则：
    若 特征 >= 阈值: 用 A 变体；否则用 B 变体
评价口径:
  - 等权平均收益
  - 几何平均（复利，更贴近实盘拼接）
  - 最差窗口（minimax）
并做 leave-one-out 交叉验证，避免 30 样本上的过拟合幻觉。

两种特征口径:
  WHOLE  = 全窗口聚合特征（解释性上界，含事后信息）
  EXANTE = 窗口起点前 60 个交易日的滚动特征（无前视，可直接执行）
"""
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 读 30 窗口收益 ----
wins = []
with open(os.path.join(HERE, 'hoshi_time_corr_windows.csv'), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        wins.append({'start': r['start'], 'end': r['end'],
                     'base': float(r['base_pct']), 'h5s9': float(r['h5s9_pct'])})

# ---- 读每日特征 ----
daily = []
with open(os.path.join(HERE, 'hoshi_market_features.csv'), encoding='utf-8') as f:
    for r in csv.DictReader(f):
        daily.append(r)
dates = [r['date'] for r in daily]
idx = {d: i for i, d in enumerate(dates)}
KEYS = ['breadth20', 'breadth60', 'uptrend', 'eq_ret', 'xdisp', 'limitup', 'limitdn', 'vol20']
NAME = {'breadth20': '广度MA20', 'breadth60': '广度MA60', 'uptrend': '多头排列%',
        'eq_ret': '市场日涨幅', 'xdisp': '截面离散度', 'limitup': '涨停占比',
        'limitdn': '跌停占比', 'vol20': '波动率20d'}
for r in daily:
    for k in KEYS:
        r[k] = float(r[k])


def whole_feat(w, k):
    sub = [r for r in daily if w['start'] <= r['date'] <= w['end']]
    n = len(sub)
    if k == 'eq_ret':
        m = 1.0
        for r in sub:
            m *= (1 + r['eq_ret'])
        return (m - 1) * 100.0
    return sum(r[k] for r in sub) / n * 100.0


def exante_feat(w, k, lookback=60):
    """窗口起点之前 lookback 个交易日的特征（无前视）"""
    i = idx.get(w['start'])
    if i is None:
        # 起点非交易日，取最近的
        cands = [d for d in dates if d <= w['start']]
        if not cands:
            return None
        i = idx[cands[-1]]
    lo = max(0, i - lookback)
    sub = daily[lo:i]
    if len(sub) < 10:
        return None
    if k == 'eq_ret':
        m = 1.0
        for r in sub:
            m *= (1 + r['eq_ret'])
        return (m - 1) * 100.0
    return sum(r[k] for r in sub) / len(sub) * 100.0


def geo(vals):
    p = 1.0
    for v in vals:
        p *= (1 + v / 100.0)
    return (p ** (1.0 / len(vals)) - 1) * 100.0 if len(vals) else 0.0


def evaluate(rows, key, thr, hi_var):
    """hi_var: 特征>=thr 时用哪个 'base'/'h5s9'"""
    picks = []
    for r in rows:
        v = r['f']
        if v is None:
            picks.append(r['h5s9'])          # 缺特征默认保守
            continue
        use = hi_var if v >= thr else ('base' if hi_var == 'h5s9' else 'h5s9')
        picks.append(r[use])
    return picks


def score(picks, mode):
    if mode == 'mean':
        return sum(picks) / len(picks)
    if mode == 'geo':
        return geo(picks)
    return min(picks)


allrows = {}
for mode_name, fn in (('WHOLE', whole_feat), ('EXANTE', exante_feat)):
    rows = []
    for w in wins:
        d = dict(w)
        d['_w'] = w
        rows.append(d)
    allrows[mode_name] = rows

# 基准
print('=' * 92)
print('===== 基准（30 窗口等权拼接）=====')
base_all = [w['base'] for w in wins]
h_all = [w['h5s9'] for w in wins]
orc = [max(w['base'], w['h5s9']) for w in wins]
wst = [min(w['base'], w['h5s9']) for w in wins]
print('%-22s 等权均值 %8.2f%%  几何均值 %8.2f%%  最差窗口 %8.2f%%  最好窗口 %8.2f%%'
      % ('全用原版', sum(base_all) / 30, geo(base_all), min(base_all), max(base_all)))
print('%-22s 等权均值 %8.2f%%  几何均值 %8.2f%%  最差窗口 %8.2f%%  最好窗口 %8.2f%%'
      % ('全用h5s9', sum(h_all) / 30, geo(h_all), min(h_all), max(h_all)))
print('%-22s 等权均值 %8.2f%%  几何均值 %8.2f%%  最差窗口 %8.2f%%  (事后诸葛，理论上限)'
      % ('Oracle 每窗选优', sum(orc) / 30, geo(orc), min(orc)))
print('%-22s 等权均值 %8.2f%%  (事后最差，下行暴露)' % ('Oracle 每窗选劣', sum(wst) / 30))

for mode_name, fn in (('WHOLE', whole_feat), ('EXANTE', exante_feat)):
    print()
    print('=' * 92)
    print('===== 单特征切分规则搜索 [%s] =====' %
          ('全窗口特征(解释性上界)' if mode_name == 'WHOLE' else '起点前60日滚动特征(可执行/无前视)'))
    best = []
    for k in KEYS:
        rows = []
        for w in wins:
            rows.append({'f': fn(w, k), 'base': w['base'], 'h5s9': w['h5s9']})
        vals = sorted(set(round(r['f'], 4) for r in rows if r['f'] is not None))
        if len(vals) < 4:
            continue
        cands = []
        for i in range(1, len(vals)):
            thr = (vals[i - 1] + vals[i]) / 2.0
            for hi_var in ('base', 'h5s9'):
                picks = evaluate(rows, k, thr, hi_var)
                cands.append((thr, hi_var, picks))
        for mode in ('mean', 'geo', 'min'):
            b = max(cands, key=lambda c: score(c[2], mode))
            n_hi = sum(1 for r in rows if r['f'] is not None and r['f'] >= b[0])
            best.append((score(b[2], mode), mode, k, b[0], b[1], n_hi, b[2]))
    best.sort(key=lambda x: -x[0])
    print('%-10s %-10s %-10s %10s %-8s %6s | %9s %9s %9s'
          % ('目标', '特征', '阈值', '高值用', '高值窗数', '', '等权均值', '几何均值', '最差窗'))
    print('-' * 92)
    seen = set()
    n = 0
    for s, mode, k, thr, hi, nhi, picks in best:
        key = (mode, k)
        if key in seen:
            continue
        seen.add(key)
        n += 1
        print('%-10s %-10s %10.3f %-10s %-8d | %+9.2f %+9.2f %+9.2f'
              % (mode, NAME[k], thr, hi, nhi,
                 sum(picks) / len(picks), geo(picks), min(picks)))

    # ---- Leave-one-out ----
    print()
    print('--- Leave-one-out 交叉验证（防过拟合）目标=几何均值 ---')
    loo_res = []
    for k in KEYS:
        rows = []
        for w in wins:
            rows.append({'f': fn(w, k), 'base': w['base'], 'h5s9': w['h5s9']})
        if any(r['f'] is None for r in rows):
            pass
        held = []
        for i in range(len(rows)):
            train = rows[:i] + rows[i + 1:]
            vals = sorted(set(round(r['f'], 4) for r in train if r['f'] is not None))
            if len(vals) < 4:
                continue
            bestc = None
            for j in range(1, len(vals)):
                thr = (vals[j - 1] + vals[j]) / 2.0
                for hi_var in ('base', 'h5s9'):
                    pk = evaluate(train, k, thr, hi_var)
                    sc = geo(pk)
                    if bestc is None or sc > bestc[0]:
                        bestc = (sc, thr, hi_var)
            _, thr, hi = bestc
            r = rows[i]
            if r['f'] is None:
                pick = r['h5s9']
            else:
                use = hi if r['f'] >= thr else ('base' if hi == 'h5s9' else 'h5s9')
                pick = r[use]
            held.append(pick)
        if len(held) == len(rows):
            loo_res.append((geo(held), sum(held) / len(held), min(held), k))
    loo_res.sort(key=lambda x: -x[0])
    print('%-12s %10s %10s %10s' % ('特征', 'LOO几何', 'LOO等权', 'LOO最差'))
    print('-' * 46)
    for g, m, mn, k in loo_res:
        print('%-12s %+10.2f %+10.2f %+10.2f' % (NAME[k], g, m, mn))
    print('  参照: 全用原版 几何 %+.2f%% | 全用h5s9 几何 %+.2f%% | Oracle 几何 %+.2f%%'
          % (geo(base_all), geo(h_all), geo(orc)))

print('\n完成', flush=True)
