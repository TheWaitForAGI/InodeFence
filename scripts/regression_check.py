"""Compatibility alias: this driver moved to ``inodefence.drivers.regression_check``
(src/inodefence/drivers/regression_check.py).

Kept because CI (repro-evidence.yml), the Makefile and frozen experiment / paper records invoke
it by path. Importing ``scripts.regression_check`` gives the real module (the same object, so a
``monkeypatch`` of ``scripts.regression_check.<name>`` patches the code that runs); ``python
scripts/regression_check.py`` and ``python -m scripts.regression_check`` run its ``main``.
"""

import sys
from typing import TYPE_CHECKING

from inodefence.drivers import regression_check as _module

if TYPE_CHECKING:  # the alias below is invisible to type checkers
    from inodefence.drivers.regression_check import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(_module.main())
sys.modules[__name__] = _module
