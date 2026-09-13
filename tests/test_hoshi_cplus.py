# -*- coding: utf-8 -*-
"""hoshi-cplus 单元测试。

快测试（默认跑）：纯函数，不需要行情数据，秒级完成。
慢测试（需要 scripts/hoshi_csv_long 全量数据）：用 `-m slow` 单独跑。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hoshi_cplus.config import get_preset, PRESETS                     # noqa: E402
from hoshi_cplus.signals import (is_hammer, is_doji, calc_score,       # noqa: E402
                                 detect_signal, body_size, lower_shadow)
from hoshi_cplus.exits import new_position, step_exit                  # noqa: E402
from hoshi_cplus.gates import R3Gate, breadth_ok, breadth_value        # noqa: E402
from hoshi_cplus.backtest import buy_fee, sell_fee                     # noqa: E402


# ---------------------------------------------------------------- 命名与预设
def test_preset_aliases_all_point_to_expected_keys():
    """历史称呼必须都映射到正确的方案。"""
    assert get_preset('cplus').key == 'cplus'
    assert get_preset('Bp').key == 'cplus'
    assert get_preset("B'").key == 'cplus'
    assert get_preset('Bprime').key == 'cplus'
    assert get_preset('hoshi-cplus').key == 'cplus'
    assert get_preset('B').key == 'B'
    assert get_preset('original').key == 'original'
    assert get_preset('base').key == 'original'


def test_cplus_parameters():
    """hoshi-cplus 的核心参数（与研究报告一致）。"""
    p = get_preset('cplus')
    assert p.min_score == 9.0
    assert p.loss_hard_start_day == 5
    assert p.loss_hard_pct == -6.0
    assert p.use_r3_gate is False


def test_cplus_differs_from_B_only_in_threshold():
    """hoshi-cplus 与方案 B 唯一的区别是硬止损阈值。"""
    a, b = get_preset('cplus'), get_preset('B')
    assert a.min_score == b.min_score
    assert a.loss_hard_start_day == b.loss_hard_start_day
    assert a.use_r3_gate == b.use_r3_gate
    assert a.loss_hard_pct != b.loss_hard_pct


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        get_preset('no-such-scheme')


# ---------------------------------------------------------------- K 线形态
def test_hammer_requires_long_lower_shadow():
    # 小实体 + 长下影 + 短上影 -> 是锤子
    assert is_hammer(10.0, 10.2, 9.0, 10.1) is True
    # 大阴线 -> 不是锤子
    assert is_hammer(10.5, 10.6, 9.0, 9.1) is False


def test_doji_requires_tiny_body():
    assert is_doji(10.0, 11.0, 9.0, 10.01) is True
    assert is_doji(10.0, 11.0, 9.0, 10.8) is False


def test_hammer_and_doji_reject_zero_range():
    assert is_hammer(10.0, 10.0, 10.0, 10.0) is False
    assert is_doji(10.0, 10.0, 10.0, 10.0) is False


def test_body_and_shadow_helpers():
    assert body_size(10.0, 9.0) == pytest.approx(1.0)
    assert lower_shadow(10.0, 9.0, 8.0) == pytest.approx(1.0)


# ---------------------------------------------------------------- 评分
def test_score_is_capped_at_ten():
    s = calc_score(-40.0, 10.0, 10.5, 9.0, 10.2, 30.0)
    assert s <= 10.0


def test_score_increases_with_confirm_strength():
    weak = calc_score(-12.0, 10.0, 10.2, 9.5, 10.05, 1.0)
    strong = calc_score(-12.0, 10.0, 10.2, 9.5, 10.05, 8.0)
    assert strong > weak


def test_deeper_drop_scores_higher_than_shallow():
    shallow = calc_score(-6.0, 10.0, 10.2, 9.5, 10.05, 3.0)
    deep = calc_score(-15.0, 10.0, 10.2, 9.5, 10.05, 3.0)
    assert deep >= shallow


# ---------------------------------------------------------------- 信号
def test_detect_signal_returns_none_when_too_few_bars():
    n = 40
    o = [10.0] * n
    h = [10.5] * n
    l = [9.5] * n
    c = [10.0] * n
    assert detect_signal(o, h, l, c) is None


def test_detect_signal_requires_uptrend():
    """MA20 <= MA60 时应无信号。"""
    n = 100
    # 单调下跌 -> ma20 < ma60
    c = [100.0 - i * 0.5 for i in range(n)]
    o = [x + 0.1 for x in c]
    h = [x + 0.5 for x in c]
    l = [x - 0.5 for x in c]
    assert detect_signal(o, h, l, c) is None


# ---------------------------------------------------------------- 出场
def _mk_pos(entry=10.0, shares=1000, mode='S4'):
    return new_position('600000', entry, shares, entry * shares, mode=mode)


def test_entry_day_advances_hold_day():
    """买入当天推进 hold_day（COUNT_ENTRY_DAY）—— 漏掉会让所有出场晚一天。"""
    p = _mk_pos()
    assert p['hold_day'] == 0
    step_exit(p, 10.5, 9.9, 10.0, 10.2, False, 5, -6.0)
    assert p['hold_day'] == 1


def test_hard_stop_triggers_from_day5_for_cplus():
    """hoshi-cplus：第 5 天起 armed 前跌破 −6% 立即走。"""
    p = _mk_pos()
    price = None
    for _ in range(5):
        res = step_exit(p, 9.9, 9.0, 9.8, 9.5, True, 5, -6.0)
        if res:
            price, reason = res
            break
    assert price is not None, '第5天起应触发硬止损'
    assert price == pytest.approx(10.0 * (1 - 0.06))
    assert '止损' in reason


def test_hard_stop_not_before_start_day():
    p = _mk_pos()
    for _ in range(4):
        res = step_exit(p, 9.9, 9.0, 9.8, 9.5, True, 5, -6.0)
        assert res is None, '第5天前不应触发硬止损'
    assert p['hold_day'] == 4


def test_eventually_exits_within_max_hold():
    """40 天内必须出场（第 25 天超时或第 40 天兜底强平均可）。"""
    p = _mk_pos()
    res = None
    for _ in range(40):
        res = step_exit(p, 10.1, 9.9, 10.0, 10.0, True, 5, -6.0)
        if res:
            break
    assert res is not None
    assert res[1] in ('超时', '强平')


def test_profit_arm_and_trail():
    entry = 10.0
    p = _mk_pos(entry, mode='S4')
    # 第一天冲高到 +6% -> 武装
    step_exit(p, 10.7, 10.0, 10.0, 10.6, True, 5, -6.0)
    assert p['armed'] is True
    assert p['trail_pct'] == pytest.approx(1.2)


# ---------------------------------------------------------------- 门控
def test_breadth_gate():
    assert breadth_ok(30, 100) is True      # 30% >= 20%
    assert breadth_ok(10, 100) is False     # 10% < 20%
    assert breadth_ok(10, 20) is False      # 样本不足 30 -> 不给信号


def test_breadth_value_none_when_insufficient_sample():
    assert breadth_value(10, 20) is None


def test_r3_disabled_by_default_in_cplus():
    assert get_preset('cplus').use_r3_gate is False


def test_r3_stops_after_big_drawdown():
    g = R3Gate()
    rets = [-30.0, -30.0]        # 复利回撤远超 25%
    assert g(rets, None) is False


def test_r3_passes_on_flat_history():
    g = R3Gate()
    assert g([1.0, 1.0, 1.0], None) is True


# ---------------------------------------------------------------- 费率
def test_buy_fee_has_minimum():
    assert buy_fee(100.0) == 5.0            # 100*0.00025 < 5
    assert buy_fee(100000.0) == pytest.approx(25.0)


def test_sell_fee_includes_stamp_tax_and_sh_transfer():
    sh = sell_fee(100000.0, '600000')
    sz = sell_fee(100000.0, '000001')
    assert sh > sz                          # 沪市多过户费


# ---------------------------------------------------------------- 慢测试（需全量数据）
@pytest.mark.slow
def test_anchor_windows_need_data():
    """锚点对拍：需要 scripts/hoshi_csv_long，耗时数分钟。"""
    from hoshi_cplus.data import load_data, precompute
    from hoshi_cplus.backtest import run_backtest
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, 'scripts', 'hoshi_csv_long')
    if not os.path.isdir(d):
        pytest.skip('缺少数据目录')
    code_bars, _ = load_data(d)
    prepared = precompute(code_bars, verbose=False)

    # 方案 B 的三个已知锚点（原引擎 153.1699 / 146.8178 / 52.7429）
    for (s, e, exp) in (('2011-03-01', '2016-02-29', 153.1699),
                        ('2014-12-01', '2016-11-30', 146.8178),
                        ('2020-10-01', '2022-09-30', 52.7429)):
        r = run_backtest(prepared, preset='B', start=s, end=e, code_bars=code_bars)
        assert r is not None
        assert abs(r['ret'] - exp) < 0.01, '%s~%s 得到 %.4f 期望 %.4f' % (s, e, r['ret'], exp)
