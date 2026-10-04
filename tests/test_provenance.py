"""Pre-execution configuration, distinct from observed execution evidence."""

from dataclasses import FrozenInstanceError, asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest

from inodefence.model import canonical_json
from inodefence.model.provenance import (
    EnvironmentProvenance,
    ExecutionProvenance,
    ExecutionSafety,
    SentinelProvenance,
    SourceProvenance,
    TargetProvenance,
)
from inodefence.provenance import capture_environment, capture_source, freeze_provenance
from inodefence.runtime import SentinelSpec
from inodefence.targets import PythonTarfileTarget


def test_freeze_preserves_configuration_and_deterministic_sentinels() -> None:
    target = PythonTarfileTarget(2.5)
    specs = (SentinelSpec("z", b"z", 0o640), SentinelSpec("a", b"a", 0o600))
    source = SourceProvenance("a" * 40, True)
    frozen = freeze_provenance(target.provenance, specs, source=source)
    assert frozen.source is source
    assert frozen.target == target.provenance
    assert frozen.target.timeout_seconds == 2.5
    assert frozen.sentinels == (
        SentinelProvenance("a", sha256(b"a").hexdigest(), 0o600),
        SentinelProvenance("z", sha256(b"z").hexdigest(), 0o640),
    )
    assert frozen == freeze_provenance(target.provenance, tuple(reversed(specs)), source=source)
    assert canonical_json(frozen) == canonical_json(
        freeze_provenance(target.provenance, specs, source=source)
    )
    for record in (frozen, frozen.source, frozen.environment, frozen.target, *frozen.sentinels):
        with pytest.raises(FrozenInstanceError):
            setattr(record, next(iter(asdict(record))), None)
        assert not hasattr(record, "__dict__")


@pytest.mark.parametrize("mode", (True, -1, 0o10000, 1.5, "600"))
def test_invalid_sentinel_modes_rejected(mode) -> None:
    with pytest.raises(ValueError):
        SentinelProvenance("sentinel", "a" * 64, mode)


@pytest.mark.parametrize("name,digest", (("../s", "a" * 64), (".", "a" * 64), ("s", "A" * 64)))
def test_invalid_sentinel_path_or_digest_rejected(name: str, digest: str) -> None:
    with pytest.raises(ValueError):
        SentinelProvenance(name, digest, 0o600)


@pytest.mark.parametrize("timeout", (True, "1", 0, -1, float("inf"), float("nan")))
def test_invalid_target_timeout_rejected(timeout) -> None:
    with pytest.raises(ValueError):
        TargetProvenance("target", "1.2.3", timeout)


def test_invalid_nested_types_and_sentinel_order_rejected() -> None:
    target = TargetProvenance("target", "1.2.3", None)
    frozen = freeze_provenance(target, (SentinelSpec(),), source=SourceProvenance())
    for changes in (
        {"source": "revision"},
        {"environment": {}},
        {"target": "target"},
        {"sentinels": list(frozen.sentinels)},
        {"sentinels": ()},
        {"sentinels": (*frozen.sentinels, *frozen.sentinels)},
    ):
        with pytest.raises(ValueError):
            replace(frozen, **changes)
    a, z = SentinelProvenance("a", "a" * 64, 0), SentinelProvenance("z", "a" * 64, 0)
    with pytest.raises(ValueError):
        replace(frozen, sentinels=(z, a))


def test_unavailable_source_is_explicit(tmp_path: Path) -> None:
    assert capture_source(tmp_path) == SourceProvenance(None, None)
    assert asdict(SourceProvenance()) == {"revision": None, "dirty": None}
    with pytest.raises(ValueError):
        SourceProvenance("main")
    with pytest.raises(ValueError):
        SourceProvenance(None, True)


def test_environment_is_stable_and_contains_only_documented_fields() -> None:
    assert capture_environment() == capture_environment()
    assert set(asdict(capture_environment())) == {"system", "release", "machine", "python_version"}
    with pytest.raises(ValueError):
        EnvironmentProvenance("Linux", 123, "x86_64", "3.12")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TargetProvenance("", "version", None)


def test_source_capture_reports_git_revision_and_dirty_state(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(("git", "init", str(tmp_path)), check=True, capture_output=True)
    (tmp_path / "input").write_text("baseline")
    subprocess.run(("git", "-C", str(tmp_path), "add", "input"), check=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ),
        check=True,
        capture_output=True,
    )
    source = capture_source(tmp_path)
    assert source.revision is not None and source.dirty is False
    (tmp_path / "input").write_text("changed")
    assert capture_source(tmp_path) == SourceProvenance(source.revision, True)


def test_execution_provenance_is_a_value_contract() -> None:
    value = ExecutionProvenance(
        SourceProvenance(),
        capture_environment(),
        TargetProvenance("target", "1.2.3", None),
        (SentinelProvenance("s", "a" * 64, 0o600),),
    )
    encoded = canonical_json(value)
    assert '"revision":null' in encoded
    assert "st_ino" not in encoded and "duration_seconds" not in encoded


def test_safety_requirement_defaults_to_isolation_and_requires_enum() -> None:
    target = TargetProvenance("target", "1.2.3", 1.0)
    assert target.execution_safety == ExecutionSafety.ISOLATION_REQUIRED
    assert '"execution_safety":"isolation_required"' in canonical_json(target)
    with pytest.raises(ValueError):
        replace(target, execution_safety="trusted_reference")
    assert PythonTarfileTarget().provenance.execution_safety == ExecutionSafety.TRUSTED_REFERENCE
