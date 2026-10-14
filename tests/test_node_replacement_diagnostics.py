"""Portable checks for independent diagnostic observation and comparison boundaries."""

import importlib.util
import os
from pathlib import Path

import pytest

DIAGNOSTICS = Path(__file__).resolve().parents[1] / "tools/node-tar/diagnostics"


def module(name):
    spec = importlib.util.spec_from_file_location(name, DIAGNOSTICS / f"{name}.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_independent_snapshot_preserves_link_identity_without_following_symlinks(tmp_path):
    probe = module("investigate")
    original = tmp_path / "original"
    original.write_bytes(b"first")
    os.link(original, tmp_path / "alias")
    os.symlink("missing", tmp_path / "dangling")
    before = probe.independent_snapshot(tmp_path)
    assert before["original"]["st_ino"] == before["alias"]["st_ino"]
    assert before["original"]["st_nlink"] == 2
    assert before["dangling"]["content_digest"] is None
    assert before["dangling"]["link_target"] == "missing"
    original.unlink()
    original.write_bytes(b"second")
    after = probe.independent_snapshot(tmp_path)
    assert after["alias"]["st_ino"] == before["alias"]["st_ino"]
    assert after["alias"]["content_digest"] == before["alias"]["content_digest"]
    assert after["original"]["st_ino"] != after["alias"]["st_ino"]


def test_semantic_comparison_retains_identity_relation_and_content(tmp_path):
    probe, analysis = module("investigate"), module("analyze")
    extract = tmp_path / "extract"
    extract.mkdir()
    (extract / "a").write_bytes(b"first")
    os.link(extract / "a", extract / "alias")
    before = analysis.semantic_state(probe.independent_snapshot(tmp_path))
    assert before["extract/a"]["identity_paths"] == ["extract/a", "extract/alias"]
    (extract / "a").unlink()
    (extract / "a").write_bytes(b"second")
    after = analysis.semantic_state(probe.independent_snapshot(tmp_path))
    assert before != after
    assert after["extract/a"]["identity_paths"] == ["extract/a"]


def test_evidence_publication_refuses_overwrite(tmp_path):
    probe = module("investigate")
    target = tmp_path / "raw.json"
    probe.publish(target, {"fact": 1})
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        probe.publish(target, {"fact": 2})
    assert target.read_bytes() == original
