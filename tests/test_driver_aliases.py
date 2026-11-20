"""The product drivers live in ``inodefence.drivers``; the old ``scripts/`` paths still work.

Checks the move contract: the seven kept ``scripts/<name>.py`` aliases are the real module (same
object, so a monkeypatch through the old name patches the running code) and run the same command
(path run, ``-m`` run and the new module agree on the exit code); the other fifteen moved without
an alias; the package never imports ``scripts`` (no reverse dependency), ``locate`` or ``cli``;
the repository resolver and the launcher crossing point behave as before the move.
"""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.git_checkout import head_or_none

REPO = Path(__file__).resolve().parents[1]
DRIVERS = REPO / "src" / "inodefence" / "drivers"

#: old scripts module -> new module, for the aliases kept on purpose (see each alias's docstring)
ALIASES = {
    "run_target": "inodefence.drivers.run_target",
    "run_target_explore": "inodefence.drivers.run_target_explore",
    "run_target_replay": "inodefence.drivers.run_target_replay",
    "regression_check": "inodefence.drivers.regression_check",
    "node_tar_registry_prepare": "inodefence.drivers.node_tar.registry_prepare",
    "oras_go_registry_prepare": "inodefence.drivers.oras_go.registry_prepare",
    "python_tarfile_producer": "inodefence.drivers.python_tarfile.producer",
}
#: moved without an alias: nothing outside the package called them by the old path
MOVED_WITHOUT_ALIAS = {
    "explore_result": "inodefence.drivers.explore_result",
    "image_prepare": "inodefence.drivers.image_prepare",
    "npm_registry": "inodefence.drivers.npm_registry",
    "run_node_tar_target": "inodefence.drivers.node_tar.adapter",
    "node_tar_explore": "inodefence.drivers.node_tar.explore",
    "node_tar_replay": "inodefence.drivers.node_tar.replay",
    "node_tar_image": "inodefence.drivers.node_tar.image",
    "run_decompress_target": "inodefence.drivers.decompress.adapter",
    "decompress_explore": "inodefence.drivers.decompress.explore",
    "decompress_image": "inodefence.drivers.decompress.image",
    "decompress_registry_prepare": "inodefence.drivers.decompress.registry_prepare",
    "run_oras_go_target": "inodefence.drivers.oras_go.adapter",
    "oras_go_explore": "inodefence.drivers.oras_go.explore",
    "run_python_tarfile_target": "inodefence.drivers.python_tarfile.adapter",
    "python_tarfile_explore": "inodefence.drivers.python_tarfile.explore",
}
WITH_MAIN = [name for name in ALIASES if name != "python_tarfile_producer"]


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
    env.pop("INODEFENCE_PROG", None)
    return subprocess.run(
        [sys.executable, *argv], cwd=REPO, env=env, capture_output=True, text=True, timeout=120
    )


@pytest.mark.parametrize("old", sorted(ALIASES))
def test_alias_is_the_real_module(old: str) -> None:
    assert importlib.import_module(f"scripts.{old}") is importlib.import_module(ALIASES[old])


def test_from_scripts_import_gives_the_real_module() -> None:
    from scripts import regression_check, run_target

    from inodefence.drivers import regression_check as rc
    from inodefence.drivers import run_target as rt

    assert run_target is rt and regression_check is rc


def test_monkeypatch_through_the_old_name_patches_the_running_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inodefence.drivers import run_target

    monkeypatch.setattr("scripts.run_target.docker_problem", lambda: "patched via scripts")
    assert run_target.docker_problem() == "patched via scripts"


@pytest.mark.parametrize("old", WITH_MAIN)
@pytest.mark.parametrize("args", [("--help",), ("--no-such-option",)], ids=["help", "usage"])
def test_path_run_dash_m_and_new_module_agree(old: str, args: tuple[str, ...]) -> None:
    by_path = _run(f"scripts/{old}.py", *args)
    by_old_m = _run("-m", f"scripts.{old}", *args)
    by_new_m = _run("-m", ALIASES[old], *args)
    assert by_path.returncode == by_old_m.returncode == by_new_m.returncode
    # the old path and the old -m see the same program name, so the output is identical too
    assert by_path.stdout == by_old_m.stdout


def test_producer_alias_has_no_command_line_as_before() -> None:
    assert _run("scripts/python_tarfile_producer.py").returncode == 0


@pytest.mark.parametrize("old", sorted(MOVED_WITHOUT_ALIAS))
def test_moved_without_alias(old: str) -> None:
    assert not (REPO / "scripts" / f"{old}.py").exists()
    assert importlib.import_module(MOVED_WITHOUT_ALIAS[old]).__name__ == MOVED_WITHOUT_ALIAS[old]


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
    return found


def test_drivers_import_neither_scripts_nor_locate_nor_cli() -> None:
    offenders = {
        str(path.relative_to(REPO)): sorted(
            name
            for name in _imports(path)
            if name.split(".")[0] == "scripts" or name in ("inodefence.locate", "inodefence.cli")
        )
        for path in DRIVERS.rglob("*.py")
    }
    assert {path: names for path, names in offenders.items() if names} == {}


