"""Repo-root fixtures shared by `tests/` and `evals/`.

`generated_corpus` renders the deterministic corpus generator's documents into
a temp directory. Test suites ingest *that*, never the repo's `corpus/` folder —
so users can drop their own documents into `corpus/` (the supported workflow)
without breaking a single test. Drift between the committed corpus files and
the generator is still guarded, by an explicit integrity test that checks only
the generator-owned filenames.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from requirements_audit.corpus import generator


@pytest.fixture(scope="session")
def generated_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("generated-corpus")
    for doc in generator.build_documents():
        (out / f"{doc.id}.md").write_text(generator.render_markdown(doc), encoding="utf-8")
    return out
