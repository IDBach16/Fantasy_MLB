"""
Run the analysis pipeline: load rosters (cached) -> join Savant -> cross-league report.
  python build.py            # use cached rosters
  python build.py --refresh  # re-pull live rosters first
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import rosters as R, analyze as A

refresh = "--refresh" in sys.argv
df = R.load_all(refresh=refresh)
report = A.full_report(df)

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reports")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "roster_analysis_2026-06-30.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(report)

print(report)
print(f"\n\nSaved -> {out_path}")
