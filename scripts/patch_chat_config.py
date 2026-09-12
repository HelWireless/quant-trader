"""Patch app/routers/chat.py /config to derive tool list dynamically."""
import io
import sys

PATH = "/home/cody/projects/quant-trader/app/routers/chat.py"

old_block = '''        "tools": [
            "query_sql_select", "get_quote", "batch_quote",
            "get_kline", "get_signals", "list_watchlist",
            "backtest_ma_cross", "backtest_macd",
        ],'''

helper = '''def _chat_tool_names() -> list[str]:
    """返回当前 agent 实际注册的工具名（动态派生，避免与 agent.py 脱节）。"""
    fallback = [
        "query_sql_select", "get_quote", "batch_quote", "get_kline",
        "get_quote_realtime", "get_fund_flow", "get_dragon_tiger",
        "get_margin_summary", "get_hsgt_north", "get_hot_themes_today",
        "get_signals", "list_watchlist", "backtest_ma_cross", "backtest_macd",
        "search_knowledge_tool", "recall_memory", "optimize_strategy_grid",
        "backtest_strategy",
    ]
    try:
        from core.chat.agent import build_agent

        agent = build_agent()
        names = list(agent._function_toolset.tools.keys())
        if names:
            return names
    except Exception as exc:  # pragma: no cover - 配置缺失时退回静态列表
        logger.warning("无法动态获取 agent 工具列表，使用静态回退: %s", exc)
    return fallback


'''

new_block = '        "tools": _chat_tool_names(),'

with io.open(PATH, "r", encoding="utf-8") as fh:
    src = fh.read()

assert old_block in src, "OLD BLOCK NOT FOUND"
assert "_chat_tool_names" not in src, "helper already present"

# Insert helper right before the /config router decorator.
anchor = '@router.get("/config"'
assert anchor in src, "anchor not found"
src = src.replace(anchor, helper + anchor, 1)

src = src.replace(old_block, new_block, 1)

with io.open(PATH, "w", encoding="utf-8") as fh:
    fh.write(src)

print("PATCH_OK tool_names_derivation_installed")
