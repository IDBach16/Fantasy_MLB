"""Run the Claude trade evaluator (Ottoneu) and save the report.
  python find_trades.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import trade as T

print("Evaluating Ottoneu trades with Claude...\n")
report = T.analyze()

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reports")
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, "trade_targets_ottoneu.md")
with open(path, "w", encoding="utf-8") as f:
    f.write(report)
print(report)
print(f"\n\nSaved -> {path}")
