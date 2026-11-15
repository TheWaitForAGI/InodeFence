"""User config: environment over file, user keys only, research/runtime keys refused."""

from pathlib import Path

import pytest

from inodefence import locate
from inodefence.user_config import (
    UserConfigError,
    config_path,
    load_user_config,
    parse_config_text,
)


def test_config_path_precedence(tmp_path: Path) -> None:
    assert config_path({"INODEFENCE_CONFIG": str(tmp_path / "x.env")}) == tmp_path / "x.env"
    assert config_path({"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "inodefence/config.env"
    assert config_path({}) == Path.home() / ".config/inodefence/config.env"


def test_parse_accepts_user_keys_comments_quotes_and_export() -> None:
    text = '# c\n\nexport INODEFENCE_HOME="/src/if"\nINODEFENCE_OUTPUT_DIR=/data/if\n'
    assert parse_config_text(text, "f") == {
        "INODEFENCE_HOME": "/src/if",
        "INODEFENCE_OUTPUT_DIR": "/data/if",
    }


@pytest.mark.parametrize(
    "line",
    ["INODEFENCE_RUNTIME_ROOT=/tmp/x", "INODEFENCE_DOCKER_CONTEXT=remote", "BUDGET=10", "noequals"],
)
def test_parse_refuses_runtime_research_and_malformed_lines(line: str) -> None:
    with pytest.raises(UserConfigError):
        parse_config_text(line + "\n", "f")


def test_environment_wins_over_file_and_loading_leaves_environ_alone(tmp_path: Path) -> None:
    config = tmp_path / "c.env"
    config.write_text("INODEFENCE_OUTPUT_DIR=/from/file\nINODEFENCE_HOME=/h\n", encoding="utf-8")
    env = {"INODEFENCE_CONFIG": str(config), "INODEFENCE_OUTPUT_DIR": "/from/env"}
    loaded = load_user_config(env)
    assert loaded.config_found
    assert loaded.output_base.value == "/from/env"
    assert loaded.output_base.source == "environment"
    home = loaded.get("INODEFENCE_HOME")
    assert home is not None and home.source == str(config)
    assert env == {"INODEFENCE_CONFIG": str(config), "INODEFENCE_OUTPUT_DIR": "/from/env"}


def test_default_output_base_is_home(tmp_path: Path) -> None:
    loaded = load_user_config({"INODEFENCE_CONFIG": str(tmp_path / "absent.env")})
    assert not loaded.config_found
    assert loaded.output_base.source == "default"
    assert loaded.default_out("inodefence-explore") == Path.home() / "inodefence-explore"


def test_repo_root_reads_inodefence_home_from_the_config_file(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "run_target.py").write_text("", encoding="utf-8")
    (repo / "tools").mkdir()
    config = tmp_path / "c.env"
    config.write_text(f"INODEFENCE_HOME={repo}\n", encoding="utf-8")
    monkeypatch.delenv("INODEFENCE_HOME", raising=False)
    monkeypatch.setenv("INODEFENCE_CONFIG", str(config))
    assert locate.repo_root() == repo
