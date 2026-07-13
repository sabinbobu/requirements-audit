"""Requirement-document parser (Markdown, and PDF via text extraction).

One parser handles every dialect we ingest, because they differ only in how a
requirement *opens*:

- **Generated corpus** — `### SYS-REQ-0101 — Title`, then body and `- Key: value`
  metadata bullets under H2 sections.
- **Real-world spec** — inline-bold identifiers at paragraph start
  (`**HL-FUN-001** The HLCM shall …`), numbered structural headings
  (`### 3.1 Low Beam`, treated as sections because `3.1 Low Beam` is not a
  requirement ID), preamble tables/prose (ignored), and often no
  `Document ID:` header (the ID then falls back to the filename).
- **PDF** — the same content after `pypdf` text extraction, which frequently
  drops heading markers; a bare `SYS-REQ-0101 — Title` line still opens a
  requirement.

A line opens a requirement iff its leading token (optionally wrapped in `**`)
matches the requirement-ID convention (`ABC-XYZ-001` style). Everything else is
document structure. That single rule is what keeps a realistic supplier spec
from being shredded into junk requirements.

ARXML is the remaining unsupported format; it plugs in behind the same
`RequirementDocument` return type.
"""

from __future__ import annotations

import re
from pathlib import Path

from requirements_audit.models import Requirement, RequirementDocument, RequirementStatus

# The requirement-ID convention: uppercase alnum segments joined by hyphens,
# at least one hyphen, ending in a numeric segment (SYS-REQ-0101, HL-FUN-001).
REQUIREMENT_ID = re.compile(r"^[A-Z][A-Z0-9]{0,9}(?:-[A-Z0-9]{1,10})*-\d{1,6}$")

# A requirement opener: an ID (optionally **bold**) at line start, then the rest
# of the line (a "— Title", a ": text", or body prose).
_REQ_OPENER = re.compile(r"^\*{0,2}([A-Z][A-Z0-9]{0,9}(?:-[A-Z0-9]{1,10})*-\d{1,6})\*{0,2}(.*)$")
# A leading title separator on the remainder: "— Title" / "- Title" / ": Title".
_TITLE_SEP = re.compile(r"^\s*(?:[—–]|-(?=\s)|:)\s*(.*)$")  # noqa: RUF001 - dash variants intended
# A metadata bullet: "- Status: active", "- Parameters: k = v", etc.
_META_KEYS = ("status", "superseded by", "references", "parameters")


def _open_requirement(line: str) -> tuple[str, str, str] | None:
    """If `line` opens a requirement, return (id, title, first_body); else None.

    `title` and `first_body` are mutually exclusive: a `— Title` remainder is a
    title (no body yet), any other remainder is body text (title defaults to the
    ID so the UI always has a label)."""
    m = _REQ_OPENER.match(line.strip())
    if m is None or not REQUIREMENT_ID.match(m.group(1)):
        return None
    req_id = m.group(1)
    rest = m.group(2).strip()
    if not rest:
        return req_id, "", ""
    sep = _TITLE_SEP.match(rest)
    if sep is not None:
        return req_id, sep.group(1).strip(), ""
    return req_id, "", rest


