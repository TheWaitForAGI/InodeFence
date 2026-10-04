from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.builder import build_tar
from inodefence.evaluation.encoding import json_bytes, read_json
from inodefence.evaluation.gnu_packaging import (
    BASE,
    benign_profile_bytes,
    prepare_gnu_benign,
    validate_gnu_benign,
)
from inodefence.replay.benign import benign_replay_cases

REPOSITORY = Path(__file__).resolve().parents[2]


def test_exact_pins_and_fixed_builder_fixture_identities(tmp_path):
    directory = tmp_path / "context"
    manifest = prepare_gnu_benign(directory, repository=REPOSITORY)
    assert validate_gnu_benign(directory, repository=REPOSITORY) == manifest
    assert BASE in (directory / "Dockerfile").read_text()
    assert BASE in (REPOSITORY / "tools/container-helper/Dockerfile").read_text()
    profile = read_json(benign_profile_bytes())
    assert isinstance(profile, dict)
    assert profile["cases"] == [
        {"case_id": case.case_id, "archive_sha256": sha256(build_tar(case)).hexdigest()}
        for case in benign_replay_cases()
    ]
    assert (directory / "worker.py").read_bytes() == (
        REPOSITORY / "tools/benchmarks/gnu-tar/worker.py"
    ).read_bytes()
    with pytest.raises(FileExistsError):
        prepare_gnu_benign(directory, repository=REPOSITORY)


@pytest.mark.parametrize("name", ["worker.py", "profile.json", "Dockerfile"])
def test_rehashed_context_changes_cannot_replace_trusted_profile(tmp_path, name):
    directory = tmp_path / "context"
    manifest = prepare_gnu_benign(directory, repository=REPOSITORY)
    (directory / name).write_bytes(b"changed\n")
    manifest["files_sha256"][name] = sha256(b"changed\n").hexdigest()
    (directory / "packaging.json").write_bytes(json_bytes(manifest) + b"\n")
    with pytest.raises(ValueError, match="trusted fixed profile"):
        validate_gnu_benign(directory, repository=REPOSITORY)


def test_extra_files_or_missing_completion_are_not_valid_build_contexts(tmp_path):
    directory = tmp_path / "context"
    prepare_gnu_benign(directory, repository=REPOSITORY)
    extra = directory / "unrelated"
    extra.write_bytes(b"unit marker")
    with pytest.raises(ValueError, match="exact completed"):
        validate_gnu_benign(directory, repository=REPOSITORY)
    extra.unlink()
    (directory / "packaging.json").unlink()
    with pytest.raises(ValueError, match="exact completed"):
        validate_gnu_benign(directory, repository=REPOSITORY)
