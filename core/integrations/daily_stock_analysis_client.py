"""HTTP client for the daily_stock_analysis AI-analysis microservice (T007).

daily_stock_analysis runs as a *separate* FastAPI service in its own venv/port
so its heavy, version-pinned dependencies stay isolated from quant-trader.
This client calls ``POST /api/v1/analysis/analyze`` (sync mode) and normalizes
the result into a compact, LLM-friendly summary.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DSA_API_BASE = os.getenv("DSA_API_BASE", "http://127.0.0.1:8010").rstrip("/")
DSA_TIMEOUT = int(os.getenv("DSA_TIMEOUT", "300"))


def _post_analyze(code: str, report_type: str) -> dict:
    url = f"{DSA_API_BASE}/api/v1/analysis/analyze"
    payload = {
        "stock_code": code,
        "async_mode": False,
        "report_type": report_type,
        "analysis_phase": "auto",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=DSA_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize(payload: dict) -> dict:
    """Extract a compact, LLM-friendly summary from a full AnalysisResultResponse."""
    report = payload.get("report") or {}
    meta = report.get("meta") or {}
    summary = report.get("summary") or {}
    strategy = report.get("strategy") or {}
    details = report.get("details") or {}
    raw_result = details.get("raw_result") or {}

    return {
        "stock_code": payload.get("stock_code") or meta.get("stock_code"),
        "stock_name": payload.get("stock_name") or meta.get("stock_name"),
        "current_price": meta.get("current_price"),
        "change_pct": meta.get("change_pct"),
        "operation_advice": summary.get("operation_advice"),
        "trend_prediction": summary.get("trend_prediction"),
        "sentiment_score": summary.get("sentiment_score"),
        "sentiment_label": summary.get("sentiment_label"),
        "analysis_summary": summary.get("analysis_summary"),
        "strategy": {
            "ideal_buy": strategy.get("ideal_buy"),
            "secondary_buy": strategy.get("secondary_buy"),
            "stop_loss": strategy.get("stop_loss"),
            "take_profit": strategy.get("take_profit"),
        },
        "news_summary": raw_result.get("news_summary"),
        "technical_analysis": raw_result.get("technical_analysis"),
        "fundamental_analysis": raw_result.get("fundamental_analysis"),
        "risk_warning": raw_result.get("risk_warning"),
    }


def analyze_stock(code: str, report_type: str = "brief", compact: bool = True) -> dict:
    """Deep AI analysis of a single A-share via the daily_stock_analysis service.

    Returns ``{"ok": True, ...}`` on success or ``{"ok": False, "error": ...}``
    on failure. When ``compact=True`` the result is a normalized summary (for
    chat tools); when ``False`` the full AnalysisResultResponse is returned (for
    the REST proxy).
    """
    try:
        payload = _post_analyze(code, report_type)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:  # network / timeout / JSON
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if not payload.get("report"):
        return {"ok": False, "error": payload.get("detail") or "empty report"}

    if compact:
        out = _normalize(payload)
        out["ok"] = True
        return out
    return {"ok": True, "data": payload}
