# -*- coding: utf-8 -*-
"""hoshi-cplus 零依赖自测（不需要 pytest）。

用法：
    python hoshi_cplus/selftest.py            # 只跑快测试
    python hoshi_cplus/selftest.py --slow     # 含锚点对拍（需 scripts/hoshi_csv_long，数分钟）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hoshi_cplus.config import get_preset                              # noqa: E402
from hoshi_cplus.signals import (is_hammer, is_doji, calc_score,       # noqa: E402
                                 detect_signal, body_size, lower_shadow)
from hoshi_cplus.exits import new_position, step_exit                  # noqa: E402
from hoshi_cplus.gates import R3Gate, breadth_ok, breadth_value        # noqa: E402
from hoshi_cplus.backtest import buy_fee, sell_fee                     # noqa: E402

_PASS = []
_FAIL = []


def check(name, fn):
    try:
        fn()
        _PASS.append(name)
        print('  PASS  %s' % name)
    except AssertionError as e:
        _FAIL.append((name, str(e) or '断言失败'))
        print('  FAIL  %s  -> %s' % (name, e))
    except Exception as e:
        _FAIL.append((name, '%s: %s' % (type(e).__name__, e)))
        print('  ERROR %s  -> %s: %s' % (name, type(e).__name__, e))


def approx(a, b, tol=1e-6):
    assert abs(a - b) <= tol, '%.6f != %.6f' % (a, b)


# =================================================================== 命名
def t_aliases():
    assert get_preset('cplus').key == 'cplus'
    assert get_preset('Bp').key == 'cplus'
    assert get_preset("B'").key == 'cplus'
    assert get_preset('Bprime').key == 'cplus'
    assert get_preset('hoshi-cplus').key == 'cplus'
    assert get_preset('B').key == 'B'
    assert get_preset('base').key == 'original'


def t_cplus_params():
    p = get_preset('cplus')
    assert p.min_score == 9.0
    assert p.loss_hard_start_day == 5
    assert p.loss_hard_pct == -6.0
    assert p.use_r3_gate is False


def t_cplus_vs_B_only_threshold():
    a, b = get_preset('cplus'), get_preset('B')
    assert a.min_score == b.min_score
    assert a.loss_hard_start_day == b.loss_hard_start_day
    assert a.use_r3_gate == b.use_r3_gate
    assert a.loss_hard_pct != b.loss_hard_pct


def t_unknown_preset():
    try:
        get_preset('nope')
    except KeyError:
        return
    raise AssertionError('未知方案应抛 KeyError')


# =================================================================== 形态
def t_hammer_true():
    assert is_hammer(10.0, 10.2, 9.0, 10.1) is True      # 小实体+长下影+短上影


def t_hammer_false_big_body():
    assert is_hammer(10.5, 10.6, 9.0, 9.1) is False      # 大阴线


def t_doji():
    assert is_doji(10.0, 11.0, 9.0, 10.01) is True
    assert is_doji(10.0, 11.0, 9.0, 10.8) is False


def t_zero_range_rejected():
    assert is_hammer(10.0, 10.0, 10.0, 10.0) is False
    assert is_doji(10.0, 10.0, 10.0, 10.0) is False


def t_helpers():
    approx(body_size(10.0, 9.0), 1.0)
    approx(lower_shadow(10.0, 9.0, 8.0), 1.0)


# =================================================================== 评分
def t_score_cap():
    assert calc_score(-40.0, 10.0, 10.5, 9.0, 10.2, 30.0) <= 10.0


def t_score_confirm_strength():
    w = calc_score(-12.0, 10.0, 10.2, 9.5, 10.05, 1.0)
    s = calc_score(-12.0, 10.0, 10.2, 9.5, 10.05, 8.0)
    assert s > w


def t_score_depth():
    shallow = calc_score(-6.0, 10.0, 10.2, 9.5, 10.05, 3.0)
    deep = calc_score(-15.0, 10.0, 10.2, 9.5, 10.05, 3.0)
    assert deep >= shallow


# =================================================================== 信号
def t_signal_too_few_bars():
    n = 40
    assert detect_signal([10.0] * n, [10.5] * n, [9.5] * n, [10.0] * n) is None


def t_signal_requires_uptrend():
    n = 100
    c = [100.0 - i * 0.5 for i in range(n)]
    assert detect_signal([x + 0.1 for x in c], [x + 0.5 for x in c],
                         [x - 0.5 for x in c], c) is None


# =================================================================== 出场
def _pos(entry=10.0, shares=1000, mode='S4'):
    return new_position('600000', entry, shares, entry * shares, mode=mode)


def t_entry_day_advances():
    p = _pos()
    assert p['hold_day'] == 0
    step_exit(p, 10.5, 9.9, 10.0, 10.2, False, 5, -6.0)
    assert p['hold_day'] == 1, '买入当天必须推进 hold_day'


def t_hard_stop_from_day5():
    p = _pos()
    res = None
    for _ in range(5):
        res = step_exit(p, 9.9, 9.0, 9.8, 9.5, True, 5, -6.0)
        if res:
            break
    assert res is not None, '第5天起应触发硬止损'
    approx(res[0], 10.0 * (1 - 0.06))
    assert '止损' in res[1]


def t_no_hard_stop_before_day5():
    p = _pos()
    for _ in range(4):
        assert step_exit(p, 9.9, 9.0, 9.8, 9.5, True, 5, -6.0) is None
    assert p['hold_day'] == 4


def t_eventually_exits():
    """40 天内必须出场（超时或强平均可）。"""
    p = _pos()
    res = None
    for _ in range(40):
        res = step_exit(p, 10.1, 9.9, 10.0, 10.0, True, 5, -6.0)
        if res:
            break
    assert res is not None


def t_profit_arm():
    p = _pos(mode='S4')
    step_exit(p, 10.7, 10.0, 10.0, 10.6, True, 5, -6.0)
    assert p['armed'] is True
    approx(p['trail_pct'], 1.2)


# =================================================================== 门控
def t_breadth():
    assert breadth_ok(30, 100) is True
    assert breadth_ok(10, 100) is False
    assert breadth_ok(10, 20) is False      # 样本不足
    assert breadth_value(10, 20) is None
    approx(breadth_value(30, 100), 30.0)


def t_r3():
    assert get_preset('cplus').use_r3_gate is False
    assert R3Gate()([1.0, 1.0, 1.0], None) is True
    assert R3Gate()([-30.0, -30.0], None) is False


# =================================================================== 费率
def t_fees():
    approx(buy_fee(100.0), 5.0)             # 最低佣金
    approx(buy_fee(100000.0), 25.0)
    assert sell_fee(100000.0, '600000') > sell_fee(100000.0, '000001')


# =================================================================== 慢测试
def t_anchor_slow():
    from hoshi_cplus.data import load_data, precompute
    from hoshi_cplus.backtest import run_backtest
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, 'scripts', 'hoshi_csv_long')
    if not os.path.isdir(d):
        raise AssertionError('缺少数据目录 %s' % d)
    code_bars, _ = load_data(d)
    prepared = precompute(code_bars, verbose=False)
    for (s, e, exp) in (('2011-03-01', '2016-02-29', 153.1699),
                        ('2014-12-01', '2016-11-30', 146.8178),
                        ('2020-10-01', '2022-09-30', 52.7429)):
        r = run_backtest(prepared, preset='B', start=s, end=e, code_bars=code_bars)
        assert r is not None
        assert abs(r['ret'] - exp) < 0.02, '%s~%s 得到 %.4f 期望 %.4f' % (s, e, r['ret'], exp)


FAST = [
    ('命名别名映射', t_aliases),
    ('cplus 参数正确', t_cplus_params),
    ('cplus 与 B 仅阈值不同', t_cplus_vs_B_only_threshold),
    ('未知方案抛 KeyError', t_unknown_preset),
    ('锤子线-是', t_hammer_true),
    ('锤子线-否(大实体)', t_hammer_false_big_body),
    ('十字星判定', t_doji),
    ('零振幅被拒', t_zero_range_rejected),
    ('形态辅助函数', t_helpers),
    ('评分封顶 10', t_score_cap),
    ('评分随确认强度上升', t_score_confirm_strength),
    ('评分随跌幅加深', t_score_depth),
    ('K线不足无信号', t_signal_too_few_bars),
    ('空头排列无信号', t_signal_requires_uptrend),
    ('买入当天推进 hold_day', t_entry_day_advances),
    ('第5天起硬止损生效', t_hard_stop_from_day5),
    ('第5天前不硬止损', t_no_hard_stop_before_day5),
    ('40天内必定出场', t_eventually_exits),
    ('止盈武装', t_profit_arm),
    ('广度门控', t_breadth),
    ('R3 门控', t_r3),
    ('费率计算', t_fees),
]


def main():
    slow = '--slow' in sys.argv
    print('=' * 60)
    print('hoshi-cplus 自测' + ('（含慢测试）' if slow else '（快测试）'))
    print('=' * 60)
    for name, fn in FAST:
        check(name, fn)
    if slow:
        print()
        print('--- 慢测试：锚点对拍（原引擎 153.1699 / 146.8178 / 52.7429）---')
        check('锚点对拍', t_anchor_slow)

    print()
    print('=' * 60)
    print('通过 %d，失败 %d' % (len(_PASS), len(_FAIL)))
    if _FAIL:
        for n, m in _FAIL:
            print('  FAIL %s -> %s' % (n, m))
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
