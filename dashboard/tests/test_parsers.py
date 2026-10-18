"""Parser tests on synthetic fixtures shaped like the ops files (docs/11-data-model.md). No personal data."""
from __future__ import annotations

import json
from pathlib import Path

from jobhunt import parsers as P

OUTCOMES_HEADER = ("run_id,attempt_id,job_id,company,ats,tenant,outcome,confirmation_method,started_at,ended_at,"
                   "duration_s,pages,fields,required_fields,human_interventions,halt_reason,trace_file")


def make_ops(tmp: Path) -> Path:
    ops = tmp / "ops"
    cap = ops / "AppApply-Capture"
    (cap / "traces" / "R20260101-1000-apply").mkdir(parents=True)
    (cap / "outcomes.csv").write_text(
        OUTCOMES_HEADER + "\n"
        "R20260101-1000-apply,111111111-a1,111111111,Acme,ashby,jobs.ashbyhq.com/acme,submitted,in_flow_text,"
        "2026-01-01T16:00:00Z,2026-01-01T16:02:00Z,120,1,5,3,0,,traces/R20260101-1000-apply/TRACE-111111111-a1.jsonl\n"
        "R20260101-1000-apply,222222222-a1,222222222,Beta,workday,beta.wd1,paused,,2026-01-01T17:00:00Z,,,,,,1,"
        "sign-in wall,traces/R20260101-1000-apply/TRACE-222222222-a1.jsonl\n", encoding="utf-8")
    steps = [
        {"ts": "t0", "run_id": "R20260101-1000-apply", "attempt_id": "111111111-a1", "job_id": "111111111", "step": 0,
         "action": "start", "card": "PREP-acme-111111111-R20260101-0900-prep.md", "resume": "X_ATS_Sales.pdf",
         "browser": "Browser 1", "human": "approval"},
        {"ts": "t1", "run_id": "R20260101-1000-apply", "attempt_id": "111111111-a1", "job_id": "111111111", "step": 1,
         "action": "type", "target": {"role": "textbox", "name": "First Name"}, "answer_key": "identity.first_name",
         "answer_source": "standing_answers", "value_ref": "answers.identity.first_name", "verify": {"ok": True}, "result": "ok"},
        {"ts": "t2", "run_id": "R20260101-1000-apply", "attempt_id": "111111111-a1", "job_id": "111111111", "step": 2,
         "action": "end", "outcome": "submitted"},
    ]
    (cap / "traces" / "R20260101-1000-apply" / "TRACE-111111111-a1.jsonl").write_text(
        "\n".join(json.dumps(s) for s in steps) + "\nnot json\n", encoding="utf-8")
    (cap / "question-bank.csv").write_text(
        "question_id,label_normalized,times_seen,seen_on_live_form,answer_key,answer_sources,ats_list,example_labels\n"
        "q1,first name,4,yes,identity.first_name,02,ashby|workday,First Name\n", encoding="utf-8")
    (ops / "04-ACCOUNT-LEDGER.md").write_text(
        "# 04 — Account Ledger\n\n## Tenants\n\n"
        "| Tenant key | Match on (URL host / path prefix) | ATS | State | Since | Queue rows waiting (Job ID) | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
        "| `beta.wd1.myworkdayjobs.com/Beta` | `beta.wd1.myworkdayjobs.com` | Workday | **account exists** | 2026-01-01 | 222222222 | pw in vault |\n"
        "\n## Hand-off list\n\n| Tenant | Where |\n|---|---|\n| Other | x |\n", encoding="utf-8")
    runs = ops / "Runs" / "2026-01-01"
    (runs / "dispatch-R20260101-0950-orch").mkdir(parents=True)
    (runs / "dispatch-R20260101-0950-orch" / "board.csv").write_text(
        "order,lane,job_id,company,role,ats,ats_label,tenant,tenant_key,lock,ea,login,priority,queue_row,state,card,card_run,resume,apply_url,jd\n"
        "1,1,333333333,Gamma,AE,greenhouse,Greenhouse,,,,0,no,3,5,ready,PREP-gamma.md,,X_ATS_Sales.pdf,https://example.test/a,\n"
        "2,2,444444444,Delta,AE,other,Other,,,,0,no,3,6,hold:question — fit,PREP-delta.md,,X_ATS_Sales.pdf,javascript:alert(1),\n",
        encoding="utf-8")
    (runs / "jd-R20260101-0900-prep.csv").write_text(
        "LinkedIn Job ID,Company,Job Title,Source,Complete?,Captured Date,Source URL,Characters,Notes,Full Job Description\n"
        '333333333,Gamma,AE,li,Y,2026-01-01,https://x.test,10,,"short"\n'
        '333333333,Gamma,AE,li,Y,2026-01-01,https://x.test,30,,"a much longer\nmultiline description"\n', encoding="utf-8")
    (runs / "PREP-gamma-333333333-R20260101-0900-prep.md").write_text("# PREP\n", encoding="utf-8")
    (ops / "Resume").mkdir()
    (ops / "Resume" / "Example_ATS_Sales.pdf").write_bytes(b"%PDF-1.4\n")
    (ops / "00-START-HERE.md").write_text("# Start here\n", encoding="utf-8")
    (ops / "Sheets-Export").mkdir()
    (ops / "Sheets-Export" / "Queue.csv").write_text(
        "LinkedIn Job ID,Status,Portal Password\n333333333,Ready,hunter2\n", encoding="utf-8")
    return ops


