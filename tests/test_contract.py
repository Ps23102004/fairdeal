from __future__ import annotations

from fairdeal.clauses import CONTRACT_CLAUSES
from fairdeal.contract import run


def _by_title(result: dict, title: str) -> dict:
    return next(r for r in result["results"] if r["title"] == title)


def test_red_flag_language_is_flagged_unfair() -> None:
    text = "9. Limitation of liability. Contractor accepts unlimited liability under this agreement."
    row = _by_title(run(text), "Liability Clause")

    assert row["rating"] == "unfair"
    assert row["delta"] is None
    assert "unlimited liability" in row["explanation"]


def test_safe_version_of_a_present_clause_is_not_flagged() -> None:
    text = "9. Limitation of liability. Each party's total liability is capped at the fees paid hereunder."
    row = _by_title(run(text), "Liability Clause")

    assert row["rating"] == "fair"


def test_topic_absent_from_document_is_unknown() -> None:
    text = "9. Limitation of liability. Each party's total liability is capped at the fees paid hereunder."
    row = _by_title(run(text), "Non-Compete / Non-Solicitation Clause")

    assert row["rating"] == "unknown"
    assert "never mentioned" in row["explanation"]


def test_empty_document_degrades_without_raising() -> None:
    result = run("")

    assert result["results"] == []
    assert result["data_source"] == "clause-library-v1"
    assert "nothing to review" in result["reply_text"]


def test_scans_the_contract_library_not_the_lease_one() -> None:
    result = run("a contract with no recognisable clauses at all")

    assert {r["title"] for r in result["results"]} == {rule.label for rule in CONTRACT_CLAUSES}


def test_worst_finding_surfaces_first() -> None:
    text = (
        "5. Payment terms: net 90 from invoice. "
        "9. Limitation of liability: contractor accepts unlimited liability."
    )
    ratings = [r["rating"] for r in run(text)["results"]]

    assert ratings[0] == "unfair"  # liability (high severity) beats the medium-severity payment flag
    assert ratings.index("borderline") < ratings.index("unknown")
