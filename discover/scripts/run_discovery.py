"""Scheduler entry point: python scripts/run_discovery.py <profile-name> [--dry-run]"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from jobhunt_tools import discover  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("usage: run_discovery.py <profile-name> [--dry-run]")
    res = discover.run(ROOT / "config" / "profiles" / f"{args[0]}.json", ROOT / "state" / "discovery",
                       dry_run="--dry-run" in sys.argv)
    print(json.dumps(res))