def test_outcomes_and_traces(tmp_path):
    ops = make_ops(tmp_path)
    cap = ops / "AppApply-Capture"
    atts = P.parse_outcomes(cap)
    assert [a["outcome"] for a in atts] == ["submitted", "paused"]
    assert atts[0]["duration_s"] == 120 and atts[0]["started_at"].tzinfo is not None
    warnings: list[str] = []
    steps, starts = P.parse_traces(cap, warnings)
    assert len(steps) == 3
    assert warnings and "bad JSON" in warnings[0]
    assert starts[("R20260101-1000-apply", "111111111-a1")]["resume"] == "X_ATS_Sales.pdf"
    typed = next(s for s in steps if s["action"] == "type")
    assert typed["target_name"] == "First Name" and typed["verify_ok"] is True


def test_ledger_keeps_state_and_drops_notes(tmp_path):
    ops = make_ops(tmp_path)
    w: list[str] = []
    rows = P.parse_ledger(ops / "04-ACCOUNT-LEDGER.md", w)
    assert rows == [{"tenant_key": "beta.wd1.myworkdayjobs.com/Beta", "match_on": "beta.wd1.myworkdayjobs.com",
                     "ats": "Workday", "state": "account exists", "since": "2026-01-01", "waiting": "222222222"}]
    assert "notes" not in rows[0] and not w


def test_board_jd_and_run_files(tmp_path):
    ops = make_ops(tmp_path)
    board = {b["job_id"]: b for b in P.parse_boards(ops / "Runs")}
    assert board["333333333"]["state"] == "ready" and board["444444444"]["state"].startswith("hold:")
    jds = P.parse_jds(ops / "Runs")
    assert len(jds) == 1 and "multiline" in jds[0]["full_text"]
    rf = P.parse_run_files(ops)
    assert rf[0]["kind"] == "PREP" and rf[0]["job_id"] == "333333333"


