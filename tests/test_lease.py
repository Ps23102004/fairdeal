from __future__ import annotations

from fairdeal.clauses import LEASE_CLAUSES, ClauseRule
from fairdeal.lease import run, scan_clauses


def _by_title(result: dict, title: str) -> dict:
    return next(r for r in result["results"] if r["title"] == title)


def _rule(key="x", severity="high", keywords=("topic",), red_flags=("bad wording",)) -> ClauseRule:
    return ClauseRule(
        key=key,
        label=f"{key.title()} Clause",
        keywords=list(keywords),
        red_flag_keywords=list(red_flags),
        safe_description="Safe version looks like this.",
        red_flag_description="Red-flag version looks like this.",
        severity=severity,
    )


def test_red_flag_language_is_flagged_unfair() -> None:
    text = "Section 4. Any annual increase in rent shall be at landlord's sole discretion."
    row = _by_title(run(text), "Rent Escalation Clause")

    assert row["rating"] == "unfair"  # rent_escalation is severity="high"
    assert row["delta"] is None
    assert "sole discretion" in row["explanation"]


def test_safe_version_of_a_present_clause_is_not_flagged() -> None:
    text = (
        "Section 4. Any annual increase in rent shall be capped at three percent (3%) "
        "per year and requires sixty (60) days written notice to the tenant."
    )
    row = _by_title(run(text), "Rent Escalation Clause")

    assert row["rating"] == "fair"
    assert row["delta"] is None


def test_topic_absent_from_document_is_unknown() -> None:
    text = "Section 4. Any annual increase in rent shall be capped at three percent (3%) per year."
    row = _by_title(run(text), "Security Deposit Clause")

    assert row["rating"] == "unknown"
    assert "never mentioned" in row["explanation"]


def test_empty_document_degrades_without_raising() -> None:
    for text in ("", "   \n\t "):
        result = run(text)
        assert result["results"] == []
        assert "nothing to review" in result["reply_text"]
        assert result["data_source"] == "clause-library-v1"


def test_every_lease_clause_gets_exactly_one_result_row() -> None:
    result = run("A lease with no recognisable clauses at all.")

    assert len(result["results"]) == len(LEASE_CLAUSES)
    assert {r["title"] for r in result["results"]} == {rule.label for rule in LEASE_CLAUSES}
    assert all(r["delta"] is None for r in result["results"])
    assert all(r["rating"] in ("fair", "borderline", "unfair", "unknown") for r in result["results"])


def test_severity_maps_to_rating_and_a_low_severity_flag_is_never_fair() -> None:
    rules = [_rule(key="hi", severity="high"), _rule(key="mid", severity="medium"), _rule(key="lo", severity="low")]
    result = scan_clauses("this document mentions topic with bad wording in it", rules)
    ratings = {r["title"]: r["rating"] for r in result["results"]}

    assert ratings == {"Hi Clause": "unfair", "Mid Clause": "borderline", "Lo Clause": "borderline"}


def test_results_are_ranked_worst_first_with_silence_above_safe_clauses() -> None:
    rules = [
        _rule(key="safe", severity="high", keywords=("safe topic",), red_flags=("never appears",)),
        _rule(key="silent_low", severity="low", keywords=("nowhere",)),
        _rule(key="silent_high", severity="high", keywords=("also nowhere",)),
        _rule(key="flagged_med", severity="medium", keywords=("med topic",)),
        _rule(key="flagged_high", severity="high", keywords=("high topic",)),
    ]
    text = "safe topic is fine here. med topic has bad wording. high topic has bad wording too."
    order = [(r["title"], r["rating"]) for r in scan_clauses(text, rules)["results"]]

    assert order == [
        ("Flagged_High Clause", "unfair"),
        ("Flagged_Med Clause", "borderline"),
        # Silence outranks a confirmed-safe clause; high-severity silence leads it.
        ("Silent_High Clause", "unknown"),
        ("Silent_Low Clause", "unknown"),
        ("Safe Clause", "fair"),
    ]


def test_reply_text_counts_flags_discussed_and_silent_topics() -> None:
    rules = [
        _rule(key="a", severity="high", keywords=("topic",)),
        _rule(key="b", severity="high", keywords=("topic",), red_flags=("never appears",)),
        _rule(key="c", severity="high", keywords=("absent",)),
    ]
    reply = scan_clauses("topic with bad wording", rules)["reply_text"]

    assert reply == "Found 1 red flag out of 2 clauses discussed; 1 topic not addressed at all."
