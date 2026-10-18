"""Applications view model: Queue status mapping and the Applied fallback to Queue col C."""
from __future__ import annotations

import pytest

pytest.importorskip("psycopg")
from jobhunt.web import data as D  # noqa: E402


def test_queue_status_mapping():
    assert D.queue_status({"Status": "Submitted-unconfirmed"}) == ("Submitted", "s-sub", "unconfirmed")
    assert D.queue_status({"Status": "In progress"})[:2] == ("In progress", "s-ready")
    assert D.queue_status({"Status": "Paused-SignIn"}) == ("Paused", "s-pause", "SignIn")
    assert D.queue_status({"Status": ""}) is None


def test_queue_touched_formats():
    t = D.queue_touched({"Last touched": "2026-09-23 3:30"})
    assert (t.hour, t.minute, t.tzinfo) == (3, 30, D.CT)
    assert D.queue_touched({"Last touched": "2026-09-29 13:45"}).hour == 13
    assert D.queue_touched({"Last touched": "2026-09-29"}).day == 29
    assert D.queue_touched({"Last touched": "46281"}) is None


def test_token_usage_totals_and_weekly_share(monkeypatch):
    from datetime import datetime, timezone
    t = datetime(2026, 1, 2, 19, 0, tzinfo=timezone.utc)
    base = dict(run_date="2026-01-02", model="m", started_at=None, cache_creation_tokens=0,
                jobs_attempted=None, weekly_resets_at=None, source_file="x")
    usage = [
        {**base, "run_id": "R1", "phase": "3", "session": "orch", "session_run_id": None, "updated_at": t,
         "input_tokens": 100_000, "output_tokens": 0, "cache_read_tokens": 0, "jobs_submitted": None,
         "weekly_pct_start": 40, "weekly_pct_now": 46},
        {**base, "run_id": "R1", "phase": "3", "session": "lane1", "session_run_id": "R1-apply1", "updated_at": t,
         "input_tokens": 300_000, "output_tokens": 0, "cache_read_tokens": 0, "jobs_submitted": None,
         "weekly_pct_start": None, "weekly_pct_now": None},
    ]

    def fake_q(sql, params=None):
        if "token_usage" in sql:
            return usage
        return [{"run_id": "R1-apply1", "n": 3}]  # submitted attempts per lane run

    monkeypatch.setattr(D, "q", fake_q)
    u = D.token_usage()
    day = u["days"][0]
    assert day["tokens"] == "400k" and day["submitted"] == 3 and day["pct_s"] == "6.0%"
    run = day["runs"][0]
    lane = next(s for s in run["sessions"] if s["session"] == "lane1")
    assert lane["submitted"] == 3 and lane["per_job"] == "100k" and lane["pct"] == "~4.5%"
    assert u["weekly_now"] == "46%" and day["n_sessions"] == 2


def test_token_usage_empty(monkeypatch):
    monkeypatch.setattr(D, "q", lambda sql, params=None: [])
    assert D.token_usage() == {"days": [], "weekly_now": None}
