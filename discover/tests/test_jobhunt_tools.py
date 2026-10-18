import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pytest  # noqa: E402
from jobhunt_tools import db, discover, export  # noqa: E402
from jobhunt_tools.grade import grade  # noqa: E402
from jobhunt_tools.keys import job_key, jt_key  # noqa: E402
from jobhunt_tools.resolve import resolve  # noqa: E402

P = {"title_any": ["account executive"], "title_exclude": ["intern"], "boost": ["saas"]}


def test_linkedin_key_is_numeric_id():
    assert job_key("A", "B", "C", "https://www.linkedin.com/jobs/view/senior-ae-at-x-4012345678?x=1") == "4012345678"


def test_jt_key_stable_across_case_and_punctuation():
    a = job_key("Acme, Inc.", "Account Executive", "Denver, CO")
    assert a == job_key("ACME Inc", "account  executive", "denver co") and a.startswith("JT-") and len(a) == 13


def test_jt_key_matches_ops_rule():
    # same value as ops/tools/common.py job_tools_key (JT- + sha1(normalized company|title|location)[:10])
    assert job_key("Acme, Inc.", "Account Executive", "Denver, CO") == "JT-194799d947"
    assert job_key("A", "B", "C", "https://www.linkedin.com/jobs/search/?currentJobId=4476880256") == "4476880256"


def test_grade():
    assert grade(P, "Account Executive", "SaaS platform") == "A"
    assert grade(P, "Account Executive", "retail") == "B"
    assert grade(P, "Account Executive Intern", "saas") is None
    assert grade(P, "Plumber", "saas") is None


def test_resolve_prefers_direct_then_follows_then_none():
    assert resolve("https://indeed.com/v", "https://acme.com/jobs/1") == "https://acme.com/jobs/1"
    assert resolve("https://indeed.com/v", None, fetch=lambda u: "https://boards.greenhouse.io/acme/1") == "https://boards.greenhouse.io/acme/1"
    assert resolve("https://indeed.com/v", None, fetch=lambda u: "https://www.indeed.com/viewjob?x") is None
    assert resolve("https://indeed.com/v", "https://indeed.com/x", fetch=lambda u: (_ for _ in ()).throw(OSError())) is None


ROW = {"title": "Account Executive", "company": "Acme", "location": "Denver, CO", "site": "indeed",
       "job_url": "https://indeed.com/viewjob?jk=1", "job_url_direct": None, "description": "SaaS"}


def _profile(tmp_path):
    p = tmp_path / "p.json"
    p.write_text('{"name":"t","search_term":"x","title_any":["account executive"],"boost":["saas"]}')
    return p


def test_discover_dry_run_writes_no_seen_and_no_insert(tmp_path):
    calls = []
    res = discover.run(_profile(tmp_path), tmp_path / "s", dry_run=True, scraper=lambda p: [ROW],
                       inserter=lambda c: calls.append(c), resolver=lambda *a: None)
    assert res["new"] == 1 and res["inserted"] == 0 and not calls
    assert not (tmp_path / "s" / "seen_jobs_t.json").exists()


def test_discover_inserts_once_then_dedupes(tmp_path):
    calls = []
    kw = dict(scraper=lambda p: [ROW, ROW], inserter=lambda c: calls.append(c) or True, resolver=lambda *a: None)
    r1 = discover.run(_profile(tmp_path), tmp_path / "s", **kw)
    r2 = discover.run(_profile(tmp_path), tmp_path / "s", **kw)
    assert r1["new"] == 1 and r1["inserted"] == 1 and r1["duplicates"] == 1
    assert r2["new"] == 0 and len(calls) == 1
    assert calls[0]["url"] is None and calls[0]["grade"] == "A"


def test_export_writes_before_stamping(tmp_path):
    rows = [dict(zip(db.EXPORT_COLS, ["k1", "T", "C", "L", "A", "indeed", "", "approved", "2026-10-11", "operator"]))]
    seen_files = []
    path, n = export.run_export(tmp_path, fetch=lambda: rows,
                                stamp=lambda keys: (seen_files.extend(tmp_path.glob("approved-jobs-*.csv")), len(keys))[1])
    assert n == 1 and seen_files and list(csv.DictReader(open(path)))[0]["job_key"] == "k1"


def test_export_failed_write_does_not_stamp(tmp_path, monkeypatch):
    stamped = []
    monkeypatch.setattr(export, "write_csv", lambda rows, path: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        export.run_export(tmp_path, fetch=lambda: [{"job_key": "k1"}], stamp=lambda k: stamped.append(k))
    assert not stamped


def test_unsafe_key_refused():
    with pytest.raises(ValueError):
        db.stamp_exported(["a'; drop table x;--"], runner=lambda *a, **k: None)

