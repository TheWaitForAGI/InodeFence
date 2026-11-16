"""Compatibility alias: this driver moved to ``inodefence.drivers.run_target``
(src/inodefence/drivers/run_target.py).

Kept because the installed CLI (inodefence.locate) runs it by path and it marks the repository
root. Importing ``scripts.run_target`` gives the real module (the same object, so a
``monkeypatch`` of ``scripts.run_target.<name>`` patches the code that runs); ``python
scripts/run_target.py`` and ``python -m scripts.run_target`` run its ``main``.
"""

import sys
from typing import TYPE_CHECKING

from inodefence.drivers import run_target as _module

if TYPE_CHECKING:  # the alias below is invisible to type checkers
    from inodefence.drivers.run_target import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(_module.main())
sys.modules[__name__] = _module
