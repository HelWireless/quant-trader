# Hoshi-cplus 实战手册：踩坑全集 · 方案 · 完整代码 · 邮件指导方案

> 整理：2026-09-14（基于 2026-09-12~09-14 的回测、双系统模拟、实盘持仓投影三轮工作）
> 适用对象：要把 hoshi-cplus 真正上线实盘的人

---

## 〇、TL;DR（先读这段）

1. **策略结论可信**：在「回测 / 理想执行模拟 / 真实执行模拟（20% 失误）」三种口径下，排序一致 —— **hoshi-cplus > 方案 B > 原版**。选 hoshi-cplus 不会错。
2. **绝对收益不可信**：三种口径的期末资金还差 171~302pp，回测/模拟的具体数字（如「243 万」）**不要引用**。本策略只管「买卖触发点」，不管「赚多少」。
3. **实战最大坑不是策略，是执行**：券商条件单只支持「价格触发」、不支持「时间条件」，而本策略满是「第 5 天 / 第 14 天 / 第 25 天」的时间规则 → 必须**人工按时间表挂/改/撤条件单**。
4. **前 4 天（D2–D4）无止损保护**（策略设计的一部分）。这 4 天是裸奔，风险敞口最大。
5. **投影脚本已就绪**：`scripts/hoshi_email_guide.py` 复用回测同款 `step_exit`，每天盘前生成「下个交易日操作 + 新信号候选」邮件。

---

## 一、模拟与回测踩过的坑（全集）

> 来源：① `docs/Hoshi_双系统模拟_三方案验证_2026-09-14.md` 的 9-bug 表；② 本会话实盘投影时新发现的 `hold_day` 投影坑；③ `MEMORY.md` 数据层纪律。

### 1.1 回测 ↔ 双系统模拟 对齐的 9 个 bug

| # | 坑 | 现象 | 根因 | 处理 |
|---|---|---|---|---|
| 1 | **信号源取错日** | 模拟整体晚一天 | `sig_by_date[D]` 是「以 D 为执行日、用截止 D-1 数据」；模拟却取了 `sig_by_date[D-1]` | 改取 `sig_by_date[T]`（执行日） |
| 2 | **`hold_day` 重复计数** | 出场整体错位 | 买入当天与次日各 +1 | 统一「买入当天 +1、之后每天 +1」 |
| 3 | **出场状态依赖回报推进** | 前 4 天持仓不推进 hold_day | 只在有成交时才 step | 每天（含停牌判断）都 step |
| 4 | **S4「每天可武装」被漏** | 止盈偏晚 | S4 本应随时可武装，代码只在 hd14/15 检查 | S4 每天检查 high≥arm |
| 5 | **S4 hd≥15 双路径漏** | 出场不完整 | 武装后只走硬止损，漏了「反弹卖出」 | 加 fallback 路径 |
| 6 | **已武装后未无条件跟踪止盈** | 被硬拖到超时 | 武装后仍走硬止损窗口 | 武装后只走移动止盈 |
| 7 | **peak / 破位低点累积规则** | 止盈价偏差 | peak 只在特定日更新 | 每天 max 更新 |
| 8 | **R3 门控从未实现（系统 A）** | **伪造「反转」** | 原版是唯一开 R3 的方案，模拟侧没实现 → 原版被跑成另一个策略 | 系统 A 实现 R3；修复后原版笔数 38→10、收益 −7.90%→−0.00% |
| 9 | **S3/S4 与 R3 依赖「当日出场已完成」的收益链** | 模式判定滞后、残差 171~302pp | 回测「先出场再买入」，A 盘前不知当天能否成交只能估算 | 部分修（用触发价估算），未根除 |

**第 8 个最致命**：它直接伪造了一个「原版 > cplus > B」的反转，差点让人推翻正确结论。教训：**对齐模拟与回测必须同区间、且模拟侧要把策略的所有门控都实现**。

### 1.2 本会话实盘投影新发现的坑

| # | 坑 | 现象 | 根因 | 修法 |
|---|---|---|---|---|
| 10 | **`hold_day` 投影 off-by-one** | 把「青山周一=hd5（硬止损生效首日）」误算成「hd4（未生效）」 | 漏了回测主循环里「**买入当天用当日 OHLC 推进一次 hold_day**」（`COUNT_ENTRY_DAY=True`，注释明写「漏了会让所有出场晚一天」） | 投影脚本 `project_holding` 严格复刻：买入当天先 `step_exit(allow_sell=False)` 再逐日 step |

