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


def test_repository_root_is_the_checkout_the_scripts_drivers_used() -> None:
    from inodefence.drivers import run_target
    from inodefence.drivers.repo import is_repo, repository_root

    # before the move: Path(scripts/run_target.py).parents[1], i.e. this checkout
    assert repository_root() == REPO == run_target.REPO_ROOT
    assert is_repo(REPO) and not is_repo(REPO / "src")


def test_repository_root_prefers_the_running_checkout_over_inodefence_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from inodefence.drivers import repo

    other = tmp_path / "other-clone"
    (other / "scripts").mkdir(parents=True)
    (other / "scripts" / "run_target.py").write_text("")
    (other / "tools").mkdir()
    monkeypatch.setenv("INODEFENCE_HOME", str(other))
    assert repo.repo_root() == other  # the CLI's view: INODEFENCE_HOME wins
    assert repo.repository_root() == REPO  # the drivers' view: the code's own checkout


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
