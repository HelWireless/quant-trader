# -*- coding: utf-8 -*-
"""锚点不一致排查 v2：窗口 2022-02-01~2025-01-31（9-11 锚点 t8 = +27.9341%）

已排除：
  H1 数据末端新增 9-07~9-11 的 bar
     -> run_backtest 在 dates 层就过滤了 end 之后全部日期（exp5:594-600），
        且 bar_on 用 idx_of[code].get(today) 精确匹配，新增末端数据无法影响
  H3 exp5 期末强平残留 bug
     -> A 组实测「期末未平仓 = 0」，根本没走强平路径

剩余候选 H2：广度门控数据漂移
  hoshi_market_features.py 直接从 data/tdx.duckdb 实时计算广度，
  而 9-11~9-12 做过 TDX 全量增量刷新；该表时间戳 9-12 00:47 晚于锚点 9-11 10:13。
  只要刷新改动了历史 K 线或 raw_symbol_name 的 ST 标记，历史广度值就会整体漂移。

本脚本用「门控敏感度」来判定 H2 是否成立：
  若开关/改变门控阈值能把结果拉回锚点附近，说明门控正是差异之源。
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0
hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
code_bars, names, all_dates = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))

START, END, ANCHOR = '2022-02-01', '2025-01-31', 27.9341
print('数据集：%d codes，日期 %s ~ %s' % (len(code_bars), all_dates[0], all_dates[-1]))
print('目标窗口 %s ~ %s，9-11 锚点(t8) = %+.4f%%\n' % (START, END, ANCHOR))

BASE = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
            ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
            SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
            USE_R3_GATE=False, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
            MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, LOSS_HARD_PCT=-8.2)


def run(label):
    r = hbe.run_backtest(code_bars, names, all_dates, start=START, end=END)
    ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
    print('  %-30s %+10.4f%%   买入%3d笔  期末未平仓 %d'
          % (label, ret, len(r.get('buys', []) or []), len(r.get('open_positions', []) or [])))
    return ret


for k, v in BASE.items():
    setattr(hbe, k, v)

print('=== 门控敏感度测试 ===')
a = run('A 原样(BREADTH=20)')
hbe.USE_BREADTH_GATE = False
b = run('B 关闭广度门控')
hbe.USE_BREADTH_GATE = True
hbe.BREADTH_THRESH = 0.0
c = run('C 门控阈值=0 (永久放行)')
hbe.BREADTH_THRESH = 100.0
d = run('D 门控阈值=100 (永久拦截)')
hbe.BREADTH_THRESH = 20.0
hbe.USE_BREADTH_GATE = False
hbe.MIN_SCORE = 8.0
hbe.LOSS_HARD_START_DAY = 15
e = run('E 原版(8分/止损15/无门控)')
hbe.MIN_SCORE = 9.0
hbe.LOSS_HARD_START_DAY = 5

print('\n=== 判定 ===')
print('9-11 锚点          = %+.4f%%' % ANCHOR)
print('A 原样             = %+.4f%%   (差 %+.4f)' % (a, a - ANCHOR))
print('B 关广度门控       = %+.4f%%   (与 A 差 %+.4f)' % (b, b - a))
print('C 门控全放行       = %+.4f%%   (与 A 差 %+.4f)' % (c, c - a))
print('D 门控全拦截       = %+.4f%%   (与 A 差 %+.4f)' % (d, d - a))
if max(abs(b - a), abs(c - a), abs(d - a)) > 1.0:
    print('\n-> 门控对结果影响显著(>1pp)，H2(广度数据漂移) 成立：')
    print('   market_features 在锚点之后被重算，历史广度值随之改变，')
    print('   导致跨版本的回测数值不可直接比较。')
else:
    print('\n-> 门控对结果几乎无影响，H2 不成立，需另找差异源。')