**为何关键**：青山周五 9-11 实际是 **hd=4**（不是第 4 天整，是 hold_day 计数=4），周一 9-14 = **hd=5 = 硬止损生效首日**。若按错误的 hd=4 投影，会误判「周一还不到止损日、不用挂单」→ 错过最佳卖点。

### 1.3 数据层坑（来自 MEMORY.md 血泪教训）

| # | 坑 | 后果 | 纪律 |
|---|---|---|---|
| 11 | **`v_stock_qfq` 前复权视图已损坏**（2026-09-12 发现） | 最新日平安银行算出 0.04 元（真实 11.89）；全市场中位 3.34 vs bfq 10.48；514 只 <0.5 元；失真随日期逼近现在急剧扩大 | **禁用 qfq 视图**，一律用 `raw_kline_daily` 或 `v_stock_bfq`（其 close 是对的）；`qfq_factor` 列不可用 |
| 12 | **刷新后脏数据** | `max(date)` 变 9998-08-02（指数 upsert 溢出） | 每次 `refresh_tdx_duckdb.py` 后清脏：`DELETE FROM raw_kline_daily WHERE date > DATE '<今天>'`（同法清 `raw_basic_daily`）；约 142+115 行 |
| 13 | **国债逆回购价格陷阱** | `sh204003` 的「价格」是年化利率（145.50=14.55%），当股价用算出 −98.96% 假暴跌，能把一年期回测从 +20.29% 拖成 −15.58% | 用**白名单**过滤：只留 `sh600/601/603/605/688/689` + `sz000/001/002/003/300/301` |
| 14 | **非股票品种混入** | 指数/ETF/债券/北交所混入，信号失真 | 同上白名单；现成数据 `scripts/hoshi_csv_2005` 已过滤 |

---

## 二、实战注意事项（上线前必读 12 条）

1. **条件单只支持价格触发**：本策略的「第 5/14/15/25/40 天」全是时间规则，券商做不出。→ 必须**人工按时间表挂/改/撤**（见 §5 邮件每日提醒你）。这是实盘最大风险源，不是策略风险。
2. **前 4 天裸奔**：D2–D4 无止损保护（−6.0% 口径的一部分）。这 4 天若撞大跌，亏损可能远超 −6%。心理上要有准备。
3. **T+1**：买入当天不可卖。周一买的，周二才能卖。
4. **别手软改参数**：既然验证选了 hoshi-cplus（−6.0% 止损、关 R3），就不要因为「青山趋势健康想放宽到 −8.2%」而改 → 破坏 180 窗验证的一致性，长期更亏。
5. **触发价取整**：A 股 tick 0.01。条件单触发价设为取整值（如 `≤ 3.67`），实测成交在触发价或略差；别设到 3.66 导致多亏 0.007。
6. **盘前挂单、别等盘中**：青山离止损只差 1 分钱时，开盘一瞬就成交，手动追不上。
7. **反弹式止损多数券商做不出**：D15 起的「−5.2% 破位后反弹 +2.2% 卖」在条件单里难实现。实盘建议**只用 −6.0% 硬止损覆盖**（回测已验证两者接近但不等价，差异未量化，建议上线后跟踪）。
8. **数据新鲜度**：盘前确认行情已增量刷新、无 9998 年脏行；用 raw/bfq，禁用 qfq 视图。
9. **绝对收益不可信**：回测/模拟绝对值差 171~302pp，本指导只管触发点，不管赚多少。别用回测数字做资金规划。
10. **滑点/冲击成本未建模**：策略交易超跌小盘股，冲击成本不低，实盘收益会低于回测。
11. **幸存者偏差未处理**：标的池按当前名称表剔除 ST/退市，历史已退市票未纳入 → 回测收益可能略被高估。
12. **广度门控依赖全市场数据**：广度 = 「昨日收盘 > 自身 MA60 的标的数占比」，需全市场（如 `hoshi_csv_2005`，5310 只）才准；样本不足（n_valid<30）则不开新仓。

---

## 三、hoshi-cplus 完整方案

### 3.1 一句话策略

> **在大盘仍多头排列的个股中，找「连跌两天 + 企稳 + 次日收阳」的买点，第 5 天起武装 −6.0% 硬止损，靠高周转与复利累积收益。**

### 3.2 参数总表（hoshi-cplus）

