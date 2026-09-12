"""Chat E2E that triggers the analyze_stock_ai tool (deep AI analysis via dsa)."""
import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", data={"username": "qa_test@quanttrader.io", "password": "QaTest1234!"}, timeout=15)
print(f"login={r.status_code} cookie={'qtauth' in s.cookies}", flush=True)
if r.status_code != 204:
    print("LOGIN FAIL", r.text[:200]); sys.exit(1)

r = s.post(f"{BASE}/api/chat/conversations", json={"title": "E2E-analyze"}, timeout=15)
conv_id = r.json().get("id")
print("conv_id=", conv_id, flush=True)

msg = "帮我深度分析一下贵州茅台（600519）这只股票，请使用你的 AI 深度分析工具，给出操作建议、趋势判断和具体买卖点。"
t0 = time.time()
tool_calls, tool_results, text = [], [], []
with s.post(f"{BASE}/api/chat/conversations/{conv_id}/send", json={"message": msg}, stream=True, timeout=320) as resp:
    print("send_stream=", resp.status_code, flush=True)
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if not payload:
            continue
        try:
            ev = json.loads(payload)
        except Exception:
            continue
        t = ev.get("type")
        if t == "tool_call":
            tool_calls.append(ev.get("tool"))
        elif t == "tool_result":
            tool_results.append(ev.get("tool"))
        elif t == "text_delta":
            text.append(ev.get("content", ""))
        elif t == "error":
            print("AGENT_ERROR", ev.get("message"), flush=True)

elapsed = round(time.time() - t0, 1)
print("elapsed=", elapsed, "tool_calls=", tool_calls, "results=", tool_results, flush=True)
print("final_text_len=", len("".join(text)), flush=True)
print("final_text[:500]=", "".join(text)[:500], flush=True)
ok = "analyze_stock_ai" in tool_calls
print("ANALYZE_TOOL_INVOKED_OK" if ok else "ANALYZE_TOOL_MISSING", flush=True)