def test_sheet_values_drop_credential_columns_and_key_rows():
    values = [["LinkedIn Job ID", "Status", "Portal Password"],
              ["333333333", "Ready", "hunter2"],
              [],                              # blank row is skipped
              ["333333333", "Applied"],        # duplicate key, short row
              ["", "Saved"]]                   # no Job ID: skipped on the Queue (never keyed by position)
    w: list[str] = []
    rows = P.rows_from_values("Queue", "sheet:Queue/Queue", values, w)
    assert [r["row_key"] for r in rows] == ["333333333", "333333333#row-4"]
    assert any("skipped row 5" in x for x in w)
    other = P.rows_from_values("Raw", "sheet:Queue/Raw", values, [])
    assert [r["row_key"] for r in other] == ["333333333", "333333333#row-4", "row-5"]  # other sheets unchanged
    assert all("Portal Password" not in r["data"] for r in rows)
    assert rows[1]["data"] == {"LinkedIn Job ID": "333333333", "Status": "Applied"}
    assert any("Portal Password" in x for x in w)
    assert P.rows_from_values("Queue", "x", [], w) == []


def test_bullets_only_approved(tmp_path):
    p = tmp_path / "Approved-Bullets.md"
    p.write_text("# Approved Bullets\n## Counts\n- not a bullet\n## Professional experience\n### Co\n#### AE\n"
                 "- Did a thing\n## Held (not used)\n- held one\n## Retired claims\n- retired one\n", encoding="utf-8")
    b = P.parse_bullets(p)
    assert [x["text"] for x in b] == ["Did a thing"] and b[0]["subsection"] == "Co" and b[0]["role"] == "AE"


def test_resumes_docs_fingerprint(tmp_path, monkeypatch):
    ops = make_ops(tmp_path)
    monkeypatch.setenv("JOBHUNT_RESUME_PREFIX", "Example_")
    assert P.parse_resumes(ops)[0]["tract"] == "ATS_Sales"
    assert P.parse_docs(ops)[0]["title"] == "Start here"
    fp1 = P.fingerprint(ops)
    (ops / "00-START-HERE.md").write_text("# Start here, longer\n", encoding="utf-8")
    assert P.fingerprint(ops) != fp1


def test_outcomes_read_staging_fragments_and_dedupe(tmp_path):
    ops = make_ops(tmp_path)
    cap = ops / "AppApply-Capture"
    (cap / "staging" / "_imported").mkdir(parents=True)
    # A live fragment for a new attempt, a fragment for an attempt already merged (outcomes.csv must win),
    # and an already-imported fragment that must not be read at all.
    (cap / "staging" / "OUTCOME-333333333-a1-R20260102-1200-apply1.csv").write_text(
        OUTCOMES_HEADER + "\nR20260102-1200-apply1,333333333-a1,333333333,\"Gamma, Inc.\",greenhouse,gh/gamma,submitted,,"
        "2026-01-02T18:00:00Z,2026-01-02T18:05:00Z,300,,,,0,,\n", encoding="utf-8")
    (cap / "staging" / "OUTCOME-111111111-a1-R20260101-1000-apply.csv").write_text(
        OUTCOMES_HEADER + "\nR20260101-1000-apply,111111111-a1,111111111,Acme STAGED,ashby,x,paused,,,,,,,,,,\n",
        encoding="utf-8")
    (cap / "staging" / "_imported" / "OUTCOME-444444444-a1-R20260102-1200-apply1.csv").write_text(
        OUTCOMES_HEADER + "\nR20260102-1200-apply1,444444444-a1,444444444,Delta,ashby,x,submitted,,,,,,,,,,\n",
        encoding="utf-8")
    atts = {a["attempt_id"]: a for a in P.parse_outcomes(cap)}
    assert set(atts) == {"111111111-a1", "222222222-a1", "333333333-a1"}
    assert atts["111111111-a1"]["company"] == "Acme" and atts["111111111-a1"]["outcome"] == "submitted"
    assert atts["333333333-a1"]["company"] == "Gamma, Inc." and atts["333333333-a1"]["ended_at"].tzinfo is not None


