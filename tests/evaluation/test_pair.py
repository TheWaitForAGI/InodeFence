"""Pair/storage contracts tested on benign core evidence, not benchmark wins."""

from dataclasses import replace
from hashlib import sha256

import pytest

from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.pair import PairArm, compare_pair, export_pair, read_pair
from inodefence.evaluation.verify import VerificationError
from inodefence.pipeline import run_case
from inodefence.provenance import freeze_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets.python_tarfile import PythonTarfileTarget


@pytest.fixture
def pair(campaign):
    a = PairArm(campaign.provenance, campaign.steps[0].result)
    target = PythonTarfileTarget(timeout_seconds=5.0)
    b = PairArm(
        freeze_provenance(target.provenance, (SentinelSpec(),)), run_case(a.result.case, target)
    )
    return compare_pair(a.result.case, a, b)


def test_pair_preserves_every_raw_field_and_distinct_provenance(pair, tmp_path):
    assert pair.a.provenance != pair.b.provenance
    assert pair.a.result.before.sandbox_root != pair.b.result.before.sandbox_root
    path = tmp_path / "pair.json"
    digest = export_pair(pair, path)
    assert digest == sha256(path.read_bytes()).hexdigest()
    assert read_pair(path, expected_sha256=digest) == pair
    assert pair.a.result.case.case_id == pair.b.result.case.case_id == pair.case_id
    assert pair.a.result.archive_sha256 == pair.b.result.archive_sha256 == pair.archive_sha256


def test_mismatched_input_or_target_binding_is_rejected(pair, campaign):
    with pytest.raises(ValueError, match="requested ArchiveCase"):
        compare_pair(campaign.steps[1].result.case, pair.a, pair.b)
    with pytest.raises(ValueError, match="pair logical"):
        replace(pair, case_id="0" * 64)
    with pytest.raises(ValueError, match="frozen provenance"):
        PairArm(pair.a.provenance, pair.b.result)
    with pytest.raises(ValueError, match="TAR checksum"):
        PairArm(pair.a.provenance, replace(pair.a.result, archive_sha256="0" * 64))


def test_tampered_pair_fails_even_after_payload_rehash(pair, tmp_path):
    path = tmp_path / "pair.json"
    export_pair(pair, path)
    record = read_json(path.read_bytes())
    assert isinstance(record, dict)
    record["payload"]["value"]["b"]["result"]["archive_sha256"] = "0" * 64
    record["payload_sha256"] = sha256(json_bytes(record["payload"])).hexdigest()
    path.write_bytes(json_bytes(record) + b"\n")
    with pytest.raises(VerificationError):
        read_pair(path)


def test_existing_evidence_is_never_overwritten(pair, tmp_path):
    path = tmp_path / "pair.json"
    original = b"previous evidence"
    path.write_bytes(original)
    with pytest.raises(FileExistsError):
        export_pair(pair, path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_publication_failure_leaves_no_partial_final_record(pair, tmp_path, monkeypatch, operation):
    def fail(*args, **kwargs):
        raise OSError("controlled publication failure")

    monkeypatch.setattr(f"inodefence.evaluation.storage.os.{operation}", fail)
    path = tmp_path / "pair.json"
    with pytest.raises(OSError, match="controlled"):
        export_pair(pair, path)
    assert list(tmp_path.iterdir()) == []


def test_post_publication_sync_failure_leaves_complete_record(pair, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("controlled parent sync failure")

    monkeypatch.setattr("inodefence.evaluation.storage.sync_directory", fail)
    path = tmp_path / "pair.json"
    with pytest.raises(OSError, match="parent sync"):
        export_pair(pair, path)
    assert read_pair(path) == pair
    assert list(tmp_path.iterdir()) == [path]
