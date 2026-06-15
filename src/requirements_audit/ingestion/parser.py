"""Markdown requirement-document parser.

Parses the structured Markdown emitted by the corpus generator back into a typed
`RequirementDocument`. The format is: an H1 title with `Document ID:` / `Type:`
header lines, H2 sections, and one H3 per requirement followed by its body text
and `- Key: value` metadata bullets.

Other formats (ARXML, PDF) plug in behind the same `RequirementDocument` return
type; only Markdown is implemented for now since the corpus is Markdown.
"""

from __future__ import annotations

from pathlib import Path

from requirements_audit.models import Requirement, RequirementDocument, RequirementStatus

_HEADING_SEP = " — "  # "id — title"


def parse_markdown(text: str) -> RequirementDocument:
    lines = text.splitlines()
    title = ""
    doc_id = ""
    doc_type = ""
    section = ""

    # Header block.
    body_start = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("Document ID:"):
            doc_id = line.split(":", 1)[1].strip()
        elif line.startswith("Type:"):
            doc_type = line.split(":", 1)[1].strip()
        elif line.startswith("## "):
            body_start = idx
            break

    requirements: list[Requirement] = []
    current_block: list[str] = []

    def flush() -> None:
        if current_block:
            req = _parse_requirement_block(current_block, doc_id, section)
            if req is not None:
                requirements.append(req)
            current_block.clear()

    for line in lines[body_start:]:
        if line.startswith("## "):
            flush()
            section = line[3:].strip()
        elif line.startswith("### "):
            flush()
            current_block.append(line)
        elif current_block:
            current_block.append(line)
    flush()

    return RequirementDocument(id=doc_id, title=title, doc_type=doc_type, requirements=requirements)


def _parse_requirement_block(block: list[str], doc_id: str, section: str) -> Requirement | None:
    heading = block[0][4:].strip()  # strip "### "
    req_id, _, req_title = heading.partition(_HEADING_SEP)
    req_id = req_id.strip()
    req_title = req_title.strip()
    if not req_id:
        return None

    text_lines: list[str] = []
    status = RequirementStatus.ACTIVE
    superseded_by: str | None = None
    refs: list[str] = []
    parameters: dict[str, str] = {}

    for line in block[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            key, _, value = stripped[2:].partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "status":
                status = RequirementStatus(value)
            elif key == "superseded by":
                superseded_by = value
            elif key == "references":
                refs = [r.strip() for r in value.split(",") if r.strip()]
            elif key == "parameters":
                parameters = _parse_parameters(value)
        else:
            text_lines.append(stripped)

    return Requirement(
        id=req_id,
        doc_id=doc_id,
        section=section,
        title=req_title,
        text=" ".join(text_lines),
        category="",
        parameters=parameters,
        refs=refs,
        status=status,
        superseded_by=superseded_by,
    )


def _parse_parameters(value: str) -> dict[str, str]:
    # Pairs are joined with ", " by the renderer; a value may itself contain a
    # bare comma (e.g. "10,50"), so split on ", " not ",".
    params: dict[str, str] = {}
    for pair in value.split(", "):
        key, sep, val = pair.partition(" = ")
        if sep:
            params[key.strip()] = val.strip()
    return params


def parse_file(path: Path) -> RequirementDocument:
    return parse_markdown(path.read_text(encoding="utf-8"))


def parse_corpus(corpus_dir: Path) -> list[RequirementDocument]:
    """Parse every ``*.md`` file in a directory, ordered by filename."""
    return [parse_file(p) for p in sorted(corpus_dir.glob("*.md"))]
