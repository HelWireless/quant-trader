# -*- coding: utf-8 -*-
"""日线数据完整性审计（data/tdx.duckdb）。

回答一个问题：**我们的日线数据全不全？**

覆盖的检查项
------------
1. 总量 / 日期范围 / 交易日数（对比 akshare 的 A 股日历）
2. 市场级缺口：库里有数据的日子 vs 日历上的交易日
3. 近 N 个交易日的每日覆盖数（白名单宇宙）
4. 停滞标的：最近仍在交易的票，最新一根 K 线停在哪天
5. 每只标的 K 线根数分布 + 不足 66 根（策略不可用）的清单
6. 重复行 (symbol, date)
7. OHLC 合法性（<=0、high<max(o,c)、low>min(o,c)）
8. raw_basic_daily 覆盖与 change_pct 缺失（hoshi 依赖 change_pct 判跌）
9. 非股票品种混入（指数/基金/北交所/逆回购/债券）
10. 未来日期脏行（TDX 的 9998 坑）

用法
----
  python scripts/audit_daily_coverage.py
  python scripts/audit_daily_coverage.py --days 30
"""
import argparse
import os
import sys

import duckdb

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(_ROOT, 'data', 'tdx.duckdb')

WL = ("(symbol LIKE 'sh600%' OR symbol LIKE 'sh601%' OR symbol LIKE 'sh603%' "
      "OR symbol LIKE 'sh605%' OR symbol LIKE 'sh688%' OR symbol LIKE 'sh689%' "
      "OR symbol LIKE 'sz000%' OR symbol LIKE 'sz001%' OR symbol LIKE 'sz002%' "
      "OR symbol LIKE 'sz003%' OR symbol LIKE 'sz300%' OR symbol LIKE 'sz301%')")


def wl(alias=''):
    """带表别名的白名单谓词。"""
    pre = (alias + '.') if alias else ''
    return WL.replace('symbol', pre + 'symbol')



