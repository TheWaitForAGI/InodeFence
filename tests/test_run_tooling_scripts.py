"""make_run_criteria and fill_run_registration (#347): the run inputs made just before a run."""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from scripts import fill_run_registration as fill
from scripts import launcher_guards as guards
from scripts import make_run_criteria as criteria
from scripts import qualify_host

REPO = Path(criteria.__file__).resolve().parents[1]
SHA = "a" * 40
IDS = {
    "inodefence-node-tar-effect:7.5.2": "sha256:" + "1" * 64,
    "inodefence-controller:local": "sha256:" + "2" * 64,
    "inodefence-helper:local": "sha256:" + "3" * 64,
}


def _docker(*call: str) -> str:
    if call[:2] == ("image", "inspect"):
        return IDS[call[2]]
    assert call[:1] == ("version",), call  # nothing else: no pull, no build
    return "29.8.0"


def _build(**override: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "tree": REPO,
        "execution_sha": SHA,
        "host": "HOST1",
        "other_engines": {"HOST2": "29.9.3"},
        "docker": _docker,
        "state": lambda tree: (SHA, True),
        **override,
    }
    return criteria.build_criteria(**options)


# ---- make_run_criteria ----------------------------------------------------------------------


def test_the_criteria_file_passes_the_qualify_host_checks(tmp_path: Path) -> None:
    built = _build()
    path = tmp_path / "criteria.json"
    digest = criteria.write_once(path, built)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = qualify_host.load_criteria(path, digest)
    assert set(loaded) == qualify_host.CRITERIA_KEYS
    assert loaded["expected_image_ids"] == IDS
    assert loaded["expected_docker_engine"] == {"HOST1": "29.8.0", "HOST2": "29.9.3"}
    assert loaded["expected_execution_sha"] == SHA
    assert loaded["expected_shared_path_sha256"] == guards.shared_path_sha256(REPO)
    assert len(loaded["expected_shared_path_sha256"]) == len(guards.SHARED_PATH_FILES)
    assert {key: loaded[key] for key in criteria.THRESHOLDS} == dict(criteria.THRESHOLDS)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"state": lambda tree: ("b" * 40, True)}, "!= --execution-sha"),
        ({"state": lambda tree: (SHA, False)}, "not clean"),
        ({"thresholds": {**criteria.THRESHOLDS, "max_cell_seconds": 3600}}, "differ from"),
        ({"host": "HOST3"}, "hosts must be"),
        ({"other_engines": {"HOST1": "29.8.0"}}, "hosts must be"),
    ],
)
def test_make_criteria_refuses(override: dict[str, Any], message: str) -> None:
    with pytest.raises(criteria.CriteriaError, match=message):
        _build(**override)


def test_make_criteria_refuses_a_design_file_with_other_thresholds(tmp_path: Path) -> None:
    design = tmp_path / criteria.DESIGN_FILE
    design.parent.mkdir(parents=True)
    text = (REPO / criteria.DESIGN_FILE).read_text(encoding="utf-8")
    design.write_text(text.replace("7200 s", "3600 s"), encoding="utf-8")
    with pytest.raises(criteria.CriteriaError, match="no longer states"):
        _build(tree=tmp_path)


def test_a_bad_image_id_is_refused_by_the_qualify_host_check() -> None:
    def docker(*call: str) -> str:
        return "sha256:short" if call[:2] == ("image", "inspect") else "29.8.0"

    with pytest.raises(criteria.CriteriaError, match="would be refused by qualify_host"):
        _build(docker=docker)


def test_an_existing_file_is_kept_when_equal_and_refused_when_different(tmp_path: Path) -> None:
    path = tmp_path / "criteria.json"
    built = _build()
    first = criteria.write_once(path, built)
    assert criteria.write_once(path, built) == first
    with pytest.raises(criteria.CriteriaError, match="not overwritten"):
        criteria.write_once(path, {**built, "expected_execution_sha": "c" * 40})
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first


def test_make_criteria_main_refuses_a_tree_at_another_sha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "criteria.json"
    argv = ["--tree", str(REPO), "--execution-sha", "0" * 40, "--host", "HOST1", "--out", str(out)]
    assert criteria.main(argv) == 2
    assert "criteria not written" in capsys.readouterr().err
    assert not out.exists()


# ---- fill_run_registration ------------------------------------------------------------------

QUAL = REPO / "experiments" / "configs" / "host-qualification-v1-run.md"
VALUES = {
    "engine_sha": SHA,
    "exposure_ledger_sha256": "b" * 64,
    "execution_deadline": "2026-11-20T12:00:00+09:00",
    "host.HOST1.docker_engine": "29.8.0",
    "host.HOST2.docker_engine": "29.9.3",
}


def test_fill_writes_a_copy_outside_the_worktree(tmp_path: Path) -> None:
    out = tmp_path / "filled.md"
    source_sha, copy_sha = fill.write_copy(QUAL, out, VALUES)
    assert source_sha == hashlib.sha256(QUAL.read_bytes()).hexdigest()
    assert copy_sha == hashlib.sha256(out.read_bytes()).hexdigest()
    text = out.read_text(encoding="utf-8")
    block = text.split(fill.FENCE_OPEN, 1)[1].split("\n```", 1)[0]
    keys = [line for line in block.splitlines() if not line.lstrip().startswith("#")]
    assert not any(fill.TOKEN in line for line in keys)
    for key, value in VALUES.items():
        assert f"\n{key} = {value}\n" in block
    # Only the given lines change.
    original = QUAL.read_text(encoding="utf-8").splitlines()
    changed = [a for a, b in zip(original, text.splitlines(), strict=True) if a != b]
    assert len(changed) == len(VALUES)
    # The same values again leave the file; other values are refused.
    assert fill.write_copy(QUAL, out, VALUES)[1] == copy_sha
    with pytest.raises(fill.FillError, match="not overwritten"):
        fill.write_copy(QUAL, out, {**VALUES, "execution_deadline": "2026-11-21T12:00:00+09:00"})


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({k: v for k, v in VALUES.items() if k != "engine_sha"}, "TBD-FREEZE left"),
        ({**VALUES, "budget": "1"}, "has no 'budget = TBD-FREEZE' line"),
        ({**VALUES, "engine_sha": "TBD-FREEZE"}, "unusable value"),
        ({**VALUES, "engine_sha": ""}, "unusable value"),
    ],
)
def test_fill_refuses(tmp_path: Path, values: dict[str, str], message: str) -> None:
    out = tmp_path / "filled.md"
    with pytest.raises(fill.FillError, match=message):
        fill.write_copy(QUAL, out, values)
    assert not out.exists()


def test_fill_refuses_a_copy_inside_the_worktree(capsys: pytest.CaptureFixture[str]) -> None:
    out = REPO / "experiments" / "configs" / "w1-347-never-written.md"
    argv = [str(QUAL), *[f"--set={k}={v}" for k, v in VALUES.items()], "--out", str(out)]
    assert fill.main(argv) == 2
    assert "inside the worktree" in capsys.readouterr().err
    assert not out.exists()


def test_fill_main_prints_both_hashes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "filled.md"
    argv = [str(QUAL), *[f"--set={k}={v}" for k, v in VALUES.items()], "--out", str(out)]
    assert fill.main(argv) == 0
    text = capsys.readouterr().out
    assert hashlib.sha256(QUAL.read_bytes()).hexdigest() in text
    assert hashlib.sha256(out.read_bytes()).hexdigest() in text
