"""Authenticated REST test of /api/analysis/stock proxy -> daily_stock_analysis."""
import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", data={"username": "qa_test@quanttrader.io", "password": "QaTest1234!"}, timeout=15)
print(f"login={r.status_code} cookie={'qtauth' in s.cookies}", flush=True)
if r.status_code != 204:
    print("LOGIN FAIL", r.text[:300])
    sys.exit(1)

t0 = time.time()
try:
    r = s.post(f"{BASE}/api/analysis/stock", json={"stock_code": "600519", "report_type": "brief"}, timeout=300)
    print(f"analyze http={r.status_code} elapsed={round(time.time()-t0,1)}s", flush=True)
    if r.status_code == 200:
        d = r.json()
        rep = d.get("report", {})
        meta = rep.get("meta", {})
        summ = rep.get("summary", {})
        print("STOCK:", meta.get("stock_name"), meta.get("stock_code"),
              "price", meta.get("current_price"), "chg%", meta.get("change_pct"), flush=True)
        print("ADVICE:", summ.get("operation_advice"), "TREND:", summ.get("trend_prediction"),
              "SCORE:", summ.get("sentiment_score"), flush=True)
        print("REST_PROXY_OK", flush=True)
        with open("/tmp/analysis_rest_out.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    else:
        print("ANALYZE FAIL", r.text[:400], flush=True)
        print("REST_PROXY_FAIL", flush=True)
except Exception as e:
    print(f"EXC {type(e).__name__}: {e}", flush=True)
    print("REST_PROXY_FAIL", flush=True)
