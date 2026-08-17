"""Module 2: lease review — extracted document text in, worst-first clause verdicts out.

Takes ALREADY-EXTRACTED text (the caller runs fairdeal/ocr.py, not us), which
keeps this module independent of both the OCR toolchain and the LLM cascade —
lease review still answers when Ollama is down, unlike rent-check's chat parsing.

`scan_clauses` is shared with fairdeal/contract.py: same algorithm, different
clause list, so it lives here once rather than in two near-identical files.
"""

from __future__ import annotations

from fairdeal.clauses import LEASE_CLAUSES, ClauseRule

DATA_SOURCE = "clause-library-v1"

# A red-flagged clause is never "fair" — "fair" is reserved for "the topic IS
# addressed and reads like the safe version". So severity maps to how bad the
# flag is, not to whether it is one: high -> unfair, medium/low -> borderline.
# A low-severity flag is still worth negotiating, just not a dealbreaker, so it
# shares "borderline" with medium and is separated from it by the severity
# tie-break in _rank_key instead of by a third rating.
_FLAG_RATING = {"high": "unfair", "medium": "borderline", "low": "borderline"}

# Worst-first — the OPPOSITE of rentcheck's best-first ranking. The user opens
# this screen to find trouble, not to browse good news.
#
# "unknown" here means "the document never addresses this topic" — which is not
# the same as bad, but is not nothing either: a lease silent on liability or a
# contract silent on IP assignment leaves you with whatever the legal default
# is. So silence ranks ABOVE confirmed-safe clauses (you should still read it)
# but BELOW explicit red-flag language (silence is weaker evidence, and plenty
# of documents legitimately omit topics). Within every band, higher severity
# sorts first, which floats a silent HIGH-severity topic to the top of the
# silence band without letting it outrank a real red flag.
_RATING_ORDER = {"unfair": 0, "borderline": 1, "unknown": 2, "fair": 3}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _first_match(text: str, keywords: list[str]) -> str | None:
    return next((k for k in keywords or [] if k.lower() in text), None)


def _rank_key(scored: tuple[str, dict]) -> tuple[int, int]:
    severity, result = scored
    return (_RATING_ORDER.get(result["rating"], 2), _SEVERITY_ORDER.get(severity, 1))


def scan_clauses(document_text: str, rules: list[ClauseRule]) -> dict:
    """Scan document text for each rule's topic and red-flag language.

    Pure and total: no network, no exceptions for a "no data" outcome. `delta`
    is always None — this is a presence/absence comparison, not a numeric ratio,
    so engine.evaluate() (which divides a claim by a benchmark) does not apply.
    """
    text = (document_text or "").lower()
    if not text.strip():
        return {
            "reply_text": "No document text was provided, so there was nothing to review.",
            "data_source": DATA_SOURCE,
            "results": [],
        }

    scored: list[tuple[str, dict]] = []
    for rule in rules:
        topic_hit = _first_match(text, rule.keywords)
        flag_hit = _first_match(text, rule.red_flag_keywords) if topic_hit else None
        if topic_hit is None:
            rating = "unknown"
            explanation = (
                f"{rule.label} is never mentioned in this document. "
                f"Normally you'd expect: {rule.safe_description} "
                "Silence means you get whatever the default is."
            )
        elif flag_hit is not None:
            rating = _FLAG_RATING.get(rule.severity, "borderline")
            explanation = (
                f"Found {flag_hit!r} in the {rule.label.lower()} language — {rule.red_flag_description}"
            )
        else:
            rating = "fair"
            explanation = (
                f"{rule.label} is addressed ({topic_hit!r}) with no red-flag wording — "
                f"{rule.safe_description}"
            )
        scored.append((rule.severity, {"title": rule.label, "rating": rating, "delta": None, "explanation": explanation}))

    scored.sort(key=_rank_key)
    results = [result for _, result in scored]

    flags = sum(1 for r in results if r["rating"] in ("unfair", "borderline"))
    discussed = sum(1 for r in results if r["rating"] != "unknown")
    silent = len(results) - discussed
    reply_text = (
        f"Found {flags} red flag{'' if flags == 1 else 's'} out of "
        f"{discussed} clause{'' if discussed == 1 else 's'} discussed"
        + (f"; {silent} topic{'' if silent == 1 else 's'} not addressed at all." if silent else ".")
    )
    return {"reply_text": reply_text, "data_source": DATA_SOURCE, "results": results}


def run(document_text: str) -> dict:
    """Review already-extracted lease text. `document_text` is a plain string
    (the caller does the PDF/OCR extraction), never raw PDF bytes."""
    return scan_clauses(document_text, LEASE_CLAUSES)
