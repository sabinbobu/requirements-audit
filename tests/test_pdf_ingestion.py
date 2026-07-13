"""PDF ingestion tests.

The fixture is a real PDF, generated in-test (fpdf2, dev-only dependency) from a
synthetic corpus document's text — so the assertion is *parity*: parsing the PDF
recovers the same requirements the Markdown parser reads from the source file.
fpdf2's core fonts are latin-1 only, so the renderer swaps the em-dash for a
hyphen; the PDF heading regex accepts both, and text comparisons normalize it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fpdf import FPDF

from requirements_audit.ingestion.parser import parse_file, parse_markdown
from requirements_audit.ingestion.pdf import PdfParseError, parse_pdf
from requirements_audit.ingestion.pipeline import ingest_corpus
from requirements_audit.ingestion.store import SqliteStore

_ROOT = Path(__file__).resolve().parents[1]
_SYS_MD = _ROOT / "corpus" / "SYS.md"


def _pdf_from_text(lines: list[str], out: Path) -> None:
    """Render text lines to a real PDF the way a plain exporter would:
    Markdown heading markers stripped (PDFs lose them), latin-1 charset."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("helvetica", size=8)
    for line in lines:
        clean = line.removeprefix("### ").removeprefix("# ").replace("—", "-")
        if not clean.strip():
            continue  # blank lines carry no structure once headings are stripped
        # Keep "## " section markers: the parser recovers sections from them.
        pdf.multi_cell(
            w=0,
            h=4,
            text=clean.encode("latin-1", "replace").decode("latin-1"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.output(str(out))


@pytest.fixture
def sys_pdf(tmp_path: Path) -> Path:
    out = tmp_path / "SYS.pdf"
    _pdf_from_text(_SYS_MD.read_text(encoding="utf-8").splitlines(), out)
    return out


def test_pdf_parses_to_same_requirements_as_markdown(sys_pdf: Path) -> None:
    from_md = parse_markdown(_SYS_MD.read_text(encoding="utf-8"))
    from_pdf = parse_pdf(sys_pdf)

    assert from_pdf.id == from_md.id
    assert [r.id for r in from_pdf.requirements] == [r.id for r in from_md.requirements]
    for md_req, pdf_req in zip(from_md.requirements, from_pdf.requirements, strict=True):
        assert pdf_req.status == md_req.status
        assert pdf_req.refs == md_req.refs
        assert pdf_req.parameters == md_req.parameters
        assert pdf_req.section == md_req.section
        # Text survives modulo wrapping (rejoined with spaces) + the dash swap.
        assert pdf_req.text == md_req.text.replace("—", "-")


def test_parse_file_dispatches_on_extension(sys_pdf: Path) -> None:
    doc = parse_file(sys_pdf)
    assert doc.id == "SYS" and doc.requirements


def test_pdf_without_requirement_ids_fails_loudly(tmp_path: Path) -> None:
    out = tmp_path / "notes.pdf"
    _pdf_from_text(["Meeting notes", "We should probably fix the watchdog."], out)
    with pytest.raises(PdfParseError, match="no requirement IDs"):
        parse_pdf(out)


def test_pdf_doc_id_falls_back_to_filename(tmp_path: Path) -> None:
    out = tmp_path / "brake.pdf"
    _pdf_from_text(
        ["BRK-REQ-0001 - Pedal latency", "Engage within 50 ms.", "- Status: active"], out
    )
    doc = parse_pdf(out)
    assert doc.id == "BRAKE"  # filename stem, uppercased
    assert doc.requirements[0].id == "BRK-REQ-0001"


def test_ingest_mixes_markdown_and_pdf(tmp_path: Path, sys_pdf: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # One Markdown doc and one PDF doc with distinct IDs.
    (corpus / "COM.md").write_text((_ROOT / "corpus" / "COM.md").read_text(encoding="utf-8"))
    pdf_target = corpus / "BRAKE.pdf"
    _pdf_from_text(
        [
            "Brake Requirements",
            "Document ID: BRAKE",
            "Type: component",
            "## Timing",
            "BRAKE-REQ-0101 - Actuation latency",
            "The brake actuator shall engage within 50 ms.",
            "- Status: active",
            "- Parameters: brake_latency_ms = 50",
        ],
        pdf_target,
    )

    with SqliteStore(":memory:") as store:
        report = ingest_corpus(corpus, store)
        assert sorted(report.new_docs) == ["BRAKE", "COM"]
        brake = store.chunks_for_doc("BRAKE")
        assert len(brake) == 1
        assert brake[0].parameters == {"brake_latency_ms": "50"}
        assert brake[0].section_path[-1] == "Timing"

        # Idempotency holds for PDFs too (byte-level content hash).
        again = ingest_corpus(corpus, store)
        assert sorted(again.unchanged_docs) == ["BRAKE", "COM"]
