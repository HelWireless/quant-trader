"""Fix: move the analyze_stock_ai tool INSIDE build_agent (before _agent_singleton = agent)."""
import io

ROOT = "/home/cody/projects/quant-trader"
agent_path = f"{ROOT}/core/chat/agent.py"
with io.open(agent_path, "r", encoding="utf-8") as fh:
    src = fh.read()

# 1) Remove the misplaced tool block (currently after `return agent`, before def reset_agent_singleton)
marker = '    @agent.tool_plain\n    async def analyze_stock_ai'
assert marker in src, "tool marker not found"
idx = src.index(marker)
# find the end: the next module-level def after the marker
rest = src[idx:]
end = rest.index("def reset_agent_singleton")
# include the trailing blank lines up to that def
block = rest[:end]
src = src[:idx] + rest[end:]  # drop the misplaced block

# 2) Re-insert correctly before `_agent_singleton = agent`
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

anchor = "    _agent_singleton = agent"
assert anchor in src, "anchor missing"
assert "analyze_stock_ai" not in src, "tool still present after removal"
src = src.replace(anchor, tool_block + anchor, 1)

with io.open(agent_path, "w", encoding="utf-8") as fh:
    fh.write(src)
print("FIX_APPLIED")