def test_outcomes_read_jt_file(tmp_path):
    ops = make_ops(tmp_path)
    cap = ops / "AppApply-Capture"
    (cap / "outcomes-jt.csv").write_text(
        OUTCOMES_HEADER + "\nR20260103-1000-apply1,JT-abcdef0123-a1,JT-abcdef0123,Jetco,greenhouse,gh/jet,submitted,,"
        "2026-01-03T18:00:00Z,2026-01-03T18:05:00Z,300,,,,0,,\n", encoding="utf-8")
    atts = {a["attempt_id"]: a for a in P.parse_outcomes(cap)}
    assert atts["JT-abcdef0123-a1"]["job_id"] == "JT-abcdef0123" and "222222222-a1" in atts


def test_run_state_flag_and_events(tmp_path):
    import os
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 1, 2, 18, 0, tzinfo=timezone.utc)
    day = tmp_path / "Runs" / "2026-01-02"
    events = day / "dispatch-R20260102-1200-orch" / "events"
    events.mkdir(parents=True)
    assert P.run_state(tmp_path, now) is None

    ev = events / "lane1.jsonl"
    ev.write_text("{}\n", encoding="utf-8")
    fresh = (now - timedelta(minutes=2)).timestamp()
    os.utime(ev, (fresh, fresh))
    st = P.run_state(tmp_path, now)
    assert st and st["source"] == "events" and st["run_id"] == "R20260102-1200-orch"
    stale = (now - timedelta(minutes=10)).timestamp()
    os.utime(ev, (stale, stale))
    assert P.run_state(tmp_path, now) is None

    flag = day / "RUN-ACTIVE.json"
    flag.write_text(json.dumps({"run_id": "R20260102-1200-orch", "expires_at": "2026-01-02T18:10:00Z"}), encoding="utf-8")
    st = P.run_state(tmp_path, now)
    assert st and st["source"] == "flag" and st["run_id"] == "R20260102-1200-orch"
    # Expired flag: off, even with fresh events (once a flag exists it alone decides).
    flag.write_text(json.dumps({"run_id": "R20260102-1200-orch", "expires_at": "2026-01-02T17:50:00Z"}), encoding="utf-8")
    os.utime(ev, (fresh, fresh))
    assert P.run_state(tmp_path, now) is None
    # Unreadable flag: live for 15 min from its mtime.
    flag.write_text("{half-synced", encoding="utf-8")
    os.utime(flag, (fresh, fresh))
    assert P.run_state(tmp_path, now)["source"] == "flag"


USAGE_HEADER = ("run_id,phase,session,session_run_id,model,started_at,updated_at,input_tokens,output_tokens,"
                "cache_creation_tokens,cache_read_tokens,jobs_attempted,jobs_submitted,weekly_pct_start,"
                "weekly_pct_now,weekly_resets_at")


def test_usage_rows_lenient(tmp_path):
    day = tmp_path / "Runs" / "2026-01-02"
    day.mkdir(parents=True)
    (day / "USAGE-R20260102-1200-orch.csv").write_text(
        USAGE_HEADER + ",extra_col\n"
        ",3,orch,,opus,2026-01-02T18:00:00Z,2026-01-02T19:00:00Z,1000,200,50,90000,,,40,46.5,2026-01-05T00:00:00Z,x\n"
        "R20260102-1200-orch,3,lane1,R20260102-1216-apply1,sonnet,,,5000,800,,120000,9,8,,,,\n"
        "R20260102-1200-orch,3,,,,,,,,,,,,,,\n", encoding="utf-8")
    warnings: list[str] = []
    rows = {r["session"]: r for r in P.parse_usage(tmp_path / "Runs", warnings)}
    assert set(rows) == {"orch", "lane1"} and warnings and "no session" in warnings[0]
    assert rows["orch"]["run_id"] == "R20260102-1200-orch"  # blank run_id falls back to the file name
    assert rows["orch"]["weekly_pct_now"] == 46.5 and rows["orch"]["jobs_submitted"] is None
    assert rows["lane1"]["cache_read_tokens"] == 120000 and rows["lane1"]["jobs_submitted"] == 8
    assert rows["lane1"]["run_date"] == "2026-01-02"
