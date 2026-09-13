# -*- coding: utf-8 -*-
"""hoshi-cplus 策略 —— 参数定义与方案预设。

命名沿革
--------
该策略在 2026-09-12~09-13 的研究中被称为 **方案 B′（B prime）**，
为便于传播与工程化，自 2026-09-13 起**统一命名为 hoshi-cplus**。

    hoshi-cplus  ==  方案 B′  ==  评分9 + 启用日5 + R3关 + 广度20 + 硬止损 −6.0%

三个预设的对照（详见 docs/Hoshi_终局报告_2026-09-13.md §4）：

    原版 original : 评分8.0 / 硬止损启用日15 / −8.2% / R3 开
    方案B      B  : 评分9.0 / 硬止损启用日 5 / −8.2% / R3 关
    hoshi-cplus   : 评分9.0 / 硬止损启用日 5 / −6.0% / R3 关   ← 推荐
"""
from collections import namedtuple

# ================================================================================
# 一、固定参数（三方案共用，一般不要动）
# ================================================================================

# ---- 信号 ----
MA_FAST, MA_SLOW = 20, 60          # 趋势过滤均线
DROP_THRESH = -2.0                 # 单日跌幅低于此值算"连跌"中的一天
MIN_BARS = 66                      # 参与计算所需的最少 K 线根数

# ---- 资金管理 ----
TOTAL_CAPITAL = 500000.0
MAX_POSITION_R = 0.10              # 单股仓位上限（占权益比例）
MAX_SLOTS = 10                     # 最多同时持有
LOT_SIZE = 100

# ---- 出场 ----
MAX_HOLD = 40                      # 兜底最大持有交易日
PROFIT_ARM_PCT = 5.2               # 止盈武装阈值 +5.2%
PROFIT_TRAIL_PCT = 1.2             # 武装后峰值回落 1.2% 卖出
PROFIT_ARM_PCT_LATE = 3.2          # 第 15 天放宽后的武装阈值
PROFIT_TRAIL_PCT_LATE = 1.0
LOSS_ARM_PCT = -5.2                # 止损武装阈值
LOSS_REBOUND_PCT = 2.2             # 止损武装后反弹 +2.2% 卖出
LOSS_START_DAY = 15                # 反弹卖出式止损的起始日
DEADLINE_DAY = 25                  # 超时平仓日

# ---- 门控 ----
BREADTH_THRESH = 20.0              # 广度低于此值不开新仓
BREADTH_MIN_SAMPLE = 30            # 有效样本不足时不给广度信号
R3_DD_THRESH = 25.0
R3_COOLDOWNS = [60, 120, 120]
R3_ESCALATE_WINDOW = 120

# ---- 出场模式自适应 ----
HEALTH_N = 10                      # 看最近几笔已完成交易
HEALTH_THRESH = -1.0               # 平均收益率低于此值切 S4

# ---- 执行与费率 ----
COUNT_ENTRY_DAY = True             # 买入当天推进一次 hold_day（关键！）
ENFORCE_T1 = True                  # 买入当天不允许卖出
COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001        # 仅沪市（代码以 6 开头）

# ================================================================================
# 二、方案预设
# ================================================================================

Preset = namedtuple('Preset', [
    'name', 'key', 'min_score', 'loss_hard_start_day', 'loss_hard_pct', 'use_r3_gate',
])

PRESETS = {
    'original': Preset(
        name='原版 (8分/止损15/R3开)', key='original',
        min_score=8.0, loss_hard_start_day=15, loss_hard_pct=-8.2, use_r3_gate=True,
    ),
    'B': Preset(
        name='方案B (9分/止损5/R3关/−8.2%)', key='B',
        min_score=9.0, loss_hard_start_day=5, loss_hard_pct=-8.2, use_r3_gate=False,
    ),
    'cplus': Preset(
        name='hoshi-cplus (9分/止损5/R3关/−6.0%)', key='cplus',
        min_score=9.0, loss_hard_start_day=5, loss_hard_pct=-6.0, use_r3_gate=False,
    ),
}

#: 推荐的默认方案
DEFAULT_PRESET = 'cplus'

# 别名，方便按历史称呼取用
ALIASES = {
    'base': 'original',
    '原版': 'original',
    'Bp': 'cplus',
    "B'": 'cplus',
    'Bprime': 'cplus',
    'hoshi-cplus': 'cplus',
    'cplus': 'cplus',
}


def get_preset(key):
    """按名称/别名取方案预设，找不到抛 KeyError。"""
    k = ALIASES.get(key, key)
    if k not in PRESETS:
        raise KeyError('未知方案 %r，可选：%s' % (key, sorted(PRESETS)))
    return PRESETS[k]
