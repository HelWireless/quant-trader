# -*- coding: utf-8 -*-
"""应卖核对：逐日重放 step_exit，找出「按 hoshi-cplus 规则本该卖出」的持仓。

为什么需要它（2026-09-18 踩到的坑）
----------------------------------
`resync.py` 只改持仓/成本，**不跑出场判定**；而 `mail_trader.py run DAY` 在
`last_day 已 == DAY`（当天已经对过账）时会直接返回「无待处理交易日」。
⇒ 镜像模式下，当天"按规则该卖"的票**不会被发现、也不会自动卖**，
   于是台账与实盘悄悄脱节；次日的 `run` 又会按引擎规则自动补卖。

本脚本把每只持仓从建仓日重放到 `--day`，完全复用 `exits.step_exit`，
打印每一处触发点（含触发价与原因），用于人工确认实盘是否已经卖出。

用法
----
  python hoshi_cplus/sim/check_exits.py                 # 默认重放到今天
  python hoshi_cplus/sim/check_exits.py --day 2026-09-21
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.config import get_preset
from hoshi_cplus.exits import new_position, step_exit

DB = os.path.join(_ROOT, 'data', 'tdx.duckdb')
CAL_SYMBOL = 'sz000001'


def _sym(code):
    return ('sh' if code[0] == '6' else 'sz') + code


def _con():
    import duckdb
    return duckdb.connect(DB, read_only=True)


def trading_days(a, b):
    con = _con()
    rows = con.execute(
        "SELECT DISTINCT date FROM raw_kline_daily WHERE symbol=? "
        "AND date >= DATE '%s' AND date <= DATE '%s' ORDER BY date" % (a, b),
        [CAL_SYMBOL]).fetchall()
    con.close()
    return [str(r[0]) for r in rows]


def bar(code, day):
    con = _con()
    r = con.execute(
        "SELECT open,high,low,close FROM raw_kline_daily WHERE symbol='%s' AND date = DATE '%s'"
        % (_sym(code), day)).fetchone()
    con.close()
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--day', default=None, help='重放到该日（默认数据里最新交易日）')
    ap.add_argument('--state', default=os.path.join(_HERE, 'state.json'))
    ap.add_argument('--preset', default='cplus')
    args = ap.parse_args()

    import json
    with open(args.state, encoding='utf-8') as fh:
        st = json.load(fh)

    p = get_preset(args.preset)
    end = args.day
    if end is None:
        con = _con()
        end = str(con.execute("SELECT max(date) FROM raw_kline_daily").fetchone()[0])
        con.close()

    print('应卖核对（重放 step_exit）｜ 预设 %s ｜ 重放终点 %s' % (args.preset, end))
    print('  硬止损：第 %d 天起 %.1f%%' % (p.loss_hard_start_day, p.loss_hard_pct))
    print('=' * 68)

    any_hit = False
    for p0 in st.get('positions', []):
        code, name = p0['code'], p0.get('name', '')
        start = p0.get('buy_date') or st['start_date']
        days = trading_days(start, end)
        pos = new_position(code, p0['entry'], p0['shares'], p0['cost'],
                           mode=p0.get('mode', 'S4'), score=p0.get('score', 0.0))
        hits = []
        for d in days:
            b = bar(code, d)
            if not b:
                continue
            o, h, l, c = b
            allow = (d != start)                    # T+1：建仓当日不可卖
            res = step_exit(pos, h, l, o, c, allow, p.loss_hard_start_day, p.loss_hard_pct)
            if res:
                hits.append((d, res[0], res[1]))
        last = bar(code, days[-1]) if days else None
        close_px = last[3] if last else None
        cur = (close_px - p0['entry']) / p0['entry'] * 100.0 if close_px else 0.0
        line = ('  %s %-6s 成本%.3f 现价%s 浮动%+.2f%% 持%d天 状态:%s'
                % (code, name, p0['entry'], ('%.2f' % close_px) if close_px else '-',
                   cur, pos['hold_day'], '已达止盈阈值' if pos['armed'] else '未达阈值'))
        print(line)
        if pos['armed']:
            trail = pos['peak'] * (1 - pos['trail_pct'] / 100.0)
            print('       └ 跟踪止盈：峰值 %.3f，止盈线 %.3f%s'
                  % (pos['peak'], trail, '（现价已跌破，次日开盘卖出）' if close_px and close_px < trail else '（现价在其上，继续持有）'))
        if hits:
            any_hit = True
            for d, px, why in hits:
                print('       ⚠ %s 触发【%s】@%.3f' % (d, why, px))
        else:
            print('       └ 重放区间内无触发')
    print('=' * 68)
    print('结论：' + ('存在应卖点，请核对实盘是否已卖出 ⚠' if any_hit else '所有持仓均无应卖点 ✓'))


if __name__ == '__main__':
    main()