| 类别 | 参数 | 值 | 说明 |
|---|---|---|---|
| 信号 | MA_FAST / MA_SLOW | 20 / 60 | 趋势过滤均线（要求 MA20>MA60） |
| 信号 | DROP_THRESH | −2.0% | 单日跌幅低于此算「连跌」 |
| 信号 | MIN_BARS | 66 | 参与计算最少 K 线 |
| 资金 | TOTAL_CAPITAL | 50 万 | 默认本金 |
| 资金 | MAX_POSITION_R | 10% | 单股仓位上限 |
| 资金 | MAX_SLOTS | 10 | 最多同时持有 |
| 资金 | LOT_SIZE | 100 | 一手 |
| 出场 | 硬止损 | **−6.0%**，第 5 天起 | `loss_hard_pct` / `loss_hard_start_day` |
| 出场 | 止盈武装 | +5.2%（D14）/ +3.2%（D15 放宽） | `PROFIT_ARM_PCT` / `PROFIT_ARM_PCT_LATE` |
| 出场 | 移动止盈 | 峰值回落 1.2%（D14）/ 1.0%（D15） | `PROFIT_TRAIL_PCT` / `PROFIT_TRAIL_PCT_LATE` |
| 出场 | 反弹式止损 | −5.2% 破位后反弹 +2.2% 卖（D15 起） | `LOSS_ARM_PCT` / `LOSS_REBOUND_PCT` |
| 出场 | 超时 | 第 25 天开盘平 | `DEADLINE_DAY` |
| 出场 | 兜底 | 第 40 天收盘强平 | `MAX_HOLD` |
| 门控 | 广度阈值 | 20% | `BREADTH_THRESH`（<30 样本不开仓） |
| 门控 | R3 | **关闭** | `use_r3_gate=False`（顺周期错误风控） |
| 模式 | S3/S4 | 近 10 笔均收益 < −1% 切 S4 | `HEALTH_THRESH` |

### 3.3 三方案对比

| 方案 | 评分 | 硬止损启用日 | 硬止损 | R3 | 180 窗几何 | 最差窗 | 负窗 |
|---|---|---|---|---|---|---|---|
| 原版 original | 8.0 | 15 | −8.2% | 开 | +15.82% | −33.53% | 68/179 |
| 方案 B | 9.0 | 5 | −8.2% | 关 | +89.19% | −8.11% | 13/179 |
| **hoshi-cplus** | **9.0** | **5** | **−6.0%** | **关** | **+109.07%** | **−6.78%** | **4/179** |

**hoshi-cplus = cplus = B′ = 评分 9 + 硬止损第 5 天 + −6.0% + 关 R3 + 广度 20%**

### 3.4 出场规则优先级（自上而下，命中即返回）

1. **止盈**：已武装且 `low ≤ peak×(1−trail%)` → 卖（止盈）
2. **硬止损兜底**：第 5~14 天且未武装，`low ≤ 成本×(1−6%)` → 卖（硬止损）
3. **反弹式止损**：第 15 天起且未武装，跌破 `成本×(1−5.2%)` 后反弹 `+2.2%` → 卖；或触 `成本×(1−6%)` 硬兜底
4. **超时**：第 25 天开盘 → 卖
5. **兜底强平**：第 40 天收盘 → 卖

> ⚠️ **武装（armed）在 S3 模式下只在第 14、15 天检查**（见 `exits.py`）：即便持仓期间峰值早已过武装线，第 14 天前 `armed` 恒为 False，走硬止损。这是 1.2 节第 10 坑的反面——**别因为峰值过线就以为已武装**。

### 3.5 验证结论（180 窗，数据 2005 起，5310 只）

- hoshi-cplus vs 原版：**+109.58pp**（173/179 胜，97%），t=15.25，p=1.1e-43
- hoshi-cplus vs 方案 B：**+24.39pp**（160/179 胜，89%），t=11.83，p=5.8e-29
- 优势随持有期单调放大（1 年 +1.5pp → 7 年 +46pp）；14 个起点年份全部胜出
- 样本从 60 窗扩到 180 窗，效应量不减反增 → 非样本偶然

### 3.6 逻辑流程（文字版）

```
每日盘前：
  ├─ 持仓投影（每只）：step_exit 从买入日复刻到昨收
  │     → 算出「下个交易日」触发价与动作（硬止损/止盈/超时）
  ├─ 新信号扫描：MA20>MA60 且连跌2天+企稳+次日收阳 → 评分≥9
  │     → 广度门控通过才给候选
  └─ 生成邮件：持仓操作 + 买入指令单 + 风控提示
盘中：
  ├─ 条件单自动成交（价格触发）
  └─ 人工按时间表挂/改/撤（第5天挂止损、第14天查武装、第25天超时平）
```

---

## 四、完整代码（hoshi_cplus 包）

> 代码即 `hoshi_cplus/` 目录，纯标准库、零依赖、可独立使用。以下为截至 2026-09-14 的完整内容。

### 4.1 `config.py`

