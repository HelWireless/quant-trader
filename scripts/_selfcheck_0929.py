# -*- coding: utf-8 -*-
"""09-29 自检：两目录一致性 + 分数分布 + 涨停核对 + 腾讯独立源比对。"""
import os, sys, json, urllib.request
from datetime import date
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from hoshi_cplus.config import MIN_BARS, get_preset
from hoshi_cplus.data import load_data
from hoshi_cplus.signals import detect_signal

CONFIRM = date(2026, 9, 29)
p = get_preset('cplus')

print("=" * 74)
for dp in ['scripts/hoshi_csv_2005', 'scripts/hoshi_csv_long']:
    code_bars, names = load_data(dp)
    n_today = sum(1 for b in code_bars.values() if b and b[-1].date == CONFIRM)
    scores = []
    for code, bars in code_bars.items():
        if not bars or bars[-1].date != CONFIRM:
            continue
        k = len(bars) - 1
        seg = bars[max(0, k - (MIN_BARS - 1)):k + 1]
        if len(seg) < MIN_BARS - 1:
            continue
        s = detect_signal([b.open for b in seg], [b.high for b in seg],
                          [b.low for b in seg], [b.close for b in seg])
        if s is not None:
            scores.append((s, code))
    scores.sort(reverse=True)
    print("[%s]" % dp)
    print("  universe=%d  confirm_day_bars=%d  with_signal=%d  max=%s"
          % (len(code_bars), n_today, len(scores), (round(scores[0][0], 1) if scores else None)))
    print("  top5:", [(c, round(s, 1)) for s, c in scores[:5]])
    if '2005' in dp:
        for c in ('000031', '600657'):
            b = code_bars.get(c)
            if b:
                k = len(b) - 1
                prev = b[k - 1].close
                print("  %s %s: %s O=%s H=%s L=%s C=%s chg=%+.2f%% close==high=%s"
                      % (c, names.get(c, ''), b[k].date, b[k].open, b[k].high, b[k].low,
                         b[k].close, (b[k].close / prev - 1) * 100,
                         abs(b[k].close - b[k].high) < 1e-9))

print("=" * 74)
print("腾讯独立源比对（不复权口径）")
db = __import__('duckdb').connect(
    os.path.join(_ROOT, 'data', 'tdx.duckdb'), read_only=True)

def mkt(code):
    return ('sh' if code[:2] in ('60', '68', '69') else 'sz') + code

ok = bad = 0
for code in ['000031', '600657', '301216', '002365', '000001', '601398']:
    sym = mkt(code)
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,10,'
           % sym)
    try:
        raw = urllib.request.urlopen(url, timeout=15).read().decode('utf-8')
        js = json.loads(raw)
        node = js['data'][sym]
        kl = node.get('day') or node.get('qfqday')
        tx = {r[0]: float(r[1]) for r in kl}   # [日期, 开, 收, 高, 低, 量]
        # close = index 2
        tx = {r[0]: float(r[2]) for r in kl}
    except Exception as e:
        print("  %s FETCH_FAIL %s" % (sym, e))
        continue
    rows = db.execute(
        "select date, close from raw_kline_daily where symbol=? and date >= DATE '2026-09-22' order by date",
        [sym]).fetchall()
    line = []
    for d, c in rows:
        ds = str(d)
        t = tx.get(ds)
        if t is None:
            line.append("%s:no-tx" % ds)
            continue
        if abs(t - c) < 1e-6:
            ok += 1
            line.append("%s:OK" % ds[5:])
        else:
            bad += 1
            line.append("%s:DIFF db=%s tx=%s" % (ds[5:], c, t))
    print("  %s: %s" % (sym, ' '.join(line)))
print("  === matched=%d mismatched=%d ===" % (ok, bad))
db.close()
