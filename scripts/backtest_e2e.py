"""Backtest E2E: run a backtest via API and verify enhanced metrics are returned."""
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

t0 = time.time()
r = s.post(f"{BASE}/api/backtest/run", json={"code": "600519", "strategy": "ma_cross", "days": 365, "initial_cash": 100000}, timeout=180)
print(f"run http={r.status_code} elapsed={round(time.time()-t0,1)}s", flush=True)
if r.status_code != 200:
    print("RUN FAIL", r.text[:400]); sys.exit(1)

d = r.json()
m = d.get("metrics", {})
curve = d.get("equity_curve", [])
print("METRICS KEYS:", sorted(m.keys()), flush=True)
for k in ["total_return_pct", "annual_return_pct", "sharpe", "sortino", "max_drawdown_pct", "win_rate_pct", "trade_count", "final_equity"]:
    print(f"  {k} = {m.get(k)}", flush=True)
print("equity_curve points:", len(curve), flush=True)

required = ["sharpe", "max_drawdown_pct", "total_return_pct", "annual_return_pct", "win_rate_pct"]
missing = [k for k in required if k not in m]
ok = (not missing) and len(curve) > 0 and m.get("trade_count", 0) >= 0
print(("BACKTEST_E2E_OK" if ok else f"BACKTEST_E2E_FAIL missing={missing}"), flush=True)