```python
# -*- coding: utf-8 -*-
"""hoshi-cplus 策略 —— 参数定义与方案预设。"""
from collections import namedtuple

# ================================================================================
# 一、固定参数（三方案共用，一般不要动）
# ================================================================================
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
    'original': Preset(name='原版 (8分/止损15/R3开)', key='original',
        min_score=8.0, loss_hard_start_day=15, loss_hard_pct=-8.2, use_r3_gate=True),
    'B': Preset(name='方案B (9分/止损5/R3关/−8.2%)', key='B',
        min_score=9.0, loss_hard_start_day=5, loss_hard_pct=-8.2, use_r3_gate=False),
    'cplus': Preset(name='hoshi-cplus (9分/止损5/R3关/−6.0%)', key='cplus',
        min_score=9.0, loss_hard_start_day=5, loss_hard_pct=-6.0, use_r3_gate=False),
}

DEFAULT_PRESET = 'cplus'

ALIASES = {
    'base': 'original', '原版': 'original', 'Bp': 'cplus', "B'": 'cplus',
    'Bprime': 'cplus', 'hoshi-cplus': 'cplus', 'cplus': 'cplus',
}

def get_preset(key):
    k = ALIASES.get(key, key)
    if k not in PRESETS:
        raise KeyError('未知方案 %r，可选：%s' % (key, sorted(PRESETS)))
    return PRESETS[k]
```

### 4.2 `signals.py`

```python
# -*- coding: utf-8 -*-
"""K 线形态与入场信号（hoshi-cplus）。"""
from .config import (MA_FAST, MA_SLOW, DROP_THRESH, MIN_BARS)

def body_size(o, c):
    return abs(c - o)

def upper_shadow(o, h, c):
    return h - max(o, c)

def lower_shadow(o, c, l):
    return min(o, c) - l

def candle_range(h, l):
    return h - l

def is_hammer(o, h, l, c):
    rng = candle_range(h, l)
    if rng <= 0 or c <= 0:
        return False
    body = body_size(o, c)
    low_sh = lower_shadow(o, c, l)
    up_sh = upper_shadow(o, h, c)
    if body / rng > 0.3:
        return False
    if body > 0 and low_sh < body * 1.5:
        return False
    if body == 0 and low_sh < rng * 0.4:
        return False
    if up_sh > rng * 0.5:
        return False
    return True

def is_doji(o, h, l, c):
    rng = candle_range(h, l)
    if rng <= 0 or c <= 0:
        return False
    return body_size(o, c) / rng < 0.15

def is_stabilization(o, h, l, c):
    return is_hammer(o, h, l, c) or is_doji(o, h, l, c)

def calc_score(total_drop, o1, h1, l1, c1, confirm_chg):
    score = 3.0
    d = abs(total_drop)
    if 10 <= d <= 25:
        score += 2.0
    elif d > 25:
        score += 1.5
    elif d >= 5:
        score += 1.0
    if is_hammer(o1, h1, l1, c1):
        score += 2.5
    elif is_doji(o1, h1, l1, c1):
        score += 2.0
    else:
        score += 1.0
    ls = lower_shadow(o1, c1, l1)
    rng = candle_range(h1, l1)
    if rng > 0 and ls / rng > 0.5:
        score += 1.0
    if confirm_chg > 5:
        score += 1.5
    elif confirm_chg > 2:
        score += 1.0
    return round(min(score, 10.0), 1)

def detect_signal(opens, highs, lows, closes):
    """检测 Hoshi confirmation 信号。传入序列是【截止信号日 D 的昨天】的 OHLC。"""
    n = len(closes)
    if n < MIN_BARS - 1:
        return None
    ma20 = sum(closes[-MA_FAST:]) / float(MA_FAST)
    ma60 = sum(closes[-MA_SLOW:]) / float(MA_SLOW)
    if ma60 <= 0 or ma20 <= ma60:
        return None

    def chg(i):
        prev = closes[i - 1]
        if prev <= 0:
            return 0.0
        return (closes[i] - prev) / prev * 100.0

    chg_d3 = chg(n - 4); chg_d2 = chg(n - 3)
    chg_d1 = chg(n - 2); chg_d0 = chg(n - 1)

    drop_days = []
    if chg_d3 < DROP_THRESH:
        drop_days.append(chg_d3)
    if chg_d2 < DROP_THRESH:
        drop_days.append(chg_d2)
    if len(drop_days) < 2:
        return None
    total_drop = sum(drop_days)

    i_d1 = n - 2
    o1, h1, l1, c1 = opens[i_d1], highs[i_d1], lows[i_d1], closes[i_d1]
    stabilization = is_stabilization(o1, h1, l1, c1) or (
        -2 <= chg_d1 <= 5 and c1 > 0 and body_size(o1, c1) / c1 < 0.03)
    if not stabilization:
        return None
    if chg_d0 <= 0:
        return None
    return calc_score(total_drop, o1, h1, l1, c1, chg_d0)
```

