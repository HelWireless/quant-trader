# -*- coding: utf-8 -*-
"""下单指令单生成（hoshi-cplus）。

把策略信号翻译成**实盘可执行**的委托清单。

核心难点：券商条件单只支持「价格触发」，**不支持「时间条件」**。
而 hoshi-cplus 的出场规则里有「第 5 天起武装硬止损」「第 15 天切换止损逻辑」
「第 25 天超时平仓」这类时间条件 —— 所以只能生成一份**带日期时间表的手动操作清单**：
到指定交易日，人工去挂 / 改 / 撤条件单。
"""
from .config import (LOT_SIZE, MAX_POSITION_R, PROFIT_ARM_PCT, PROFIT_TRAIL_PCT,
                     PROFIT_ARM_PCT_LATE, PROFIT_TRAIL_PCT_LATE, LOSS_ARM_PCT,
                     LOSS_REBOUND_PCT, LOSS_START_DAY, DEADLINE_DAY, MAX_HOLD,
                     get_preset)


def nth_trade_day(dates, d, n):
    """d 之后第 n 个交易日（n=1 即下一个交易日）。越界返回 None。"""
    try:
        i = dates.index(d)
    except ValueError:
        return None
    j = i + n
    return dates[j] if 0 <= j < len(dates) else None


def scan_signals(prepared, code_bars, names, day, preset,
                 equity=500000.0, held=(), max_slots=10):
    """扫描某交易日的买入候选（只筛信号 + 算下单量，不模拟成交）。

    返回 dict(breadth, breadth_pass, candidates)
    """
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
                   if x[0] >= preset.min_score and x[1] not in held],
                  key=lambda x: -x[0])
    cands = []
    for score, code in sigs:
        if len(cands) >= free:
            break
        k = idx_of[code].get(day)
        if k is None:
            continue
        ref = code_bars[code][k].close          # 信号日收盘，仅作参考
        budget = equity * MAX_POSITION_R
        shares = int(budget // ref // LOT_SIZE) * LOT_SIZE
        if shares <= 0:
            continue
        cands.append(dict(code=code, name=names.get(code, ''), score=score,
                          signal_day=day, ref_close=ref, shares=shares,
                          est_amount=shares * ref))
    return dict(breadth=b_val, breadth_pass=True, candidates=cands)


def build_plan(cand, dates, preset, entry_price=None):
    """生成单只标的的完整指令单。preset 可传 Preset 对象或名称字符串。"""
    p = preset if hasattr(preset, 'loss_hard_pct') else get_preset(preset)
    entry = entry_price if entry_price else cand['ref_close']
    sig = cand['signal_day']

    def day_n(n):
        return nth_trade_day(dates, sig, n)

    def px(pct):
        return round(entry * (1 + pct / 100.0), 2)

    return dict(
        code=cand['code'], name=cand['name'], score=cand['score'],
        preset=p.key, preset_name=p.name,
        signal_day=sig, exec_day=day_n(1),
        ref_close=cand['ref_close'], entry=entry,
        shares=cand['shares'], est_amount=cand['est_amount'],
        hard_stop=round(entry * (1 + p.loss_hard_pct / 100.0), 2),
        loss_hard_pct=p.loss_hard_pct,
        days=dict(d1=day_n(1), d5=day_n(5) if p.loss_hard_start_day <= 5 else None,
                  d14=day_n(14), d15=day_n(15), d25=day_n(DEADLINE_DAY),
                  d40=day_n(MAX_HOLD)),
        levels=dict(profit_arm=px(PROFIT_ARM_PCT), profit_trail=PROFIT_TRAIL_PCT,
                    profit_arm_late=px(PROFIT_ARM_PCT_LATE),
                    profit_trail_late=PROFIT_TRAIL_PCT_LATE,
                    loss_arm=px(LOSS_ARM_PCT), loss_rebound=LOSS_REBOUND_PCT),
    )


def _d(v, na='（待届时确认）'):
    return na if v is None else str(v)


def render_plan(pl):
    """渲染成 Markdown 指令单。"""
    L = pl['levels']
    D = pl['days']
    out = []
    A = out.append
    A('### %s %s' % (pl['code'], pl['name'] or ''))
    A('')
    A('| 项 | 值 |')
    A('|---|---|')
    A('| 方案 | %s |' % pl['preset_name'])
    A('| 信号评分 | **%.1f / 10** |' % pl['score'])
    A('| 信号日 | %s（**收盘后**确认） |' % pl['signal_day'])
    A('| **执行日** | **%s 开盘** |' % _d(pl['exec_day']))
    A('| 买入方式 | 开盘集合竞价挂单价 / 开盘后市价单（见下方说明） |')
    A('| 参考价 | %.2f（信号日收盘） |' % pl['ref_close'])
    A('| 建议股数 | **%d 股**（%d 手） |' % (pl['shares'], pl['shares'] // LOT_SIZE))
    A('| 预计金额 | 约 %.0f 元 |' % pl['est_amount'])
    A('')
    A('**持有期条件单时间表**（到日子手动操作 —— 券商条件单做不了「第 N 天起生效」）')
    A('')
    A('| 持有第几天 | 日期 | 动作 |')
    A('|---|---|---|')
    A('| D1 | %s | 开盘买入。**当日不可卖**（T+1） |' % _d(D['d1']))
    A('| D2–D4 | — | 无止损保护（策略设计：前 4 天裸奔，这是 −6.0% 口径的一部分） |')
    if D['d5']:
        A('| **D5** | **%s** | **开盘前挂条件止损单：现价 ≤ %.2f 卖出全部**（−%.1f%%） |'
          % (_d(D['d5']), pl['hard_stop'], abs(pl['loss_hard_pct'])))
    A('| D14 | %s | 收盘后检查：期间最高价是否 ≥ **%.2f**（+%.1f%%）<br>'
      '是 → 撤掉止损单，改挂**移动止盈**：自最高价回落 %.1f%% 卖出 |'
      % (_d(D['d14']), L['profit_arm'], PROFIT_ARM_PCT, L['profit_trail']))
    A('| D15 | %s | 若仍未触发止盈：止损单继续有效（实盘简化版见下） |' % _d(D['d15']))
    A('| **D25** | **%s** | **开盘撤销全部条件单，市价卖出**（超时平仓） |' % _d(D['d25']))
    A('| D40 | %s | 兜底强平（正常走不到） |' % _d(D['d40']))
    A('')
    A('**回测口径的完整出场规则（供对照）**')
    A('')
    A('- 止盈武装：D14 盘中最高 ≥ %.2f（+5.2%%）→ 移动止盈回落 %.1f%%；'
      'D15 放宽为 ≥ %.2f（+3.2%%）→ 回落 %.1f%%'
      % (L['profit_arm'], L['profit_trail'], L['profit_arm_late'], L['profit_trail_late']))
    A('- 硬止损：第 %d 天起，价格 ≤ %.2f 无条件卖出' % (D['d5'] and 5 or 0, pl['hard_stop']))
    A('- 反弹卖出：第 15 天起，跌破 %.2f（−5.2%%）后反弹 %.1f%% 卖出'
      % (L['loss_arm'], L['loss_rebound']))
    A('- 超时：第 25 天开盘卖出；兜底：第 40 天收盘强平')
    A('')
    return '\n'.join(out)
