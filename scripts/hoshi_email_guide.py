# -*- coding: utf-8 -*-
"""Hoshi-cplus 盘前邮件指导生成器（实战引擎）。

输入：当前持仓清单（holdings.json）+ 行情数据 + 方案(cplus)
输出：一封可直接发送的 Markdown 邮件正文，含——
  ① 每只持仓「下个交易日」的操作（触发价 / 是否卖出 / 后续时间表）
  ② 当日新信号候选的买入指令单
  ③ 风控提示（数据日期、广度、R3 状态）

设计要点
--------
- 持仓投影**复用回测同款 step_exit**，且严格复刻回测主循环：
  买入当天用当日 OHLC 推进一次 hold_day（COUNT_ENTRY_DAY），否则出场整体晚一天。
- 券商条件单只支持「价格触发」、不支持「时间条件」，所以本脚本输出的是
  **带日期时间表的手动操作清单**，由人工在到点交易日去挂/改/撤条件单。

用法
----
  python scripts/hoshi_email_guide.py \
      --data scripts/hoshi_csv_2005 \
      --holdings scripts/holdings.json \
      --preset cplus --scan-day 2026-09-11 \
      --out scripts/hoshi_email_guide.md

  # 直接发信（需配置环境变量 SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/MAIL_TO）
  python scripts/hoshi_email_guide.py --data scripts/hoshi_csv_2005 --send
"""
import argparse
import json
import os
import sys
from datetime import date

# 让脚本可直接以 `python scripts/hoshi_email_guide.py` 运行（项目根在 sys.path）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hoshi_cplus.config import (get_preset, LOT_SIZE, MAX_POSITION_R,
                                PROFIT_ARM_PCT, PROFIT_TRAIL_PCT,
                                PROFIT_ARM_PCT_LATE, PROFIT_TRAIL_PCT_LATE,
                                LOSS_ARM_PCT, LOSS_REBOUND_PCT, LOSS_START_DAY,
                                DEADLINE_DAY, MAX_HOLD)
from hoshi_cplus.data import load_data, precompute
from hoshi_cplus.exits import new_position, step_exit
from hoshi_cplus.orders import scan_signals, build_plan, render_plan


# ------------------------------------------------------------------ 持仓投影
def _next_business_day(d):
    """d 之后的下一个工作日（Mon-Fri），忽略法定假日（接近即可，假日手动微调）。"""
    from datetime import timedelta
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def _nth_day_date(dates, buy_date, n):
    """buy_date 为第 1 天（与回测 hold_day 一致），返回第 n 个交易日日期。

    优先用历史交易日表；超出历史范围（持仓早期、未来日期）则按工作日向前推。
    """
    try:
        i = dates.index(buy_date)
    except ValueError:
        i = None
    if i is not None:
        j = i + (n - 1)
        if 0 <= j < len(dates):
            return dates[j]
    # 兜底：按工作日数第 n 天（buy_date 当天算第 1 天）
    from datetime import timedelta
    d = buy_date
    cnt = 1
    while cnt < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            cnt += 1
    return d


