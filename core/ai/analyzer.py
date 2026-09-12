"""M7: AI 分析引擎 — 基于 LiteLLM 调用 DeepSeek/Qwen

将技术指标 + 基本面数据 + 新闻信息打包成结构化 prompt，
调用 LLM 生成结构化分析报告。
"""

import json
import os
from typing import Optional

import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# 分析 Prompt 模板
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_TEMPLATE = """你是一位专业的 A 股分析师。请基于以下数据对股票 {code} ({name}) 进行全面分析。

## 技术指标数据 (最新交易日)
- 收盘价: {close:.2f}
- MA5={ma5:.2f}, MA10={ma10:.2f}, MA20={ma20:.2f}, MA60={ma60:.2f}
- MACD: DIF={macd_dif:.4f}, DEA={macd_dea:.4f}, 柱状={macd_hist:.4f}
- RSI: RSI6={rsi6:.1f}, RSI12={rsi12:.1f}, RSI24={rsi24:.1f}, KDJ: K={kdj_k:.1f}, D={kdj_d:.1f}, J={kdj_j:.1f}
- 布林带: 上轨={boll_upper:.2f}, 中轨={boll_mid:.2f}, 下轨={boll_lower:.2f}
- ATR(14)={atr14:.4f}
- 量比(5日)={vol_ratio:.2f}

## 技术信号
{signals_text}

## 近期走势摘要
{trend_summary}

{news_section}

请输出 JSON 格式的分析报告，包含以下字段:
{{
  "overall_score": 0-100的综合评分,
  "trend": "上升趋势|下降趋势|震荡整理",
  "short_term_outlook": "短期(1-5日)展望",
  "operation_advice": "买入|增持|持有|减持|卖出|观望",
  "confidence": 0.0-1.0的置信度,
  "risk_level": "低|中|高",
  "entry_price": 建议入场价(数字),
  "stop_loss": 止损价(数字),
  "take_profit": 止盈价(数字),
  "risk_alerts": ["风险提醒列表"],
  "catalysts": ["潜在催化剂"],
  "analysis_summary": "200字以内的分析摘要"
}}

只输出 JSON，不要多余文字。"""


def _build_trend_summary(df: pd.DataFrame, lookback: int = 20) -> str:
    """生成近期走势摘要"""
    recent = df.tail(lookback)
    if recent.empty:
        return "数据不足"

    lines = []
    first_close = recent["close"].iloc[0]
    last_close = recent["close"].iloc[-1]
    pct = (last_close - first_close) / first_close * 100 if first_close else 0

    lines.append(f"- 近{lookback}日涨跌幅: {pct:+.2f}%")
    lines.append(f"- 最高: {recent['high'].max():.2f}, 最低: {recent['low'].min():.2f}")
    lines.append(f"- 日均成交量: {recent['volume'].mean():,.0f}")

    if "amount" in recent.columns:
        lines.append(f"- 日均成交额: {recent['amount'].mean():,.0f}")

    return "\n".join(lines)


def _build_signals_text(signals: dict) -> str:
    """将信号字典格式化为文本"""
    if not signals:
        return "无明显信号"
    return "\n".join(f"- {k}: {v}" for k, v in signals.items())


# ---------------------------------------------------------------------------
# AI 分析器
# ---------------------------------------------------------------------------

class AIAnalyzer:
    """AI 股票分析器

    使用方式:
        analyzer = AIAnalyzer(model="deepseek/deepseek-chat")
        report = analyzer.analyze(code, name, df_with_indicators, signals)
    """

    def __init__(
        self,
        model: str = "deepseek/deepseek-chat",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.api_base = api_base or os.getenv("LLM_API_BASE", "")

    def analyze(
        self,
        code: str,
        name: str,
        df: pd.DataFrame,
        signals: dict = None,
        news: list = None,
    ) -> dict:
        """分析单只股票，返回结构化报告"""
        if df.empty or len(df) < 60:
            return {"error": "数据不足60条，无法分析", "code": code, "name": name}

        latest = df.iloc[-1]

        # 构建新闻段落
        news_section = ""
        if news:
            news_items = [f"- {n.get('title', '')}: {n.get('summary', '')}" for n in news[:5]]
            news_section = "## 近期新闻\n" + "\n".join(news_items)

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            code=code,
            name=name,
            close=latest.get("close", 0),
            ma5=latest.get("ma5", 0),
            ma10=latest.get("ma10", 0),
            ma20=latest.get("ma20", 0),
            ma60=latest.get("ma60", 0),
            macd_dif=latest.get("macd_dif", 0),
            macd_dea=latest.get("macd_dea", 0),
            macd_hist=latest.get("macd_hist", 0),
            rsi6=latest.get("rsi6", 50),
            rsi12=latest.get("rsi12", 50),
            rsi24=latest.get("rsi24", 50),
            kdj_k=latest.get("kdj_k", 50),
            kdj_d=latest.get("kdj_d", 50),
            kdj_j=latest.get("kdj_j", 50),
            boll_upper=latest.get("boll_upper", 0),
            boll_mid=latest.get("boll_mid", 0),
            boll_lower=latest.get("boll_lower", 0),
            atr14=latest.get("atr14", 0),
            vol_ratio=latest.get("vol_ratio5", 1),
            signals_text=_build_signals_text(signals or {}),
            trend_summary=_build_trend_summary(df),
            news_section=news_section,
        )

        try:
            from litellm import completion

            kwargs = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1000,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.api_base:
                kwargs["api_base"] = self.api_base

            response = completion(**kwargs)
            content = response.choices[0].message.content.strip()

            # 尝试解析 JSON
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            report = json.loads(content)
            report["code"] = code
            report["name"] = name
            return report

        except ImportError:
            logger.error("litellm not installed")
            return {"error": "litellm not installed", "code": code, "name": name}
        except json.JSONDecodeError as e:
            logger.error(f"LLM response JSON parse failed: {e}")
            return {"error": "parse_failed", "raw": content, "code": code, "name": name}
        except Exception as e:
            logger.error(f"AI analysis failed for {code}: {e}")
            return {"error": str(e), "code": code, "name": name}

    def batch_analyze(
        self,
        candidates: list,
        df_dict: dict,
        signals_dict: dict = None,
    ) -> list[dict]:
        """批量分析筛选出的股票

        Args:
            candidates: [{"code": "600519", "name": "贵州茅台", "score": 5.0, "signals": [...]}]
            df_dict: {code: df_with_indicators}
            signals_dict: {code: signals}

        Returns:
            分析报告列表
        """
        if signals_dict is None:
            signals_dict = {}

        reports = []
        for c in candidates:
            code = c["code"]
            df = df_dict.get(code)
            if df is None or df.empty:
                continue
            signals = signals_dict.get(code, {})
            report = self.analyze(code, c.get("name", ""), df, signals)
            report["screening_score"] = c.get("score", 0)
            report["screening_signals"] = c.get("signals", [])
            reports.append(report)
            logger.info(f"Analyzed {code} {c.get('name', '')}: score={report.get('overall_score', 'N/A')}")

        return reports
