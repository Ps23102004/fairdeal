"""Module 4: freelance/consulting contract review.

Same scan as lease review against a different clause list — the algorithm and
its ranking rationale live in fairdeal/lease.py.
"""

from __future__ import annotations

from fairdeal.clauses import CONTRACT_CLAUSES
from fairdeal.lease import scan_clauses


def run(document_text: str) -> dict:
    """Review already-extracted contract text. `document_text` is a plain string
    (the caller does the PDF/OCR extraction), never raw PDF bytes."""
    return scan_clauses(document_text, CONTRACT_CLAUSES)
