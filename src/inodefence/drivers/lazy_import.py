"""A module reference imported on first use: keeps ``experiments/`` out of a plain driver import.

The fixture-regression paths of the adapters (and ``regression_check``) run the committed repro
programs under ``experiments/repro/``. ``experiments`` lives in the repository clone, not in the
installed package, so importing it at module top level made ``import inodefence.drivers.run_target``
(and every adapter) need a clone. :class:`LazyModule` defers the import to the first attribute use,
which only happens on a real run -- and a real run already requires the clone
(:func:`inodefence.drivers.repo.require_repository`).

It forwards ``getattr``/``setattr``/``delattr`` to the real module, so ``monkeypatch.setattr(
adapter.cri, "run_one", fake)`` keeps patching the real ``experiments.repro`` module exactly as
before.

If the module's top-level package itself is missing (the driver runs from a clone, but the clone
root is not on ``sys.path`` -- an editable install run directly from another directory), the first
use prints :data:`inodefence.drivers.repo.REPOSITORY_CODE_NOT_ON_PATH` and exits with
:data:`~inodefence.drivers.repo.REPOSITORY_CODE_EXIT` (a setup error) instead of a traceback. Any
other import error (a module *inside* the package failing) is raised unchanged.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any


class LazyModule:
    """Stands in for ``import <name>``; the module is imported on first attribute access."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)

    def _module(self) -> ModuleType:
        name = object.__getattribute__(self, "_name")
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as error:
            top = name.partition(".")[0]
            if error.name != top:
                raise
            from inodefence.drivers import repo

            message = repo.REPOSITORY_CODE_NOT_ON_PATH.format(module=top, root=repo.code_checkout())
            print(f"error: {message}", file=sys.stderr)
            raise SystemExit(repo.REPOSITORY_CODE_EXIT) from error

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._module(), attribute)

    def __setattr__(self, attribute: str, value: Any) -> None:
        setattr(self._module(), attribute, value)

    def __delattr__(self, attribute: str) -> None:
        delattr(self._module(), attribute)

    def __repr__(self) -> str:
        return f"<lazy module {object.__getattribute__(self, '_name')!r}>"
