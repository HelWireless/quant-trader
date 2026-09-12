"""Headless smoke test for the static frontend served at /web on :8001.

Verifies:
  1. Every web/*.html is served (200) at /web/<file>
  2. Every <script src> / <link href> asset it references resolves (200)
"""
import re
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8001"
WEB_DIR = "/home/cody/projects/quant-trader/web"

from pathlib import Path

html_files = sorted(Path(WEB_DIR).glob("*.html"))

fails = []
checked = 0


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:  # pragma: no cover
        return f"ERR:{e!r}", 0


print(f"HTML pages: {len(html_files)}")
for hf in html_files:
    url = f"/web/{hf.name}"
    st, _ = get(url)
    checked += 1
    ok = st == 200
    print(f"[{'OK' if ok else 'XX'}] page {url} -> {st}")
    if not ok:
        fails.append(f"page {url} -> {st}")
    # extract asset refs (src/href quoted values)
    text = Path(hf).read_text(encoding="utf-8", errors="ignore")
    refs = set()
    for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+)"', text):
        val = m.group(1).strip()
        if val.startswith(("http://", "https://", "mailto:", "tel:", "#", "data:")):
            continue
        if "/web/assets/" in val:
            refs.add(val)
        elif val.startswith("assets/") or val.startswith("./assets/"):
            refs.add("/web/" + val.lstrip("./"))
        elif val.startswith("/") and (val.endswith(".js") or val.endswith(".css")):
            refs.add(val)
    for ref in sorted(refs):
        st, _ = get(ref)
        checked += 1
        ok = st == 200
        print(f"    [{'OK' if ok else 'XX'}] asset {ref} -> {st}")
        if not ok:
            fails.append(f"asset {ref} -> {st}")

print(f"\nChecked {checked} URLs, failures: {len(fails)}")
if fails:
    print("FAILURES:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("FRONTEND_SMOKE_OK")
