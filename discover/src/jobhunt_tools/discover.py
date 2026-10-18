"""Daily discovery for one profile: scrape with python-jobspy, grade, resolve, de-dupe, insert pending.

Local de-dupe uses state/discovery/seen_jobs_<profile>.json; the database de-dupes again by job_key
(ON CONFLICT DO NOTHING), which is what keeps denied jobs from coming back. Dedupe against the
Queue's existing IDs happens on the ops side at ingest (the scheduler host has no Queue access).
"""
import json
from datetime import datetime
from pathlib import Path

from . import db
from .grade import grade
from .keys import job_key
from .resolve import resolve


def _s(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v)


def scrape(profile):
    from jobspy import scrape_jobs

    return scrape_jobs(
        site_name=profile.get("sites", ["indeed"]),
        search_term=profile["search_term"],
        location=profile.get("location", ""),
        results_wanted=profile.get("results_wanted", 20),
        hours_old=profile.get("hours_old", 36),
        country_indeed=profile.get("country_indeed", "USA"),
        is_remote=profile.get("is_remote", False),
        verbose=0,
    ).to_dict("records")


def build_candidates(profile, rows, resolver=resolve):
    out = []
    for r in rows:
        title, company, loc = _s(r.get("title")), _s(r.get("company")), _s(r.get("location"))
        if not title or not company:
            continue
        g = grade(profile, title, _s(r.get("description")))
        if not g:
            continue
        url = _s(r.get("job_url"))
        out.append(dict(
            job_key=job_key(company, title, loc, url), title=title, company=company, location=loc,
            grade=g, source=_s(r.get("site")) or "unknown",
            url=resolver(url, _s(r.get("job_url_direct")) or None), board_url=url))
    return out


def run(profile_path, state_dir, dry_run=False, scraper=scrape, inserter=db.insert_pending, resolver=resolve):
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    name = profile["name"]
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    seen_path = state / f"seen_jobs_{name}.json"
    seen = set(json.loads(seen_path.read_text(encoding="utf-8"))) if seen_path.exists() else set()

    cands = build_candidates(profile, scraper(profile), resolver)
    fresh, dupes = [], 0
    for c in cands:
        if c["job_key"] in seen or any(c["job_key"] == f["job_key"] for f in fresh):
            dupes += 1
        else:
            fresh.append(c)

    inserted = 0
    if not dry_run:
        for c in fresh:
            if inserter(c):
                inserted += 1
            seen.add(c["job_key"])
        seen_path.write_text(json.dumps(sorted(seen)), encoding="utf-8")

    report = state / f"report_{name}_{datetime.now():%Y-%m-%d}.md"
    lines = [f"# {name} {datetime.now():%Y-%m-%d %H:%M}", "",
             f"scraped→graded A/B: {len(cands)} | already seen: {dupes} | new: {len(fresh)} | inserted: {inserted}"
             + (" (dry run, nothing written to the database)" if dry_run else ""), ""]
    for c in fresh:
        lines.append(f"- [{c['grade']}] {c['title']} — {c['company']} ({c['location']}) "
                     f"{c['source']} direct={'yes' if c['url'] else 'NO'} key={c['job_key']} {c['board_url']}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dict(candidates=len(cands), duplicates=dupes, new=len(fresh), inserted=inserted, report=str(report))
