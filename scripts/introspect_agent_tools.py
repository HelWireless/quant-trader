"""Introspect the built chat agent's function toolset (server-side helper)."""
import sys
sys.path.insert(0, "/home/cody/projects/quant-trader")

from core.chat.agent import build_agent

agent = build_agent()
fts = agent._function_toolset
print("FTS_TYPE:", type(fts).__name__)
print("FTS_DIR:", [a for a in dir(fts) if not a.startswith("__")])

# Try common accessors
for attr in ("tools", "all_tools", "call_tools", "functions", "_tools"):
    if hasattr(fts, attr):
        val = getattr(fts, attr)
        print(f"FTS.{attr}: type={type(val).__name__} val={val!r}"[:300])

# Try calling tool_defs / get_tool / run
for meth in ("tool_defs", "get_tools", "tools_for_model"):
    if hasattr(fts, meth):
        try:
            out = getattr(fts, meth)()
            print(f"FTS.{meth}() -> {out!r}"[:400])
        except Exception as e:
            print(f"FTS.{meth}() err: {e!r}"[:200])
