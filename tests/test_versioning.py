#!/usr/bin/env python3
"""Tests for revision/version metadata helpers."""

import json
from pathlib import Path

from arod_common.versioning import build_revision_record, write_revision_manifest


def test_build_revision_record_contains_expected_keys() -> None:
    record = build_revision_record(extra={"tool": "unit-test"})
    for key in ["project", "version", "git_revision", "generated_utc", "python_version", "tool"]:
        assert key in record
    assert record["tool"] == "unit-test"


def test_write_revision_manifest(tmp_path: Path) -> None:
    output = tmp_path / "revision_manifest.json"
    record = write_revision_manifest(output, extra={"context": "pytest"})

    assert output.exists()
    on_disk = json.loads(output.read_text(encoding="utf-8"))
    assert on_disk["context"] == "pytest"
    assert on_disk["git_revision"] == record["git_revision"]
