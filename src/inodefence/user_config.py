"""User settings for the ``inodefence`` command: where to find the repository and write outputs.

Two kinds of state are kept apart on purpose:

- **User data** (this module): where the command writes its outputs (``verify`` / ``explore``
  results, live progress, violation cases, summaries). The user chooses it.
- **Experiment runtime and research settings** (not this module): ``INODEFENCE_RUNTIME_ROOT`` (the
  disposable filesystem-experiment directory, see :mod:`inodefence.runtime`; its meaning and
  default are unchanged and it is read from the environment only), and the seed / arm / budget /
  executed SHA / isolation policy of a run. Those come from explicit command flags or from the
  frozen preregistration files, never from a user config file, so a stray config line cannot
  silently change what an experiment measured.

Settings are read from the process environment first, then from an optional ``KEY=VALUE`` file
(``$INODEFENCE_CONFIG``, else ``$XDG_CONFIG_HOME/inodefence/config.env``, else
``~/.config/inodefence/config.env``). Only :data:`USER_KEYS` are accepted from the file; any other
key is refused with a reason (it is not silently ignored), so a research setting placed there is
visible as an error rather than a no-op that looks applied. The file is parsed, never executed,
and loading it does not modify ``os.environ`` (so nothing in it reaches the drivers' environment).

What the parser refuses rather than guesses (each would otherwise become a different path than the
user meant, silently): a value with an inline `` #`` comment (put comments on their own line, or
quote the value), and a value with an unmatched quote. An empty value (``KEY=``), in the file or
the environment, means "not set" and the next source applies; ``inodefence doctor`` names the
source in effect. A path given as ``INODEFENCE_CONFIG`` that is a directory is an error.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

#: Keys a user config file may set, with their meaning.
USER_KEYS: dict[str, str] = {
    "INODEFENCE_HOME": "repository root (needed when the command is not an editable install)",
    "INODEFENCE_OUTPUT_DIR": "base folder for default --out locations (verify / explore)",
}

#: Keys that look like settings but must not come from a user config file, with the reason.
PROTECTED_KEYS: dict[str, str] = {
    "INODEFENCE_RUNTIME_ROOT": "experiment runtime directory; set it in the environment only",
    "INODEFENCE_DOCKER_CONTEXT": "execution/isolation setting of experiment drivers",
    "INODEFENCE_EVIDENCE_DIR": "set per run by the drivers",
}

#: Default output folder names, under the output base (home directory unless configured).
VERIFY_OUT_NAME = "inodefence-target-run"
EXPLORE_OUT_NAME = "inodefence-explore"


class UserConfigError(ValueError):
    """The user config file could not be read or holds a refused key."""


@dataclass(frozen=True, slots=True)
class Setting:
    value: str
    source: str  # "environment", the config file path, or "default"
    #: The config file's value for the same key when the environment overrides it, else None.
    overridden: str | None = None


@dataclass(frozen=True, slots=True)
class UserConfig:
    config_path: Path
    config_found: bool
    settings: dict[str, Setting] = field(default_factory=dict)

    def get(self, key: str) -> Setting | None:
        return self.settings.get(key)

    @property
    def output_base(self) -> Setting:
        configured = self.get("INODEFENCE_OUTPUT_DIR")
        if configured is not None:
            return Setting(str(Path(configured.value).expanduser()), configured.source)
        return Setting(str(Path.home()), "default")

    def default_out(self, name: str) -> Path:
        return Path(self.output_base.value) / name


def config_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get("INODEFENCE_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    base = env.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "inodefence" / "config.env"


def parse_config_text(text: str, source: str) -> dict[str, str]:
    """``KEY=VALUE`` lines; blank lines and ``#`` comments skipped; surrounding quotes stripped."""
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise UserConfigError(f"{source}:{number}: expected KEY=VALUE, got {raw!r}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif value[:1] in ("'", '"') or value[-1:] in ("'", '"'):
            raise UserConfigError(
                f"{source}:{number}: unmatched quote in {raw!r}; quote all of the value or none"
            )
        elif " #" in value or "\t#" in value:
            raise UserConfigError(
                f"{source}:{number}: inline comment in {raw!r} is not supported (it would become "
                "part of the value); put the comment on its own line, or quote the value"
            )
        if key in PROTECTED_KEYS:
            raise UserConfigError(
                f"{source}:{number}: {key} cannot be set in the user config ({PROTECTED_KEYS[key]})"
            )
        if key not in USER_KEYS:
            raise UserConfigError(
                f"{source}:{number}: unknown key {key}; the user config accepts only "
                f"{', '.join(sorted(USER_KEYS))}. Research settings (seed, arm, budget, executed "
                "SHA, isolation) come from command flags or the frozen preregistration files."
            )
        values[key] = value
    return values


def load_user_config(environ: Mapping[str, str] | None = None) -> UserConfig:
    """Environment first, then the config file, for :data:`USER_KEYS` only."""
    env = os.environ if environ is None else environ
    path = config_path(env)
    file_values: dict[str, str] = {}
    found = path.is_file()
    if path.exists() and not found:
        raise UserConfigError(
            f"{path}: is a directory or another non-file; the config must be a file"
        )
    if not found and env.get("INODEFENCE_CONFIG"):
        # Named explicitly: a missing file is an error, not "no settings" (silent defaults would
        # hide a typo in the path).
        raise UserConfigError(f"INODEFENCE_CONFIG={env['INODEFENCE_CONFIG']}: no such file")
    if found:
        try:
            text = path.read_text(encoding="utf-8-sig")  # a leading BOM is not part of a key
        except OSError as error:
            raise UserConfigError(f"{path}: unreadable ({error})") from error
        file_values = parse_config_text(text, str(path))
    settings: dict[str, Setting] = {}
    for key in USER_KEYS:
        if env.get(key):
            shadowed = file_values.get(key) or None
            overridden = shadowed if shadowed != env[key] else None
            settings[key] = Setting(env[key], "environment", overridden)
        elif file_values.get(key):
            settings[key] = Setting(file_values[key], str(path))
    return UserConfig(config_path=path, config_found=found, settings=settings)