### 4.3 `exits.py`

```python
# -*- coding: utf-8 -*-
"""出场规则（hoshi-cplus）。"""
from .config import (PROFIT_ARM_PCT, PROFIT_TRAIL_PCT, PROFIT_ARM_PCT_LATE,
                     PROFIT_TRAIL_PCT_LATE, LOSS_ARM_PCT, LOSS_REBOUND_PCT,
                     LOSS_START_DAY, DEADLINE_DAY, MAX_HOLD)

def new_position(code, entry, shares, cost, mode='S3', score=0.0):
    return dict(code=code, entry=entry, shares=shares, cost=cost,
                hold_day=0, peak=entry, armed=False, trail_pct=PROFIT_TRAIL_PCT,
                loss_armed=False, trough=entry, mode=mode, score=score)

def step_exit(pos, high, low, open_, close, allow_sell,
              loss_hard_start_day, loss_hard_pct):
    pos['hold_day'] += 1
    hd = pos['hold_day']
    entry = pos['entry']
    mode = pos['mode']
    armed = pos['armed']
    trail_pct = pos['trail_pct']

    # ---- 止盈武装 ----
    if mode == 'S3':
        if hd == 14 and not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                armed = True; trail_pct = PROFIT_TRAIL_PCT; pos['peak'] = high
            else:
                pos['peak'] = max(pos['peak'], high)
        elif hd == 15 and not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT_LATE / 100.0):
                armed = True; trail_pct = PROFIT_TRAIL_PCT_LATE
            pos['peak'] = max(pos['peak'], high)
        elif hd > 15:
            pos['peak'] = max(pos['peak'], high)
    else:  # S4
        if not armed:
            if high >= entry * (1 + PROFIT_ARM_PCT / 100.0):
                armed = True; trail_pct = PROFIT_TRAIL_PCT; pos['peak'] = high
            else:
                pos['peak'] = max(pos['peak'], high)

    pos['armed'] = armed
    pos['trail_pct'] = trail_pct

    # ---- 1. 止盈 ----
    if armed:
        pos['peak'] = max(pos['peak'], high)
        trail_price = pos['peak'] * (1 - trail_pct / 100.0)
        if low <= trail_price:
            return (trail_price, '止盈') if allow_sell else None

    # ---- 2. 提前硬止损兜底 ----
    if loss_hard_start_day < LOSS_START_DAY and not armed:
        if loss_hard_start_day <= hd < LOSS_START_DAY:
            hard_price = entry * (1 + loss_hard_pct / 100.0)
            if low <= hard_price:
                return (hard_price, '止损(硬)') if allow_sell else None

    # ---- 3. 反弹卖出式止损 ----
    if hd >= LOSS_START_DAY and not armed:
        if not pos['loss_armed'] and low <= entry * (1 + LOSS_ARM_PCT / 100.0):
            pos['loss_armed'] = True; pos['trough'] = low
        if pos['loss_armed']:
            pos['trough'] = min(pos['trough'], low)
            rebound = pos['trough'] * (1 + LOSS_REBOUND_PCT / 100.0)
            if high >= rebound:
                return (rebound, '止损(反弹)') if allow_sell else None
            if pos['trough'] <= entry * (1 + loss_hard_pct / 100.0):
                return (entry * (1 + loss_hard_pct / 100.0), '止损(硬)') if allow_sell else None

    # ---- 4. 超时 ----
    if not armed and hd == DEADLINE_DAY:
        return (open_, '超时') if allow_sell else None

    # ---- 5. 兜底强平 ----
    if hd >= MAX_HOLD:
        return (close, '强平') if allow_sell else None

    return None
```

### 4.4 `gates.py`

