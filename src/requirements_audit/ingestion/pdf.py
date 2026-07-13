"""PDF requirement-document parser (text-based PDFs only).

Extraction (`pypdf`) turns pages into text lines; the shared Markdown parser
then recovers requirements from them by convention (requirement IDs at line
start, `- Key: value` metadata). Delegating to one parser means every dialect —
generated corpus, inline-bold real-world specs, marker-stripped PDF exports —
goes through the same battle-tested logic.

Failure is loud, never silent: a PDF with no extractable text (scanned/image)
or no recognizable requirement IDs raises `PdfParseError` with the reason — an
empty document would silently weaken every downstream number. Quality depends
on the exporter: text PDFs from Word/LaTeX/pandoc work well; scanned images
(OCR territory) and heavy multi-column layouts do not.

ARXML remains the outstanding format; it plugs in behind the same
`RequirementDocument` return type.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from requirements_audit.ingestion.parser import _doc_id_from_filename, parse_markdown
from requirements_audit.models import RequirementDocument


class PdfParseError(ValueError):
    """A PDF that cannot honestly be turned into requirements."""


def _extract_text(path: Path) -> str:
    """Non-empty text lines across all pages, rejoined for the Markdown parser."""
    reader = PdfReader(str(path))
    lines: list[str] = []
    for page in reader.pages:
        lines.extend(line.rstrip() for line in (page.extract_text() or "").splitlines())
    return "\n".join(line for line in lines if line.strip())


def parse_pdf(path: Path) -> RequirementDocument:
    text = _extract_text(path)
    if not text:
        raise PdfParseError(
            f"{path.name}: no extractable text — scanned/image PDFs need OCR, which is out of scope."
        )

    doc = parse_markdown(text, fallback_doc_id=_doc_id_from_filename(path))
    if not doc.requirements:
        raise PdfParseError(
            f"{path.name}: no requirement IDs recognized — the pipeline keys on "
            "`XXX-REQ-0000` style identifiers at the start of a line."
        )
    # Mark the source format when the document carried no explicit `Type:`.
    if not doc.doc_type:
        doc.doc_type = "pdf"
    return doc