def project_holding(h, prepared, code_bars, p):
    """逐只投影持仓到下个交易日，返回 dict（status: holding / sold_earlier / no_data）。"""
    dates, sig_by_date, n_above, n_valid, idx_of = prepared
    code = h['code']
    bars = code_bars.get(code)
    if not bars:
        return dict(status='no_data', code=code, name=h.get('name', ''),
                    buy_date=h.get('buy_date'))
    cost = float(h['cost'])
    shares = int(h['shares'])
    bd = date.fromisoformat(h['buy_date'])
    # 找买入日那根 bar（取 >= buy_date 的第一根）
    bi = None
    for k, b in enumerate(bars):
        if b.date >= bd:
            bi = k
            break
    if bi is None:
        return dict(status='no_data', code=code, name=h.get('name', ''),
                    buy_date=h['buy_date'])
    b0 = bars[bi]
    pos = new_position(code, cost, shares, cost * shares, mode='S3')
    # 买入当天推进一次（关键，与回测一致）
    step_exit(pos, b0.high, b0.low, b0.open, b0.close, False,
              p.loss_hard_start_day, p.loss_hard_pct)
    sold = None
    for b in bars[bi + 1:]:
        res = step_exit(pos, b.high, b.low, b.open, b.close, True,
                        p.loss_hard_start_day, p.loss_hard_pct)
        if res:
            sold = (b.date, res[0], res[1])
            break
    last = bars[-1]
    if sold:
        return dict(status='sold_earlier', code=code, name=h.get('name', ''),
                    cost=cost, shares=shares, buy_date=h['buy_date'],
                    sold_date=str(sold[0]), sold_price=sold[1], reason=sold[2],
                    last_date=str(last.date), last_close=last.close)

    # 未触发：计算下个交易日与指令
    last_date = last.date
    di = dates.index(last_date)
    next_date = dates[di + 1] if di + 1 < len(dates) else _next_business_day(last_date)
    next_hd = pos['hold_day'] + 1

    hard = cost * (1 + p.loss_hard_pct / 100.0)
    arm = cost * (1 + PROFIT_ARM_PCT / 100.0)
    arm_late = cost * (1 + PROFIT_ARM_PCT_LATE / 100.0)
    loss_arm = cost * (1 + LOSS_ARM_PCT / 100.0)
    trail = pos['peak'] * (1 - pos['trail_pct'] / 100.0) if pos['armed'] else None

    if pos['armed']:
        instr = ("🟢 已武装移动止盈：下个交易日若最低 ≤ %.2f 卖出（止盈）；"
                 "持仓峰值 %.2f" % (trail, pos['peak']))
    elif p.loss_hard_start_day <= next_hd < LOSS_START_DAY:
        instr = ("🔴 硬止损窗口：下个交易日若最低 ≤ %.2f 卖出全部（硬止损 %.1f%%）"
                 % (hard, p.loss_hard_pct))
    elif next_hd >= LOSS_START_DAY:
        if next_hd == DEADLINE_DAY:
            instr = ("⏰ 第 %d 天超时：下个交易日(%s)开盘撤销全部条件单、市价卖出"
                     % (DEADLINE_DAY, next_date))
        else:
            instr = ("🟠 反弹式止损：跌破 %.2f(−%.1f%%)后反弹 +%.1f%% 卖出；"
                     "硬止损兜底 %.2f；临近第 %d 天开盘超时平"
                     % (loss_arm, abs(LOSS_ARM_PCT), LOSS_REBOUND_PCT, hard, DEADLINE_DAY))
    else:
        instr = ("⚪ 前 4 天裸奔（策略设计，无止损保护）：下个交易日仍不可卖"
                 "（hd=%d < %d），仅盯盘" % (next_hd, p.loss_hard_start_day))

    cur_pnl = (last.close / cost - 1) * 100.0
    # 后续时间表
    timeline = []
    for n, label in [(5, '硬止损生效首日'), (14, '收盘查武装止盈'),
                    (15, '反弹式止损窗口'), (DEADLINE_DAY, '超时开盘平'),
                    (MAX_HOLD, '兜底强平')]:
        dn = _nth_day_date(dates, b0.date, n)
        if dn is None:
            continue
        note = ''
        if n == 14:
            note = '若期间最高 ≥ %.2f 则撤止损、改移动止盈(回落%.1f%%)' % (arm, PROFIT_TRAIL_PCT)
        elif n == 15:
            note = '若未武装，止损单继续有效；可改用 −%.1f%%破位后反弹+%.1f%%卖' % (
                abs(LOSS_ARM_PCT), LOSS_REBOUND_PCT)
        timeline.append((n, str(dn), label, note))

    return dict(status='holding', code=code, name=h.get('name', ''),
                cost=cost, shares=shares, buy_date=h['buy_date'],
                hold_day=pos['hold_day'], next_hd=next_hd,
                next_date=str(next_date) if next_date else '（无后续交易日）',
                armed=pos['armed'], peak=pos['peak'],
                last_date=str(last_date), last_close=last.close,
                cur_pnl=cur_pnl, hard=hard, instr=instr, timeline=timeline)


# ------------------------------------------------------------------ 渲染
def render_holding(hp):
    if hp['status'] == 'no_data':
        return ('### %s %s\n\n⚠️ 行情数据缺失（代码未在数据目录中），无法投影。\n'
                % (hp['code'], hp.get('name', '')))
    if hp['status'] == 'sold_earlier':
        return ('### %s %s\n\n⚠️ **历史回看已触发卖出**：%s 以 %.2f 卖出（原因=%s），'
                '但持仓清单仍记录为持有——请核对是否已实际平仓，若已平请从 holdings.json 删除。\n'
                % (hp['code'], hp['name'], hp['sold_date'], hp['sold_price'], hp['reason']))
    L = []
    A = L.append
    A('### %s %s' % (hp['code'], hp['name']))
    A('')
    A('| 项 | 值 |')
    A('|---|---|')
    A('| 成本 | %.3f × %d 股 |' % (hp['cost'], hp['shares']))
    A('| 买入日 | %s |' % hp['buy_date'])
    A('| 最新(%s) | %.2f（浮动 %+.2f%%） |' % (hp['last_date'], hp['last_close'], hp['cur_pnl']))
    A('| 持有天数 | 第 %d 天（下个交易日 = 第 %d 天，%s） |'
      % (hp['hold_day'], hp['next_hd'], hp['next_date']))
    A('| 是否武装 | %s |' % ('是（峰值 %.2f）' % hp['peak'] if hp['armed'] else '否'))
    A('| **下个交易日动作** | **%s** |' % hp['instr'])
    A('')
    A('**后续时间表**（到点手动挂/改/撤条件单）')
    A('')
    A('| 第几天 | 日期 | 节点 | 备注 |')
    A('|---|---|---|---|')
    for n, dn, label, note in hp['timeline']:
        A('| D%d | %s | %s | %s |' % (n, dn, label, note or '—'))
    A('')
    return '\n'.join(L)