def test_repo_resolver_is_a_leaf() -> None:
    inodefence_imports = {
        name for name in _imports(DRIVERS / "repo.py") if name.split(".")[0] == "inodefence"
    }
    assert inodefence_imports <= {"inodefence.user_config"}


def _fake_clone(path: Path) -> Path:
    (path / "scripts").mkdir(parents=True)
    (path / "scripts" / "run_target.py").write_text("")
    (path / "tools").mkdir()
    return path


def _head() -> str | None:
    """HEAD, or None outside a git checkout: then the engine records no revision (None)."""
    return head_or_none()


def test_constants_are_the_checkout_the_scripts_drivers_used() -> None:
    from inodefence.drivers import repo, run_target

    # before the move: Path(scripts/run_target.py).parents[1], i.e. this checkout
    assert repo.code_checkout() == REPO == run_target.REPO_ROOT == repo.require_repository()
    assert repo.is_repo(REPO) and not repo.is_repo(REPO / "src")


def test_cli_clone_choice_is_home_then_the_installed_checkout_never_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from inodefence.drivers import repo

    other = _fake_clone(tmp_path / "other-clone")
    monkeypatch.setenv("INODEFENCE_HOME", str(other))
    assert repo.repo_root() == other
    monkeypatch.delenv("INODEFENCE_HOME")
    monkeypatch.setattr(repo, "configured_home", lambda: None)
    assert repo.repo_root() == REPO
    monkeypatch.setattr(repo, "_CHECKOUT", tmp_path / "site-packages")
    monkeypatch.chdir(other)
    assert repo.repo_root() is None  # as locate before the move: no cwd guess


def test_direct_run_uses_its_own_checkout_whatever_inodefence_home_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # (i) INODEFENCE_HOME = another clone B, this clone A's driver run directly: A, as at 430b802
    from inodefence.drivers import repo, run_target

    monkeypatch.setenv("INODEFENCE_HOME", str(_fake_clone(tmp_path / "other-clone")))
    monkeypatch.chdir(tmp_path / "other-clone")
    assert repo.require_repository() == REPO == run_target.REPO_ROOT
    assert run_target.engine_provenance(None).engine_sha == _head()


