"""校验 DuckDB 补数据后的完整性与新鲜度（只读）。

用法： python scripts/verify_tdx_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb

DB = str(Path(__file__).parent.parent / "data" / "tdx.duckdb")
CLASS_STOCK = "stock"


def main():
    con = duckdb.connect(DB, read_only=True)
    ok = True

    print("=" * 68)
    print("  数据新鲜度（按库内最新日期分档，仅 A 股）")
    print("=" * 68)
    rows = con.execute(
        """
        SELECT CASE
                 WHEN maxd >= DATE '2026-08-28' THEN '1) 最新 (>=08-28)'
                 WHEN maxd >= DATE '2026-08-01' THEN '2) 滞后 (08-01~08-27)'
                 WHEN maxd >= DATE '2026-07-01' THEN '3) 停牌 (07-01~07-31)'
                 ELSE                                '4) 退市/长停 (<07-01)'
               END AS grp, COUNT(*) AS n
        FROM (SELECT k.symbol, MAX(k.date) AS maxd
              FROM raw_kline_daily k
              JOIN raw_symbol_class c ON c.symbol = k.symbol AND c.class = ?
              GROUP BY k.symbol)
        GROUP BY 1 ORDER BY 1
        """,
        [CLASS_STOCK],
    ).fetchall()
    for g, n in rows:
        print(f"  {g:<26} {n:>6}")

    print()
    print("=" * 68)
    print("  补数据区间完整性")
    print("=" * 68)
    dates = [
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT date FROM raw_kline_daily WHERE date > DATE '2026-06-26' "
            "ORDER BY date"
        ).fetchall()
    ]
    print(f"  新增交易日数 : {len(dates)}")
    print(f"  区间         : {dates[0]} ~ {dates[-1]}")
    # 简单校验：区间内不应出现连续 10 天以上的空白（非节假日长假的异常）
    from datetime import date as D

    ds = [D.fromisoformat(x) for x in dates]
    gaps = [
        (str(ds[i]), str(ds[i + 1]), (ds[i + 1] - ds[i]).days)
        for i in range(len(ds) - 1)
        if (ds[i + 1] - ds[i]).days > 5
    ]
    print(f"  >5 天的间隔  : {gaps if gaps else '无'}")

    print()
    print("=" * 68)
    print("  basic 表覆盖（change_pct 缺失 → hoshi 静默漏信号）")
    print("=" * 68)
    k, b, miss = con.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM raw_kline_daily k
             JOIN raw_symbol_class c ON c.symbol=k.symbol AND c.class=?
             WHERE k.date > DATE '2026-06-26'),
          (SELECT COUNT(*) FROM raw_basic_daily b
             JOIN raw_symbol_class c ON c.symbol=b.symbol AND c.class=?
             WHERE b.date > DATE '2026-06-26'),
          (SELECT COUNT(*) FROM raw_basic_daily b
             JOIN raw_symbol_class c ON c.symbol=b.symbol AND c.class=?
             WHERE b.date > DATE '2026-06-26' AND b.change_pct IS NULL)
        """,
        [CLASS_STOCK] * 3,
    ).fetchone()
    print(f"  raw_kline_daily 新增 : {k:,}")
    print(f"  raw_basic_daily 新增 : {b:,}")
    print(f"  change_pct 缺失      : {miss:,}")
    if miss > 0:
        ok = False
        print("  ✗ 存在缺失！hoshi 会漏信号")
    else:
        print("  ✓ 无缺失")

    print()
    print("=" * 68)
    print("  抽验：sh600367 红星发展 近 8 个交易日")
    print("=" * 68)
    for d, c_, v, chg in con.execute(
        """
        SELECT k.date, k.close, k.volume, b.change_pct
        FROM raw_kline_daily k
        LEFT JOIN raw_basic_daily b ON b.symbol=k.symbol AND b.date=k.date
        WHERE k.symbol='sh600367' ORDER BY k.date DESC LIMIT 8
        """
    ).fetchall():
        chg_s = f"{chg:+.2f}%" if chg is not None else "缺失"
        print(f"  {d}  close={c_:>8.2f}  volume={v:>14,}  chg={chg_s}")

    print()
    print("=" * 68)
    print(f"  结论: {'数据可用 ✓' if ok else '存在问题 ✗'}")
    print("=" * 68)
    con.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
