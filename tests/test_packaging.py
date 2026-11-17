"""Packaging and installation: which clone runs, what the refusals say, what the wheel carries.

Measured on three clean Python 3.12 installs (editable, wheel only, wheel + INODEFENCE_HOME). These
tests pin the defects that measurement found, without building a wheel or touching Docker.
"""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

import pytest

from inodefence import locate
from inodefence.drivers import repo

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "inodefence"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch) -> None:
    """No developer config file or INODEFENCE_HOME leaks in."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("cfg")))
    monkeypatch.delenv("INODEFENCE_CONFIG", raising=False)
    monkeypatch.delenv("INODEFENCE_HOME", raising=False)


def _clone(path: Path) -> Path:
    (path / "scripts").mkdir(parents=True)
    (path / "scripts" / "run_target.py").write_text("", encoding="utf-8")
    (path / "tools").mkdir()
    return path


# ---- a relative INODEFENCE_HOME names the clone it says, not the installed code ----


@pytest.mark.parametrize("source", ["environment", "config"])
def test_a_relative_inodefence_home_is_made_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # Before: repo_root() returned Path("clone"); the CLI then ran the driver with cwd=clone and
    # PYTHONPATH=clone/src (relative), which from inside the clone points nowhere -- so an editable
    # install silently ran its own checkout's drivers (exit 0) and a wheel was refused.
    _clone(tmp_path / "clone")
    monkeypatch.chdir(tmp_path)
    if source == "environment":
        monkeypatch.setenv("INODEFENCE_HOME", "clone")
    else:
        config = tmp_path / "cfg" / "inodefence" / "config.env"
        config.parent.mkdir(parents=True)
        config.write_text("INODEFENCE_HOME=clone\n", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    root = repo.repo_root()
    assert root is not None and root == tmp_path / "clone" and root.is_absolute()
    env = locate._driver_env(root)
    assert env["PYTHONPATH"].split(":")[0] == str(tmp_path / "clone" / "src")


def test_an_absolute_inodefence_home_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    clone = _clone(tmp_path / "clone")
    monkeypatch.setenv("INODEFENCE_HOME", str(clone))
    assert repo.repo_root() == clone


# ---- "repository not found" says what is wrong with INODEFENCE_HOME when it is set ----


def test_not_found_without_inodefence_home_is_the_generic_message(monkeypatch) -> None:
    monkeypatch.setattr(repo, "configured_home", lambda: None)
    assert locate.repo_not_found_message() == locate.REPO_NOT_FOUND


@pytest.mark.parametrize(
    ("layout", "lacks"),
    [
        ("missing", "that folder does not exist"),
        ("empty", "it has no scripts/run_target.py and no tools/"),
        ("no-tools", "it has no tools/"),
    ],
)
def test_not_found_names_the_set_inodefence_home_and_what_it_lacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str, lacks: str
) -> None:
    home = tmp_path / "home"
    if layout != "missing":
        home.mkdir()
    if layout == "no-tools":
        (home / "scripts").mkdir()
        (home / "scripts" / "run_target.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("INODEFENCE_HOME", str(home))
    assert repo.repo_root() is None
    message = locate.repo_not_found_message()
    assert message.startswith(f"INODEFENCE_HOME (environment) is {str(home)!r} -> {home}")
    assert lacks in message
    assert "set INODEFENCE_HOME to the clone's root" in message and "unset it" in message


def test_not_found_says_when_inodefence_home_comes_from_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "cfg" / "inodefence" / "config.env"
    config.parent.mkdir(parents=True)
    config.write_text(f"INODEFENCE_HOME={tmp_path / 'nowhere'}\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert locate.repo_not_found_message().startswith("INODEFENCE_HOME (user config file) is ")


# ---- a driver run directly from an installed copy: advice that works ----


def test_direct_driver_refusal_does_not_advise_what_it_ignores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Before: "Run from the clone ... or set INODEFENCE_HOME", which this path never consults --
    # measured with both done (cwd = a clone, INODEFENCE_HOME = that clone): still refused.
    monkeypatch.setattr(repo, "_CHECKOUT", tmp_path / "site-packages")
    with pytest.raises(RuntimeError) as refused:
        repo.require_repository()
    message = str(refused.value)
    assert message.startswith("InodeFence repository not found for this driver: its code at ")
    assert "not inside a clone" in message
    assert "INODEFENCE_HOME and the working directory are not consulted here" in message
    assert "Run it as `inodefence verify / explore / replay`" in message
    assert "Run from the clone" not in message and "set INODEFENCE_HOME to" not in message


# ---- what the wheel carries: every package and every runtime data file ----


def _package_data() -> dict[str, list[str]]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["setuptools"]["package-data"]


def test_every_package_directory_is_a_package() -> None:
    # setuptools' find_packages drops a directory without __init__.py from the wheel, silently.
    missing = [
        path.relative_to(PACKAGE.parent).as_posix()
        for path in [PACKAGE, *PACKAGE.rglob("*")]
        if path.is_dir() and path.name != "__pycache__" and not (path / "__init__.py").is_file()
    ]
    assert missing == []


def test_every_non_python_file_the_code_ships_is_package_data() -> None:
    # Measured: the wheel holds every file under src/inodefence except the *.md notes. A new data
    # file (like the node-tar worker .cjs) must be declared, or a wheel install lacks it.
    declared = _package_data()
    undeclared = []
    for path in PACKAGE.rglob("*"):
        if not path.is_file() or path.suffix in {".py", ".md", ".pyc"}:
            continue
        package = ".".join(path.parent.relative_to(PACKAGE.parent).parts)
        if not any(fnmatch.fnmatch(path.name, p) for p in declared.get(package, [])):
            undeclared.append(path.relative_to(PACKAGE.parent).as_posix())
    assert undeclared == []


def test_project_metadata_contract() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == []  # the command runs on the standard library alone
    assert project["scripts"] == {"inodefence": "inodefence.cli:main"}
    # An SPDX expression (the TOML-table form is deprecated in setuptools; builds fail after
    # 2027-02-18), which needs setuptools >= 77.
    assert project["license"] == "MIT" and project["license-files"] == ["LICENSE"]
    assert config["build-system"]["requires"] == ["setuptools>=77"]
    assert (ROOT / "LICENSE").is_file()
