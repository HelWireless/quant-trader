from fastapi import APIRouter

from core.strategy.base import StrategyRegistry

router = APIRouter()
registry = StrategyRegistry()


@router.get("/")
async def list_strategies():
    """列出所有可用策略"""
    return registry.list_strategies()


@router.post("/backtest")
async def run_backtest(body: dict):
    """运行回测 (预留接口)"""
    strategy_name = body.get("strategy", "")
    code = body.get("code", "")
    # TODO: implement backtest execution
    return {
        "message": f"Backtest for {strategy_name} on {code} (not yet implemented)",
    }