def parse_markdown(text: str, *, fallback_doc_id: str = "") -> RequirementDocument:
    lines = text.splitlines()
    title = ""
    doc_id = ""
    doc_type = ""
    section = ""

    # Preamble: title + Document ID/Type headers, up to the first section or
    # requirement (real-world specs may open with requirements and no sections).
    body_start = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        low = stripped.lower()
        if line.startswith("# "):
            title = line[2:].strip()
        elif low.startswith("document id:"):
            doc_id = stripped.split(":", 1)[1].strip()
        elif low.startswith("type:"):
            doc_type = stripped.split(":", 1)[1].strip()
        elif line.startswith("## ") or _open_requirement(stripped) is not None:
            body_start = idx
            break
    doc_id = doc_id or fallback_doc_id

    requirements: list[Requirement] = []
    block: list[str] | None = None  # lines of the requirement currently open

    def flush() -> None:
        nonlocal block
        if block:
            req = _parse_requirement_block(block, doc_id, section)
            if req is not None:
                requirements.append(req)
        block = None

    for line in lines[body_start:]:
        stripped = line.strip()
        if line.startswith("## "):
            flush()
            section = line[3:].strip()
        elif line.startswith("### "):
            heading = line[4:].strip()
            if _open_requirement(heading) is not None:
                flush()
                block = [heading]
            else:  # structural subsection, e.g. "### 3.1 Low Beam"
                flush()
                section = heading
        elif _open_requirement(stripped) is not None:
            flush()
            block = [stripped]
        elif block is not None and not stripped.startswith("|"):
            # Continuation of the open requirement (tables are not body text).
            block.append(line)
        # Anything else (preamble prose, tables, blanks) is structure noise.
    flush()

    return RequirementDocument(id=doc_id, title=title, doc_type=doc_type, requirements=requirements)


def _parse_requirement_block(block: list[str], doc_id: str, section: str) -> Requirement | None:
    opened = _open_requirement(block[0])
    if opened is None:
        return None
    req_id, title, first_body = opened

    text_lines: list[str] = [first_body] if first_body else []
    status = RequirementStatus.ACTIVE
    superseded_by: str | None = None
    refs: list[str] = []
    parameters: dict[str, str] = {}

    for line in block[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        key_body = stripped[2:] if stripped.startswith("- ") else stripped
        key = key_body.split(":", 1)[0].strip().lower()
        if key in _META_KEYS and ":" in key_body:
            value = key_body.split(":", 1)[1].strip()
            if key == "status":
                status = RequirementStatus(value)
            elif key == "superseded by":
                superseded_by = value
            elif key == "references":
                refs = [r.strip() for r in value.split(",") if r.strip()]
            else:  # parameters
                parameters = parse_parameters(value)
        else:
            text_lines.append(stripped)

    return Requirement(
        id=req_id,
        doc_id=doc_id,
        section=section,
        title=title or req_id,  # inline-bold dialect has no separate title
        text=" ".join(text_lines).strip(),
        category="",
        parameters=parameters,
        refs=refs,
        status=status,
        superseded_by=superseded_by,
    )


def parse_parameters(value: str) -> dict[str, str]:
    # Pairs are joined with ", " by the renderer; a value may itself contain a
    # bare comma (e.g. "10,50"), so split on ", " not ",".
    params: dict[str, str] = {}
    for pair in value.split(", "):
        key, sep, val = pair.partition(" = ")
        if sep:
            params[key.strip()] = val.strip()
    return params


def _doc_id_from_filename(path: Path) -> str:
    """Fallback document ID for files without a `Document ID:` header.

    The stem's leading token (up to the first `_`/space) is kept verbatim when
    it already looks like a document number ("SRS-HLCM-2026-004_headlights.md"
    → "SRS-HLCM-2026-004"); plain words are uppercased ("brake.pdf" → "BRAKE").
    """
    head = re.split(r"[_\s]", path.stem, maxsplit=1)[0]
    return head if "-" in head else head.upper()


def parse_file(path: Path) -> RequirementDocument:
    """Parse one document, dispatching on extension (.md / .pdf)."""
    if path.suffix.lower() == ".pdf":
        # Local import: pypdf stays off the import path of pure-Markdown runs.
        from requirements_audit.ingestion.pdf import parse_pdf

        return parse_pdf(path)
    return parse_markdown(
        path.read_text(encoding="utf-8"), fallback_doc_id=_doc_id_from_filename(path)
    )


def corpus_paths(corpus_dir: Path) -> list[Path]:
    """Every ingestible file in a directory, ordered by filename."""
    return sorted([*corpus_dir.glob("*.md"), *corpus_dir.glob("*.pdf")])


def parse_corpus(corpus_dir: Path) -> list[RequirementDocument]:
    """Parse every ``*.md`` and ``*.pdf`` file in a directory, ordered by filename."""
    return [parse_file(p) for p in corpus_paths(corpus_dir)]
