"""Patch quant-trader to integrate daily_stock_analysis (T007):
  1. add analyze_stock_ai chat tool in core/chat/agent.py
  2. add it to the /config fallback list in app/routers/chat.py
  3. mount the analysis_proxy router in app/main.py
"""
import io

ROOT = "/home/cody/projects/quant-trader"

# ---------------------------------------------------------------------------
# 1) agent.py: insert analyze_stock_ai tool before reset_agent_singleton
# ---------------------------------------------------------------------------
agent_path = f"{ROOT}/core/chat/agent.py"
with io.open(agent_path, "r", encoding="utf-8") as fh:
    agent_src = fh.read()

tool_block = '''    @agent.tool_plain
    async def analyze_stock_ai(code: str, report_type: str = "brief") -> dict:
        """对单只 A 股做深度 AI 分析（技术面+基本面+消息面+作战计划），调用 daily_stock_analysis 子服务。

        Args:
            code: A 股代码，如 600519
            report_type: brief(简洁,默认) / detailed(完整) / full / simple
        """
        import asyncio

        from core.integrations.daily_stock_analysis_client import analyze_stock

        try:
            return await asyncio.to_thread(analyze_stock, code, report_type, True)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

'''

assert "def reset_agent_singleton" in agent_src, "reset anchor missing"
assert "analyze_stock_ai" not in agent_src, "tool already present"
agent_src = agent_src.replace("def reset_agent_singleton", tool_block + "def reset_agent_singleton", 1)
with io.open(agent_path, "w", encoding="utf-8") as fh:
    fh.write(agent_src)
print("PATCH1 agent.py OK")

# ---------------------------------------------------------------------------
# 2) chat.py: add analyze_stock_ai to the /config fallback list
# ---------------------------------------------------------------------------
chat_path = f"{ROOT}/app/routers/chat.py"
with io.open(chat_path, "r", encoding="utf-8") as fh:
    chat_src = fh.read()

assert '"backtest_strategy",' in chat_src, "fallback anchor missing"
assert '"analyze_stock_ai",' not in chat_src, "fallback entry already present"
chat_src = chat_src.replace(
    '        "backtest_strategy",\n',
    '        "backtest_strategy",\n        "analyze_stock_ai",\n',
    1,
)
with io.open(chat_path, "w", encoding="utf-8") as fh:
    fh.write(chat_src)
print("PATCH2 chat.py OK")

# ---------------------------------------------------------------------------
# 3) main.py: import + mount analysis_proxy router
# ---------------------------------------------------------------------------
main_path = f"{ROOT}/app/main.py"
with io.open(main_path, "r", encoding="utf-8") as fh:
    main_src = fh.read()

assert "analysis_proxy" not in main_src, "router already imported"
main_src = main_src.replace(
    "    watchlist,\n)",
    "    watchlist,\n    analysis_proxy,\n)",
    1,
)
main_src = main_src.replace(
    'app.include_router(\n    strategies.router, prefix="/api/strategies", tags=["自定义策略"],\n    dependencies=_login_required,\n)',
    'app.include_router(\n    strategies.router, prefix="/api/strategies", tags=["自定义策略"],\n    dependencies=_login_required,\n)\n'
    'app.include_router(\n'
    '    analysis_proxy.router, prefix="/api/analysis", tags=["AI分析"],\n'
    '    dependencies=_login_required,\n)',
    1,
)
with io.open(main_path, "w", encoding="utf-8") as fh:
    fh.write(main_src)
print("PATCH3 main.py OK")
print("ALL_PATCHES_DONE")
