"""Run the Claude prospect-finder and save the report.
  python find_prospects.py [top_n]
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import prospect_finder as PF

top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 45
print(f"Analyzing top {top_n} available prospects with Claude...\n")
report = PF.find(top_n)

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reports")
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, "available_prospect_targets.md")
with open(path, "w", encoding="utf-8") as f:
    f.write(report)
print(report)
print(f"\n\nSaved -> {path}")
