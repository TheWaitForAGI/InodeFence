"""Compatibility alias: this driver moved to ``inodefence.drivers.run_target_explore``
(src/inodefence/drivers/run_target_explore.py).

Kept because the installed CLI (inodefence.locate) runs it by path. Importing
``scripts.run_target_explore`` gives the real module (the same object, so a ``monkeypatch`` of
``scripts.run_target_explore.<name>`` patches the code that runs); ``python
scripts/run_target_explore.py`` and ``python -m scripts.run_target_explore`` run its ``main``.
"""

import sys
from typing import TYPE_CHECKING

from inodefence.drivers import run_target_explore as _module

if TYPE_CHECKING:  # the alias below is invisible to type checkers
    from inodefence.drivers.run_target_explore import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(_module.main())
sys.modules[__name__] = _module