def render_email(holdings_out, scan_res, meta):
    out = []
    A = out.append
    A('# Hoshi-cplus 盘前操作指导')
    A('')
    A('> 生成时间：%s　方案：%s　数据截至：%s'
      % (meta['gen_time'], meta['preset_name'], meta['data_date']))
    A('')
    A('## 一、当前持仓 · 下个交易日操作')
    A('')
    if not holdings_out:
        A('（无持仓）')
    else:
        for hp in holdings_out:
            A(render_holding(hp))
    A('')
    A('## 二、新信号候选（买入指令单）')
    A('')
    if scan_res is None:
        A('（本次跳过扫描）')
    elif not scan_res['breadth_pass']:
        bv = ('%.1f%%' % scan_res['breadth']) if scan_res['breadth'] is not None else '样本不足'
        A('市场广度 **%s**，未通过门控（阈值 20%%）——**不开新仓**。' % bv)
    elif not scan_res['candidates']:
        A('当日无合格买入信号（评分 < 9 或已在持仓）。')
    else:
        dates = meta['dates']
        p = meta['preset']
        for c in scan_res['candidates']:
            A(render_plan(build_plan(c, dates, p)))
            A('')
    A('')
    A('## 三、风控提示')
    A('')
    A('- **R3 回撤停手：关闭**（hoshi-cplus 默认）。回撤期恰是超跌反弹信号最肥时段，停手=在最优点离场。')
    A('- **前 4 天（D2–D4）无止损保护**：策略设计的一部分，这 4 天风险敞口最大，需盯盘。')
    A('- **T+1**：买入当天不可卖。')
    A('- **条件单只支持价格触发**：本策略的「第 N 天」时间规则需人工按时间表挂/改/撤。')
    A('- **反弹式止损**（D15 起）多数券商条件单做不出，实盘建议用 −6.0% 硬止损覆盖，两者行为不等价。')
    A('- **数据新鲜度**：盘前请确认行情已增量刷新且无 9998 年脏行；禁用前复权视图（v_stock_qfq 已损坏），用 raw/bfq。')
    A('- **绝对收益不可信**：回测/模拟的绝对值未对齐（差 171~302pp），本指导只管「买卖触发点」，不管「赚多少」。')
    A('')
    A('_本邮件由 `scripts/hoshi_email_guide.py` 生成，投影逻辑与回测一致（含买入当天推进 hold_day）。_')
    return '\n'.join(out)


# ------------------------------------------------------------------ 发送
def send_mail(body, subject):
    import smtplib
    from email.mime.text import MIMEText
    host = os.environ.get('SMTP_HOST')
    if not host:
        print('[warn] 未配置 SMTP_HOST，跳过发送。把正文写入文件即可手动发送。')
        return False
    port = int(os.environ.get('SMTP_PORT', 465))
    user = os.environ.get('SMTP_USER', '')
    pwd = os.environ.get('SMTP_PASS', '')
    to = os.environ.get('MAIL_TO', user)
    msg = MIMEText(body, 'markdown', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = user
    msg['To'] = to
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
    print('[ok] 已发送至 %s' % to)
    return True


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(description='Hoshi-cplus 盘前邮件指导生成器')
    ap.add_argument('--data', default='scripts/hoshi_csv_2005', help='日线 CSV 目录')
    ap.add_argument('--holdings', default='scripts/holdings.json', help='持仓清单 JSON')
    ap.add_argument('--preset', default='cplus', help='方案名')
    ap.add_argument('--scan-day', default=None, help='扫描哪天的信号（默认=数据最后一天）')
    ap.add_argument('--equity', type=float, default=500000.0)
    ap.add_argument('--no-scan', action='store_true', help='跳过新信号扫描')
    ap.add_argument('--out', default=None, help='输出 Markdown 文件路径')
    ap.add_argument('--send', action='store_true', help='通过 SMTP 发送（需环境变量）')
    args = ap.parse_args()

    p = get_preset(args.preset)
    print('加载数据: %s' % args.data)
    code_bars, names = load_data(args.data)
    print('  标的数 %d' % len(code_bars))
    prepared = precompute(code_bars)
    dates = prepared[0]

    # 持仓投影
    with open(args.holdings, encoding='utf-8') as f:
        holdings = json.load(f)
    holdings_out = [project_holding(h, prepared, code_bars, p) for h in holdings]

    # 新信号扫描
    scan_res = None
    if not args.no_scan:
        from datetime import date as _d
        scan_day = (_d.fromisoformat(args.scan_day) if args.scan_day
                    else dates[-1])
        scan_res = scan_signals(prepared, code_bars, names, scan_day, p,
                                equity=args.equity, held=(), max_slots=10)

    meta = dict(gen_time=str(_now()), preset_name=p.name, preset=p,
                data_date=str(dates[-1]), dates=dates)
    body = render_email(holdings_out, scan_res, meta)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(body)
        print('[ok] 已写入 %s' % args.out)
    else:
        print('\n' + body)

    if args.send:
        send_mail(body, 'Hoshi-cplus 盘前指导 %s' % meta['data_date'])
    return 0


def _now():
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M')


if __name__ == '__main__':
    sys.exit(main())