```python
# -*- coding: utf-8 -*-
"""门控：市场广度 + R3 回撤停手（hoshi-cplus）。"""
from .config import (BREADTH_THRESH, BREADTH_MIN_SAMPLE,
                     R3_DD_THRESH, R3_COOLDOWNS, R3_ESCALATE_WINDOW)

def breadth_ok(n_above, n_valid, thresh=BREADTH_THRESH):
    if n_valid < BREADTH_MIN_SAMPLE:
        return False
    return (n_above * 100.0 / n_valid) >= thresh

def breadth_value(n_above, n_valid):
    if n_valid < BREADTH_MIN_SAMPLE:
        return None
    return n_above * 100.0 / n_valid

class R3Gate(object):
    """R3 权益回撤门控（hoshi-cplus 默认关闭）。顺周期风控，超跌反弹策略下是错误风控。"""
    def __init__(self, dd_thresh=R3_DD_THRESH, cooldowns=None, esc_window=R3_ESCALATE_WINDOW):
        self.dd_thresh = dd_thresh
        self.cooldowns = list(cooldowns or R3_COOLDOWNS)
        self.esc_window = esc_window
        self.stop_since = None
        self.peak_offset = 0
        self.last_recover = None
        self.level = 0

    def __call__(self, completed_rets, cur_date):
        if not completed_rets:
            return True
        if self.stop_since is not None and cur_date is not None:
            if (cur_date - self.stop_since).days < self.cooldowns[self.level]:
                return False
            self.peak_offset = len(completed_rets)
            self.stop_since = None
            self.last_recover = cur_date
            return True
        eq = 1.0
        for t in completed_rets[:self.peak_offset]:
            eq *= (1 + t / 100.0)
        peak = eq
        for t in completed_rets[self.peak_offset:]:
            eq *= (1 + t / 100.0)
            peak = max(peak, eq)
        dd = (eq - peak) / peak * 100.0 if peak > 0 else 0.0
        if dd < -self.dd_thresh:
            if self.last_recover is not None and cur_date is not None:
                if (cur_date - self.last_recover).days < self.esc_window:
                    self.level = min(self.level + 1, len(self.cooldowns) - 1)
                else:
                    self.level = 0
            self.stop_since = cur_date
            return False
        return True
```

### 4.5 `data.py`（核心片段）

```python
# -*- coding: utf-8 -*-
"""数据加载与预计算（hoshi-cplus）。"""
import csv, glob, os
from datetime import date
from .config import MA_FAST, MA_SLOW, MIN_BARS
from .signals import detect_signal

class Bar(object):
    __slots__ = ('date', 'open', 'high', 'low', 'close', 'volume')
    def __init__(self, d, o, h, l, c, v):
        self.date = d; self.open = o; self.high = h
        self.low = l; self.close = c; self.volume = v

def load_data(input_path):
    """目录模式：每个 CSV 一列 date,open,high,low,close,volume，文件名 <code>_<name>.csv。"""
    code_bars = {}; names = {}
    for path in sorted(glob.glob(os.path.join(input_path, '*.csv'))):
        stem = os.path.basename(path)[:-4]
        code = stem.split('_')[0]
        name = stem[len(code) + 1:] if len(stem) > len(code) + 1 else ''
        rows = []
        try:
            with open(path, encoding='utf-8-sig') as f:
                rd = csv.reader(f); next(rd, None)
                for r in rd:
                    if len(r) < 6:
                        continue
                    try:
                        rows.append(Bar(date(int(r[0][0:4]), int(r[0][5:7]), int(r[0][8:10])),
                                        float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
                    except (ValueError, IndexError):
                        continue
        except Exception:
            continue
        if rows:
            rows.sort(key=lambda b: b.date)
            code_bars[code] = rows; names[code] = name
    return code_bars, names

def precompute(code_bars, verbose=True):
    """预计算全局日期、逐日信号、逐日广度。返回 (dates, sig_by_date, n_above, n_valid, idx_of)。"""
    dateset = set()
    for bars in code_bars.values():
        for b in bars:
            dateset.add(b.date)
    dates = sorted(dateset)
    didx = {d: i for i, d in enumerate(dates)}
    idx_of = {code: {b.date: k for k, b in enumerate(bars)} for code, bars in code_bars.items()}
    n_above = [0] * len(dates); n_valid = [0] * len(dates); sig_by_date = {}
    for code, bars in code_bars.items():
        n = len(bars)
        pre = [0.0] * (n + 1)
        for k in range(n):
            pre[k + 1] = pre[k] + bars[k].close
        for k in range(n):
            if k < MIN_BARS - 1:
                continue
            d = bars[k].date; di = didx[d]
            ma60 = (pre[k] - pre[k - MA_SLOW]) / float(MA_SLOW) if k >= MA_SLOW else None
            if ma60 is not None and ma60 > 0:
                n_valid[di] += 1
                if bars[k - 1].close > ma60:
                    n_above[di] += 1
            lo = max(0, k - MIN_BARS)
            seg = bars[lo:k]
            s = detect_signal([b.open for b in seg], [b.high for b in seg],
                              [b.low for b in seg], [b.close for b in seg])
            if s is not None:
                sig_by_date.setdefault(d, []).append((s, code))
    if verbose:
        print('  预计算完成：%d 只标的，%d 个交易日（%s ~ %s）' % (len(code_bars), len(dates), dates[0], dates[-1]))
    return dates, sig_by_date, n_above, n_valid, idx_of
```

