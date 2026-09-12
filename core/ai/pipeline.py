"""AI 分析流水线

将筛选结果 → 数据加载 → 技术指标计算 → AI 深度分析 串联起来。
支持从 scan_market.py 或其他脚本直接调用。

使用方式:
    from core.ai.pipeline import analyze_screening_results

    # 对筛选结果做 AI 分析
    reports = analyze_screening_results(
        screening_results,   # list[ScreeningResult]
        db=db,               # StockDB 实例
        top_n=5,
        model="deepseek/deepseek-chat",
    )
"""

import json
from typing import Optional

import pandas as pd
from loguru import logger

from core.ai.analyzer import AIAnalyzer
from core.analysis.indicators import add_all_indicators, generate_signals
from core.data.storage import StockDB
from core.screener.screener import ScreeningResult


def prepare_analysis_data(
    code: str,
    db: StockDB,
    min_records: int = 60,
) -> Optional[pd.DataFrame]:
    """从数据库加载K线并计算技术指标

    加载全部历史数据，取最近 250 条做分析。
    (百度网盘数据截止到 2025-03-31，按当前日期过滤会返回空)

    Returns:
        带技术指标列的 DataFrame, 或 None (数据不足)
    """
    df = db.load_daily_kline(code)
    if df.empty or len(df) < min_records:
        logger.debug(f"{code} K线数据不足 ({len(df)} 条), 跳过")
        return None

    # 取最近 250 条 (约1年) 做指标计算
    if len(df) > 250:
        df = df.tail(250).reset_index(drop=True)

    try:
        df = add_all_indicators(df)
        return df
    except Exception as e:
        logger.warning(f"{code} 指标计算失败: {e}")
        return None


def analyze_screening_results(
    results: list[ScreeningResult],
    db: StockDB,
    top_n: int = 5,
    model: str = "deepseek/deepseek-chat",
    api_key: str = "",
    api_base: str = "",
) -> list[dict]:
    """对筛选结果中的 top N 只做 AI 深度分析

    Args:
        results: 筛选结果列表 (已按 score 降序)
        db: 数据库实例 (用于加载K线)
        top_n: 分析前 N 只
        model: LLM 模型标识
        api_key: API Key (可选, 默认从环境变量读取)
        api_base: API Base URL (可选)
        recent_days: 加载最近 N 天数据

    Returns:
        AI 分析报告列表
    """
    candidates = results[:top_n]
    if not candidates:
        logger.info("无候选股票, 跳过 AI 分析")
        return []

    analyzer = AIAnalyzer(model=model, api_key=api_key, api_base=api_base)
    reports = []

    for i, r in enumerate(candidates, 1):
        logger.info(f"[{i}/{len(candidates)}] AI 分析: {r.code} {r.name} (得分: {r.score})")

        # 加载数据 + 计算指标
        df = prepare_analysis_data(r.code, db)
        if df is None:
            reports.append({
                "code": r.code,
                "name": r.name,
                "error": "数据不足",
                "screening_score": r.score,
            })
            continue

        # 生成技术信号
        try:
            signals = generate_signals(df)
        except Exception:
            signals = {}

        # 补充筛选信号
        if r.signals:
            signals["筛选信号"] = ", ".join(r.signals)

        # 调用 AI 分析
        report = analyzer.analyze(
            code=r.code,
            name=r.name,
            df=df,
            signals=signals,
        )

        report["screening_score"] = r.score
        report["screening_signals"] = r.signals
        reports.append(report)

        if "error" not in report:
            score = report.get("overall_score", "N/A")
            advice = report.get("operation_advice", "N/A")
            summary = report.get("analysis_summary", "")[:80]
            logger.info(
                f"  → AI评分: {score}, 建议: {advice}, {summary}..."
            )
        else:
            logger.warning(f"  → 分析失败: {report.get('error')}")

    return reports


def print_ai_reports(reports: list[dict]):
    """格式化打印 AI 分析报告"""
    for report in reports:
        code = report.get("code", "")
        name = report.get("name", "")

        print(f"\n{'='*60}")
        print(f"  {code} {name}")
        print(f"{'='*60}")

        if "error" in report:
            print(f"  分析失败: {report['error']}")
            continue

        print(f"  AI 综合评分: {report.get('overall_score', 'N/A')}/100")
        print(f"  趋势判断: {report.get('trend', 'N/A')}")
        print(f"  短期展望: {report.get('short_term_outlook', 'N/A')}")
        print(f"  操作建议: {report.get('operation_advice', 'N/A')}")
        print(f"  置信度: {report.get('confidence', 'N/A')}")
        print(f"  风险等级: {report.get('risk_level', 'N/A')}")

        entry = report.get("entry_price", 0)
        stop = report.get("stop_loss", 0)
        target = report.get("take_profit", 0)
        if entry:
            print(f"  入场价: {entry:.2f}  止损: {stop:.2f}  止盈: {target:.2f}")

        summary = report.get("analysis_summary", "")
        if summary:
            print(f"\n  {summary}")

        risks = report.get("risk_alerts", [])
        if risks:
            print(f"\n  风险提醒:")
            for r in risks:
                print(f"    - {r}")

        catalysts = report.get("catalysts", [])
        if catalysts:
            print(f"\n  潜在催化剂:")
            for c in catalysts:
                print(f"    - {c}")

    print(f"\n{'='*60}")


def save_reports(reports: list[dict], output_path: str):
    """保存 AI 分析报告到 JSON"""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)
    logger.info(f"AI 报告已保存: {output_path}")
