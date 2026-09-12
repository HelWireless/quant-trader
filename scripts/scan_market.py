"""全市场批量扫描脚本

流程:
  1. 从 SQLite 加载全部股票日K线数据
  2. 技术面筛选 (M5): 均线/MACD/RSI/KDJ 等指标
  3. 基本面筛选 (M6): PE/PB/市值/换手率/量比
  4. 综合评分排名
  5. 可选: AI 深度分析 (M7) top candidates
  6. 保存结果 + 输出报告

使用方式:
    # 综合扫描 (技术面 + 基本面)
    py -3 scripts/scan_market.py --tech bull_trend --fund value --top 30

    # 纯技术面扫描
    py -3 scripts/scan_market.py --tech golden_cross --top 50

    # 纯基本面扫描
    py -3 scripts/scan_market.py --fund-only --fund blue_chip --top 30

    # 带 AI 分析的完整扫描
    py -3 scripts/scan_market.py --tech bull_trend --fund value --top 20 --ai --ai-top 5
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.storage import StockDB
from core.screener.screener import StockScreener, PRESET_STRATEGIES
from core.screener.fundamentals import (
    CombinedScreener,
    FundamentalScreener,
    FUND_PRESETS,
    get_batch_fund_flow,
)


def parse_args():
    parser = argparse.ArgumentParser(description="全市场批量扫描")
    parser.add_argument(
        "--tech", type=str, default="bull_trend",
        choices=list(PRESET_STRATEGIES.keys()),
        help="技术面策略 (default: bull_trend)",
    )
    parser.add_argument(
        "--fund", type=str, default="value",
        choices=list(FUND_PRESETS.keys()),
        help="基本面策略 (default: value)",
    )
    parser.add_argument(
        "--fund-only", action="store_true",
        help="仅做基本面筛选 (跳过技术面)",
    )
    parser.add_argument("--top", type=int, default=30, help="返回前 N 只 (default: 30)")
    parser.add_argument("--db", type=str, default="", help="数据库 URL (默认: PostgreSQL quant_minute)")
    parser.add_argument(
        "--recent-days", type=int, default=120,
        help="加载最近 N 天K线 (default: 120, 约半年)",
    )
    parser.add_argument("--ai", action="store_true", help="对 top 候选做 AI 深度分析")
    parser.add_argument("--ai-top", type=int, default=5, help="AI 分析 top N 只")
    parser.add_argument("--save", action="store_true", help="保存结果到数据库")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    return parser.parse_args()


def load_all_kline(db: StockDB, recent_days: int = 120) -> tuple[dict, dict]:
    """从 SQLite 加载全部股票K线数据

    因百度网盘数据截止到 2025-03-31，不按当前日期过滤。
    改为加载全部数据后取最近 N 条记录。

    Returns:
        (df_dict, name_map)
        df_dict: {code: kline_df}
        name_map: {code: stock_name}
    """
    all_codes = db.get_all_codes()
    logger.info(f"数据库共有 {len(all_codes)} 只股票, 逐只加载K线")

    df_dict = {}
    name_map = {}
    loaded = 0
    skipped = 0

    for code in all_codes:
        try:
            df = db.load_daily_kline(code)
            if df.empty or len(df) < 30:
                skipped += 1
                continue
            # 取最近 120 条 (约半年) 用于技术筛选
            if len(df) > 120:
                df = df.tail(120).reset_index(drop=True)
            df_dict[code] = df
            loaded += 1
        except Exception as e:
            skipped += 1
            logger.debug(f"加载 {code} 失败: {e}")

    # 从 stock_info 获取名称
    try:
        with db.SessionFactory() as session:
            from core.data.storage import StockInfo
            for row in session.query(StockInfo.code, StockInfo.name).all():
                name_map[row.code] = row.name
    except Exception:
        pass

    logger.info(f"加载完成: {loaded} 只有效, {skipped} 只跳过")
    return df_dict, name_map


def print_results(results: list, title: str = "筛选结果"):
    """格式化打印结果"""
    print(f"\n{'='*80}")
    print(f"  {title}  ({len(results)} 只)")
    print(f"{'='*80}")
    print(f"{'#':>3}  {'代码':<8} {'名称':<8} {'得分':>6} {'价格':>8} {'涨跌%':>7}  信号")
    print(f"{'-'*80}")

    for i, r in enumerate(results, 1):
        signals_str = ", ".join(r.signals[:4])
        if len(r.signals) > 4:
            signals_str += f" +{len(r.signals)-4}"
        print(
            f"{i:>3}  {r.code:<8} {r.name:<8} {r.score:>6.1f} "
            f"{r.price:>8.2f} {r.pct_change:>+7.2f}  {signals_str}"
        )

    print(f"{'='*80}")


def run_tech_screen(db: StockDB, args) -> list:
    """纯技术面扫描"""
    df_dict, name_map = load_all_kline(db, args.recent_days)

    screener = StockScreener(strategy=args.tech)
    results = screener.screen_batch(df_dict, name_map, top_n=args.top)

    print_results(results, f"技术面筛选 [{args.tech}]")
    return results


def run_fund_only_screen(args) -> list:
    """纯基本面扫描"""
    screener = FundamentalScreener(strategy=args.fund)
    results = screener.screen_all(top_n=args.top)

    print_results(results, f"基本面筛选 [{args.fund}]")
    return results


def run_combined_screen(db: StockDB, args) -> list:
    """技术面 + 基本面综合扫描"""
    df_dict, name_map = load_all_kline(db, args.recent_days)

    cs = CombinedScreener(
        tech_strategy=args.tech,
        fund_strategy=args.fund,
        tech_weight=1.0,
        fund_weight=0.8,
    )
    results = cs.screen(df_dict, name_map, top_n=args.top)

    print_results(results, f"综合筛选 [技术:{args.tech} + 基本面:{args.fund}]")
    return results


def run_ai_analysis(results: list, db: StockDB, args):
    """对 top 候选做 AI 深度分析"""
    try:
        from core.ai.pipeline import analyze_screening_results, print_ai_reports
    except ImportError:
        logger.warning("AI 分析模块不可用, 跳过")
        return

    if not results:
        logger.info("无候选股票, 跳过 AI 分析")
        return

    logger.info(f"开始 AI 深度分析 top {args.ai_top} 只...")

    reports = analyze_screening_results(
        results=results,
        db=db,
        top_n=args.ai_top,
    )

    print_ai_reports(reports)
    return reports


def save_results(results: list, db: StockDB, output_path: str = ""):
    """保存筛选结果"""
    run_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 保存到数据库
    db_results = [
        {"code": r.code, "name": r.name, "score": r.score, "signals": r.signals}
        for r in results
    ]
    db.save_screening_result(run_id, db_results)
    logger.info(f"结果已保存到数据库 run_id={run_id}")

    # 保存 JSON
    if output_path:
        data = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON 已保存: {output_path}")


def main():
    args = parse_args()
    start_time = time.time()

    logger.info(f"全市场扫描开始 | 技术={args.tech} 基本面={args.fund} top={args.top}")

    # 初始化数据库
    db_url = args.db or "postgresql://postgres@localhost:5432/quant_minute"
    db = StockDB(db_url)
    stats = db.get_stats()
    logger.info(f"数据库: {stats}")

    # 执行扫描
    if args.fund_only:
        results = run_fund_only_screen(args)
    else:
        results = run_combined_screen(db, args)

    # AI 分析
    if args.ai and results:
        run_ai_analysis(results, db, args)

    # 保存结果
    if args.save or args.output:
        save_results(results, db, args.output)

    elapsed = time.time() - start_time
    logger.info(f"扫描完成, 耗时 {elapsed:.1f}s")

    # 输出统计
    print(f"\n统计: {len(results)} 只命中, 耗时 {elapsed:.1f}s")
    if results:
        scores = [r.score for r in results]
        print(f"得分范围: {min(scores):.1f} ~ {max(scores):.1f}, 均值: {sum(scores)/len(scores):.1f}")


if __name__ == "__main__":
    main()
