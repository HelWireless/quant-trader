import duckdb
p = r"C:\Users\cody\PycharmProjects\quant-trader\data\tdx.duckdb"
con = duckdb.connect(p)
k = con.execute("select count(*) from raw_kline_daily where date > DATE '2026-09-29'").fetchone()[0]
b = con.execute("select count(*) from raw_basic_daily where date > DATE '2026-09-29'").fetchone()[0]
con.execute("delete from raw_kline_daily where date > DATE '2026-09-29'")
con.execute("delete from raw_basic_daily where date > DATE '2026-09-29'")
con.close()
con = duckdb.connect(p, read_only=True)
t = con.execute("select count(*) from raw_kline_daily where date = DATE '2026-09-29'").fetchone()[0]
mx = con.execute("select max(date) from raw_kline_daily").fetchone()[0]
print(f"deleted_kline={k} deleted_basic={b} rows_0929={t} kline_max={mx}")
con.close()
