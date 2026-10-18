"""Scheduler entry point: python scripts/run_export.py  (decided jobs -> state/staging/*.csv, then stamp)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from jobhunt_tools import export  # noqa: E402

if __name__ == "__main__":
    path, n = export.run_export(ROOT / "state" / "staging")
    print(f"exported {n} row(s) to {path}" if path else "nothing to export")
