"""Tests for nl_housing.report (README key-findings block, D-033). Offline, tmp_path only."""

from __future__ import annotations

import pytest

from nl_housing import config, report

README = f"""# Title

intro

{report.START_MARKER}
old text
{report.END_MARKER}

## Next section
"""


def test_replace_block_only_touches_the_block():
    new = report.replace_block(README, "new text\nsecond line")
    assert new.startswith("# Title\n\nintro\n\n")
    assert new.endswith("\n\n## Next section\n")
    assert report.extract_block(new) == "new text\nsecond line"


def test_replace_block_is_idempotent():
    once = report.replace_block(README, "x")
    assert report.replace_block(once, "x") == once


@pytest.mark.parametrize(
    "text",
    [
        "no markers at all",
        f"{report.START_MARKER}\nonly a start",
        f"{report.START_MARKER}\na\n{report.END_MARKER}\n{report.START_MARKER}\nb\n{report.END_MARKER}",
        f"{report.END_MARKER}\nreversed\n{report.START_MARKER}",
    ],
)
def test_bad_markers_raise(text):
    with pytest.raises(ValueError):
        report.replace_block(text, "x")


def test_write_key_findings_writes_both_files_and_reports_change(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(README, encoding="utf-8")

    assert report.write_key_findings("generated\n", root=tmp_path) is True
    assert (tmp_path / "docs" / "KEY_FINDINGS.md").read_text(encoding="utf-8") == "generated\n"
    assert report.extract_block((tmp_path / "README.md").read_text(encoding="utf-8")) == "generated"

    # second run with the same text changes nothing
    assert report.write_key_findings("generated", root=tmp_path) is False


def test_committed_readme_block_matches_generated_file():
    """The README block must be exactly the notebook's output; edit the notebook, not the README."""
    readme = report.readme_path(config.REPO_ROOT).read_text(encoding="utf-8")
    generated = report.key_findings_path(config.REPO_ROOT).read_text(encoding="utf-8")
    assert report.extract_block(readme) == generated.strip("\n"), (
        "README key-findings block differs from docs/KEY_FINDINGS.md: re-run the notebook (make notebook)"
    )
