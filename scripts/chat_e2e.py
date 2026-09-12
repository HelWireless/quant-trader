"""End-to-end chat verification against :8001 — cookie-auth login, config, conversation, tool-using send."""
import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"
EMAIL = "qa_test@quanttrader.io"
PASSWORD = "QaTest1234!"

results = {"steps": [], "tool_calls": [], "tool_results": [], "final_text": "", "ok": False}


def log(step, ok, detail=""):
    results["steps"].append({"step": step, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {step} {detail}")


s = requests.Session()

# 1) login (CookieTransport -> 204 + Set-Cookie qtauth)
r = s.post(
    f"{BASE}/api/auth/login",
    data={"username": EMAIL, "password": PASSWORD},
    timeout=15,
)
cookie_set = "qtauth" in s.cookies
log("login(cookie)", r.status_code == 204 and cookie_set, f"http={r.status_code} cookie_qtauth={cookie_set}")

# 2) config (public)
r = s.get(f"{BASE}/api/chat/config", timeout=15)
cfg = r.json()
n_tools = len(cfg.get("tools", []))
log("config", r.status_code == 200 and n_tools == 18, f"http={r.status_code} tools={n_tools} provider={cfg.get('provider')} model={cfg.get('model')} has_key={cfg.get('has_key')}")

# 3) create conversation
r = s.post(f"{BASE}/api/chat/conversations", json={"title": "E2E-verify"}, timeout=15)
log("create_conv", r.status_code in (200, 201), f"http={r.status_code}")
conv_id = (r.json().get("id") if r.status_code in (200, 201) else None)
if not conv_id:
    print("CREATE CONV BODY:", r.text[:500])
    print(json.dumps(results))
    sys.exit(1)

# 4) send message that should trigger tool calls
msg = "帮我查一下贵州茅台（600519）现在的实时价格，最近几天的主力资金流向，以及今天北向资金是净流入还是净流出。请用你的工具获取真实数据后汇总。"
t0 = time.time()
with s.post(
    f"{BASE}/api/chat/conversations/{conv_id}/send",
    json={"message": msg},
    stream=True,
    timeout=120,
) as resp:
    log("send_stream", resp.status_code == 200, f"http={resp.status_code}")
    text_parts = []
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if raw.startswith("data:"):
            payload = raw[len("data:"):].strip()
            if not payload:
                continue
            try:
                ev = json.loads(payload)
            except Exception:
                continue
            etype = ev.get("type")
            if etype == "tool_call":
                results["tool_calls"].append({"tool": ev.get("tool"), "args": ev.get("args")})
            elif etype == "tool_result":
                results["tool_results"].append({"tool": ev.get("tool"), "content_len": len(str(ev.get("content", "")))})
            elif etype == "text_delta":
                text_parts.append(ev.get("content", ""))
            elif etype == "error":
                log("agent_error", False, f"msg={ev.get('message')}")
    results["final_text"] = "".join(text_parts)

elapsed = round(time.time() - t0, 1)
tools_used = sorted({t["tool"] for t in results["tool_calls"]})
log("tool_invocation", len(results["tool_calls"]) > 0, f"calls={len(results['tool_calls'])} tools={tools_used} elapsed={elapsed}s")
log("tool_results", len(results["tool_results"]) > 0, f"results={len(results['tool_results'])}")
log("final_text_present", len(results["final_text"]) > 0, f"len={len(results['final_text'])}")

results["ok"] = (
    any(x["step"] == "login(cookie)" and x["ok"] for x in results["steps"])
    and any(x["step"] == "config" and x["ok"] for x in results["steps"])
    and any(x["step"] == "tool_invocation" and x["ok"] for x in results["steps"])
    and any(x["step"] == "final_text_present" and x["ok"] for x in results["steps"])
)
print("\n=== SUMMARY ===")
print("tools_used:", tools_used)
print("final_text[:800]:", results["final_text"][:800])
print("OVERALL_OK:", results["ok"])
