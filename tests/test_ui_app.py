"""Streamlit script-execution test via streamlit's AppTest harness.

Skipped automatically where the optional `ui` dependency group is not installed
(CI installs only `dev`); locally, `make install` pulls streamlit and this runs.
Hermetic: the API base URL points at a closed port, so the script must render
its unreachable-API state without raising — rendering is all the UI owns.
"""

from __future__ import annotations

import pytest

st = pytest.importorskip("streamlit", reason="ui dependency group not installed")

from streamlit.testing.v1 import AppTest  # noqa: E402  (import needs the skip above)

_APP = "src/requirements_audit/ui/app.py"


def test_ui_script_runs_without_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port 9 (discard) is never serving: the sidebar must show the error state.
    monkeypatch.setenv("REQUIREMENTS_AUDIT_API", "http://127.0.0.1:9")

    at = AppTest.from_file(_APP, default_timeout=30)
    at.run()

    assert not at.exception  # rendering never raises, even with no API
    assert [tab.label for tab in at.tabs] == ["Ingest", "Query", "Audit"]
    assert at.sidebar.error  # the unreachable-API message is shown