> ⚠️ 三个实现坑（漏任何一个系统性偏差）：① 买入当天推进 `hold_day`；② 广度样本需 ≥66 根 K 线；③ 广度按**全局日期索引**累加（停牌错位）。

### 4.6 `orders.py`（核心片段：扫描 + 指令单渲染）

```python
# -*- coding: utf-8 -*-
"""下单指令单生成（hoshi-cplus）。券商条件单只支持价格触发，故输出带日期时间表的手动清单。"""
from .config import (LOT_SIZE, MAX_POSITION_R, PROFIT_ARM_PCT, PROFIT_TRAIL_PCT,
                     PROFIT_ARM_PCT_LATE, PROFIT_TRAIL_PCT_LATE, LOSS_ARM_PCT,
                     LOSS_REBOUND_PCT, LOSS_START_DAY, DEADLINE_DAY, MAX_HOLD, get_preset)

def scan_signals(prepared, code_bars, names, day, preset, equity=500000.0, held=(), max_slots=10):
    from .gates import breadth_ok, breadth_value
    dates, sig_by_date, n_above, n_valid, idx_of = prepared
    if day not in dates:
        return None
    di = dates.index(day)
    b_val = breadth_value(n_above[di], n_valid[di])
    if not breadth_ok(n_above[di], n_valid[di]):
        return dict(breadth=b_val, breadth_pass=False, candidates=[])
    free = max_slots - len(held)
    sigs = sorted([x for x in sig_by_date.get(day, ())
                   if x[0] >= preset.min_score and x[1] not in held], key=lambda x: -x[0])
    cands = []
    for score, code in sigs:
        if len(cands) >= free:
            break
        k = idx_of[code].get(day)
        if k is None:
            continue
        ref = code_bars[code][k].close
        budget = equity * MAX_POSITION_R
        shares = int(budget // ref // LOT_SIZE) * LOT_SIZE
        if shares <= 0:
            continue
        cands.append(dict(code=code, name=names.get(code, ''), score=score, signal_day=day,
                          ref_close=ref, shares=shares, est_amount=shares * ref))
    return dict(breadth=b_val, breadth_pass=True, candidates=cands)
```

> 完整 `build_plan` / `render_plan`（生成每只标的 D1~D40 时间表与触发价 Markdown）见仓库 `hoshi_cplus/orders.py`。

### 4.7 `backtest.py`（主循环，含关键注释）

```python
# 买入当天用当日 OHLC 推进一次出场状态（关键！漏了会让所有出场晚一天）
if COUNT_ENTRY_DAY:
    step_exit(positions[code], b.high, b.low, b.open, b.close, False,
              p.loss_hard_start_day, p.loss_hard_pct)
```

> 出场判定顺序：① 出场（step_exit）→ ② 门控（R3/breadth）→ ③ 广度+买入（新_position 后立刻 COUNT_ENTRY_DAY 推进）。期末用窗口内最后一根 bar 强平。完整代码见仓库 `hoshi_cplus/backtest.py`。

### 4.8 运行方式

```bash
# 单窗口回测
python -m hoshi_cplus --data scripts/hoshi_csv_2005 --preset cplus \
    --start 2011-03-01 --end 2016-02-29

# 批量：多方案 × 多窗口
python -m hoshi_cplus --data scripts/hoshi_csv_2005 \
    --windows scripts/windows_180.csv --schemes cplus,B,original --out verify.csv

# 信号扫描（输出买入指令单）
python -m hoshi_cplus --data scripts/hoshi_csv_2005 --scan 2026-09-11
```

---

## 五、邮件指导输出方案（细节）

### 5.1 目标

每个交易日**盘前**（建议北京 08:30 前，即 UTC 00:30）自动生成一封邮件，让操作者一眼知道：

1. **当前持仓的下个交易日操作**：每只的触发价、是否该卖、后续时间表（D5 挂止损 / D14 查武装 / D25 超时平）
2. **当日新信号候选**：评分≥9 且广度通过的买入指令单（含股数、金额、时间表）
3. **风控提示**：数据日期、广度值、R3 状态、前 4 天裸奔提醒

### 5.2 输入

| 输入 | 来源 | 说明 |
|---|---|---|
| 持仓清单 `holdings.json` | 人工维护 / 券商导出 | `[{code,name,cost,shares,buy_date}, ...]` |
| 行情数据 | `scripts/hoshi_csv_2005`（5310 只，全量） | 盘前需增量刷新 |
| 方案 | `cplus` | 固定 |

