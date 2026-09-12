"""REST proxy to the daily_stock_analysis AI-analysis microservice (T007).

Exposes authenticated endpoints so the frontend can request a deep AI stock
analysis without talking to the sub-service directly. The heavy lifting (LLM +
multi-source data + news) happens in the isolated daily_stock_analysis service.
"""
from __future__ import annotations

import asyncio
import logging
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import current_active_user
from core.auth.models import User
from core.integrations.daily_stock_analysis_client import (
    DSA_API_BASE,
    analyze_stock,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyzeIn(BaseModel):
    stock_code: str = Field(..., description="A 股代码，如 600519", examples=["600519"])
    report_type: str = Field(
        "brief", description="报告类型：brief(简洁) / detailed / full / simple"
    )


@router.post("/stock", summary="深度 AI 分析单只股票（接入 daily_stock_analysis）")
async def proxy_analyze(payload: AnalyzeIn, user: User = Depends(current_active_user)):
    """代理到 daily_stock_analysis 子服务，返回完整 AnalysisResultResponse。"""
    res = await asyncio.to_thread(analyze_stock, payload.stock_code, payload.report_type, False)
    if not res.get("ok"):
        raise HTTPException(status_code=502, detail=res.get("error", "analysis failed"))
    return res["data"]


@router.get("/health", summary="检查 daily_stock_analysis 子服务可达性")
async def proxy_health():
    """探测子服务是否在线（供前端/运维使用）。"""
    try:
        with urllib.request.urlopen(f"{DSA_API_BASE}/health", timeout=5) as r:
            return {"ok": True, "dsa_status": r.status, "dsa_base": DSA_API_BASE}
    except Exception as e:  # noqa: BLE001 - 探测失败也要返回结构化信息
        return {"ok": False, "dsa_base": DSA_API_BASE, "error": f"{type(e).__name__}: {e}"}
