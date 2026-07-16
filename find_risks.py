"""Run the Claude injury/risk agent across all leagues and save the report.
  python find_risks.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import injury_risk as IR

print("Scanning injury/risk across leagues with Claude...\n")
report = IR.run()

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reports")
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, "injury_risk.md")
with open(path, "w", encoding="utf-8") as f:
    f.write(report)
print(report)
print(f"\n\nSaved -> {path}")
