# -*- coding: utf-8 -*-
"""验证"能否避免 hard5_score9 在特定市场形态下大幅跑输"的候选方案。

窗口（含3个问题窗口 + 3个正向对照）:
  A 2014-12~2016-11 疯牛+股灾   gap -461.9
  B 2019-05~2021-04 核心资产慢牛 gap -49.0
  C 2018-10~2019-09 政策底反弹   gap -42.1
  D 2022-02~2025-01 熊          gap +40.5
  E 2016-02~2019-01 熊          gap +21.3
  F 2014-06~2015-05 疯牛(原版亏) gap +62.6

方案:
  1 baseline      评分8 + 止损15（原版）
  2 h5s9          评分9 + 硬止损第5天（当前改进版）
  3 S1_广度自适应   h5s9 + 广度20>=55%时评分放宽到8（普涨时参与）
  4 S2_波动自适应   h5s9 + 波动率>=1.8%时硬止损第5天，否则回到15（低波动不误杀）
  5 S3_相对强度     h5s9 + 剔除20日涨幅落后于市场均值的票（不买落后股）
  6 S4_折中门槛    评分8.5 + 硬止损第5天
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp3.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

WINDOWS = [
    ('A 2014-12~16-11', '2014-12-01', '2016-11-30'),
    ('B 2019-05~21-04', '2019-05-01', '2021-04-30'),
    ('C 2018-10~19-09', '2018-10-01', '2019-09-30'),
    ('D 2022-02~25-01', '2022-02-01', '2025-01-31'),
    ('E 2016-02~19-01', '2016-02-01', '2019-01-31'),
    ('F 2014-06~15-05', '2014-06-01', '2015-05-31'),
]

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO')


def set_cfg(**kw):
    for k, v in BASE.items():
        setattr(hbe, k, v)
    hbe.MIN_SCORE = 8.0
    hbe.LOSS_HARD_START_DAY = 15
    hbe.ADAPTIVE_SCORE = False
    hbe.ADAPTIVE_STOP = False
    hbe.RS_FILTER = False
    for k, v in kw.items():
        setattr(hbe, k, v)


SCHEMES = [
    ('1 baseline', dict(MIN_SCORE=8.0, LOSS_HARD_START_DAY=15)),
    ('2 h5s9', dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5)),
    ('3 S1_广度47', dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, ADAPTIVE_SCORE=True,
                       BREADTH_HI=47.0, SCORE_BREADTH_HI_MODE=8.0, SCORE_BREADTH_LO_MODE=9.0)),
    ('4 S2_波动1.8', dict(MIN_SCORE=9.0, ADAPTIVE_STOP=True, VOL_HI=1.8,
                        STOP_VOL_HI=5, STOP_VOL_LO=15)),
    ('5 S3_相对强度', dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, RS_FILTER=True, RS_ALPHA=1.0)),
    ('6 S4_折中8.5', dict(MIN_SCORE=8.5, LOSS_HARD_START_DAY=5)),
    ('7 S5_广度47+波动', dict(MIN_SCORE=9.0, ADAPTIVE_SCORE=True, BREADTH_HI=47.0,
                           SCORE_BREADTH_HI_MODE=8.0, SCORE_BREADTH_LO_MODE=9.0,
                           ADAPTIVE_STOP=True, VOL_HI=1.8, STOP_VOL_HI=5, STOP_VOL_LO=15)),
]

print('方案 x 窗口: %s' % ' | '.join(w[0] for w in WINDOWS), flush=True)
res = {}
for name, cfg in SCHEMES:
    res[name] = []
    for tag, s, e in WINDOWS:
        set_cfg(**cfg)
        r = hbe.run_backtest(code_bars, names, all_dates, start=s, end=e)
        ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
        res[name].append(ret)
        print('%-16s %-12s %+8.2f%%  (累计窗口 %d)' % (name, tag, ret, len(res[name])), flush=True)

print('\n===== 汇总：各窗口收益% =====', flush=True)
print('%-16s %10s %10s %10s %10s %10s %10s | %10s' %
      ('方案', 'A疯牛', 'B慢牛', 'C反弹', 'D熊', 'E熊', 'F疯牛', '6窗累加'))
for name, vals in res.items():
    print('%-16s %10.1f %10.1f %10.1f %10.1f %10.1f %10.1f | %10.0f' %
          (name, vals[0], vals[1], vals[2], vals[3], vals[4], vals[5],
           sum(500000 * (1 + v / 100.0) for v in vals)))
print('\n完成', flush=True)