### 5.3 引擎（本会话产出）

**`scripts/hoshi_email_guide.py`** —— 复用回测同款 `step_exit`，严格复刻「买入当天推进 hold_day」，逐只投影持仓到下个交易日；再用 `scan_signals` 扫候选；最后渲染 Markdown。

```bash
python scripts/hoshi_email_guide.py \
    --data scripts/hoshi_csv_2005 \
    --holdings scripts/holdings.json \
    --preset cplus --scan-day 2026-09-11 \
    --out scripts/hoshi_email_guide.md
# 直发（需环境变量 SMTP_HOST/PORT/USER/PASS/MAIL_TO）
python scripts/hoshi_email_guide.py --data scripts/hoshi_csv_2005 --send
```

投影逻辑核心（与回测一致，避开 1.2 第 10 坑）：

```python
pos = new_position(code, cost, shares, cost*shares, mode='S3')
# 买入当天推进一次（关键）
step_exit(pos, b0.high, b0.low, b0.open, b0.close, False, p.loss_hard_start_day, p.loss_hard_pct)
for b in bars[bi+1:]:                      # 之后每天
    res = step_exit(pos, b.high, b.low, b.open, b.close, True,
                    p.loss_hard_start_day, p.loss_hard_pct)
    if res:  # 历史已触发 → 提示"应已卖出，请核对"
        ...
next_hd = pos['hold_day'] + 1             # 下个交易日
# 按 next_hd 与 armed 状态生成指令（硬止损 / 止盈 / 反弹 / 超时）
```

### 5.4 输出格式（模板）

```
# Hoshi-cplus 盘前操作指导
> 生成时间：…　方案：hoshi-cplus (9分/止损5/R3关/−6.0%)　数据截至：…

## 一、当前持仓 · 下个交易日操作
### 600103 青山纸业
| 成本 | 3.901 × 7300 股 |
| 最新(2026-09-11) | 3.67（浮动 −6.0%） |
| 持有天数 | 第 4 天（下个交易日 = 第 5 天，2026-09-14） |
| 是否武装 | 否 |
| 下个交易日动作 | 🔴 硬止损窗口：下个交易日若最低 ≤ 3.67 卖出全部（硬止损 −6.0%） |
后续时间表：D5 挂止损 / D14 查武装(≥4.10) / D25 超时平 / D40 兜底

### 601020 华钰矿业
…（硬止损 20.73，下个交易日第 9 天，已在区间内）

## 二、新信号候选（买入指令单）
（广度 X% 通过/未通过；候选 N 只；每只给 D1 买入+D5~D40 时间表）

## 三、风控提示
- R3 关闭；前 4 天裸奔；T+1；条件单只价格触发；反弹式止损多数券商做不出；
  数据需刷新且无脏行；禁用 qfq；绝对收益不可信。
```

### 5.5 cron 集成（建议）

```cron
# 盘后生成草稿（北京 20:00 = UTC 12:00）：跑信号扫描，存文件
0 12 * * 1-5  cd /home/cody/projects/quant-trader && \
  python scripts/hoshi_email_guide.py --data scripts/hoshi_csv_2005 \
  --scan-day $(date -d tomorrow +%F) --out /tmp/hoshi_guide.md

# 盘前发送（北京 08:30 = UTC 00:30）
30 0 * * 2-6  cd /home/cody/projects/quant-trader && \
  python scripts/hoshi_email_guide.py --data scripts/hoshi_csv_2005 --send
```

> 注：现有服务器 crontab 已有 `12:00 UTC run_hoshi_live_cody.sh`（实盘每日决策）。本邮件指导可挂在同一台 cody_pc，复用其行情与 SMTP 配置。

### 5.6 复用现有邮件设施

`daily_stock_analysis/` 下已有 `notification_sender/email_sender.py` 与 `formatters.py`，可直接复用其 SMTP 封装；本脚本的 `send_mail` 是最小可用版（环境变量驱动），二选一即可。

### 5.7 注意事项

- **`holdings.json` 要随实盘同步**：卖出后从清单删掉，否则邮件会一直提示「应已卖出」。
- **扫描日用「下一个交易日」**：盘前邮件应扫「今天信号、明天执行」，故 `--scan-day` 传下一交易日。
- **全量数据才准**：广度门控需 5310 只全市场；用 `hoshi_csv_long` 子集会低估广度。
- **先本地跑通再上 cron**：`hoshi_email_guide.py` 首次加载全量约 1~5 分钟，cron 超时设足。

---

_整理：小b　2026-09-14_
