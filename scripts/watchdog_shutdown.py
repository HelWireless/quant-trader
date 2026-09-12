"""Watchdog: monitor baostock gap fill and shutdown when done."""
import subprocess
import time
import os

LOG = r"C:\Users\cody\PycharmProjects\quant-trader\data\baostock_gap_import.log"

while True:
    # Check if any python processes are still running (besides ourselves)
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"],
        capture_output=True, text=True
    )
    python_procs = [l for l in result.stdout.strip().splitlines() if l.strip()]
    
    # Check if import completed by looking for "Gap fill complete" in log
    try:
        with open(LOG, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "Gap fill complete" in content:
            # Extract last progress line
            lines = content.strip().splitlines()
            for line in reversed(lines):
                if "Gap fill complete" in line:
                    print(f"IMPORT DONE: {line.strip()}")
                    break
            break
    except Exception:
        pass
    
    # If no python processes left, import must have finished/crashed
    if len(python_procs) <= 1:  # only ourselves (or none)
        print("No python processes found — import appears finished")
        break
    
    print(f"Still running ({len(python_procs)} python procs), waiting 60s...")
    time.sleep(60)

# Shutdown in 60 seconds (gives user time to cancel)
print("Import finished! Shutting down in 60 seconds...")
print("To cancel shutdown, run: shutdown /a")
os.system("shutdown /s /t 60 /c \"BaoStock gap fill completed. Auto shutdown.\"")
