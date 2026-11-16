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
    loaded = load_user_config({"XDG_CONFIG_HOME": str(tmp_path)})  # no config.env there
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


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("INODEFENCE_OUTPUT_DIR=/data/if # mine", "inline comment"),
        ("INODEFENCE_OUTPUT_DIR=/data/if\t# mine", "inline comment"),
        ("INODEFENCE_OUTPUT_DIR='/data/if", "unmatched quote"),
        ('INODEFENCE_HOME=/src/if"', "unmatched quote"),
    ],
)
def test_parse_refuses_values_that_would_silently_become_another_path(
    line: str, reason: str
) -> None:
    # Before 0.4 these were accepted as "/data/if # mine" and "'/data/if" (a different path).
    with pytest.raises(UserConfigError, match=reason):
        parse_config_text(line + "\n", "f")


def test_parse_keeps_a_quoted_hash_and_a_hash_inside_a_word() -> None:
    text = 'INODEFENCE_OUTPUT_DIR="/data/my #1"\nINODEFENCE_HOME=/src/if#2\n'
    assert parse_config_text(text, "f") == {
        "INODEFENCE_OUTPUT_DIR": "/data/my #1",
        "INODEFENCE_HOME": "/src/if#2",
    }


def test_a_config_path_that_is_a_directory_is_named_as_such(tmp_path: Path) -> None:
    with pytest.raises(UserConfigError, match="is a directory or another non-file"):
        load_user_config({"INODEFENCE_CONFIG": str(tmp_path)})
    (tmp_path / "inodefence" / "config.env").mkdir(parents=True)  # the default location, too
    with pytest.raises(UserConfigError, match="is a directory or another non-file"):
        load_user_config({"XDG_CONFIG_HOME": str(tmp_path)})


def test_an_empty_value_means_not_set_and_the_next_source_applies(tmp_path: Path) -> None:
    config = tmp_path / "c.env"
    config.write_text("INODEFENCE_OUTPUT_DIR=\n", encoding="utf-8")
    loaded = load_user_config({"INODEFENCE_CONFIG": str(config), "INODEFENCE_OUTPUT_DIR": ""})
    assert loaded.get("INODEFENCE_OUTPUT_DIR") is None
    assert loaded.output_base.source == "default"


def test_an_environment_value_records_the_file_value_it_overrides(tmp_path: Path) -> None:
    config = tmp_path / "c.env"
    config.write_text("INODEFENCE_HOME=/from/file\n", encoding="utf-8")
    env = {"INODEFENCE_CONFIG": str(config), "INODEFENCE_HOME": "/from/env"}
    setting = load_user_config(env).get("INODEFENCE_HOME")
    assert setting is not None
    assert (setting.value, setting.source, setting.overridden) == (
        "/from/env",
        "environment",
        "/from/file",
    )
    env["INODEFENCE_HOME"] = "/from/file"  # the same value: nothing is overridden
    same = load_user_config(env).get("INODEFENCE_HOME")
    assert same is not None and same.overridden is None


def test_the_shipped_env_example_parses_as_is_and_with_its_keys_uncommented() -> None:
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert parse_config_text(text, ".env.example") == {}
    uncommented = text.replace("# INODEFENCE_HOME=", "INODEFENCE_HOME=").replace(
        "# INODEFENCE_OUTPUT_DIR=", "INODEFENCE_OUTPUT_DIR="
    )
    assert set(parse_config_text(uncommented, ".env.example")) == {
        "INODEFENCE_HOME",
        "INODEFENCE_OUTPUT_DIR",
    }


def test_a_config_file_saved_with_a_utf8_bom_reads_its_first_key(tmp_path: Path) -> None:
    config = tmp_path / "c.env"
    config.write_bytes("\ufeffINODEFENCE_OUTPUT_DIR=/data/if\r\n".encode())
    loaded = load_user_config({"INODEFENCE_CONFIG": str(config)})
    assert loaded.output_base.value == "/data/if"
