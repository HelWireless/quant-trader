"""集成测试: 验证数据采集 -> 存储 -> 指标计算 -> 筛选 -> AI分析 全链路"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from core.data.fetcher import DataFetcherManager
from core.data.storage import StockDB
from core.analysis.indicators import add_all_indicators, generate_signals
from core.screener.screener import StockScreener


def test_single_stock():
    """测试单只股票数据获取 + 指标计算"""
    print("=" * 60)
    print("TEST 1: 单只股票数据获取 + 指标计算")
    print("=" * 60)

    mgr = DataFetcherManager()
    code = "600519"  # 贵州茅台

    df = mgr.get_daily_kline(code, start_date="20240101")
    if df.empty:
        print(f"[FAIL] 无法获取 {code} 数据")
        return False

    print(f"[OK] 获取 {code} {len(df)} 条日K线数据")
    print(f"     日期范围: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")

    df = add_all_indicators(df)
    signals = generate_signals(df)
    print(f"[OK] 技术指标计算完成，信号: {signals}")
    return True


def test_storage():
    """测试数据存储"""
    print("\n" + "=" * 60)
    print("TEST 2: 数据存储")
    print("=" * 60)

    db = StockDB("sqlite:///./data/test_quant.db")
    mgr = DataFetcherManager()

    code = "000001"  # 平安银行
    df = mgr.get_daily_kline(code, start_date="20250101")
    if df.empty:
        print(f"[FAIL] 无法获取 {code} 数据")
        return False

    count = db.save_daily_kline(code, df)
    print(f"[OK] 保存 {code} {count} 条K线数据到 SQLite")

    loaded = db.load_daily_kline(code)
    print(f"[OK] 从 SQLite 加载 {code} {len(loaded)} 条数据")

    stats = db.get_stats()
    print(f"[OK] 数据库统计: {stats}")
    return True


def test_screener():
    """测试选股筛选器"""
    print("\n" + "=" * 60)
    print("TEST 3: 多条件选股筛选器")
    print("=" * 60)

    mgr = DataFetcherManager()
    screener = StockScreener(strategy="bull_trend")

    # 测试几只代表性股票
    test_codes = {
        "600519": "贵州茅台",
        "000001": "平安银行",
        "000858": "五粮液",
        "601318": "中国平安",
        "300750": "宁德时代",
    }

    print(f"开始筛选 {len(test_codes)} 只股票 (策略: 多头趋势)...")
    df_dict = {}
    for code in test_codes:
        df = mgr.get_daily_kline(code, start_date="20240101")
        if not df.empty:
            df_dict[code] = df

    results = screener.screen_batch(df_dict, name_map=test_codes)

    if results:
        print(f"\n[OK] 筛选出 {len(results)} 只符合条件的股票:")
        for r in results:
            print(f"  {r.code} {r.name} | 评分: {r.score} | 信号: {r.signals}")
    else:
        print("[INFO] 当前无符合条件的股票 (可能市场处于非多头阶段)")

    # 测试所有策略
    print(f"\n可用策略:")
    for s in screener.get_available_strategies():
        print(f"  - {s['name']}: {s['description']}")

    return True


def test_stock_list():
    """测试获取全市场股票列表"""
    print("\n" + "=" * 60)
    print("TEST 4: 全市场股票列表")
    print("=" * 60)

    mgr = DataFetcherManager()
    stock_list = mgr.get_stock_list()

    if stock_list.empty:
        print("[FAIL] 无法获取股票列表")
        return False

    print(f"[OK] 获取到 {len(stock_list)} 只股票")
    print(f"     前5只: {stock_list.head().to_dict('records')}")
    return True


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    print("Quant-Trader 集成测试")
    print("=" * 60)

    tests = [
        ("单只股票", test_single_stock),
        ("数据存储", test_storage),
        ("选股筛选", test_screener),
        ("股票列表", test_stock_list),
    ]

    results = []
    for name, test_func in tests:
        try:
            ok = test_func()
            results.append((name, ok))
        except Exception as e:
            print(f"[ERROR] {name} 测试失败: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
