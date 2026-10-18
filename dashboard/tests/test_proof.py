"""Proof screenshots in the audit trail (08-CAPTURE-SPEC §1.1)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from jobhunt.web import app as A  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def ops(tmp_path, monkeypatch):
    monkeypatch.setitem(A.ROOTS, "ops", tmp_path)
    return tmp_path


def shots(ops, run, names):
    d = ops / "AppApply-Capture" / "proof" / run
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(PNG)


def test_orders_review_text_confirm_and_ignores_other_attempts(ops):
    shots(ops, "R1", ["J1-a1-confirm.png", "J1-a1-text2.png", "J1-a1-review.png", "J1-a1-text1.png",
                      "J1-a2-review.png", "J1-a10-review.png", "J1-a1-review-old.png", "notes.txt"])
    got = A.proof_images({"run_id": "R1", "attempt_id": "J1-a1"})
    assert [g["label"] for g in got] == ["Review page (before Submit)", "Text field 1", "Text field 2",
                                         "Confirmation (after Submit)"]
    assert got[0]["rel"] == "AppApply-Capture/proof/R1/J1-a1-review.png"


def test_empty_or_missing_is_normal(ops):
    assert A.proof_images({"run_id": "R9", "attempt_id": "J1-a1"}) == []
    assert A.proof_images(None) == []


def test_run_id_cannot_escape_proof_dir(ops):
    (ops / "J1-a1-review.png").write_bytes(PNG)
    assert A.proof_images({"run_id": "../..", "attempt_id": "J1-a1"}) == []


def test_private_files_are_never_served_or_listed(ops):
    from jobhunt import parsers as P
    (ops / "ANSWERS-PRIVATE.md").write_text("# Private\n", encoding="utf-8")
    (ops / "01-PLAYBOOK.md").write_text("# Playbook\n", encoding="utf-8")
    for rel in ("ANSWERS-PRIVATE.md", "./ANSWERS-PRIVATE.md", "sub/../answers-private.md", "scratch/queue-now.csv", "config.toml"):
        with pytest.raises(Exception):
            A.safe_path("ops", rel)
    assert [d["name"] for d in P.parse_docs(ops)] == ["01-PLAYBOOK"]
    (ops / "SESSION_LOG.md").write_text("# Log\n", encoding="utf-8")
    assert [d["name"] for d in P.parse_docs(ops)] == ["01-PLAYBOOK", "SESSION_LOG"]
    assert A.safe_path("ops", "01-PLAYBOOK.md").name == "01-PLAYBOOK.md"


def test_images_are_served_but_paths_stay_inside_the_mount(ops):
    shots(ops, "R1", ["J1-a1-review.png"])
    assert A.safe_path("ops", "AppApply-Capture/proof/R1/J1-a1-review.png").name == "J1-a1-review.png"
    with pytest.raises(Exception):
        A.safe_path("ops", "../outside.png")
