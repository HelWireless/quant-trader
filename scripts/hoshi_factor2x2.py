# -*- coding: utf-8 -*-
"""2x2 因子分解：把 h5s9 相对原版的收益差拆成"评分门槛"和"硬止损起点"两个独立效应。

h5s9 = (评分门槛 8 -> 9) + (硬止损起点 15天 -> 5天)
之前一直把它当整体看，无法回答"B窗口 [8,9) 批次只贡献 +7.4 万，
但 gap 却有 -49pp，剩下的损失从哪来"。

四格:
  V0 = score8 + stop15   (原版)
  V1 = score9 + stop15   (只动门槛)
  V2 = score8 + stop5    (只动止损)
  V3 = score9 + stop5    (h5s9)

效应定义:
  门槛效应@stop15 = V1 - V0
  门槛效应@stop5  = V3 - V2
  止损效应@score8 = V2 - V0
  止损效应@score9 = V3 - V1
  交互项          = (V3-V2) - (V1-V0) = (V3-V1) - (V2-V0)
"""
import importlib.util
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp3.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

WINDOWS = [
    ('A 2014-12~16-11 疯牛+股灾', '2014-12-01', '2016-11-30'),
    ('B 2019-05~21-04 核心资产慢牛', '2019-05-01', '2021-04-30'),
    ('C 2018-10~19-09 政策底反弹', '2018-10-01', '2019-09-30'),
    ('E 2016-02~19-01 熊', '2016-02-01', '2019-01-31'),
    ('F 2014-06~15-05 疯牛原版亏', '2014-06-01', '2015-05-31'),
]

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO')

VARIANTS = [
    ('V0 score8+stop15', 8.0, 15),
    ('V1 score9+stop15', 9.0, 15),
    ('V2 score8+stop5', 8.0, 5),
    ('V3 score9+stop5 ', 9.0, 5),
]


def set_cfg(score, stop_day):
    for k, v in BASE.items():
        setattr(hbe, k, v)
    hbe.MIN_SCORE = score
    hbe.LOSS_HARD_START_DAY = stop_day
    hbe.ADAPTIVE_SCORE = False
    hbe.ADAPTIVE_STOP = False
    hbe.RS_FILTER = False


def exit_stats(closed):
    agg = defaultdict(lambda: [0, 0.0])
    for t in closed:
        a = agg[t.get('exit_reason', '?')]
        a[0] += 1
        a[1] += t['pnl']
    return agg


table = {}
for tag, s, e in WINDOWS:
    row = {}
    for vname, sc, sd in VARIANTS:
        set_cfg(sc, sd)
        r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
        ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
        row[vname] = (ret, len(r['closed']), exit_stats(r['closed']))
        print('%-24s %-22s %+9.2f%%  笔数=%3d  R3停手=%d段'
              % (vname, tag, ret, len(r['closed']), len(r['stops'])), flush=True)
    table[tag] = row
    print('', flush=True)

print('=' * 78)
print('===== 2x2 因子分解（单位：百分点 pp）=====')
print('%-24s %9s %9s %9s %9s | %9s %9s %9s'
      % ('窗口', 'V0', 'V1', 'V2', 'V3', '门槛效应', '止损效应', '交互项'))
print('%-24s %9s %9s %9s %9s | %9s %9s %9s'
      % ('', 's8+d15', 's9+d15', 's8+d5', 's9+d5', '(V3-V2)', '(V3-V1)', ''))
print('-' * 100)
for tag, row in table.items():
    v0 = row['V0 score8+stop15'][0]
    v1 = row['V1 score9+stop15'][0]
    v2 = row['V2 score8+stop5'][0]
    v3 = row['V3 score9+stop5 '][0]
    eff_score = v3 - v2      # 门槛效应（在止损=5天条件下）
    eff_stop = v3 - v1       # 止损效应（在门槛=9条件下）
    inter = (v3 - v2) - (v1 - v0)
    print('%-24s %+9.1f %+9.1f %+9.1f %+9.1f | %+9.1f %+9.1f %+9.1f'
          % (tag, v0, v1, v2, v3, eff_score, eff_stop, inter))

print()
print('===== 另一条分解路径（交叉验证）=====')
print('%-24s %12s %12s' % ('窗口', '门槛@stop15', '止损@score8'))
print('-' * 52)
for tag, row in table.items():
    v0 = row['V0 score8+stop15'][0]
    v1 = row['V1 score9+stop15'][0]
    v2 = row['V2 score8+stop5'][0]
    v3 = row['V3 score9+stop5 '][0]
    print('%-24s %+12.1f %+12.1f' % (tag, v1 - v0, v2 - v0))
print('  (两条路径: gap = 门槛@stop15 + 止损@score9 = 止损@score8 + 门槛@stop5)')

print()
print('===== 出场原因分布（硬止损笔数 / 硬止损净盈亏 元）=====')
for tag, row in table.items():
    print('-- %s' % tag)
    for vname, _, _ in VARIANTS:
        ret, n, agg = row[vname]
        keys = [k for k in agg if '硬' in k or '止损' in k]
        hs_n = sum(agg[k][0] for k in keys)
        hs_p = sum(agg[k][1] for k in keys)
        all_p = sum(a[1] for a in agg.values())
        print('   %-18s 收益%+8.1f%% 总笔%3d 净盈亏%+12.0f | 止损类出场 %3d 笔 净%+11.0f (占净盈亏 %.0f%%)'
              % (vname, ret, n, all_p, hs_n, hs_p,
                 (hs_p / all_p * 100.0) if abs(all_p) > 1 else 0.0))

print('\n完成', flush=True)
