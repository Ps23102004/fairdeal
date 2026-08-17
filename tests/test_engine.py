from __future__ import annotations

import pytest

from fairdeal.engine import Benchmark, Claim, DEFAULT_RULES, evaluate


def _benchmarks(value: float | str, name: str = "FMR, 1BR", source: str = "HUD FMR 2024") -> list[Benchmark]:
    return [Benchmark(source=source, name=name, value=value)]


def test_evaluate_fair_within_threshold() -> None:
    claim = Claim(kind="monthly_rent", value=2500.0)
    verdict = evaluate(claim, _benchmarks(2500.0), DEFAULT_RULES)
    assert verdict.rating == "fair"
    assert verdict.delta == pytest.approx(1.0)
    assert verdict.claim is claim
    assert len(verdict.benchmarks) == 1


def test_evaluate_fair_just_under_fair_max() -> None:
    # fair_max is 1.05; 1.04x stays fair.
    claim = Claim(kind="monthly_rent", value=2600.0)
    verdict = evaluate(claim, _benchmarks(2500.0), DEFAULT_RULES)
    assert verdict.rating == "fair"
    assert verdict.delta == pytest.approx(1.04)


def test_evaluate_borderline() -> None:
    claim = Claim(kind="monthly_rent", value=2800.0)
    verdict = evaluate(claim, _benchmarks(2500.0), DEFAULT_RULES)
    assert verdict.rating == "borderline"
    assert verdict.delta == pytest.approx(1.12)


def test_evaluate_unfair_above_borderline_max() -> None:
    claim = Claim(kind="monthly_rent", value=3750.0)
    verdict = evaluate(claim, _benchmarks(2500.0), DEFAULT_RULES)
    assert verdict.rating == "unfair"
    assert verdict.delta == pytest.approx(1.5)
    assert "unfair" in verdict.explanation


def test_evaluate_unknown_kind_has_no_rule() -> None:
    claim = Claim(kind="lease_term", value=12)
    verdict = evaluate(claim, _benchmarks(12), DEFAULT_RULES)
    assert verdict.rating == "unknown"
    assert verdict.delta is None
    assert "lease_term" in verdict.explanation


def test_evaluate_unknown_rule_missing_numeric_thresholds() -> None:
    rules = {"monthly_rent": {"fair_max": "high", "borderline_max": None}}
    verdict = evaluate(Claim(kind="monthly_rent", value=2500.0), _benchmarks(2500.0), rules)
    assert verdict.rating == "unknown"
    assert "missing a numeric" in verdict.explanation


def test_evaluate_unknown_claim_value_not_numeric() -> None:
    claim = Claim(kind="monthly_rent", value="$2,500/mo, negotiable")
    verdict = evaluate(claim, _benchmarks(2500.0), DEFAULT_RULES)
    assert verdict.rating == "unknown"
    assert verdict.delta is None
    assert "not numeric" in verdict.explanation


def test_evaluate_unknown_no_benchmarks_at_all() -> None:
    verdict = evaluate(Claim(kind="monthly_rent", value=2500.0), [], DEFAULT_RULES)
    assert verdict.rating == "unknown"
    assert "No numeric benchmark" in verdict.explanation


def test_evaluate_skips_negative_benchmark_like_zero() -> None:
    # A negative benchmark divides to a negative delta, which is <= fair_max
    # and would read as "fair". It's unusable, same as zero.
    verdict = evaluate(Claim(kind="monthly_rent", value=2600.0), _benchmarks(-2500.0), DEFAULT_RULES)
    assert verdict.rating == "unknown"
    assert verdict.delta is None
    assert "No numeric benchmark" in verdict.explanation


def test_evaluate_skips_unusable_benchmarks_before_dividing() -> None:
    benchmarks = [
        Benchmark(source="junk", name="unparseable", value="n/a"),
        Benchmark(source="junk", name="zero", value=0),
        Benchmark(source="HUD FMR 2024", name="FMR, 1BR", value=2500.0),
    ]
    verdict = evaluate(Claim(kind="monthly_rent", value=2600.0), benchmarks, DEFAULT_RULES)
    assert verdict.rating == "fair"
    assert verdict.delta == pytest.approx(1.04)
    assert verdict.benchmarks == benchmarks
