"""run_exp0 fixes from the HOST1 rehearsal (#347).

The dry-run checks --expected-images; --skip-build shows no warmup in the targets form; the
postflight records the checkout again and a revision change or a dirty tree is a problem;
a host run refuses an output or raw manifest that would land in the checkout un-ignored.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.run_exp0 as run_exp0

from inodefence.provenance import SourceProvenance
from test_run_exp0 import SHA, TARGET_IMAGES, _fake_runner
from test_run_exp0 import admit_fixture_holdout as admit_fixture_holdout
from test_run_exp0 import clean_engine as clean_engine
from test_two_host_split import _host_args, _setup

REPO = Path(run_exp0.__file__).resolve().parents[1]


def _host_out(out: Path, host: str = "HOST1") -> Path:
    return out.parent / f"{out.name}-{host}"


def _without(argv: list[str], flag: str) -> list[str]:
    index = argv.index(flag)
    return argv[:index] + argv[index + 2 :]


def _replace(argv: list[str], flag: str, value: str) -> list[str]:
    index = argv.index(flag)
    return [*argv[: index + 1], value, *argv[index + 2 :]]


# ---- 1. dry-run checks --expected-images ----------------------------------------------------


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_dry_run_passes_with_a_usable_expected_images_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    argv = [*_host_args(args, out, "HOST1", assignment, "2"), "--dry-run"]
    assert run_exp0.main(argv) == 0
    assert "  (nothing)" in capsys.readouterr().out


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
@pytest.mark.parametrize("damage", ["missing", "not-json", "wrong-id", "absent"])
def test_dry_run_refuses_an_unusable_or_absent_expected_images_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    damage: str,
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    argv = [*_host_args(args, out, "HOST1", assignment, "2"), "--dry-run"]
    path = Path(argv[argv.index("--expected-images") + 1])
    if damage == "missing":
        argv = _replace(argv, "--expected-images", str(tmp_path / "nope.json"))
    elif damage == "not-json":
        path.write_text("{", encoding="utf-8")
    elif damage == "wrong-id":
        data = json.loads(path.read_text(encoding="utf-8"))
        name = next(iter(data["expected_image_ids"]))
        data["expected_image_ids"][name] = ""
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        argv = _without(argv, "--expected-images")
    assert run_exp0.main(argv) == 2
    text = capsys.readouterr().out
    expected = "needs --expected-images" if damage == "absent" else "--expected-images unusable"
    assert "  - input: " in text and expected in text
    assert not (_host_out(out) / "matrix.json").exists()


# ---- 2. --skip-build shows no warmup in the targets form -------------------------------------


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
@pytest.mark.parametrize("skip", [True, False])
def test_the_dry_run_warmup_line_follows_skip_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], skip: bool
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    argv = [a for a in _host_args(args, out, "HOST1", assignment, "2") if a != "--skip-build"]
    argv = [*argv, "--dry-run", *(["--skip-build"] if skip else [])]
    assert run_exp0.main(argv) == 0
    text = capsys.readouterr().out
    assert ("warmup: skipped (--skip-build)" in text) is skip
    assert ("warmup: BUILD_ONLY=1" in text) is not skip


# ---- 3. the postflight records the checkout again --------------------------------------------


@pytest.mark.parametrize(
    ("now", "problem"),
    [
        (SourceProvenance(SHA, False), None),
        (SourceProvenance("f" * 40, False), "execution revision changed during the run"),
        (SourceProvenance(SHA, True), "the source checkout is dirty after the run"),
        (SourceProvenance(), "execution_sha unavailable after the run"),
    ],
)
def test_source_postflight(now: SourceProvenance, problem: str | None) -> None:
    record, problems = run_exp0.source_postflight({"revision": SHA, "dirty": False}, now)
    assert record == {"revision": now.revision, "dirty": now.dirty}
    if problem is None:
        assert problems == []
    else:
        assert any(problem in item for item in problems)


def _postflight(out: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((out / run_exp0.HOST_RECORD_DIR).glob("postflight-*.json"))
    ]


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
@pytest.mark.parametrize(
    ("later", "problem"),
    [
        (None, None),
        (SourceProvenance("e" * 40, False), "execution revision changed during the run"),
        (SourceProvenance(SHA, True), "the source checkout is dirty after the run"),
    ],
)
def test_a_change_of_the_checkout_during_the_run_is_a_postflight_problem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    later: SourceProvenance | None,
    problem: str | None,
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    calls: list[int] = []

    def capture() -> SourceProvenance:
        calls.append(1)
        if later is not None and len(calls) > 1:
            return later
        return SourceProvenance(SHA, False)

    monkeypatch.setattr(run_exp0, "capture_source", capture)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    run_exp0.main(_host_args(args, out, "HOST1", assignment, "2"))
    (after,) = _postflight(_host_out(out))
    assert len(calls) == 2  # once at the start, once in the postflight
    assert "execution_sha" in after
    if problem is None:
        assert after["problems"] == []
        assert after["execution_sha"] == {"revision": SHA, "dirty": False}
    else:
        assert any(problem in item for item in after["problems"])


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
def test_a_call_with_nothing_pending_writes_no_host_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", _fake_runner(TARGET_IMAGES))
    argv = _host_args(args, out, "HOST1", assignment, "2")
    run_exp0.main(argv)
    host_dir = _host_out(out) / run_exp0.HOST_RECORD_DIR
    before = sorted(path.name for path in host_dir.iterdir())
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    run_exp0.main(argv)
    assert runner.calls == []  # type: ignore[attr-defined]
    assert sorted(path.name for path in host_dir.iterdir()) == before


# ---- 4. a host run does not write into the checkout ------------------------------------------


def test_worktree_write_problems_names_only_unignored_paths_inside(tmp_path: Path) -> None:
    problems = run_exp0.worktree_write_problems(
        {
            "outside": tmp_path / "out",
            "ignored": REPO / "experiments" / "raw" / "x",
            "inside": REPO / "experiments" / "summaries" / "raw-manifest-x.sha256",
        },
        REPO,
    )
    assert len(problems) == 1 and problems[0].startswith("inside ")


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
@pytest.mark.parametrize("which", ["--output", "--manifest-out", "default manifest"])
@pytest.mark.parametrize("mode", ["dry-run", "live"])
def test_a_host_run_refuses_writes_into_the_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    which: str,
    mode: str,
) -> None:
    out, args, assignment = _setup(tmp_path, monkeypatch)
    argv = _host_args(args, out, "HOST1", assignment, "2")
    inside = REPO / "experiments" / "summaries" / "w1-347-never-written"
    if which == "--output":
        argv = _replace(argv, "--output", str(inside))
    elif which == "--manifest-out":
        argv = _replace(argv, "--manifest-out", str(inside / "m.sha256"))
    else:
        argv = _without(argv, "--manifest-out")
        monkeypatch.chdir(REPO)
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    if mode == "dry-run":
        argv.append("--dry-run")
    assert run_exp0.main(argv) == 2
    captured = capsys.readouterr()
    assert "inside the checkout and not ignored" in captured.out + captured.err
    assert runner.calls == []  # type: ignore[attr-defined]
    assert not inside.exists()


@pytest.mark.usefixtures("clean_engine", "admit_fixture_holdout")
@pytest.mark.parametrize("mode", ["dry-run", "live"])
def test_a_single_host_targets_run_also_refuses_writes_into_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    """The stop/resume smoke runs the targets form without --host-id; it is guarded too."""
    from test_run_exp0 import BEFORE, _deadline_setup

    _out, args, _ = _deadline_setup(tmp_path, monkeypatch, BEFORE)
    assert "--host-id" not in args
    inside = REPO / "experiments" / "summaries" / "w1-347-never-written"
    argv = _replace(args, "--output", str(inside))
    runner = _fake_runner(TARGET_IMAGES)
    monkeypatch.setattr(run_exp0, "run_cell_with_watchdog", runner)
    if mode == "dry-run":
        argv.append("--dry-run")
    assert run_exp0.main(argv) == 2
    captured = capsys.readouterr()
    assert "inside the checkout and not ignored" in captured.out + captured.err
    assert runner.calls == []  # type: ignore[attr-defined]
    assert not inside.exists()
