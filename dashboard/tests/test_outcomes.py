from datetime import date, datetime, timezone

from jobhunt.web import outcomes as O

HEAD = "job_id,company,title,apply_at,apply_src,confirmation_at,rejection_at,interview_at,last_mail_at,thread_count,match_methods,match_confidence,state,followup_due,mail_export_at\n"


def ops(tmp_path, rows, followups=""):
    cap = tmp_path / "AppApply-Capture"
    cap.mkdir()
    (cap / "timeline.csv").write_text(HEAD + rows, encoding="utf-8-sig")
    (cap / "followups.csv").write_text("job_id,followed_up_at,followup_days,snooze_until,note\n" + followups)
    return tmp_path


NOW = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 6)


def test_counts_spans_and_followups(tmp_path):
    rows = ("1,A,Role A,2026-09-18 00:00:00,q,2026-09-20 00:00:00,2026-09-28 00:00:00,,,1,,,rejected,2026-09-25,2026-10-06T17:00:00Z\n"
            "2,B,Role B,2026-09-20 00:00:00,q,2026-09-21 00:00:00,,,,1,,,confirmed,2026-09-27,2026-10-06T17:00:00Z\n"
            "3,,,2026-10-05 00:00:00,q,,,,,0,,,applied,2026-10-12,2026-10-06T17:00:00Z\n")
    o = O.outcomes(ops(tmp_path, rows), now=NOW, today=TODAY)
    n = {t["label"]: t["n"] for t in o["tiles"]}
    assert n["Applied"] == 3 and n["Open"] == 2 and n["Rejected"] == 1 and n["Confirmed"] == 2
    assert [d["job_id"] for d in o["due"]] == ["2"]          # rejected is excluded, row 3 is not due yet
    assert o["due"][0]["overdue"] == 9
    spans = {s["label"]: s for s in o["spans"]}
    assert spans["Applied to confirmation"]["n"] == 2 and spans["Applied to interview"]["n"] == 0
    assert o["rows"][-1]["company"] == "A" and o["rows"][0]["company"] == "Unparsed company"
    assert o["stamp"]["cls"] == "s-sub"


def test_snooze_and_followed_up_remove_a_row(tmp_path):
    rows = "2,B,Role B,2026-09-20 00:00:00,q,,,,,0,,,applied,2026-09-27,2026-10-06T17:00:00Z\n"
    assert len(O.outcomes(ops(tmp_path, rows, "2,,,2026-10-10,\n"), now=NOW, today=TODAY)["due"]) == 0
    p2 = tmp_path / "x"; p2.mkdir()
    assert len(O.outcomes(ops(p2, rows, "2,2026-09-30,,,\n"), now=NOW, today=TODAY)["due"]) == 0


def test_stale_export_is_red_and_state_filter(tmp_path):
    rows = ("1,A,R,2026-09-18 00:00:00,q,,2026-09-28 00:00:00,,,1,,,rejected,,2026-10-04T05:41:48Z\n"
            "2,B,R,2026-09-19 00:00:00,q,,,,,0,,,applied,,2026-10-04T05:41:48Z\n")
    o = O.outcomes(ops(tmp_path, rows), state="rejected", now=NOW, today=TODAY)
    assert o["stamp"]["cls"] == "s-bad" and [r["job_id"] for r in o["rows"]] == ["1"]


def test_missing_file_is_normal(tmp_path):
    o = O.outcomes(tmp_path, now=NOW, today=TODAY)
    assert o["missing"] and o["total"] == 0
