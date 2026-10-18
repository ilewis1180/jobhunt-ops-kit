"""Search step only: python scripts/run_search.py <profile-name> [--hours-old N] [--sites linkedin,indeed]

Scrapes one board at a time (never parallel, no retry loop), grades every row (find-a-job-ai rules when the profile
carries them and the vendored grader is fetched, else the simple title/boost grader; grade blank = would be
rejected) and keeps every row, writes state/staging/discover-candidates-<timestamp>.csv.
No database, no chat posts, no Queue. Exit code 2 if any board errored (e.g. HTTP 429).
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from jobhunt_tools.grade import grade  # noqa: E402
from jobhunt_tools import fajai_grade  # noqa: E402

COLS = ["board", "board_job_id", "company", "title", "location", "job_url", "job_url_direct",
        "date_posted", "salary", "grade", "score", "excluded_reason", "source_profile"]


def s(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v)


def salary(r):
    lo, hi = s(r.get("min_amount")), s(r.get("max_amount"))
    if not (lo or hi):
        return ""
    return f"{lo}-{hi} {s(r.get('currency'))} {s(r.get('interval'))}".strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--hours-old", type=int, default=72)
    ap.add_argument("--sites", default="linkedin,indeed")
    ap.add_argument("--results", type=int, default=50)
    ap.add_argument("--pause", type=int, default=45)
    ap.add_argument("--fetch-desc", action="store_true", help="LinkedIn full descriptions (slow, more 429s); the real grader needs them to score above C")
    a = ap.parse_args()
    prof = json.loads((ROOT / "config" / "profiles" / f"{a.profile}.json").read_text(encoding="utf-8"))
    from jobspy import scrape_jobs

    ctx = fajai_grade.build_ctx(prof) if fajai_grade.is_real_profile(prof) else None
    rows, log = [], []
    for i, site in enumerate(x.strip() for x in a.sites.split(",")):
        if i:
            time.sleep(a.pause)
        try:
            df = scrape_jobs(site_name=[site], search_term=prof["search_term"], location=prof.get("location", ""),
                             results_wanted=a.results, hours_old=a.hours_old, country_indeed="USA", verbose=1,
                             linkedin_fetch_description=a.fetch_desc)
            recs = df.to_dict("records")
            log.append(f"{site}: {len(recs)} rows")
            for r in recs:
                url = s(r.get("job_url"))
                if ctx:
                    g, sc, why = fajai_grade.grade_row(ctx, s(r.get("title")), s(r.get("description")),
                                                       s(r.get("company")), s(r.get("location")), url)
                else:
                    g, sc, why = grade(prof, s(r.get("title")), s(r.get("description"))) or "", "", ""
                rows.append(dict(board=site, board_job_id=s(r.get("id")), company=s(r.get("company")),
                                 title=s(r.get("title")), location=s(r.get("location")), job_url=url,
                                 job_url_direct=s(r.get("job_url_direct")), date_posted=s(r.get("date_posted")),
                                 salary=salary(r), grade=g, score=sc, excluded_reason=why,
                                 source_profile=prof["name"]))
        except Exception as e:  # report, do not retry
            log.append(f"{site}: ERROR {type(e).__name__}: {str(e)[:300]}")
    out = ROOT / "state" / "staging" / f"discover-candidates-{datetime.now():%Y-%m-%d-%H%M%S}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print("\n".join(log))
    print(f"wrote {len(rows)} rows -> {out}")
    sys.exit(2 if any("ERROR" in l for l in log) else 0)


if __name__ == "__main__":
    main()
