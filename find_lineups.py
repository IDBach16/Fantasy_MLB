"""Run the Claude lineup agent across all 3 leagues and save the report.
  python find_lineups.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import lineup as L

print("Optimizing lineups (ESPN + Ottoneu + Fantrax) with Claude...\n")
report = L.run()

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reports")
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, "lineups.md")
with open(path, "w", encoding="utf-8") as f:
    f.write(report)
print(report)
print(f"\n\nSaved -> {path}")