def test_driver_code_outside_a_clone_is_refused_even_with_a_clone_nearby(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # (ii) the running code is not in a clone: refused, never redirected to HOME or the cwd
    from inodefence.drivers import repo

    monkeypatch.setattr(repo, "_CHECKOUT", tmp_path / "site-packages")
    monkeypatch.setenv("INODEFENCE_HOME", str(REPO))
    monkeypatch.chdir(REPO)
    with pytest.raises(RuntimeError, match="not inside a clone"):
        repo.require_repository()


def test_refusal_is_a_setup_error_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from inodefence.drivers import repo, run_target, run_target_explore, run_target_replay

    monkeypatch.setattr(repo, "_CHECKOUT", tmp_path / "site-packages")
    argv = ["--target", "node-tar", "--version", "7.5.2", "--out", str(tmp_path / "out")]
    for main, args in (
        (run_target.main, argv),
        (run_target_explore.main, [*argv, "--auto-prepare", "--budget", "5"]),
        (run_target_replay.main, [str(tmp_path / "case")]),
    ):
        with pytest.raises(SystemExit) as stop:
            main(args)
        assert stop.value.code == 3
        assert "repository not found" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_cli_style_subprocess_runs_the_chosen_clone_consistently(tmp_path: Path) -> None:
    # (iii) what locate.run_driver does with INODEFENCE_HOME = B: PYTHONPATH = B/src:B, cwd = B.
    # Here B is this checkout; the subprocess's code, REPO_ROOT and recorded SHA are all B's.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
    env["INODEFENCE_HOME"] = str(REPO)
    probe = (
        "from inodefence.drivers import repo, run_target as r;"
        "print(repo.repo_root(), repo.require_repository(), r.REPO_ROOT,"
        " r.engine_provenance(None).engine_sha)"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    chosen, root, constant, sha = done.stdout.split()
    assert chosen == root == constant == str(REPO) and sha == str(_head())


def test_launcher_passes_the_hook_call_through_unchanged(tmp_path: Path) -> None:
    from inodefence.drivers.launcher import LAUNCHERS, launcher_path, run_launcher

    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(argv: list[str], **kwargs: object) -> str:
        calls.append((argv, kwargs))
        return "done"

    script = launcher_path("node-tar", tmp_path)
    assert script == tmp_path / "scripts" / "local_node_tar_smoke.sh"
    env = {"A": "1"}
    assert run_launcher(script, ["explore"], runner=runner, env=env, cwd="/x") == "done"
    assert run_launcher(script, runner=runner, env=env, check=False) == "done"
    assert calls == [
        (["bash", str(script), "explore"], {"env": env, "cwd": "/x"}),
        (["bash", str(script)], {"env": env, "check": False}),
    ]
    for name in LAUNCHERS.values():
        assert (REPO / "scripts" / name).is_file()


def test_hooks_use_the_launcher_crossing_point() -> None:
    from inodefence.drivers.decompress import explore as de
    from inodefence.drivers.node_tar import explore as ne
    from inodefence.drivers.node_tar import replay as nr
    from inodefence.drivers.oras_go import explore as oe
    from inodefence.drivers.python_tarfile import explore as pe

    scripts = REPO / "scripts"
    assert ne.SMOKE == nr.SMOKE == scripts / "local_node_tar_smoke.sh"
    assert de.SCRIPT == scripts / "local_decompress_selfdiscover.sh"
    assert oe.SCRIPT == scripts / "local_oras_go_selfdiscover.sh"
    assert pe.LAUNCHER == scripts / "local_python_tarfile_explore.sh"
    for module in (de, ne, nr, oe, pe):
        source = Path(module.__file__ or "").read_text()
        assert "run_launcher(" in source and '["bash"' not in source


def test_targets_registry_points_into_the_package() -> None:
    from inodefence.drivers import run_target

    assert run_target.TARGETS == {
        "node-tar": "inodefence.drivers.node_tar.adapter:ADAPTER",
        "python-tarfile": "inodefence.drivers.python_tarfile.adapter:ADAPTER",
        "oras-go": "inodefence.drivers.oras_go.adapter:ADAPTER",
        "decompress": "inodefence.drivers.decompress.adapter:ADAPTER",
    }
    for name, spec in run_target.TARGETS.items():
        module, _, attribute = spec.partition(":")
        assert run_target.load_adapter(name) is getattr(importlib.import_module(module), attribute)


# ---- a wheel-like install: the package alone, no clone (no experiments/, scripts/, tools/) ----

_WHEEL_PROBE = r"""
import importlib, json, pathlib, pkgutil, sys
import inodefence, inodefence.drivers
names = sorted(
    m.name for m in pkgutil.walk_packages(inodefence.drivers.__path__, "inodefence.drivers.")
)
for name in names + ["inodefence.cli"]:
    importlib.import_module(name)
from inodefence.drivers import repo, run_target
code = None
try:
    run_target.main(["--target", "node-tar", "--version", "7.5.2", "--out", "out"])
except SystemExit as stop:
    code = stop.code
package_tree = pathlib.Path(inodefence.__file__).resolve().parents[2]
print(json.dumps({
    "modules": len(names),
    "experiments": any(m == "experiments" or m.startswith("experiments.") for m in sys.modules),
    "scripts": any(m == "scripts" or m.startswith("scripts.") for m in sys.modules),
    "constant_is_code_tree": run_target.REPO_ROOT == package_tree,
    "main_exit": code,
}))
"""


def _wheel_like(tmp_path: Path, *, cwd: Path, home: Path | None = None) -> dict[str, object]:
    import json
    import shutil

    site = tmp_path / "site"
    if not site.exists():
        shutil.copytree(
            REPO / "src" / "inodefence",
            site / "inodefence",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "INODEFENCE"))}
    env["PYTHONPATH"] = str(site)
    env["HOME"] = str(tmp_path)  # no user config file
    if home is not None:
        env["INODEFENCE_HOME"] = str(home)
    done = subprocess.run(  # -S: no site-packages, so the editable install cannot leak in
        [sys.executable, "-S", "-c", _WHEEL_PROBE],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return {**json.loads(done.stdout.splitlines()[-1]), "stderr": done.stderr}


def test_wheel_like_install_imports_every_driver_without_a_clone(tmp_path: Path) -> None:
    probe = _wheel_like(tmp_path, cwd=tmp_path)
    assert int(str(probe["modules"])) >= 25
    assert probe["experiments"] is False and probe["scripts"] is False
    assert probe["constant_is_code_tree"] is True
    assert probe["main_exit"] == 3  # refused before any target work: no repository
    assert "repository not found" in str(probe["stderr"])


@pytest.mark.parametrize("via", ["cwd", "INODEFENCE_HOME"])
def test_wheel_like_code_never_runs_against_a_clone(tmp_path: Path, via: str) -> None:
    # A clone exists (this checkout, by cwd or INODEFENCE_HOME) but the running code is the
    # installed copy: refused, so code, assets and the recorded engine revision never mix trees.
    probe = _wheel_like(tmp_path, cwd=REPO, home=REPO if via == "INODEFENCE_HOME" else None)
    assert probe["main_exit"] == 3
    assert "not inside a clone" in str(probe["stderr"])


def test_python_tarfile_filters_mirror_the_repro_program() -> None:
    from experiments.repro import python_tarfile_identity as pti

    from inodefence.drivers.python_tarfile import adapter

    assert adapter.FILTERS == pti.FILTERS
    assert adapter.EXTRACTION_FILTER_OPTION.choices == pti.FILTERS


def test_lazy_repro_reference_patches_the_real_module(monkeypatch: pytest.MonkeyPatch) -> None:
    from experiments.repro import cross_release_identity

    from inodefence.drivers import regression_check

    original = cross_release_identity.run_one
    monkeypatch.setattr(regression_check.cri, "run_one", "patched")
    assert cross_release_identity.run_one == "patched"
    monkeypatch.undo()
    assert cross_release_identity.run_one is original
