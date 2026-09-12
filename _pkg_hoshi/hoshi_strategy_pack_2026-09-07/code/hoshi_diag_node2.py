# -*- coding: utf-8 -*-
"""专项诊断：hard5_score9 在 节点2(2012-2015) 为什么比 baseline(节点2 +60.05%) 差很多 (+21.83%)。

核心问题拆解：hard5_score9 = hard5(硬止损提前到第5天) + score9(评分门槛 8->9)。
- 矩阵已知：hard5 单独在节点2 = +55.61%(接近baseline)，score9 单独在节点2 = +26.33%(暴跌)。
  => 节点2 的大幅下滑主要是 score9(提高评分门槛) 造成的。

本脚本目的：用 MIN_SCORE=8.0 在节点2 跑一遍(等价 baseline 在节点2 能买到的全部信号)，
把每笔交易按 score 分桶，重点看【分数落在 [8.0, 9.0) 区间、被 score9 过滤掉的那批】的总体盈亏，
判断：这批"低分信号"在 2012-2015 牛市/普涨行情里是不是实际上很赚钱？score9 是不是误杀了它们?
"""
import importlib.util
from collections import defaultdict

spec = importlib.util.spec_from_file_location('hbe', 'scripts/hoshi_backtest_exp.py')
hbe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbe)
hbe._log = lambda *a, **k: None
hbe.DEBUG = False
hbe.TOTAL_CAPITAL = 500000.0

code_bars, names, all_dates = hbe.load_data('scripts/hoshi_csv_long')

def run_score(tag, min_score, start='2012-01-01', end='2015-12-31'):
    hbe.MAX_BUY_PER_DAY = 0
    hbe.LOSS_START_DAY = 15
    hbe.LOSS_HARD_START_DAY = 15      # 为隔离"评分"影响，硬止损保持原版15（即纯 baseline 出场）
    hbe.MIN_SCORE = min_score
    hbe.MAX_SLOTS = 10
    hbe.EXIT_MODE = 'AUTO'
    res = hbe.run_backtest(code_bars, names, all_dates, start=start, end=end)
    closed = res['closed']
    ret = (res['final_capital'] - 500000.0) / 500000.0 * 100.0
    return closed, ret

# 用 MIN_SCORE=8.0 跑：拿到节点2 所有可买信号(含 [8,9) 的低分),这样能观察被 score9 滤掉的批次
closed8, ret8 = run_score('score8(baseline口径)', 8.0)
print('\n===== 节点2 (2012-2015) 出场 = 原版(硬止损15天) | 门槛 8.0 =====')
print('总笔=%d  收益=%+.2f%%' % (len(closed8), ret8))

# 按 score 分桶看盈亏
lo = [t for t in closed8 if 8.0 <= t['score'] < 9.0]
hi = [t for t in closed8 if t['score'] >= 9.0]
print('\n--- score∈[8.0,9.0) 被 score9 过滤掉的批次 (即 8->9 少做的交易) ---')
print('笔数=%d  净盈亏=%+.0f 元  平均%.2f%%  胜率=%.0f%%' %
      (len(lo), sum(t['pnl'] for t in lo),
       (sum(t['pnl'] for t in lo)/sum(t['cost'] for t in lo)*100 if lo else 0),
       100*sum(1 for t in lo if t['pnl']>0)/len(lo) if lo else 0))
# 低分批次的出场结构
from collections import Counter
cat = defaultdict(list)
for t in lo:
    r = t['exit_reason']
    if '止盈' in r and '超时' not in r: cat['止盈(峰值回落)'].append(t)
    elif '止损' in r: cat['止损'].append(t)
    elif '止盈超时' in r or '超时' in r: cat['超时强平'].append(t)
    else: cat[r].append(t)
for k, sub in sorted(cat.items(), key=lambda x: -sum(t['pnl'] for t in x[1])):
    print('   %-16s %4d笔  净%+8.0f  (均%+.1f%%)' %
          (k, len(sub), sum(t['pnl'] for t in sub),
           sum(t['pnl'] for t in sub)/sum(t['cost'] for t in sub)*100 if sub else 0))

print('\n--- score∈[9.0,∞) score9 保留的批次 ---')
print('笔数=%d  净盈亏=%+.0f 元  平均%.2f%%' %
      (len(hi), sum(t['pnl'] for t in hi),
       (sum(t['pnl'] for t in hi)/sum(t['cost'] for t in hi)*100 if hi else 0)))
# 深亏单在哪个 score 区间
print('\n--- 深亏单(收益率<=-25%)的 score 分布 ---')
deep_all = [t for t in closed8 if t['pnl'] < 0 and t['return_pct'] <= -25]
print('总深亏单=%d笔' % len(deep_all))
if deep_all:
    for rng in [(8.0,9.0),(9.0,100)]:
        sub=[t for t in deep_all if rng[0]<=t['score']<rng[1]]
        if sub:
            print('  score∈[%.0f,%.0f): %d笔 %s' % (rng[0],rng[1],len(sub),' '.join('%s%+.0f'%(t['code'],t['return_pct']) for t in sub[:6])))

# 对照: 门槛9.0
closed9, ret9 = run_score('score9', 9.0)
print('\n===== 节点2 门槛 9.0 (对照) =====')
print('总笔=%d  收益=%+.2f%%  (相对score8少做%d笔)' % (len(closed9), ret9, len(closed8)-len(closed9)))
print('\n完成')
