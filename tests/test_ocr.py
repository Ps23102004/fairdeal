from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fairdeal.ocr import OCRError, extract_text


def _mock_reader(page_texts: list[str]) -> MagicMock:
    reader = MagicMock()
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader.pages = pages
    return reader


def test_extract_text_joins_all_pages_text_layer_only() -> None:
    with patch("fairdeal.ocr.pypdf.PdfReader", return_value=_mock_reader(["Page one.", "Page two."])):
        text = extract_text(b"fake pdf bytes")

    assert text == "Page one.\n\nPage two."


def test_extract_text_falls_back_to_ocr_for_blank_pages() -> None:
    with (
        patch("fairdeal.ocr.pypdf.PdfReader", return_value=_mock_reader(["Real text.", "", "   "])),
        patch("fairdeal.ocr._ocr_pages", return_value={1: "OCR'd page two.", 2: "OCR'd page three."}) as mock_ocr,
    ):
        text = extract_text(b"fake pdf bytes")

    assert text == "Real text.\n\nOCR'd page two.\n\nOCR'd page three."
    mock_ocr.assert_called_once_with(b"fake pdf bytes", [1, 2])


def test_extract_text_no_pages_need_ocr_skips_ocr_call() -> None:
    with (
        patch("fairdeal.ocr.pypdf.PdfReader", return_value=_mock_reader(["All good."])),
        patch("fairdeal.ocr._ocr_pages") as mock_ocr,
    ):
        extract_text(b"fake pdf bytes")

    mock_ocr.assert_not_called()


def test_extract_text_unreadable_pdf_raises_ocr_error() -> None:
    with patch("fairdeal.ocr.pypdf.PdfReader", side_effect=Exception("not a PDF")):
        with pytest.raises(OCRError, match="could not read PDF"):
            extract_text(b"not actually a pdf")


def test_extract_text_ocr_failure_on_one_page_leaves_it_blank_not_raising() -> None:
    # _ocr_pages already swallows per-page OCR failures internally and just
    # omits that page index from its returned dict — confirm the caller
    # tolerates a partial/empty OCR result instead of crashing.
    with (
        patch("fairdeal.ocr.pypdf.PdfReader", return_value=_mock_reader(["Real text.", ""])),
        patch("fairdeal.ocr._ocr_pages", return_value={}),
    ):
        text = extract_text(b"fake pdf bytes")

    assert text == "Real text."


def test_ocr_pages_missing_toolchain_returns_empty_dict() -> None:
    from fairdeal.ocr import _ocr_pages

    with patch.dict("sys.modules", {"pytesseract": None, "pdf2image": None}):
        result = _ocr_pages(b"fake pdf bytes", [0])

    assert result == {}