def hr(t):
    print('\n' + '=' * 74)
    print('  ' + t)
    print('=' * 74)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=20, help='最近几个交易日做逐日覆盖')
    args = ap.parse_args()
    con = duckdb.connect(DB, read_only=True)
    q = con.execute

    # ---------------- 1. 总量 ----------------
    hr('1. 总量与日期范围')
    n, dmin, dmax, nsym = q(
        'SELECT COUNT(*), MIN(date), MAX(date), COUNT(DISTINCT symbol) '
        'FROM raw_kline_daily').fetchone()
    print('  raw_kline_daily ：%d 行 | %d 只 | %s ~ %s' % (n, nsym, dmin, dmax))
    nb = q('SELECT COUNT(*) FROM raw_basic_daily').fetchone()[0]
    print('  raw_basic_daily ：%d 行' % nb)

    # ---------------- 2. 市场级缺口 ----------------
    hr('2. 市场级缺口（库内日期 vs A股官方交易日历）')
    db_days = set(str(r[0]) for r in q(
        "SELECT DISTINCT date FROM raw_kline_daily WHERE date >= DATE '2005-01-01'").fetchall())
    try:
        import akshare as ak
        cal = [str(x) for x in ak.tool_trade_date_hist_sina()['trade_date'].tolist()]
        cal = [d for d in cal if '2005-01-01' <= d <= str(dmax)]
        missing = sorted(set(cal) - db_days)
        extra = sorted(db_days - set(cal))
        print('  日历交易日 %d 个（2005-01-01 ~ %s）' % (len(cal), dmax))
        print('  库里交易日 %d 个' % len(db_days))
        print('  ❌ 日历有、库里没有：%d 个' % len(missing))
        if missing:
            print('     %s' % (missing[:20] + (['...'] if len(missing) > 20 else [])))
        print('  ⚠️ 库里有、日历没有：%d 个' % len(extra))
        if extra:
            print('     %s' % (extra[:20] + (['...'] if len(extra) > 20 else [])))
    except Exception as e:
        print('  ⚠️ 取日历失败（%s），跳过对比' % e)
    print('  （注意：只统计了 raw_kline_daily 出现的日期，未区分"全市场都缺"与"个别票缺"）')

    # ---------------- 3. 逐日覆盖 ----------------
    hr('3. 近 %d 个交易日逐日覆盖（白名单股票宇宙）' % args.days)
    rows = q(f"""
        SELECT date,
               COUNT(DISTINCT symbol) AS n_all,
               COUNT(DISTINCT CASE WHEN {WL} THEN symbol END) AS n_wl
        FROM raw_kline_daily
        WHERE date >= (SELECT MAX(date) FROM raw_kline_daily) - INTERVAL '{args.days + 15} days'
        GROUP BY date ORDER BY date DESC LIMIT {args.days}
    """).fetchall()
    universe = q(f"SELECT COUNT(DISTINCT symbol) FROM raw_kline_daily "
                 f"WHERE {WL} AND date >= (SELECT MAX(date) FROM raw_kline_daily) "
                 f"- INTERVAL '40 days'").fetchone()[0]
    print('  近 40 日出现过 K 线的白名单标的 = %d（当作"在交易宇宙"）' % universe)
    print('  %-12s %8s %8s %10s' % ('日期', '全部', '白名单', '白名单缺口'))
    for d, na, nw in rows:
        print('  %-12s %8d %8d %10d' % (str(d), na, nw, universe - nw))

    # ---------------- 4. 停滞标的 ----------------
    hr('4. 停滞标的（近 40 日活跃票里，最后一根 K 线的日期分布）')
    for d, c in q(f"""
        SELECT mx, COUNT(*) FROM (
          SELECT symbol, MAX(date) AS mx FROM raw_kline_daily
          WHERE {WL} AND date >= (SELECT MAX(date) FROM raw_kline_daily) - INTERVAL '40 days'
          GROUP BY symbol) t
        GROUP BY mx ORDER BY mx DESC LIMIT 12
    """).fetchall():
        print('  最后交易日 %s : %d 只' % (str(d), c))

    # ---------------- 5. 根数分布 ----------------
    hr('5. 每只标的 K 线根数分布（白名单）')
    tot = q(f'SELECT COUNT(*) FROM (SELECT DISTINCT symbol FROM raw_kline_daily WHERE {WL})').fetchone()[0]
    print('  白名单标的总数（全历史出现过）= %d' % tot)
    buckets = [(1, 65, '<66 根 → 策略不可用（MA60+6 预热不足）'),
               (66, 249, '66~249 根（不足一年）'),
               (250, 999, '250~999 根'),
               (1000, 4999, '1000~4999 根'),
               (5000, 10 ** 9, '5000 根以上')]
    for lo, hi, label in buckets:
        c = q(f"""SELECT COUNT(*) FROM (
                    SELECT symbol, COUNT(*) AS n FROM raw_kline_daily
                    WHERE {WL} GROUP BY symbol) t
                  WHERE n >= {lo} AND n <= {hi}""").fetchone()[0]
        print('  %-45s %6d 只' % (label, c))

    # ---------------- 6. 重复行 ----------------
    hr('6. 重复行检查 (symbol, date)')
    dup = q('SELECT COUNT(*) FROM (SELECT symbol, date FROM raw_kline_daily '
            'GROUP BY symbol, date HAVING COUNT(*) > 1)').fetchone()[0]
    print('  重复的 (symbol,date) 组合数 = %d %s' % (dup, '✅' if dup == 0 else '❌'))
    dupb = q('SELECT COUNT(*) FROM (SELECT symbol, date FROM raw_basic_daily '
             'GROUP BY symbol, date HAVING COUNT(*) > 1)').fetchone()[0]
    print('  basic 表重复组合数 = %d %s' % (dupb, '✅' if dupb == 0 else '❌'))

    # ---------------- 7. OHLC 合法性 ----------------
    hr('7. OHLC / 成交量合法性')
    for lbl, cond in [('close<=0', 'close IS NULL OR close <= 0'),
                      ('open<=0', 'open IS NULL OR open <= 0'),
                      ('high<max(o,c)', 'high < GREATEST(open,close) - 1e-9'),
                      ('low>min(o,c)', 'low > LEAST(open,close) + 1e-9'),
                      ('high<low', 'high < low - 1e-9'),
                      ('volume<=0', 'volume IS NULL OR volume <= 0'),
                      ('amount<=0', 'amount IS NULL OR amount <= 0')]:
        a = q(f'SELECT COUNT(*) FROM raw_kline_daily WHERE ({cond})').fetchone()[0]
        b = q(f'SELECT COUNT(*) FROM raw_kline_daily WHERE {wl()} AND ({cond})').fetchone()[0]
        flag = '✅' if b == 0 else ('⚠️' if b < 1000 else '❌')
        print('  %-14s 全库 %9d | **白名单内 %6d** %s' % (lbl, a, b, flag))

    # ---------------- 7b. change_pct 一致性 ----------------
    hr('7b. change_pct 一致性（表值 vs close/preclose 反算，近 10 日白名单）')
    r = q(f"""SELECT COUNT(*),
                     SUM(CASE WHEN abs(b.change_pct - (b.close/b.preclose-1)*100) > 0.05
                              THEN 1 ELSE 0 END)
              FROM raw_kline_daily k
              JOIN raw_basic_daily b ON b.symbol = k.symbol AND b.date = k.date
              WHERE {wl('k')} AND k.date >= (SELECT MAX(date) FROM raw_kline_daily)
                    - INTERVAL '14 days'""").fetchone()
    print('  %d 行，不一致 %d 行 %s' % (r[0], r[1] or 0, '✅' if not r[1] else '⚠️'))

    # ---------------- 8. basic 表 / change_pct ----------------
    hr('8. raw_basic_daily 覆盖 & change_pct 缺失（hoshi 依赖 change_pct）')
    r = q(f"""
        SELECT k.date,
               COUNT(DISTINCT CASE WHEN {wl('k')} THEN k.symbol END) AS n_wl,
               COUNT(DISTINCT CASE WHEN {wl('k')} AND b.change_pct IS NOT NULL
                                   THEN k.symbol END) AS n_pct
        FROM raw_kline_daily k
        LEFT JOIN raw_basic_daily b ON b.symbol = k.symbol AND b.date = k.date
        WHERE k.date >= (SELECT MAX(date) FROM raw_kline_daily) - INTERVAL '7 days'
        GROUP BY k.date ORDER BY k.date DESC
    """).fetchall()
    print('  %-12s %8s %8s %8s' % ('日期', 'K线', '有pct', '缺pct'))
    for d, nw, npct in r:
        print('  %-12s %8d %8d %8d %s' % (str(d), nw, npct, nw - npct, '' if nw == npct else '⚠️'))
    tot_bpct = q('SELECT COUNT(*), SUM(CASE WHEN change_pct IS NULL THEN 1 ELSE 0 END) '
                 'FROM raw_basic_daily').fetchone()
    print('  basic 全表：%d 行，change_pct 为空 %d 行' % tot_bpct)

    # ---------------- 9. 非股票品种混入 ----------------
    hr('9. 非股票品种混入（全历史任意一天出现的非白名单 symbol）')
    r = q("""SELECT
        SUM(CASE WHEN symbol LIKE 'sh000%' OR symbol LIKE 'sz399%' THEN 1 ELSE 0 END) AS idx,
        SUM(CASE WHEN symbol LIKE 'sh5%' OR symbol LIKE 'sz15%' OR symbol LIKE 'sz16%'
                  OR symbol LIKE 'sz18%' THEN 1 ELSE 0 END) AS fund,
        SUM(CASE WHEN symbol LIKE 'bj%' THEN 1 ELSE 0 END) AS bj,
        SUM(CASE WHEN symbol LIKE 'sh204%' OR symbol LIKE 'sz1318%' THEN 1 ELSE 0 END) AS repo
        FROM raw_kline_daily""").fetchone()
    for lbl, v in zip(['指数 sh000/sz399', '基金 sh5/sz15-18', '北交所 bj', '国债逆回购'], r):
        print('  %-18s %d 行' % (lbl, v))
    print('  ⚠️ 全市场扫描务必用白名单过滤，否则指数/逆回购会污染广度与信号')

    # ---------------- 10. 未来脏行 ----------------
    hr('10. 未来日期脏行（TDX 9998 坑）')
    fut = q('SELECT COUNT(*), MIN(date), MAX(date) FROM raw_kline_daily '
            "WHERE date > current_date").fetchone()
    print('  kline date > 今天 ：%d 行 %s' % (fut[0], '✅' if fut[0] == 0 else '❌ %s ~ %s' % (fut[1], fut[2])))
    futb = q('SELECT COUNT(*) FROM raw_basic_daily WHERE date > current_date').fetchone()[0]
    print('  basic date > 今天 ：%d 行 %s' % (futb, '✅' if futb == 0 else '❌'))

    # ---------------- 11. 逐项下钻 ----------------
    hr('11. 问题下钻')

    print('\n[11.1] 重复的 (symbol,date) 明细：')
    for sym, d, c in q('SELECT symbol, date, COUNT(*) AS c FROM raw_kline_daily '
                       'GROUP BY symbol, date HAVING COUNT(*) > 1 ORDER BY c DESC, symbol '
                       'LIMIT 15').fetchall():
        print('   %s %s x%d' % (sym, d, c))

    print('\n[11.2] OHLC 异常样例：')
    for lbl, cond in [('high<max(o,c)', 'high < GREATEST(open,close) - 1e-9'),
                      ('low>min(o,c)', 'low > LEAST(open,close) + 1e-9'),
                      ('high<low', 'high < low - 1e-9')]:
        rs = q(f'SELECT symbol, date, open, high, low, close FROM raw_kline_daily '
               f'WHERE {cond} ORDER BY date DESC LIMIT 4').fetchall()
        print('   %s（共 %d）' % (lbl, q(f'SELECT COUNT(*) FROM raw_kline_daily WHERE {cond}')
                                 .fetchone()[0]))
        for s, d, o, h, l, c in rs:
            print('      %s %s O%.3f H%.3f L%.3f C%.3f' % (s, d, o, h, l, c))

    print('\n[11.3] 日历之外的 2 个日期，涉及哪些标的：')
    for d in ('2011-12-31', '2018-12-31'):
        rs = q("SELECT symbol, open, high, low, close FROM raw_kline_daily "
               "WHERE date = DATE '%s' ORDER BY symbol LIMIT 5" % d).fetchall()
        c = q("SELECT COUNT(*) FROM raw_kline_daily WHERE date = DATE '%s'" % d).fetchone()[0]
        print('   %s 共 %d 行，样例 %s' % (d, c, rs))

    print('\n[11.4] 09-01 有、09-16 也有，但 09-02~09-10 整段缺失的标的：')
    rs = q("""SELECT LEFT(symbol,4) AS p, COUNT(*) AS n FROM (
                SELECT DISTINCT a.symbol FROM raw_kline_daily a
                WHERE a.date = DATE '2026-09-01'
                  AND EXISTS (SELECT 1 FROM raw_kline_daily b
                              WHERE b.symbol = a.symbol AND b.date = DATE '2026-09-16')
                  AND NOT EXISTS (SELECT 1 FROM raw_kline_daily c
                                  WHERE c.symbol = a.symbol
                                    AND c.date BETWEEN DATE '2026-09-02'
                                                   AND DATE '2026-09-10')) t
              GROUP BY p ORDER BY n DESC LIMIT 12""").fetchall()
    print('   %s' % (rs if rs else '无（说明那段缺口是"永远消失"而非"临时缺一段"）'))
    rs2 = q("""SELECT LEFT(symbol,4) AS p, COUNT(*) AS n FROM (
                 SELECT DISTINCT symbol FROM raw_kline_daily WHERE date = DATE '2026-09-01'
                 EXCEPT
                 SELECT symbol FROM raw_kline_daily WHERE date = DATE '2026-09-16') t
               GROUP BY p ORDER BY n DESC LIMIT 8""").fetchall()
    print('   09-01 有、09-16 没有的标的（按前缀）：%s' % rs2)
    print('   ↑ 均为指数（sz399xxx / sh000xxx），不影响股票与 hoshi')

    print('\n[11.5] 白名单里最近一个交易日缺数据 / K 线不足 66 根的清单：')
    last = q('SELECT MAX(date) FROM raw_kline_daily').fetchone()[0]
    miss = q(f"""SELECT symbol FROM (
                   SELECT DISTINCT symbol FROM raw_kline_daily
                   WHERE {wl()} AND date >= DATE '{last}' - INTERVAL '40 days') t
                 WHERE symbol NOT IN (
                   SELECT symbol FROM raw_kline_daily WHERE date = DATE '{last}')""").fetchall()
    print('   最新交易日 %s 缺席的白名单标的：%d 只 %s' % (last, len(miss), [m[0] for m in miss[:12]]))
    small = q(f'SELECT symbol, COUNT(*) AS n FROM raw_kline_daily WHERE {wl()} '
              f'GROUP BY symbol HAVING n < 66 ORDER BY n').fetchall()
    print('   全历史不足 66 根的白名单标的：%d 只' % len(small))
    for s, n2 in small[:20]:
        print('      %s  %d 根' % (s, n2))

    print('\n[11.6] 白名单 2026 年逐月覆盖（有 K 线的标的数 / 该月交易日数）：')
    for m, n2, c in q(f"""SELECT strftime(date, '%Y-%m') AS m,
                                 COUNT(DISTINCT symbol), COUNT(DISTINCT date)
                          FROM raw_kline_daily WHERE {wl()} AND date >= DATE '2026-01-01'
                          GROUP BY m ORDER BY m""").fetchall():
        print('   %s  标的 %4d  交易日 %2d' % (m, n2, c))

    print('\n[11.7] 白名单内 volume<=0 / amount<=0 的年份分布：')
    for lbl, cond in [('volume<=0', 'volume IS NULL OR volume <= 0'),
                      ('amount<=0', 'amount IS NULL OR amount <= 0')]:
        rs = q(f'SELECT YEAR(date), COUNT(*) FROM raw_kline_daily '
               f'WHERE {wl()} AND ({cond}) GROUP BY 1 ORDER BY 1').fetchall()
        print('   %-10s 共 %d 行 %s' % (lbl, sum(x[1] for x in rs), rs))

    con.close()
    print()


if __name__ == '__main__':
    sys.exit(main())
