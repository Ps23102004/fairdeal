from __future__ import annotations

import io

import pypdf


class OCRError(Exception):
    pass


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF: the embedded text layer first, tesseract OCR
    (via pdf2image -> PIL -> pytesseract) as a per-page fallback when a page's
    text layer is empty or near-empty (i.e. a scanned page with no selectable
    text). Deterministic and free, unlike routing every page through a vision
    model — see fairdeal/README.md's OCR approach note.

    Raises OCRError if the PDF can't be read at all. A page that fails BOTH
    text extraction and OCR contributes an empty string rather than raising —
    partial extraction is more useful to the caller than an all-or-nothing failure.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:  # noqa: BLE001 - pypdf raises several distinct exception types
        raise OCRError(f"could not read PDF: {exc}") from exc

    pages: list[str] = []
    ocr_needed_pages: list[int] = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
        else:
            pages.append("")
            ocr_needed_pages.append(i)

    if ocr_needed_pages:
        ocr_text_by_page = _ocr_pages(pdf_bytes, ocr_needed_pages)
        for i, text in ocr_text_by_page.items():
            pages[i] = text

    return "\n\n".join(p for p in pages if p)


def _ocr_pages(pdf_bytes: bytes, page_indices: list[int]) -> dict[int, str]:
    """Render specific 0-indexed pages to images and OCR them. Returns an
    empty dict (not a raise) if the OCR toolchain (poppler/tesseract) isn't
    installed — those pages just stay blank rather than failing the whole
    extraction, since the text-layer pages already succeeded."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        return {}

    results: dict[int, str] = {}
    for i in page_indices:
        try:
            images = convert_from_bytes(pdf_bytes, first_page=i + 1, last_page=i + 1)
            if images:
                results[i] = pytesseract.image_to_string(images[0]).strip()
        except Exception:  # noqa: BLE001 - a missing poppler/tesseract binary, a corrupt page, etc.
            continue
    return results
